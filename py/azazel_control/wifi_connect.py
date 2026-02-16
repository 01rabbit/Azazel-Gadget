#!/usr/bin/env python3
"""
Wi-Fi Connect Module for Azazel-Zero Control Daemon

Connects to target SSID and enables USB client NAT:
- Uses NetworkManager/nmcli for Wi-Fi management
- Validates input, detects captive portal, applies NAT
"""

import subprocess
import re
import json
import logging
import time
import socket
import tempfile
from typing import Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger("wifi_connect")

# Import wifi_scan helpers
import sys
sys.path.insert(0, str(Path(__file__).parent))
from wifi_scan import (
    get_wireless_interface,
    check_networkmanager,
    get_saved_networks_nm,
)


def get_usb_interface() -> Optional[str]:
    """Detect USB gadget interface (prefer usb0)"""
    try:
        # Try usb0 first
        result = subprocess.run(
            ["ip", "link", "show", "usb0"],
            capture_output=True,
            text=True,
            timeout=2
        )
        if result.returncode == 0:
            return "usb0"
        
        # Auto-detect gadget NIC (heuristic: look for 10.55.0.0/24 subnet)
        result = subprocess.run(
            ["ip", "-o", "addr"],
            capture_output=True,
            text=True,
            timeout=2
        )
        
        for line in result.stdout.splitlines():
            if "10.55.0." in line:
                parts = line.split()
                if len(parts) >= 2:
                    return parts[1]
        
        return None
    except Exception as e:
        logger.warning(f"Failed to detect USB interface: {e}")
        return None


def validate_input(ssid: str, security: str, passphrase: Optional[str], is_saved: bool = False) -> Optional[str]:
    """Validate Wi-Fi connection parameters"""
    # SSID length
    if not ssid or len(ssid) > 32:
        return "Invalid SSID (must be 1-32 chars)"
    
    # Passphrase requirement
    if security and security.upper() != "OPEN":
        if not passphrase and not is_saved:
            return "Passphrase required for protected network"
        if passphrase and (len(passphrase) < 8 or len(passphrase) > 63):
            return "Invalid passphrase length (8-63 chars typical)"
    
    return None


def parse_security(security: str) -> Dict[str, bool]:
    """Normalize security label into flags."""
    sec = (security or "").upper().strip()
    return {
        "open": sec == "OPEN",
        "wpa3": "WPA3" in sec,
        "wpa2": "WPA2" in sec,
        "wpa": ("WPA" in sec) and ("WPA2" not in sec) and ("WPA3" not in sec),
    }


def is_nm_managed(iface: str) -> bool:
    """Check if NetworkManager is actively managing the interface."""
    try:
        result = subprocess.run(
            ["nmcli", "-t", "-f", "DEVICE,STATE", "dev"],
            capture_output=True,
            text=True,
            timeout=2
        )
        if result.returncode != 0:
            return False
        for line in result.stdout.splitlines():
            if ":" not in line:
                continue
            dev, state = line.split(":", 1)
            if dev != iface:
                continue
            state = state.strip().lower()
            return state not in {"unmanaged", "unavailable"}
        return False
    except Exception:
        return False


def connect_nm(iface: str, ssid: str, security: str, passphrase: Optional[str], persist: bool) -> Dict[str, Any]:
    """Connect using NetworkManager/nmcli"""
    try:
        sec_flags = parse_security(security)

        def find_nm_connection_for_ssid(target_ssid: str) -> Optional[str]:
            """Find NM connection name by matching 802-11-wireless.ssid."""
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
                    timeout=5,
                )
                if result.returncode != 0:
                    return None
                for line in result.stdout.splitlines():
                    parts = line.split(":", 1)
                    if len(parts) != 2:
                        continue
                    name, con_type = parts
                    if con_type != "802-11-wireless":
                        continue
                    # Query SSID for each Wi-Fi connection (older nmcli doesn't expose it in list mode).
                    ssid_result = subprocess.run(
                        ["nmcli", "-t", "-f", "802-11-wireless.ssid", "con", "show", name],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if ssid_result.returncode != 0:
                        continue
                    ssid_line = (ssid_result.stdout or "").strip()
                    if ":" in ssid_line:
                        _, ssid_value = ssid_line.split(":", 1)
                    else:
                        ssid_value = ssid_line
                    if ssid_value == target_ssid:
                        return name
                return None
            except Exception:
                return None

        def get_nm_key_mgmt(connection_name: str) -> str:
            """Return current key-mgmt for an existing NM connection (empty if unset)."""
            try:
                result = subprocess.run(
                    ["nmcli", "-g", "802-11-wireless-security.key-mgmt", "con", "show", connection_name],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    return (result.stdout or "").strip()
            except Exception:
                pass

            try:
                result = subprocess.run(
                    ["nmcli", "-t", "-f", "802-11-wireless-security.key-mgmt", "con", "show", connection_name],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode != 0:
                    return ""
                line = (result.stdout or "").strip()
                if ":" in line:
                    _, value = line.split(":", 1)
                    return value.strip()
                return line
            except Exception:
                return ""

        def desired_nm_key_mgmt() -> Optional[str]:
            """Decide key-mgmt to set based on security flags."""
            if sec_flags["open"]:
                return "none"
            if sec_flags["wpa3"]:
                return "sae"
            if sec_flags["wpa2"] or sec_flags["wpa"]:
                return "wpa-psk"
            return None

        # Check if connection exists for this SSID
        con_name = find_nm_connection_for_ssid(ssid)
        con_exists = con_name is not None
        
        if con_exists:
            # Update credentials if provided (or clear for OPEN)
            if sec_flags["open"]:
                subprocess.run(
                    ["nmcli", "con", "mod", con_name, "wifi-sec.key-mgmt", "none"],
                    capture_output=True,
                    timeout=5
                )
                subprocess.run(
                    ["nmcli", "con", "mod", con_name, "-u", "wifi-sec.psk"],
                    capture_output=True,
                    timeout=5
                )
            else:
                existing_key_mgmt = get_nm_key_mgmt(con_name)
                desired = desired_nm_key_mgmt()
                key_mgmt = None

                # Only set key-mgmt if missing (or clearly wrong) to avoid breaking saved profiles.
                if not existing_key_mgmt or existing_key_mgmt == "none":
                    key_mgmt = desired or "wpa-psk"  # safe default for WPA2-PSK
                elif passphrase and desired and existing_key_mgmt != desired:
                    # User provided credentials explicitly; align key-mgmt with the requested security.
                    key_mgmt = desired

                if key_mgmt:
                    subprocess.run(
                        ["nmcli", "con", "mod", con_name, "wifi-sec.key-mgmt", key_mgmt],
                        capture_output=True,
                        timeout=5
                    )
                if passphrase:
                    subprocess.run(
                        ["nmcli", "con", "mod", con_name, "wifi-sec.psk", passphrase],
                        capture_output=True,
                        timeout=5
                    )

            # Connect to existing connection
            result = subprocess.run(
                ["nmcli", "con", "up", con_name],
                capture_output=True,
                text=True,
                timeout=20
            )
        else:
            if not sec_flags["open"] and not passphrase:
                return {"ok": False, "error": "Saved connection not found; passphrase required"}

            # Create new connection
            cmd = ["nmcli", "dev", "wifi", "connect", ssid, "ifname", iface]
            
            if not sec_flags["open"] and passphrase:
                cmd.extend(["password", passphrase])
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=20
            )
            
            # If not persisting, delete the connection after use (best-effort)
            if not persist and result.returncode == 0:
                con_name = find_nm_connection_for_ssid(ssid) or ssid
                subprocess.run(
                    ["nmcli", "con", "delete", con_name],
                    capture_output=True,
                    timeout=5
                )
        
        if result.returncode != 0:
            return {"ok": False, "error": result.stderr.strip() or "Connection failed"}

        # Disable auto-connect to ensure Wi-Fi only connects on explicit user action
        if con_exists or persist:
            try:
                if not con_name:
                    con_name = find_nm_connection_for_ssid(ssid) or ssid
                subprocess.run(
                    ["nmcli", "con", "mod", con_name, "connection.autoconnect", "no"],
                    capture_output=True,
                    timeout=5
                )
            except Exception as e:
                logger.debug(f"Failed to disable autoconnect for {ssid}: {e}")
        
        logger.info("Wi-Fi connected via nmcli")
        return {"ok": True}
    
    except Exception as e:
        logger.error(f"nmcli connection failed: {e}")
        return {"ok": False, "error": str(e)}


def get_interface_ip(iface: str) -> Optional[str]:
    """Get IP address of interface"""
    try:
        result = subprocess.run(
            ["ip", "-o", "-4", "addr", "show", iface],
            capture_output=True,
            text=True,
            timeout=2
        )
        
        match = re.search(r"inet\s+(\S+)", result.stdout)
        if match:
            return match.group(1).split("/")[0]
        return None
    except:
        return None


def get_gateway_ip(iface: str) -> Optional[str]:
    """Get default gateway for interface"""
    try:
        result = subprocess.run(
            ["ip", "route", "show", "dev", iface],
            capture_output=True,
            text=True,
            timeout=2
        )
        
        match = re.search(r"default via\s+(\S+)", result.stdout)
        if match:
            return match.group(1)
        return None
    except:
        return None


def _parse_location(headers: str) -> str:
    for line in headers.splitlines():
        if line.lower().startswith("location:"):
            return line.split(":", 1)[1].strip()
    return ""


def check_connectivity(iface: Optional[str]) -> Dict[str, Any]:
    """
    Connectivity checks with captive-portal aware HTTP probe.

    Returns:
        gateway_reachable: OK|FAIL
        dns_resolution: OK|FAIL
        http_code: str
        http_check: OK|FAIL
        location: str
        body_len: int
        effective_url: str
        curl_error: str
    """
    checks: Dict[str, Any] = {
        "gateway_reachable": "UNKNOWN",
        "dns_resolution": "UNKNOWN",
        "http_check": "FAIL",
        "http_code": "000",
        "location": "",
        "body_len": 0,
        "effective_url": "",
        "curl_error": "",
    }

    # Gateway ping
    try:
        result = subprocess.run(
            ["ping", "-c", "1", "-W", "2", "8.8.8.8"],
            capture_output=True,
            timeout=3
        )
        checks["gateway_reachable"] = "OK" if result.returncode == 0 else "FAIL"
    except Exception:
        checks["gateway_reachable"] = "FAIL"

    # DNS resolution
    try:
        socket.gethostbyname("connectivitycheck.gstatic.com")
        checks["dns_resolution"] = "OK"
    except Exception:
        checks["dns_resolution"] = "FAIL"

    body_path = ""
    hdr_path = ""
    try:
        with tempfile.NamedTemporaryFile(prefix="azazel_wifi_body_", delete=False, dir="/tmp") as bf:
            body_path = bf.name
        with tempfile.NamedTemporaryFile(prefix="azazel_wifi_hdr_", delete=False, dir="/tmp") as hf:
            hdr_path = hf.name

        cmd = [
            "curl",
            "-sS",
            "--max-time",
            "4",
            "-o",
            body_path,
            "-D",
            hdr_path,
            "-w",
            "%{http_code} %{url_effective}",
            "http://connectivitycheck.gstatic.com/generate_204",
        ]
        if iface:
            cmd[1:1] = ["--interface", iface]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=6
        )
        checks["http_check"] = "OK" if result.returncode == 0 else "FAIL"
        if result.returncode != 0:
            if result.returncode == 28:
                checks["curl_error"] = "TIMEOUT"
            elif result.returncode == 6:
                checks["curl_error"] = "DNS_FAIL"
            elif result.returncode in (35, 51, 58, 60):
                checks["curl_error"] = "CERT_FAIL"
            else:
                checks["curl_error"] = f"CURL_ERR_{result.returncode}"
            checks["http_check"] = "FAIL"
        else:
            payload = (result.stdout or "").strip().split(maxsplit=1)
            checks["http_code"] = payload[0] if payload else "000"
            checks["effective_url"] = payload[1] if len(payload) > 1 else ""
            try:
                checks["body_len"] = Path(body_path).stat().st_size
            except Exception:
                checks["body_len"] = 0
            try:
                headers = Path(hdr_path).read_text(encoding="utf-8", errors="ignore")
                checks["location"] = _parse_location(headers)
            except Exception:
                checks["location"] = ""
    except subprocess.TimeoutExpired:
        checks["curl_error"] = "TIMEOUT"
        checks["http_check"] = "FAIL"
    except Exception as exc:
        checks["curl_error"] = f"CURL_ERR:{exc}"
        checks["http_check"] = "FAIL"
    finally:
        for p in (body_path, hdr_path):
            if p:
                try:
                    Path(p).unlink(missing_ok=True)
                except Exception:
                    pass

    return checks


def detect_captive_portal(checks: Dict[str, Any]) -> Dict[str, str]:
    """
    Captive portal decision table:
      - 204 => NO
      - 30x => YES
      - 200(body>0) / other non-204 => SUSPECTED
      - timeout/curl errors => SUSPECTED
    """
    code = str(checks.get("http_code", "000") or "000")
    body_len = int(checks.get("body_len", 0) or 0)
    curl_error = str(checks.get("curl_error", "") or "")

    if curl_error in ("NO_IP", "LINK_DOWN", "NOT_FOUND"):
        return {"status": "NA", "reason": curl_error}
    if curl_error:
        return {"status": "SUSPECTED", "reason": curl_error}
    if code == "204":
        return {"status": "NO", "reason": "HTTP_204"}
    if code.startswith("30"):
        return {"status": "YES", "reason": "HTTP_30X"}
    if code == "200" and body_len > 0:
        return {"status": "SUSPECTED", "reason": "HTTP_200_BODY"}
    if code and code != "000":
        return {"status": "SUSPECTED", "reason": f"HTTP_{code}"}
    return {"status": "SUSPECTED", "reason": "HTTP_000"}


def detect_firewall_tool() -> Optional[str]:
    """Detect available firewall tool (prefer nftables)"""
    tools = ["nft", "iptables-nft", "iptables"]
    
    for tool in tools:
        try:
            result = subprocess.run(
                ["which", tool],
                capture_output=True,
                timeout=2
            )
            if result.returncode == 0:
                return tool
        except:
            continue
    
    return None


def apply_nat(wlan_iface: str, usb_iface: str) -> Dict[str, Any]:
    """Apply NAT/forwarding for USB client"""
    try:
        # Enable IPv4 forwarding
        subprocess.run(
            ["sysctl", "-w", "net.ipv4.ip_forward=1"],
            capture_output=True,
            timeout=2
        )
        
        # Detect firewall tool
        fw_tool = detect_firewall_tool()
        
        if not fw_tool:
            return {"ok": False, "error": "No firewall tool found (nft/iptables)"}
        
        logger.info(f"Using firewall tool: {fw_tool}")
        
        if fw_tool == "nft":
            # nftables: create table + chain + masquerade rule
            subprocess.run(
                ["nft", "add", "table", "ip", "azazel_nat"],
                capture_output=True
            )
            subprocess.run(
                ["nft", "add", "chain", "ip", "azazel_nat", "postrouting", "{", "type", "nat", "hook", "postrouting", "priority", "100", ";", "}"],
                capture_output=True
            )
            subprocess.run(
                ["nft", "add", "rule", "ip", "azazel_nat", "postrouting", "oifname", wlan_iface, "masquerade"],
                capture_output=True,
                timeout=2
            )
        else:
            # iptables/iptables-nft
            subprocess.run(
                [fw_tool, "-t", "nat", "-A", "POSTROUTING", "-o", wlan_iface, "-j", "MASQUERADE"],
                capture_output=True,
                timeout=2
            )
            subprocess.run(
                [fw_tool, "-A", "FORWARD", "-i", usb_iface, "-o", wlan_iface, "-j", "ACCEPT"],
                capture_output=True,
                timeout=2
            )
            subprocess.run(
                [fw_tool, "-A", "FORWARD", "-i", wlan_iface, "-o", usb_iface, "-m", "state", "--state", "RELATED,ESTABLISHED", "-j", "ACCEPT"],
                capture_output=True,
                timeout=2
            )
        
        logger.info("NAT applied successfully")
        return {"ok": True, "fw_tool": fw_tool}
    
    except Exception as e:
        logger.error(f"Failed to apply NAT: {e}")
        return {"ok": False, "error": str(e)}


def update_state_json(wifi_state: str, **kwargs):
    """Update /run/azazel-zero/ui_snapshot.json with Wi-Fi state"""
    state_path = Path("/run/azazel-zero/ui_snapshot.json")
    fallback_path = Path.home() / ".azazel-zero/run/ui_snapshot.json"
    
    try:
        # Read from both paths to get the most complete state
        data = {}
        
        # Try to read primary path first
        if state_path.exists():
            try:
                data = json.loads(state_path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.debug(f"Failed to read {state_path}: {e}")
        
        # If primary is empty, try fallback
        if not data and fallback_path.exists():
            try:
                data = json.loads(fallback_path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.debug(f"Failed to read {fallback_path}: {e}")
        
        default_conn = {
            "wifi_state": "DISCONNECTED",
            "usb_nat": "OFF",
            "internet_check": "N/A",
            "ssid": "",
            "ip_wlan": "",
            "ip_usb": "",
            "gateway_ip": "",
            "bssid": "",
            "captive_probe_iface": "",
            "captive_portal": "NA",
            "captive_portal_reason": "NOT_CHECKED",
            "captive_checked_at": "",
        }
        conn = {}
        if isinstance(data.get("connection"), dict):
            conn = data["connection"].copy()
        merged = default_conn.copy()
        merged.update(conn)
        merged["wifi_state"] = wifi_state
        merged.update(kwargs)

        if wifi_state == "DISCONNECTED":
            for key in ("ssid", "ip_wlan", "gateway_ip", "bssid"):
                merged[key] = ""
            merged["internet_check"] = "N/A"
            merged["usb_nat"] = "OFF"

        merged["captive_portal_detail"] = {
            "status": merged.get("captive_portal", "NA"),
            "reason": merged.get("captive_portal_reason", "NOT_CHECKED"),
            "checked_at": merged.get("captive_checked_at", ""),
        }
        data["connection"] = merged
        
        # Write to BOTH paths to ensure synchronization
        # Primary path (if accessible)
        try:
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            logger.info(f"Updated {state_path}: wifi_state={wifi_state}")
        except Exception as e:
            logger.debug(f"Could not write to {state_path}: {e}")
        
        # Fallback path (always attempt)
        try:
            fallback_path.parent.mkdir(parents=True, exist_ok=True)
            fallback_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            logger.info(f"Updated {fallback_path}: wifi_state={wifi_state}")
        except Exception as e:
            logger.debug(f"Could not write to {fallback_path}: {e}")
    
    except Exception as e:
        logger.warning(f"Failed to update state.json: {e}")


def connect_wifi(ssid: str, security: str = "UNKNOWN", passphrase: Optional[str] = None, persist: bool = False) -> Dict[str, Any]:
    """
    Main entry point: Connect to Wi-Fi and enable NAT
    
    Args:
        ssid: Target SSID
        security: OPEN | WPA2 | WPA3 | UNKNOWN
        passphrase: Passphrase (required unless OPEN)
        persist: Save network for auto-connect
    
    Returns:
        {
            "ok": bool,
            "wifi_state": "CONNECTED|FAILED",
            "ip_wlan": str,
            "ip_usb": str,
            "gateway_ip": str,
            "usb_nat": "ON|OFF",
            "internet_check": "OK|FAIL",
            "captive_portal": "YES|NO|SUSPECTED|NA",
            "captive_portal_reason": str,
            "error": str (if failed)
        }
    """
    # Sanitize passphrase from logs (never log it)
    logger.info(f"Connecting to SSID: {ssid}, Security: {security}, Persist: {persist}")
    
    # Step 2: Set CONNECTING state
    update_state_json("CONNECTING", wifi_error=None, ssid=ssid)
    
    # Step 3: Detect interfaces
    wlan_iface = get_wireless_interface()
    usb_iface = get_usb_interface()
    
    if not wlan_iface:
        update_state_json("FAILED", wifi_error="No wireless interface")
        return {"ok": False, "error": "No wireless interface found", "ts": time.time()}
    
    if not usb_iface:
        logger.warning("No USB interface detected (NAT will not be applied)")
    
    # Step 4: Check NetworkManager
    if not check_networkmanager(wlan_iface):
        update_state_json("FAILED", wifi_error="NetworkManager not available")
        return {
            "ok": False,
            "error": "NetworkManager not found or not managing interface",
            "ts": time.time()
        }
    
    logger.info("Wi-Fi manager: NetworkManager")
    
    # Get saved networks
    saved_ssids = get_saved_networks_nm()
    is_saved = ssid in saved_ssids

    # Step 5: Validate input (allow saved networks without passphrase)
    error = validate_input(ssid, security, passphrase, is_saved=is_saved)
    if error:
        update_state_json("FAILED", wifi_error=error)
        return {"ok": False, "error": error, "ts": time.time()}

    # Step 6: Connect Wi-Fi using NetworkManager
    result = connect_nm(wlan_iface, ssid, security, passphrase, persist)
    
    if not result["ok"]:
        update_state_json("FAILED", wifi_error=result.get("error", "Connection failed"))
        return {"ok": False, "error": result.get("error"), "ts": time.time()}
    
    # Step 7: Get IP info
    ip_wlan = get_interface_ip(wlan_iface)
    ip_usb = get_interface_ip(usb_iface) if usb_iface else None
    gateway_ip = get_gateway_ip(wlan_iface)
    
    # Step 8: Connectivity checks (captive aware)
    if not ip_wlan:
        checks = {
            "gateway_reachable": "FAIL",
            "dns_resolution": "FAIL",
            "http_check": "FAIL",
            "http_code": "000",
            "location": "",
            "body_len": 0,
            "effective_url": "",
            "curl_error": "NO_IP",
        }
        captive_eval = {"status": "NA", "reason": "NO_IP"}
    else:
        checks = check_connectivity(wlan_iface)
        captive_eval = detect_captive_portal(checks)
    captive_portal = captive_eval["status"]
    captive_reason = captive_eval["reason"]
    internet_check = "OK" if captive_portal == "NO" else "FAIL"
    
    # Step 9: Apply NAT
    usb_nat = "OFF"
    if usb_iface:
        nat_result = apply_nat(wlan_iface, usb_iface)
        if nat_result["ok"]:
            usb_nat = "ON"
        else:
            logger.warning(f"NAT not applied: {nat_result.get('error')}")
    
    # Step 10: Finalize state
    update_state_json(
        "CONNECTED",
        wifi_error=None,
        ssid=ssid,
        ip_wlan=ip_wlan,
        ip_usb=ip_usb,
        gateway_ip=gateway_ip,
        bssid="",
        usb_nat=usb_nat,
        internet_check=internet_check,
        captive_probe_iface=wlan_iface,
        captive_portal=captive_portal,
        captive_portal_reason=captive_reason,
        captive_checked_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )
    
    return {
        "ok": True,
        "wifi_state": "CONNECTED",
        "ip_wlan": ip_wlan,
        "ip_usb": ip_usb,
        "gateway_ip": gateway_ip,
        "usb_nat": usb_nat,
        "internet_check": internet_check,
        "captive_portal": captive_portal,
        "captive_portal_reason": captive_reason,
        "checks": checks,
        "ts": time.time()
    }


if __name__ == "__main__":
    # Test mode
    import argparse
    logging.basicConfig(level=logging.INFO)
    
    parser = argparse.ArgumentParser(description="Wi-Fi Connect Test")
    parser.add_argument("ssid", help="Target SSID")
    parser.add_argument("--security", default="UNKNOWN", help="Security type (OPEN|WPA2|WPA3)")
    parser.add_argument("--passphrase", help="Passphrase (if required)")
    parser.add_argument("--persist", action="store_true", help="Save network")
    
    args = parser.parse_args()
    
    result = connect_wifi(args.ssid, args.security, args.passphrase, args.persist)
    print(json.dumps(result, indent=2))
