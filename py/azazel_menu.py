#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Azazel-Gadget menu compatibility launcher.

The control menu is now integrated in the unified monitor:
  python3 py/azazel_zero/cli_unified.py --textual --menu
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Azazel-Gadget menu compatibility launcher"
    )
    parser.add_argument(
        "--textual",
        action="store_true",
        help="Kept for backward compatibility (ignored; Textual is always used).",
    )
    parser.add_argument("--enable-epd", action="store_true", help="Enable E-Paper display updates")
    parser.add_argument("--disable-epd", action="store_true", help="Disable E-Paper display updates")
    args, passthrough = parser.parse_known_args()

    here = Path(__file__).resolve().parent
    monitor = here / "azazel_zero" / "cli_unified.py"
    cmd = [sys.executable, str(monitor), "--textual", "--menu"]
    if args.enable_epd:
        cmd.append("--enable-epd")
    if args.disable_epd:
        cmd.append("--disable-epd")
    cmd.extend(passthrough)

    os.execv(cmd[0], cmd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
