#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Azazel-Zero - Minimal curses menu launcher
- Runs inside the persistent tmux session as the entry console
- Launches tools (blocking) and returns to the menu on exit
- Keys: ↑/↓ or j/k to move, Enter to run, r to redraw, q/ESC to quit
"""

import curses
import argparse
import asyncio
import os
import shutil
import subprocess
import sys
import time
from typing import List, Tuple, Optional, Any

# ===== Network status helpers and header renderer =====
import shlex
try:
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.widgets import Footer, Header, Static
    TEXTUAL_AVAILABLE = True
except Exception:
    TEXTUAL_AVAILABLE = False

def _sh(cmd: str) -> str:
    try:
        out = subprocess.check_output(shlex.split(cmd), stderr=subprocess.DEVNULL, timeout=1.5)
        return out.decode().strip()
    except Exception:
        return ""

def _ip4_addr(iface: str) -> str:
    out = _sh(f"ip -4 addr show {iface}")
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("inet "):
            return line.split()[1].split("/")[0]
    return ""

def _default_gw_iface() -> str:
    out = _sh("ip route get 8.8.8.8")
    parts = out.split()
    if "dev" in parts:
        try:
            return parts[parts.index("dev") + 1]
        except Exception:
            pass
    return ""

def _ssid_and_bssid() -> Tuple[str, str]:
    ssid = _sh("iwgetid -r")
    if not ssid:
        st = _sh("wpa_cli status")
        for ln in st.splitlines():
            if ln.startswith("ssid="):
                ssid = ln.split("=", 1)[1].strip()
                break
    bssid = ""
    st = _sh("wpa_cli status")
    for ln in st.splitlines():
        if ln.startswith("bssid="):
            bssid = ln.split("=", 1)[1].strip()
            break
    return ssid or "—", bssid or "—"

def _dnsmasq_leases_path() -> str:
    for p in ("/var/lib/misc/dnsmasq.leases", "/var/lib/dnsmasq/dnsmasq.leases"):
        if os.path.exists(p):
            return p
    return ""

def _latest_usb_client_ip() -> str:
    path = _dnsmasq_leases_path()
    if not path:
        return ""
    try:
        last = ""
        with open(path, "r") as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) >= 3:
                    last = parts[2]
        return last
    except Exception:
        return ""

def get_net_status() -> dict:
    gw_if = _default_gw_iface() or "wlan0"
    ssid, bssid = _ssid_and_bssid()
    wlan_ip = _ip4_addr("wlan0") or "—"
    usb_ip = _ip4_addr("usb0") or "—"
    lap_ip = _latest_usb_client_ip() or "—"
    rssi = _wifi_rssi_dbm()
    net_ok = _route_alive()
    captive = _captive_portal()
    return {
        "gw_if": gw_if or "—",
        "ssid": ssid,
        "bssid": bssid,
        "wlan_ip": wlan_ip,
        "usb_ip": usb_ip,
        "laptop_ip": lap_ip,
        "rssi_dbm": rssi,
        "net_ok": net_ok,
        "captive": captive,
    }

def _supports_emoji() -> bool:
    """Return True only when emoji display is explicitly allowed and locale supports UTF-8.
    Set AZA_EMOJI=0 (or false/no/off) to force ASCII badges in terminals without emoji fonts.
    """
    flag = os.environ.get("AZA_EMOJI", "").strip().lower()
    if flag in ("0", "false", "no", "off"):
        return False
    s = (os.environ.get("LANG", "") + os.environ.get("LC_CTYPE", "")).upper()
    return "UTF-8" in s

def _wifi_rssi_dbm() -> Optional[int]:
    out = _sh("iw dev wlan0 link")
    for ln in out.splitlines():
        ln = ln.strip().lower()
        # e.g., "signal: -43 dBm"
        if ln.startswith("signal:") and "dbm" in ln:
            try:
                val = int(ln.split()[1])
                return val
            except Exception:
                return None
    return None

def _route_alive() -> bool:
    # fast ICMP probe to default route target
    try:
        return subprocess.call(["ping", "-c1", "-W1", "8.8.8.8"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0
    except Exception:
        return False

def _captive_portal() -> Optional[bool]:
    # True if captive likely, False if open internet, None if unknown
    try:
        if shutil.which("curl") is None:
            return None
        out = subprocess.check_output(
            ["curl", "-sI", "http://connectivitycheck.gstatic.com/generate_204"],
            stderr=subprocess.DEVNULL, timeout=1.5
        ).decode("utf-8", "ignore").splitlines()
        for ln in out:
            if ln.lower().startswith("http/"):
                parts = ln.split()
                if len(parts) >= 2 and parts[1] == '204':
                    return False
                try:
                    code = int(parts[1])
                    if 300 <= code < 400:
                        return True
                    return None
                except Exception:
                    return None
        return None
    except Exception:
        return None

# Resolve repo root from this file location
HERE = os.path.abspath(os.path.dirname(__file__))
ROOT = os.path.abspath(os.path.join(HERE, os.pardir))

# Tool commands
SSID_TOOL = ["/usr/bin/python3", os.path.join(HERE, "ssid_list.py")]
# Placeholder for future tools
DELAY_TOOL = ["/usr/bin/python3", os.path.join(HERE, "delay_tool.py")]  # if not present, we gray it out

# Optional: e-paper refresh script (non-fatal if missing)
EPAPER = ["/usr/bin/python3", os.path.join(HERE, "boot_splash_epd.py")]
EPD_INFO_CMD = EPAPER + ["--mode", "info"]
EPD_START_CMD = EPAPER + ["--mode", "start"]
EPD_SHUT_CMD  = EPAPER + ["--mode", "shutdown"]


HELP = "↑/↓ or j/k: move   Enter: run   r: redraw   q: quit"

def _bin_cmd(name):
    here = os.path.abspath(os.path.join(HERE, os.pardir, "bin", name))
    usrlocal = os.path.join("/usr/local/bin", name)
    return [usrlocal] if os.path.exists(usrlocal) else [here]

MENU = [
    ("Wi-Fi Selector (ssid_list.py)", SSID_TOOL),
    ("OpenCanary: start", ["/bin/sh","-lc","sudo systemctl start opencanary.service"]),
    ("OpenCanary: stop",  ["/bin/sh","-lc","sudo systemctl stop opencanary.service"]),
    ("OpenCanary: hits (tail)", ["/bin/sh","-lc","sudo journalctl -u opencanary.service -f || tail -F /var/log/opencanary.log"]),
    # E-paper animation tests (non-fatal if script missing)
    ("EPD: start animation (test)", EPD_START_CMD),
    ("EPD: shutdown animation (test)", EPD_SHUT_CMD),
    ("Exit", None),
]


class AzazelMenuTextualApp(App):
    """Textual menu UI with key behavior aligned to the curses menu."""

    BINDINGS = [
        Binding("up", "move_up", "Up"),
        Binding("down", "move_down", "Down"),
        Binding("k", "move_up", "Up"),
        Binding("j", "move_down", "Down"),
        Binding("enter", "select", "Run"),
        Binding("r", "refresh_status", "Refresh"),
        Binding("q", "quit_menu", "Quit"),
        Binding("escape", "quit_menu", "Quit"),
        Binding("d", "detach", "Detach"),
        Binding("ctrl+q", "detach", "Detach"),
    ]

    CSS = """
    Screen {
        layout: vertical;
    }

    #status {
        border: round cyan;
        height: 6;
        padding: 0 1;
    }

    #menu {
        border: round $accent;
        height: 1fr;
        padding: 0 1;
    }

    #message {
        height: 1;
        color: black;
        background: $accent;
        content-align: left middle;
        padding: 0 1;
    }
    """

    def __init__(self, idx: int = 0, message: str = "") -> None:
        super().__init__()
        self._idx = max(0, min(idx, len(MENU) - 1))
        self._message = message or "Ready"
        self._net_status: dict[str, Any] = {}

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("Loading status...", id="status")
        yield Static("Loading menu...", id="menu")
        yield Static(self._message, id="message")
        yield Footer()

    async def on_mount(self) -> None:
        await self.action_refresh_status()

    def _render_status(self) -> None:
        ns = self._net_status or {}
        status_line = (
            f"SSID={ns.get('ssid', '—')}  BSSID={ns.get('bssid', '—')}  RSSI={ns.get('rssi_dbm', '—')} dBm\n"
            f"wlan0={ns.get('wlan_ip', '—')}  usb0={ns.get('usb_ip', '—')}  laptop={ns.get('laptop_ip', '—')}\n"
            f"gw_if={ns.get('gw_if', '—')}  net_ok={ns.get('net_ok', False)}  captive={ns.get('captive', None)}"
        )
        self.query_one("#status", Static).update(status_line)

    def _render_menu(self) -> None:
        lines = ["Azazel-Zero Console", ""]
        for i, (label, cmd) in enumerate(MENU):
            marker = ">" if i == self._idx else " "
            enabled = _exists(cmd) if cmd else True
            line = f"{marker} {label}"
            if not enabled and cmd is not None:
                line += "  [missing]"
            lines.append(line)
        self.query_one("#menu", Static).update("\n".join(lines))

    def _render(self) -> None:
        self._render_status()
        self._render_menu()
        self.query_one("#message", Static).update(self._message)

    async def action_refresh_status(self) -> None:
        self._message = "Refreshing status..."
        self._render()
        self._net_status = await asyncio.to_thread(get_net_status)
        self._message = "Status updated"
        self._render()

    def action_move_up(self) -> None:
        self._idx = (self._idx - 1) % len(MENU)
        self._render_menu()

    def action_move_down(self) -> None:
        self._idx = (self._idx + 1) % len(MENU)
        self._render_menu()

    def action_select(self) -> None:
        self.exit(("run", self._idx))

    def action_quit_menu(self) -> None:
        self.exit(("quit", self._idx))

    def action_detach(self) -> None:
        self.exit(("detach", self._idx))


def _exists(cmd: List[str]) -> bool:
    if cmd is None:
        return False
    exe = cmd[0]
    if os.path.isabs(exe):
        return os.path.exists(exe)
    return shutil.which(exe) is not None


def _safe_run(cmd: List[str]) -> int:
    """Run a tool in the foreground, then try to refresh e‑paper on return."""
    try:
        return subprocess.call(cmd)
    finally:
        _update_epaper()


def _update_epaper() -> None:
    """Best‑effort e‑paper refresh (non‑fatal)."""
    try:
        script_path = EPAPER[-1]
        if os.path.exists(script_path):
            info = _tmux_info()
            if info:
                subprocess.run(EPD_INFO_CMD + [info], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                subprocess.run(EPD_INFO_CMD, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def _tmux_info() -> str:
    """Return current tmux session:window name for display, if running under tmux."""
    if "TMUX" not in os.environ:
        return ""
    try:
        out = subprocess.check_output(["tmux", "display", "-p", "#{session_name}:#{window_index} #{window_name}"])
        return out.decode("utf-8", "ignore").strip()
    except Exception:
        return ""


def _draw_menu(stdscr, idx: int, net_status: dict) -> None:
    stdscr.erase()
    h, w = stdscr.getmaxyx()
    # Header is rendered by the upper tmux pane; draw menu only
    top_row = 0
    title = "Azazel‑Zero Console"
    stdscr.addnstr(top_row, max(0, (w - len(title)) // 2), title[:max(0, w)], w)
    stdscr.addnstr(top_row + 1, 0, "=" * max(0, w), w)
    row = top_row + 3

    for i, (label, cmd) in enumerate(MENU):
        marker = ">" if i == idx else " "
        enabled = _exists(cmd) if cmd else True
        text = f"{marker} {label}"
        if not enabled and cmd is not None:
            text += "  [missing]"
        stdscr.addnstr(row, 0, text, w)
        row += 1

    stdscr.addnstr(h - 1, 0, HELP[:max(0, w)], w)
    stdscr.refresh()


def _run_menu(stdscr) -> None:
    curses.curs_set(0)
    stdscr.nodelay(False)
    stdscr.keypad(True)

    idx = 0
    n = len(MENU)

    # Optional grace to avoid overriding EPD boot animation (seconds)
    try:
        grace = float(os.getenv("BOOT_EPD_GRACE", "0"))
        if grace > 0:
            time.sleep(grace)
    except Exception:
        pass

    # Initial epaper refresh for this screen
    _update_epaper()

    while True:
        _draw_menu(stdscr, idx, {})
        ch = stdscr.getch()
        if ch in (curses.KEY_UP, ord('k')):
            idx = (idx - 1) % n
        elif ch in (curses.KEY_DOWN, ord('j')):
            idx = (idx + 1) % n
        elif ch in (ord('r'), ord('R')):
            continue
        elif ch == curses.KEY_RESIZE:
            # On resize, just redraw with current status
            stdscr.erase()
            continue
        elif ch in (ord('D'), 17):  # 'D' or Ctrl-Q
            if 'TMUX' in os.environ:
                try:
                    subprocess.call(['tmux', 'detach-client'])
                except Exception:
                    pass
            break
        elif ch in (ord('q'), 27):
            break
        elif ch in (curses.KEY_ENTER, 10, 13):
            label, cmd = MENU[idx]
            if cmd is None:
                break
            if not _exists(cmd):
                # flash message
                _message(stdscr, f"Command not found: {cmd[-1]}")
                continue
            stdscr.erase(); stdscr.refresh()
            code = _safe_run(cmd)
            _message(stdscr, f"Exited '{label}' (code {code})")


def _message(stdscr, msg: str, timeout_ms: int = 1200) -> None:
    h, w = stdscr.getmaxyx()
    stdscr.addnstr(h - 2, 0, " " * max(0, w), w)
    stdscr.addnstr(h - 2, 0, msg[:max(0, w)], w)
    stdscr.refresh()
    curses.napms(timeout_ms)


def _run_menu_textual() -> None:
    if not TEXTUAL_AVAILABLE:
        print("[menu] Textual is not available. Install python3-textual.", file=sys.stderr)
        sys.exit(1)

    idx = 0
    message = "Ready"

    # Optional grace to avoid overriding EPD boot animation (seconds)
    try:
        grace = float(os.getenv("BOOT_EPD_GRACE", "0"))
        if grace > 0:
            time.sleep(grace)
    except Exception:
        pass

    _update_epaper()

    while True:
        result = AzazelMenuTextualApp(idx=idx, message=message).run()
        if not result:
            break
        action, idx = result

        if action == "quit":
            break
        if action == "detach":
            if "TMUX" in os.environ:
                try:
                    subprocess.call(["tmux", "detach-client"])
                except Exception:
                    pass
            break
        if action != "run":
            continue

        label, cmd = MENU[idx]
        if cmd is None:
            break
        # In Textual menu mode, launch the Textual Wi-Fi selector as well.
        if idx == 0 and cmd == SSID_TOOL:
            cmd = cmd + ["--textual"]
        if not _exists(cmd):
            message = f"Command not found: {cmd[-1]}"
            continue
        code = _safe_run(cmd)
        message = f"Exited '{label}' (code {code})"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Azazel-Zero menu launcher")
    parser.add_argument("--textual", action="store_true", help="Run Textual UI instead of curses")
    args = parser.parse_args()

    if args.textual:
        _run_menu_textual()
    else:
        try:
            curses.wrapper(_run_menu)
        except KeyboardInterrupt:
            pass
