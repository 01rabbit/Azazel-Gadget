#!/usr/bin/env python3
from __future__ import annotations

import curses
import json
import subprocess
import time
from pathlib import Path
from typing import List, Tuple, Optional

DEFAULT_ROOT = Path(__file__).resolve().parent.parent.parent
FIRST_MINUTE_SERVICE = "azazel-first-minute.service"
HEALTH_PATH = Path("/run/azazel-zero/wifi_health.json")
HEALTH_FALLBACK = DEFAULT_ROOT / ".azazel-zero" / "run" / "wifi_health.json"


def _health() -> str:
    path = HEALTH_PATH if HEALTH_PATH.exists() else HEALTH_FALLBACK
    if not path.exists():
        return "n/a"
    try:
        data = json.loads(path.read_text())
        risk = data.get("risk", "n/a")
        tags = ",".join((data.get("tags") or [])[:4])
        age = int(time.time() - data.get("ts", 0)) if data.get("ts") else None
        parts = [f"risk={risk}"]
        if tags:
            parts.append(tags)
        if age is not None:
            parts.append(f"{age}s ago")
        return " | ".join(parts)
    except Exception:
        return "error"


def _sh(cmd: str, timeout: float = 1.5) -> str:
    try:
        out = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL, timeout=timeout)
        return out.decode("utf-8", "ignore").strip()
    except Exception:
        return ""


def _ip4_addr(iface: str) -> str:
    out = _sh(f"ip -4 addr show {iface}")
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("inet "):
            return line.split()[1].split("/")[0]
    return "—"


def _ssid_bssid() -> Tuple[str, str]:
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


def _wifi_rssi() -> Optional[int]:
    out = _sh("iw dev wlan0 link")
    for ln in out.splitlines():
        ln = ln.strip().lower()
        if ln.startswith("signal:") and "dbm" in ln:
            try:
                return int(ln.split()[1])
            except Exception:
                return None
    return None


def _service_exists(name: str) -> bool:
    return subprocess.call(["systemctl", "status", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) in (0, 3)


def _service_active(name: str) -> bool:
    return subprocess.call(["systemctl", "is-active", "--quiet", name]) == 0


def _service_start(name: str) -> None:
    subprocess.call(["systemctl", "start", name])


def _service_stop(name: str) -> None:
    subprocess.call(["systemctl", "stop", name])


def _status_lines() -> List[str]:
    exists = _service_exists(FIRST_MINUTE_SERVICE)
    active = _service_active(FIRST_MINUTE_SERVICE) if exists else False
    health = _health()
    ssid, bssid = _ssid_bssid()
    wlan_ip = _ip4_addr("wlan0")
    usb_ip = _ip4_addr("usb0")
    rssi = _wifi_rssi()
    return [
        f"First-Minute: {'active' if active else 'inactive'} (unit {'found' if exists else 'missing'})",
        f"Wi-Fi health: {health}",
        f"SSID/BSSID: {ssid} / {bssid}",
        f"IPs: wlan0={wlan_ip}  usb0={usb_ip}  RSSI={rssi if rssi is not None else 'n/a'} dBm",
        "ENTER:refresh  s:start  x:stop  q:quit",
    ]


def _menu(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(False)
    stdscr.keypad(True)
    idx = 0
    items = [
        ("Refresh", "refresh"),
        ("Start First-Minute service", "start"),
        ("Stop First-Minute service", "stop"),
        ("Quit", "quit"),
    ]
    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        # status lines
        lines = _status_lines()
        for i, ln in enumerate(lines):
            stdscr.addnstr(i, 0, ln, w)
        stdscr.addnstr(len(lines), 0, "-" * max(0, w), w)
        # menu
        for i, (label, _) in enumerate(items):
            prefix = ">" if i == idx else " "
            stdscr.addnstr(len(lines) + 1 + i, 0, f"{prefix} {label}", w)
        stdscr.refresh()
        ch = stdscr.getch()
        if ch in (curses.KEY_UP, ord("k")):
            idx = (idx - 1) % len(items)
        elif ch in (curses.KEY_DOWN, ord("j")):
            idx = (idx + 1) % len(items)
        elif ch in (curses.KEY_ENTER, 10, 13):
            action = items[idx][1]
            if action == "refresh":
                continue
            if action == "start":
                if _service_exists(FIRST_MINUTE_SERVICE):
                    _service_start(FIRST_MINUTE_SERVICE)
                else:
                    pass  # unit missing; keep menu
            elif action == "stop":
                if _service_exists(FIRST_MINUTE_SERVICE):
                    _service_stop(FIRST_MINUTE_SERVICE)
            elif action == "quit":
                break
        elif ch in (ord("q"), 27):
            break
    # on exit, stop service
    if _service_exists(FIRST_MINUTE_SERVICE) and _service_active(FIRST_MINUTE_SERVICE):
        _service_stop(FIRST_MINUTE_SERVICE)


def main() -> int:
    curses.wrapper(_menu)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
