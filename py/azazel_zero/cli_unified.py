#!/usr/bin/env python3
from __future__ import annotations

import curses
import json
import subprocess
import time
from pathlib import Path
from typing import List, Tuple

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


def _service_active(name: str) -> bool:
    return subprocess.call(["systemctl", "is-active", "--quiet", name]) == 0


def _service_start(name: str) -> None:
    subprocess.call(["systemctl", "start", name])


def _service_stop(name: str) -> None:
    subprocess.call(["systemctl", "stop", name])


def _status_lines() -> List[str]:
    active = _service_active(FIRST_MINUTE_SERVICE)
    health = _health()
    return [
        f"First-Minute: {'active' if active else 'inactive'}",
        f"Wi-Fi health: {health}",
        "Press ENTER to refresh, s:start service, x:stop service, q:quit",
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
                _service_start(FIRST_MINUTE_SERVICE)
            elif action == "stop":
                _service_stop(FIRST_MINUTE_SERVICE)
            elif action == "quit":
                break
        elif ch in (ord("q"), 27):
            break
    # on exit, stop service
    _service_stop(FIRST_MINUTE_SERVICE)


def main() -> int:
    curses.wrapper(_menu)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
