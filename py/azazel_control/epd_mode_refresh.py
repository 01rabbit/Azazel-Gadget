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
EPD_LAST_RENDER = Path("/run/azazel/epd_last_render.json")


def _safe_load(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:
        return {}


def _read_live_ssid(upstream_if: str) -> str:
    iface = str(upstream_if or "").strip()
    candidates = []
    if iface:
        # iwgetid syntax varies by distro; try both forms.
        candidates.append(["iwgetid", iface, "-r"])
        candidates.append(["iwgetid", "-r", iface])
    candidates.append(["iwgetid", "-r"])

    for cmd in candidates:
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=3, check=False).stdout.strip()
            if out:
                return out
        except Exception:
            continue
    return "No SSID"


def _normal_render_spec(payload: Dict[str, Any], mode_label: str, risk_status: str) -> Dict[str, Any]:
    ssid = str(payload.get("ssid", "")).strip() or _read_live_ssid(str(payload.get("upstream_if", "")).strip())
    return {
        "state": "normal",
        "mode_label": str(mode_label or "SHIELD").strip().upper()[:12],
        "ssid": ssid,
        "risk_status": str(risk_status or "UNKNOWN").strip().upper(),
        "suspicion": 0,
        "signal": None,
    }


def _desired_render_spec(payload: Dict[str, Any]) -> Dict[str, Any]:
    mode = str(payload.get("mode", "")).strip().lower()

    # Keep base screen during mode switch (no WARNING banner).
    if mode == "switching":
        target = str(payload.get("target_mode", "shield")).strip().lower()
        if target not in ("portal", "shield", "scapegoat"):
            target = "shield"
        return _normal_render_spec(payload, target, "CHECKING")

    if mode == "failed":
        return {"state": "danger", "msg": "MODE FAIL"}

    if mode in ("portal", "shield", "scapegoat"):
        net = str(payload.get("internet", "unknown")).strip().upper()
        risk = net if net in ("OK", "FAIL") else "UNKNOWN"
        return _normal_render_spec(payload, mode, risk)

    return {"state": "warning", "msg": "MODE N/A"}


def _same_render(desired: Dict[str, Any], last_payload: Dict[str, Any]) -> bool:
    last_render = {}
    if isinstance(last_payload, dict):
        if isinstance(last_payload.get("render"), dict):
            last_render = last_payload.get("render") or {}
        elif isinstance(last_payload, dict):
            # backward compatibility: raw render dict
            last_render = last_payload
    return desired == last_render


def main() -> int:
    payload = _safe_load(EPD_STATE)
    if not payload:
        return 0

    root = Path(os.environ.get("AZAZEL_ROOT", str(Path(__file__).resolve().parents[2])))
    epd_script = root / "py" / "azazel_epd.py"
    if not epd_script.exists():
        return 0

    desired = _desired_render_spec(payload)
    last = _safe_load(EPD_LAST_RENDER)
    if _same_render(desired, last):
        return 0

    cmd = [sys.executable, str(epd_script), "--state", desired.get("state", "warning")]
    if desired.get("state") == "normal":
        cmd.extend(
            [
                "--ssid", str(desired.get("ssid", "")),
                "--mode-label", str(desired.get("mode_label", "SHIELD")),
                "--risk-status", str(desired.get("risk_status", "UNKNOWN")),
                "--suspicion", str(desired.get("suspicion", 0)),
            ]
        )
    else:
        cmd.extend(["--msg", str(desired.get("msg", "MODE"))])

    try:
        subprocess.run(cmd, timeout=45, check=False)
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
