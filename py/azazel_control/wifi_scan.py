#!/usr/bin/env python3
"""
Wi-Fi Scan Module for Azazel-Zero Control Daemon

Performs Wi-Fi AP scan using NetworkManager/nmcli:
- Returns deduplicated AP list (strongest per SSID)
"""

import subprocess
import re
import json
import logging
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

# Import common scanner module
sys.path.insert(0, str(Path(__file__).parent.parent))
from azazel_zero.sensors.wifi_scanner import scan_and_parse, get_security_label

logger = logging.getLogger("wifi_scan")


def get_wireless_interface() -> Optional[str]:
    """Detect wireless interface (prefer wlan0, else auto-detect)"""
    try:
        # Try wlan0 first
        result = subprocess.run(
            ["iw", "dev", "wlan0", "info"],
            capture_output=True,
            text=True,
            timeout=2
        )
        if result.returncode == 0:
            return "wlan0"
        
        # Auto-detect via iw dev
        result = subprocess.run(
            ["iw", "dev"],
            capture_output=True,
            text=True,
            timeout=2
        )
        
        # Parse: Interface <name>
        match = re.search(r"Interface\s+(\S+)", result.stdout)
        if match:
            return match.group(1)
        
        return None
    except Exception as e:
        logger.warning(f"Failed to detect wireless interface: {e}")
        return None


def check_networkmanager(iface: str) -> bool:
    """Check if NetworkManager manages this interface"""
    try:
        result = subprocess.run(
            ["nmcli", "-t", "-f", "DEVICE", "dev"],
            capture_output=True,
            text=True,
            timeout=2
        )
        return iface in result.stdout
    except:
        return False


def get_saved_networks_nm() -> set:
    """Get saved network SSIDs from NetworkManager"""
    try:
        result = subprocess.run(
            [
                "nmcli",
                "-t",
                "-f",
                "NAME,TYPE",
                "con",
                "show",
            ],
            capture_output=True,
            text=True,
            timeout=2
        )
        
        saved = set()
        for line in result.stdout.splitlines():
            parts = line.split(":", 1)
            if len(parts) != 2:
                continue
            name, con_type = parts
            if con_type != "802-11-wireless":
                continue
            ssid_result = subprocess.run(
                ["nmcli", "-t", "-f", "802-11-wireless.ssid", "con", "show", name],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if ssid_result.returncode != 0:
                continue
            ssid_line = (ssid_result.stdout or "").strip()
            if ":" in ssid_line:
                _, ssid_value = ssid_line.split(":", 1)
            else:
                ssid_value = ssid_line
            if ssid_value:
                saved.add(ssid_value)
        return saved
    except Exception as e:
        logger.warning(f"Failed to get saved networks from nmcli: {e}")
        return set()


def scan_with_iw(iface: str, saved_ssids: set) -> List[Dict[str, Any]]:
    """Scan Wi-Fi using iw (low-level) - now uses common scanner"""
    try:
        # Use common scanner module
        aps = scan_and_parse(iface, deduplicate=True, keep_hidden=False)
        
        # Mark saved networks and add security label
        for ap in aps:
            ap["saved"] = ap["ssid"] in saved_ssids
            ap["security"] = get_security_label(ap)
            # Convert float signal to int for consistency
            if ap["signal"] is not None:
                ap["signal_dbm"] = int(ap["signal"])
            else:
                ap["signal_dbm"] = -100
        
        return aps
    
    except Exception as e:
        logger.error(f"iw scan failed: {e}")
        return []


def scan_with_nmcli(iface: str, saved_ssids: set) -> List[Dict[str, Any]]:
    """Scan Wi-Fi using nmcli (NetworkManager)"""
    try:
        # Trigger rescan
        subprocess.run(
            ["nmcli", "dev", "wifi", "rescan", "ifname", iface],
            capture_output=True,
            timeout=10
        )
        
        # Get scan results
        result = subprocess.run(
            ["nmcli", "-t", "-f", "SSID,BSSID,CHAN,SIGNAL,SECURITY", "dev", "wifi", "list", "ifname", iface],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode != 0:
            return []
        
        aps = []
        for line in result.stdout.splitlines():
            parts = line.split(":")
            if len(parts) < 5:
                continue
            
            ssid, bssid, chan, signal, security = parts[:5]
            
            if not ssid:
                continue
            
            # Map nmcli security to standard labels
            sec_label = "UNKNOWN"
            if "WPA3" in security:
                sec_label = "WPA3"
            elif "WPA2" in security:
                sec_label = "WPA2"
            elif "WPA" in security:
                sec_label = "WPA"
            elif not security or security == "--":
                sec_label = "OPEN"
            
            aps.append({
                "ssid": ssid,
                "bssid": bssid if bssid != "--" else "unknown",
                "channel": int(chan) if chan.isdigit() else 0,
                "signal_dbm": int(signal) - 100 if signal.isdigit() else -100,  # nmcli gives 0-100, convert to dBm approx
                "security": sec_label,
                "saved": ssid in saved_ssids
            })
        
        return aps
    
    except Exception as e:
        logger.error(f"nmcli scan failed: {e}")
        return []


def deduplicate_aps(aps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Deduplicate by SSID, keep strongest signal.
    Note: Common scanner already does this, but kept for nmcli path compatibility.
    """
    ssid_map = {}
    
    for ap in aps:
        ssid = ap["ssid"]
        if ssid not in ssid_map or ap["signal_dbm"] > ssid_map[ssid]["signal_dbm"]:
            ssid_map[ssid] = ap
    
    # Sort: strongest signal first, then alpha by SSID
    result = sorted(ssid_map.values(), key=lambda x: (-x["signal_dbm"], x["ssid"]))
    return result


def scan_wifi() -> Dict[str, Any]:
    """
    Main entry point: Auto-detect environment and scan Wi-Fi
    
    Returns:
        {
            "ok": bool,
            "aps": [{"ssid", "bssid", "signal_dbm", "channel", "security", "saved"}],
            "ts": str,
            "error": str (if failed)
        }
    """
    import time
    
    # Detect wireless interface
    iface = get_wireless_interface()
    if not iface:
        return {
            "ok": False,
            "error": "No wireless interface found",
            "ts": time.time()
        }
    
    logger.info(f"Using wireless interface: {iface}")
    
    # Check if NetworkManager is available
    if not check_networkmanager(iface):
        return {
            "ok": False,
            "error": "NetworkManager not found or not managing interface",
            "ts": time.time()
        }
    
    # Get saved networks from NetworkManager
    logger.info("Using NetworkManager for scan")
    saved_ssids = get_saved_networks_nm()
    aps = scan_with_nmcli(iface, saved_ssids)
    
    if not aps:
        return {
            "ok": False,
            "error": "Scan returned no results",
            "ts": time.time()
        }
    
    # Deduplicate
    aps = deduplicate_aps(aps)
    
    return {
        "ok": True,
        "aps": aps,
        "ts": time.time()
    }


if __name__ == "__main__":
    # Test mode
    logging.basicConfig(level=logging.INFO)
    result = scan_wifi()
    print(json.dumps(result, indent=2))
