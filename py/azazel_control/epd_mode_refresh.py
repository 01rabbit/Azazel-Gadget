#!/usr/bin/env python3
"""Render mode-centric EPD state from /run/azazel/epd_state.json."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

EPD_STATE = Path("/run/azazel/epd_state.json")


def _safe_load(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:
        return {}


def _mode_message(payload: Dict[str, Any]) -> list[str]:
    mode = str(payload.get("mode", "")).strip().lower()

    if mode == "switching":
        target = str(payload.get("target_mode", "?")).strip().upper()[:10]
        return ["warning", f"-> {target}"]

    if mode == "failed":
        return ["danger", "MODE FAIL"]

    if mode in ("portal", "shield"):
        net = str(payload.get("internet", "unknown")).strip().upper()
        ssid = f"MODE:{mode.upper()}"
        risk = net if net in ("OK", "FAIL") else "UNKNOWN"
        return ["normal", ssid, risk]

    if mode == "scapegoat":
        ports = payload.get("exposed_ports", [])
        count = len(ports) if isinstance(ports, list) else 0
        return ["stale", f"SCAPE {count}P"]

    return ["warning", "MODE N/A"]


def main() -> int:
    payload = _safe_load(EPD_STATE)
    if not payload:
        return 0

    root = Path(os.environ.get("AZAZEL_ROOT", str(Path(__file__).resolve().parents[2])))
    epd_script = root / "py" / "azazel_epd.py"
    if not epd_script.exists():
        return 0

    mode_args = _mode_message(payload)
    cmd = [sys.executable, str(epd_script), "--state", mode_args[0]]
    if mode_args[0] == "normal" and len(mode_args) >= 3:
        cmd.extend(["--ssid", mode_args[1], "--risk-status", mode_args[2], "--suspicion", "0"])
    else:
        msg = mode_args[1] if len(mode_args) > 1 else "MODE"
        cmd.extend(["--msg", msg])

    try:
        subprocess.run(cmd, timeout=45, check=False)
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
