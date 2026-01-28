#!/usr/bin/env python3
"""
Generate mock state.json from current Azazel-Zero state
Bridges existing controller to new Web UI format
"""

import json
import time
import subprocess
from pathlib import Path

STATE_PATH = Path("/run/azazel/state.json")
LEGACY_API = "http://10.55.0.10:8082/"


def get_legacy_state() -> dict:
    """Fetch from legacy API"""
    try:
        result = subprocess.run(
            ["curl", "-s", LEGACY_API],
            capture_output=True,
            text=True,
            timeout=3
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
        return {}
    except:
        return {}


def get_system_metrics() -> dict:
    """Get CPU, temp, memory"""
    metrics = {"cpu_pct": 0, "temp_c": 0, "mem_used_mb": 0, "mem_total_mb": 0}
    
    # CPU
    try:
        result = subprocess.run(
            ["top", "-bn1"], capture_output=True, text=True, timeout=2
        )
        for line in result.stdout.splitlines():
            if "Cpu(s)" in line:
                idle = float(line.split("id,")[0].split()[-1])
                metrics["cpu_pct"] = int(100 - idle)
                break
    except:
        pass
    
    # Temp
    try:
        temp_file = Path("/sys/class/thermal/thermal_zone0/temp")
        if temp_file.exists():
            metrics["temp_c"] = int(temp_file.read_text()) // 1000
    except:
        pass
    
    # Memory
    try:
        result = subprocess.run(
            ["free", "-m"], capture_output=True, text=True, timeout=2
        )
        for line in result.stdout.splitlines():
            if line.startswith("Mem:"):
                parts = line.split()
                metrics["mem_total_mb"] = int(parts[1])
                metrics["mem_used_mb"] = int(parts[2])
                break
    except:
        pass
    
    return metrics


def generate_state_json() -> dict:
    """Generate state.json from legacy data"""
    legacy = get_legacy_state()
    metrics = get_system_metrics()
    
    # Map legacy to new format
    wifi = legacy.get("wifi", {})
    link = wifi.get("link", {})
    
    suspicion = legacy.get("suspicion", 0)
    stage = legacy.get("state", "NORMAL")
    
    # Risk score mapping
    risk_score = int(suspicion)
    if risk_score < 20:
        risk_status = "SAFE"
        threat_level = "LOW"
    elif risk_score < 50:
        risk_status = "CAUTION"
        threat_level = "MEDIUM"
    else:
        risk_status = "DANGER"
        threat_level = "HIGH"
    
    state = {
        "ok": True,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        
        "header": {
            "product": "Azazel-Gadget",
            "ssid": link.get("ssid", "-"),
            "iface_usb": "usb0",
            "iface_wlan": "wlan0",
            "clock": time.strftime("%H:%M:%S"),
            "temp_c": metrics["temp_c"],
            "cpu_pct": metrics["cpu_pct"],
            "mem_used_mb": metrics["mem_used_mb"],
            "mem_total_mb": metrics["mem_total_mb"],
            "view": "dashboard",
            "age_sec": 0
        },
        
        "risk": {
            "score": risk_score,
            "status": risk_status,
            "recommendation": legacy.get("reason", "Monitor connection"),
            "reason": legacy.get("reason", "-"),
            "threat_level": threat_level,
            "next": "Continue monitoring"
        },
        
        "connection": {
            "bssid": link.get("bssid", "-"),
            "channel": f"Ch{link.get('channel', '-')}",
            "congestion": "LOW",
            "ap_count": wifi.get("ap_count", 0),
            "signal_dbm": link.get("signal", -999),
            "gateway_ip": link.get("gateway", "-"),
            "recommended": "Current network OK"
        },
        
        "control": {
            "quic_443": "BLOCKED" if stage in ["PROBE", "DEGRADED", "CONTAIN"] else "ALLOWED",
            "doh_443": "BLOCKED",
            "degrade": "ON" if stage in ["PROBE", "DEGRADED"] else "OFF",
            "probe": legacy.get("last_probe", "-"),
            "stats_dns": "Monitoring",
            "ids": "Suricata active" if legacy.get("suricata", {}).get("enabled") else "Disabled",
            "traffic_down_mbps": 0,
            "traffic_up_mbps": 0
        },
        
        "evidence": {
            "window_sec": 30,
            "state": stage,
            "suspicion": suspicion,
            "scan": f"WiFi safety check: {len(wifi.get('wifi_tags', []))} tags",
            "decision": f"State: {stage}, Reason: {legacy.get('reason', '-')}"
        }
    }
    
    return state


def main():
    """Generate and write state.json"""
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    while True:
        state = generate_state_json()
        tmp = STATE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(STATE_PATH)
        
        time.sleep(2)  # Update every 2 seconds


if __name__ == "__main__":
    main()
