#!/usr/bin/env python3
"""
Wi-Fi Health Monitor - Unified module for Wi-Fi security health checks

Consolidates:
- wifi_risk_check.py (CLI tool)
- wifi_health.py (library functions)

Provides both CLI and library interfaces for Wi-Fi threat assessment.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

PY_ROOT = Path(__file__).resolve().parents[2]
if str(PY_ROOT) not in sys.path:
    sys.path.insert(0, str(PY_ROOT))

from azazel_gadget.path_schema import runtime_dir_candidates


def _fallback_dir() -> Path:
    """Get fallback directory for health state files"""
    here = Path(__file__).resolve().parents[3]  # repo root
    fb = here / ".azazel-gadget" / "run"
    fb.mkdir(parents=True, exist_ok=True)
    return fb


def health_paths() -> Tuple[Path, Path]:
    """Return (summary_path, pid_path) with schema-aware /run preferred."""
    for run_dir in runtime_dir_candidates():
        if run_dir.exists() and os.access(run_dir, os.W_OK):
            return run_dir / "wifi_health.json", run_dir / "wifi_health.pid"
    fb = _fallback_dir()
    return fb / "wifi_health.json", fb / "wifi_health.pid"


def evaluate_wifi_health(
    iface: str,
    known_db: str = "",
    gateway_ip: Optional[str] = None,
    prompt: str = "wifi_health"
) -> Dict[str, object]:
    """
    Single evaluation using judge_zero (Mock-LLM unified score).
    
    Args:
        iface: Wi-Fi interface name (e.g., wlan0)
        known_db: Path to known SSID/BSSID DB JSON (optional)
        gateway_ip: Gateway IP for ARP spoof heuristics (optional)
        prompt: Prompt label for judge_zero
    
    Returns:
        Health snapshot dict with keys:
        - ts: timestamp
        - iface: interface name
        - link: connection details (SSID, BSSID, signal, etc.)
        - tags: threat tags
        - risk: risk score (0-10)
        - category: threat category
        - reason: explanation
        - status: "ok" or "warn"
    """
    try:
        # Import here to avoid circular dependency
        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
        from azazel_gadget.app.threat_judge import judge_zero
        
        verdict = judge_zero(prompt, iface, known_db, gateway_ip)
    except Exception as e:
        verdict = {
            "risk": 0,
            "category": "unknown",
            "reason": f"error: {str(e)}",
            "tags": [],
            "meta": {}
        }
    
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


def write_health_snapshot(summary: Dict[str, object]) -> None:
    """Write health snapshot to JSON file"""
    path, _ = health_paths()
    try:
        path.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    except Exception:
        pass


def read_health_snapshot() -> Optional[Dict[str, object]]:
    """Read latest health snapshot from JSON file"""
    path, _ = health_paths()
    try:
        if path.exists():
            return json.loads(path.read_text())
    except Exception:
        pass
    return None


# ========== CLI Interface ==========

def cli_main() -> int:
    """CLI entry point for Wi-Fi health monitoring"""
    parser = argparse.ArgumentParser(
        description="Wi-Fi Health Monitor - Evaluate Wi-Fi security and write health status"
    )
    parser.add_argument(
        "--iface",
        default="wlan0",
        help="Wi-Fi interface (default: wlan0)"
    )
    parser.add_argument(
        "--known-db",
        default="",
        help="Known SSID/BSSID DB JSON path (optional)"
    )
    parser.add_argument(
        "--gateway-ip",
        default=None,
        help="Gateway IP for ARP spoof heuristics (optional)"
    )
    parser.add_argument(
        "--prompt",
        default="wifi_health",
        help="Prompt label for judge_zero (default: wifi_health)"
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.0,
        help="Loop interval seconds (0 to run once, default: 0)"
    )
    parser.add_argument(
        "--output",
        choices=["json", "summary", "silent"],
        default="json",
        help="Output format (default: json)"
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write results to health state file"
    )
    
    args = parser.parse_args()
    
    try:
        while True:
            snapshot = evaluate_wifi_health(
                args.iface,
                args.known_db,
                args.gateway_ip,
                args.prompt
            )
            
            # Write to file if requested
            if args.write:
                write_health_snapshot(snapshot)
            
            # Output to stdout based on format
            if args.output == "json":
                print(json.dumps(snapshot, ensure_ascii=False, indent=2))
            elif args.output == "summary":
                print(f"[{snapshot['status'].upper()}] "
                      f"Risk: {snapshot['risk']}/10, "
                      f"Tags: {','.join(snapshot['tags']) or 'none'}, "
                      f"SSID: {snapshot['link'].get('ssid', 'N/A')}")
            # silent: no output
            
            # Break if one-shot mode
            if args.interval <= 0:
                break
            
            time.sleep(args.interval)
            
    except KeyboardInterrupt:
        return 0
    
    return 0


if __name__ == "__main__":
    sys.exit(cli_main())
