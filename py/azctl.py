#!/usr/bin/env python3
"""Azazel control CLI."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PY_ROOT = Path(__file__).resolve().parent
if str(PY_ROOT) not in sys.path:
    sys.path.insert(0, str(PY_ROOT))

from azazel_control.mode_manager import MODE_CHOICES, ModeManager


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Azazel control utility")
    sub = parser.add_subparsers(dest="command", required=True)

    mode = sub.add_parser("mode", help="Mode operations")
    mode_sub = mode.add_subparsers(dest="mode_cmd", required=True)

    set_p = mode_sub.add_parser("set", help="Set operating mode")
    set_p.add_argument("mode", choices=MODE_CHOICES)
    set_p.add_argument("--requested-by", default="cli")
    set_p.add_argument("--dry-run", action="store_true")

    st_p = mode_sub.add_parser("status", help="Show current mode status")
    st_p.add_argument("--requested-by", default="cli")

    def_p = mode_sub.add_parser("apply-default", help="Apply persisted mode (default shield)")
    def_p.add_argument("--requested-by", default="boot")

    parser.add_argument("--json", action="store_true", help="Always print JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    mgr = ModeManager()

    if args.command == "mode":
        if args.mode_cmd in ("set", "apply-default") and os.geteuid() != 0:
            payload = {"ok": False, "error": "azctl mode set/apply-default requires root"}
            print(json.dumps(payload, ensure_ascii=False))
            return 1

        if args.mode_cmd == "set":
            payload = mgr.set_mode(args.mode, requested_by=str(args.requested_by), dry_run=bool(args.dry_run))
        elif args.mode_cmd == "status":
            payload = mgr.status()
        elif args.mode_cmd == "apply-default":
            payload = mgr.apply_default(requested_by=str(args.requested_by))
        else:
            payload = {"ok": False, "error": f"Unknown mode subcommand: {args.mode_cmd}"}

        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 0 if payload.get("ok") else 1

    print(json.dumps({"ok": False, "error": "unknown command"}, ensure_ascii=False))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
