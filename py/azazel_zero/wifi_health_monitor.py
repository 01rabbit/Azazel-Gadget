#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Tuple

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
if str(ROOT / "py") not in sys.path:
    sys.path.insert(0, str(ROOT / "py"))

from azazel_zero.wifi_health import health_paths, health_snapshot


def _is_running(pid_path: Path) -> bool:
    try:
        pid = int(pid_path.read_text().strip())
    except Exception:
        return False
    return Path(f"/proc/{pid}").exists()


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Periodic Wi-Fi health monitor (tags from wifi_safety).")
    parser.add_argument("--iface", default="wlan0", help="Wi-Fi interface")
    parser.add_argument("--known-db", default="", help="Known SSID/BSSID DB JSON (optional)")
    parser.add_argument("--gateway-ip", default=None, help="Gateway IP (optional)")
    parser.add_argument("--interval", type=float, default=20.0, help="Interval seconds between checks")
    parser.add_argument("--run-once", action="store_true", help="Single check then exit")
    args = parser.parse_args()

    out_path, pid_path = health_paths()
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    if not args.run_once and pid_path.exists() and _is_running(pid_path):
        # Another monitor is active; exit silently
        return 0
    if not args.run_once:
        pid_path.write_text(str(os.getpid()))

    while True:
        summary = health_snapshot(args.iface, args.known_db, args.gateway_ip)
        try:
            out_path.write_text(json.dumps(summary))
        except Exception:
            pass
        if args.run_once:
            break
        time.sleep(max(5.0, args.interval))
    return 0


if __name__ == "__main__":
    sys.exit(main())
