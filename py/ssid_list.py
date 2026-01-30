#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
List nearby Wi-Fi SSIDs with signal, channel, security, and connect to selected SSID.
- Requires: /sbin/iw, wpa_cli, dhcpcd
- Default iface: wlan0  (override via CLI:  ./ssid_list.py wlan1)
"""

import re
import shutil
import subprocess
import sys
import curses
import shlex
import getpass
import time
import os
import atexit
from collections import defaultdict
from pathlib import Path

# Ensure repo modules importable for health check
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT / "py") not in sys.path:
    sys.path.insert(0, str(ROOT / "py"))

# Import common Wi-Fi scanner
from azazel_zero.sensors.wifi_scanner import scan_and_parse, get_security_label

try:
    from azazel_zero.sensors.wifi_safety import evaluate_wifi_safety
except Exception:
    evaluate_wifi_safety = None  # fallback if deps missing

# Positional arg or default
IFACE = sys.argv[1] if len(sys.argv) > 1 else "wlan0"

def run(cmd):
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)


# --- E‑Paper boot splash updater ---
BOOT_SPLASH_PATH = os.path.join(os.path.dirname(__file__), "boot_splash_epd.py")

def update_epaper():
    """Invoke boot_splash_epd.py to refresh the e‑paper display. Errors are non‑fatal."""
    if os.path.exists(BOOT_SPLASH_PATH):
        try:
            subprocess.run(["/usr/bin/python3", BOOT_SPLASH_PATH],
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL,
                           check=False)
        except Exception:
            pass

# Always refresh on script exit (even if user quit without selection)
atexit.register(update_epaper)


def _rescan_nets(iface):
    """Rescan using common scanner module"""
    nets = scan_and_parse(iface, deduplicate=True, keep_hidden=True)
    
    # Convert to legacy format for compatibility
    for n in nets:
        # Add security labels used by this script
        n["sec_label"] = get_security_label(n)
    
    return nets

def run_health_check_once(iface: str) -> None:
    if evaluate_wifi_safety is None:
        return
    try:
        from azazel_zero.app.threat_judge import judge_zero
        verdict = judge_zero("wifi_health_check", iface, "", None)
    except Exception:
        return
    ssid = (verdict.get("meta", {}) or {}).get("link", {}).get("ssid", "")
    risk = verdict.get("risk", 0)
    tags = verdict.get("tags", []) or []
    status = "OK" if risk <= 2 else "WARN"
    tag_str = ",".join(tags)
    print(f"[Wi-Fi health] {status} risk={risk} tags={tag_str} ssid={ssid}")


# ---- Wi-Fi connection helpers (wpa_cli) ----

def sh(cmd):
    return subprocess.run(shlex.split(cmd), text=True, capture_output=True)


def find_network_id(ssid, iface):
    out = sh(f"wpa_cli -i {iface} list_networks").stdout.splitlines()
    for line in out[1:]:  # skip header
        cols = line.split('\t')
        if len(cols) >= 2 and cols[1] == ssid:
            return cols[0]
    return None


def has_saved_credentials(nid, iface):
    # Open network
    km = sh(f"wpa_cli -i {iface} get_network {nid} key_mgmt").stdout.strip()
    if km == "NONE":
        return True
    psk = sh(f"wpa_cli -i {iface} get_network {nid} psk").stdout.strip()
    return psk == "[MASKED]"


def get_current_network(iface):
    """Return (id, ssid, bssid) of the current network, or (None, None, None)."""
    st = sh(f"wpa_cli -i {iface} status").stdout
    cur_ssid = None
    cur_bssid = None
    cur_id = None
    for line in st.splitlines():
        if line.startswith("ssid="):
            cur_ssid = line.split("=",1)[1]
        elif line.startswith("bssid="):
            cur_bssid = line.split("=",1)[1]
        elif line.startswith("id="):
            cur_id = line.split("=",1)[1]
    if cur_id is None:
        # Fallback: find CURRENT in list_networks
        out = sh(f"wpa_cli -i {iface} list_networks").stdout.splitlines()
        for line in out[1:]:
            cols = line.split('\t')
            if len(cols) >= 4 and 'CURRENT' in cols[3]:
                return cols[0], cols[1], ''
    return cur_id, cur_ssid, cur_bssid


def reselect_network(nid, iface):
    if nid is None:
        return
    sh(f"wpa_cli -i {iface} select_network {nid}")
    sh(f"wpa_cli -i {iface} reassociate")
    sh(f"dhcpcd -n {iface}")


def ensure_connected(ssid, iface, is_open):
    """Ensure connection to SSID with rollback to previous network on failure.
    - Prompts for passphrase only if needed
    - Calls save_config ONLY on success
    - Disables/removes tentative network on failure
    Returns True on success, False otherwise.
    """
    # Snapshot current network for rollback
    prev_id, prev_ssid, prev_bssid = get_current_network(iface)

    nid = find_network_id(ssid, iface)
    created_new = False

    if nid is None:
        # Create new network (tentative)
        created_new = True
        nid = sh(f"wpa_cli -i {iface} add_network").stdout.strip()
        if not nid.isdigit():
            print("Failed to add network", file=sys.stderr)
            return False
        sh(f"wpa_cli -i {iface} set_network {nid} ssid \"{ssid}\"")
        if is_open:
            sh(f"wpa_cli -i {iface} set_network {nid} key_mgmt NONE")
        else:
            pw = getpass.getpass(prompt=f"Passphrase for '{ssid}': ")
            sh(f"wpa_cli -i {iface} set_network {nid} psk \"{pw}\"")
    else:
        # Existing profile; ensure credentials present if required
        if not is_open and not has_saved_credentials(nid, iface):
            pw = getpass.getpass(prompt=f"Passphrase for '{ssid}': ")
            sh(f"wpa_cli -i {iface} set_network {nid} psk \"{pw}\"")

    # Attempt association (do NOT save_config yet)
    sh(f"wpa_cli -i {iface} enable_network {nid}")
    sh(f"wpa_cli -i {iface} select_network {nid}")

    # Wait for association with timeout (~10s)
    for _ in range(20):
        st = sh(f"wpa_cli -i {iface} status").stdout
        if "wpa_state=COMPLETED" in st and f"ssid={ssid}" in st:
            break
        # Quick fail on explicit rejection
        if "CTRL-EVENT-ASSOC-REJECT" in st or "WRONG_KEY" in st or "reason=WRONG_KEY" in st:
            break
        time.sleep(0.5)
    else:
        # Timeout: rollback and clean tentative network
        print("Association failed (timeout). Rolling back...", file=sys.stderr)
        sh(f"wpa_cli -i {iface} disable_network {nid}")
        if created_new:
            sh(f"wpa_cli -i {iface} remove_network {nid}")
        reselect_network(prev_id, iface)
        update_epaper()
        return False

    # Check final state
    st = sh(f"wpa_cli -i {iface} status").stdout
    if not ("wpa_state=COMPLETED" in st and f"ssid={ssid}" in st):
        # Likely wrong credentials or auth failure: rollback and clean
        print("Association failed (auth). Rolling back...", file=sys.stderr)
        sh(f"wpa_cli -i {iface} disable_network {nid}")
        if created_new:
            sh(f"wpa_cli -i {iface} remove_network {nid}")
        reselect_network(prev_id, iface)
        update_epaper()
        return False

    # Success: renew IP and persist configuration
    sh(f"dhcpcd -n {iface}")
    sh(f"wpa_cli -i {iface} save_config")
    update_epaper()
    return True

# ---- Interactive selector (curses) ----

def _sec_label_for_display(n):
    return n.get("sec_label") or get_security_label(n)


def _display_line(n):
    ssid = n["ssid"] or f"<hidden:{n['bssid']}>"
    sig = "" if n.get("signal") is None else f"{int(n['signal']):>3}"
    ch  = "" if n.get("chan") is None else str(n["chan"]).rjust(2)
    sec = _sec_label_for_display(n)
    bssid = n["bssid"]
    return f"{ssid[:32]:<32}  {sec:<10}  {sig:>3} dBm  ch{ch:>2}   {bssid}"


def _interactive_select(stdscr, iface, nets):
    curses.curs_set(0)
    stdscr.nodelay(False)
    stdscr.keypad(True)

    idx = 0
    top = 0

    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        # Reserve two lines for header and separator
        header = "  SSID                              SEC          SIGNAL(dBm)  CH   BSSID"
        sep    = "-" * max(0, w)
        stdscr.addnstr(0, 0, header, w)
        stdscr.addnstr(1, 0, sep, w)
        view_h = max(1, h - 3)

        # Scroll window calculation
        if idx < top:
            top = idx
        elif idx >= top + view_h:
            top = idx - view_h + 1

        for i in range(view_h):
            j = top + i
            if j >= len(nets):
                break
            line = _display_line(nets[j])
            prefix = ">" if j == idx else " "
            stdscr.addnstr(2 + i, 0, prefix + " " + line, w)

        hint = "↑/↓: move  Enter: select  r: refresh  q: quit"
        stdscr.addnstr(h-1, 0, hint[:max(0, w)], w)

        stdscr.refresh()
        ch = stdscr.getch()
        if ch in (curses.KEY_UP, ord('k')):
            idx = (idx - 1) % len(nets)
        elif ch in (curses.KEY_DOWN, ord('j')):
            idx = (idx + 1) % len(nets)
        elif ch in (curses.KEY_ENTER, 10, 13):
            return nets[idx]
        elif ch in (ord('q'), 27):  # q or ESC to quit without selection
            return None
        elif ch in (ord('r'), ord('R')):
            nets[:] = _rescan_nets(iface)
            if not nets:
                idx = 0
                top = 0
                continue
            if idx >= len(nets):
                idx = len(nets) - 1
            if idx < 0:
                idx = 0


def interactive_select(iface, nets):
    return curses.wrapper(_interactive_select, iface, nets)


def main():
    if shutil.which("iw") is None:
        print("Error: 'iw' not found. Install 'iw' and run again.", file=sys.stderr)
        sys.exit(1)

    # スキャン（共通モジュール使用）
    nets = _rescan_nets(IFACE)
    
    if not nets:
        print("No networks found or scan failed", file=sys.stderr)
        sys.exit(2)

    # Interactive selection
    choice = interactive_select(IFACE, nets)
    if choice is None:
        return
    ssid = choice["ssid"] or f"<hidden:{choice['bssid']}>"
    is_open = not (choice.get("rsn") or choice.get("wpa"))
    ok = ensure_connected(ssid, IFACE, is_open)
    if ok:
        # Show resulting IP
        ip = run(["/sbin/ip", "-4", "addr", "show", IFACE]).stdout
        print(f"Connected to: {ssid}")
        print(ip)
        run_health_check_once(IFACE)
    else:
        print(f"Failed to connect: {ssid}", file=sys.stderr)
        sys.exit(3)


if __name__ == "__main__":
    main()
