"""
DEPRECATED: This module is deprecated and will be removed in a future version.

Please use: azazel_zero.sensors.wifi_health_monitor instead.

Migration:
    Old:
        from azazel_zero.wifi_health import health_snapshot, write_snapshot
    New:
        from azazel_zero.sensors.wifi_health_monitor import evaluate_wifi_health, write_health_snapshot
"""
from __future__ import annotations

import json
import os
import time
import warnings
from pathlib import Path
from typing import Dict, Tuple, Optional

# Show deprecation warning
warnings.warn(
    "azazel_zero.wifi_health is deprecated. Use azazel_zero.sensors.wifi_health_monitor instead.",
    DeprecationWarning,
    stacklevel=2
)


def _fallback_dir() -> Path:
    here = Path(__file__).resolve().parents[2]  # repo root
    fb = here / ".azazel-zero" / "run"
    fb.mkdir(parents=True, exist_ok=True)
    return fb


def health_paths() -> Tuple[Path, Path]:
    """Return (summary_path, legacy_pid_path) with /run preferred and fallback under repo/.azazel-zero/run."""
    run_dir = Path("/run/azazel-zero")
    if run_dir.exists() and os.access(run_dir, os.W_OK):
        return run_dir / "wifi_health.json", run_dir / "wifi_health.pid"
    fb = _fallback_dir()
    return fb / "wifi_health.json", fb / "wifi_health.pid"


def health_snapshot(iface: str, known_db: str = "", gateway_ip: Optional[str] = None) -> Dict[str, object]:
    """Single evaluation using judge_zero (Mock-LLM unified score)."""
    try:
        from azazel_zero.app.threat_judge import judge_zero
        verdict = judge_zero("wifi_health", iface, known_db, gateway_ip)
    except Exception:
        verdict = {"risk": 0, "category": "unknown", "reason": "error", "tags": [], "meta": {}}
    link = verdict.get("meta", {}).get("link", {}) if isinstance(verdict.get("meta"), dict) else {}
    tags = verdict.get("tags", []) or []
    risk = verdict.get("risk", 0) or 0
    status = "ok" if risk <= 2 else "warn"
    return {
        "ts": time.time(),
        "iface": iface,
        "link": link,
        "tags": tags,
        "risk": risk,
        "category": verdict.get("category", ""),
        "reason": verdict.get("reason", ""),
        "status": status,
    }


def write_snapshot(summary: Dict[str, object]) -> None:
    path, _ = health_paths()
    try:
        path.write_text(json.dumps(summary))
    except Exception:
        pass
