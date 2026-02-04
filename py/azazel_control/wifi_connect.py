#!/usr/bin/env python3
"""
Wi-Fi Connect Module for Azazel-Zero Control Daemon

Connects to target SSID and enables USB client NAT:
- Prefers wpa_supplicant/wpa_cli if managing wlan iface
- Falls back to NetworkManager/nmcli if available
- Validates input, detects captive portal, applies NAT
"""

import subprocess
import re
import json
import logging
import time
import socket
from typing import Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger("wifi_connect")

# Import wifi_scan helpers
import sys
sys.path.insert(0, str(Path(__file__).parent))
from wifi_scan import (
    get_wireless_interface,
    check_wpa_supplicant,
    check_networkmanager,
    get_saved_networks_wpa,
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


def run_wpa_cli(iface: str, *args: str, timeout: int = 5) -> subprocess.CompletedProcess:
    """Run wpa_cli and return the CompletedProcess."""
    return subprocess.run(
        ["wpa_cli", "-i", iface, *args],
        capture_output=True,
        text=True,
        timeout=timeout
    )


def wpa_cli_ok(result: subprocess.CompletedProcess) -> bool:
    """Check if wpa_cli command succeeded based on return code and stdout."""
    if result.returncode != 0:
        return False
    stdout = (result.stdout or "").strip()
    return stdout != "FAIL"


def parse_wpa_status(text: str) -> Dict[str, str]:
    """Parse wpa_cli status output into a dict."""
    status = {}
    for line in (text or "").splitlines():
        if "=" in line:
            key, val = line.split("=", 1)
            status[key.strip()] = val.strip()
    return status


def connect_wpa(iface: str, ssid: str, security: str, passphrase: Optional[str], persist: bool) -> Dict[str, Any]:
    """Connect using wpa_supplicant/wpa_cli"""
    try:
        sec_flags = parse_security(security)

        # Check if network already exists
        result = run_wpa_cli(iface, "list_networks")
        if not wpa_cli_ok(result):
            return {
                "ok": False,
                "error": (result.stderr.strip() or result.stdout.strip() or "wpa_cli list_networks failed")
            }
        
        network_id = None
        for line in result.stdout.splitlines()[1:]:
            parts = line.split("\t")
            if len(parts) >= 2 and parts[1].strip() == ssid:
                network_id = parts[0].strip()
                break
        
        # Create new network if needed
        created = False
        if network_id is None:
            result = run_wpa_cli(iface, "add_network")
            if not wpa_cli_ok(result):
                return {
                    "ok": False,
                    "error": (result.stderr.strip() or result.stdout.strip() or "wpa_cli add_network failed")
                }
            network_id = result.stdout.strip()
            if not network_id.isdigit():
                return {"ok": False, "error": f"wpa_cli add_network returned invalid id: {network_id}"}
            created = True

        # Configure network if newly created or credentials provided
        if created or passphrase or sec_flags["open"]:
            # Set SSID
            result = run_wpa_cli(iface, "set_network", network_id, "ssid", f'"{ssid}"')
            if not wpa_cli_ok(result):
                return {
                    "ok": False,
                    "error": (result.stderr.strip() or result.stdout.strip() or "wpa_cli set_network ssid failed")
                }

            if sec_flags["open"]:
                result = run_wpa_cli(iface, "set_network", network_id, "key_mgmt", "NONE")
                if not wpa_cli_ok(result):
                    return {
                        "ok": False,
                        "error": (result.stderr.strip() or result.stdout.strip() or "wpa_cli set_network key_mgmt failed")
                    }
            else:
                # WPA/WPA2/WPA3 handling
                if sec_flags["wpa3"]:
                    key_mgmt = "SAE WPA-PSK" if sec_flags["wpa2"] else "SAE"
                    result = run_wpa_cli(iface, "set_network", network_id, "key_mgmt", key_mgmt)
                    if not wpa_cli_ok(result):
                        return {
                            "ok": False,
                            "error": (result.stderr.strip() or result.stdout.strip() or "wpa_cli set_network key_mgmt failed")
                        }
                    if passphrase:
                        result = run_wpa_cli(iface, "set_network", network_id, "sae_password", f'"{passphrase}"')
                        if not wpa_cli_ok(result):
                            return {
                                "ok": False,
                                "error": (result.stderr.strip() or result.stdout.strip() or "wpa_cli set_network sae_password failed")
                            }
                        if sec_flags["wpa2"]:
                            result = run_wpa_cli(iface, "set_network", network_id, "psk", f'"{passphrase}"')
                            if not wpa_cli_ok(result):
                                return {
                                    "ok": False,
                                    "error": (result.stderr.strip() or result.stdout.strip() or "wpa_cli set_network psk failed")
                                }
                else:
                    result = run_wpa_cli(iface, "set_network", network_id, "key_mgmt", "WPA-PSK")
                    if not wpa_cli_ok(result):
                        return {
                            "ok": False,
                            "error": (result.stderr.strip() or result.stdout.strip() or "wpa_cli set_network key_mgmt failed")
                        }
                    if passphrase:
                        result = run_wpa_cli(iface, "set_network", network_id, "psk", f'"{passphrase}"')
                        if not wpa_cli_ok(result):
                            return {
                                "ok": False,
                                "error": (result.stderr.strip() or result.stdout.strip() or "wpa_cli set_network psk failed")
                            }

        # Enable network
        result = run_wpa_cli(iface, "enable_network", network_id)
        if not wpa_cli_ok(result):
            return {
                "ok": False,
                "error": (result.stderr.strip() or result.stdout.strip() or "wpa_cli enable_network failed")
            }
        
        # Select network
        result = run_wpa_cli(iface, "select_network", network_id)
        if not wpa_cli_ok(result) or "OK" not in (result.stdout or ""):
            return {
                "ok": False,
                "error": (result.stderr.strip() or result.stdout.strip() or "Failed to select network")
            }
        
        # Persist if requested
        if persist:
            run_wpa_cli(iface, "save_config")
        
        # Wait for connection (up to 15 seconds)
        last_status = {}
        for _ in range(15):
            result = run_wpa_cli(iface, "status", timeout=2)
            if result.returncode == 0:
                last_status = parse_wpa_status(result.stdout)
            if "wpa_state=COMPLETED" in (result.stdout or ""):
                logger.info("Wi-Fi connected via wpa_cli")
                return {"ok": True}
            
            time.sleep(1)

        wpa_state = last_status.get("wpa_state", "UNKNOWN")
        reason = last_status.get("reason", "")
        detail = f"wpa_state={wpa_state}" + (f", reason={reason}" if reason else "")
        return {"ok": False, "error": f"Connection timeout ({detail})"}
    
    except Exception as e:
        logger.error(f"wpa_cli connection failed: {e}")
        return {"ok": False, "error": str(e)}


def connect_nm(iface: str, ssid: str, security: str, passphrase: Optional[str], persist: bool) -> Dict[str, Any]:
    """Connect using NetworkManager/nmcli"""
    try:
        sec_flags = parse_security(security)

        # Check if connection exists
        result = subprocess.run(
            ["nmcli", "-t", "-f", "NAME,TYPE", "con", "show"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        con_exists = False
        for line in result.stdout.splitlines():
            parts = line.split(":")
            if len(parts) >= 2 and parts[0] == ssid and parts[1] == "802-11-wireless":
                con_exists = True
                break
        
        if con_exists:
            # Update credentials if provided (or clear for OPEN)
            if sec_flags["open"]:
                subprocess.run(
                    ["nmcli", "con", "mod", ssid, "wifi-sec.key-mgmt", "none"],
                    capture_output=True,
                    timeout=5
                )
                subprocess.run(
                    ["nmcli", "con", "mod", ssid, "-u", "wifi-sec.psk"],
                    capture_output=True,
                    timeout=5
                )
            elif passphrase:
                key_mgmt = "sae" if sec_flags["wpa3"] else "wpa-psk"
                subprocess.run(
                    ["nmcli", "con", "mod", ssid, "wifi-sec.key-mgmt", key_mgmt],
                    capture_output=True,
                    timeout=5
                )
                subprocess.run(
                    ["nmcli", "con", "mod", ssid, "wifi-sec.psk", passphrase],
                    capture_output=True,
                    timeout=5
                )

            # Connect to existing connection
            result = subprocess.run(
                ["nmcli", "con", "up", ssid],
                capture_output=True,
                text=True,
                timeout=20
            )
        else:
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
                subprocess.run(
                    ["nmcli", "con", "delete", ssid],
                    capture_output=True,
                    timeout=5
                )
        
        if result.returncode != 0:
            return {"ok": False, "error": result.stderr.strip() or "Connection failed"}

        # Disable auto-connect to ensure Wi-Fi only connects on explicit user action
        if con_exists or persist:
            try:
                subprocess.run(
                    ["nmcli", "con", "mod", ssid, "connection.autoconnect", "no"],
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


def check_connectivity() -> Dict[str, str]:
    """
    Fast connectivity checks:
    - gateway_reachable: OK/FAIL
    - dns_resolution: OK/FAIL
    - http_check: OK/FAIL
    """
    checks = {
        "gateway_reachable": "UNKNOWN",
        "dns_resolution": "UNKNOWN",
        "http_check": "UNKNOWN"
    }
    
    # Gateway ping
    try:
        result = subprocess.run(
            ["ping", "-c", "1", "-W", "2", "8.8.8.8"],
            capture_output=True,
            timeout=3
        )
        checks["gateway_reachable"] = "OK" if result.returncode == 0 else "FAIL"
    except:
        checks["gateway_reachable"] = "FAIL"
    
    # DNS resolution
    try:
        socket.gethostbyname("www.google.com")
        checks["dns_resolution"] = "OK"
    except:
        checks["dns_resolution"] = "FAIL"
    
    # HTTP check
    try:
        result = subprocess.run(
            ["curl", "-s", "-m", "3", "-o", "/dev/null", "-w", "%{http_code}", "http://www.google.com"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.stdout.strip() in ["200", "301", "302"]:
            checks["http_check"] = "OK"
        else:
            checks["http_check"] = "FAIL"
    except:
        checks["http_check"] = "FAIL"
    
    return checks


def detect_captive_portal(checks: Dict[str, str]) -> str:
    """
    Detect captive portal (heuristic):
    - Gateway reachable but HTTP/HTTPS fails -> SUSPECTED
    - All OK -> NO
    - Gateway unreachable -> UNKNOWN
    """
    if checks["gateway_reachable"] == "OK":
        if checks["http_check"] == "FAIL" or checks["dns_resolution"] == "FAIL":
            return "SUSPECTED"
        elif checks["http_check"] == "OK" and checks["dns_resolution"] == "OK":
            return "NO"
    
    return "UNKNOWN"


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
        
        # Ensure connection section exists
        if "connection" not in data:
            data["connection"] = {}
        
        # Update Wi-Fi connection state
        data["connection"]["wifi_state"] = wifi_state
        data["connection"].update(kwargs)
        
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
            "captive_portal": "YES|NO|SUSPECTED",
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
    
    # Step 4: Detect saved networks (for password-less reconnect)
    use_wpa = check_wpa_supplicant(wlan_iface)
    use_nm = check_networkmanager(wlan_iface)
    prefer_nm = use_nm and is_nm_managed(wlan_iface)
    if prefer_nm:
        logger.info("Wi-Fi manager: NetworkManager")
    elif use_wpa:
        logger.info("Wi-Fi manager: wpa_supplicant")
    elif use_nm:
        logger.info("Wi-Fi manager: NetworkManager (fallback)")
    
    if not use_wpa and not use_nm:
        update_state_json("FAILED", wifi_error="No supported Wi-Fi manager")
        return {
            "ok": False,
            "error": "No supported Wi-Fi manager found (need wpa_supplicant or NetworkManager)",
            "ts": time.time()
        }
    
    saved_ssids = set()
    if use_wpa:
        saved_ssids = get_saved_networks_wpa(wlan_iface)
    elif use_nm:
        saved_ssids = get_saved_networks_nm()

    is_saved = ssid in saved_ssids

    # Step 5: Validate input (allow saved networks without passphrase)
    error = validate_input(ssid, security, passphrase, is_saved=is_saved)
    if error:
        update_state_json("FAILED", wifi_error=error)
        return {"ok": False, "error": error, "ts": time.time()}

    # Step 6: Connect Wi-Fi
    if prefer_nm:
        result = connect_nm(wlan_iface, ssid, security, passphrase, persist)
    elif use_wpa:
        result = connect_wpa(wlan_iface, ssid, security, passphrase, persist)
    else:
        result = connect_nm(wlan_iface, ssid, security, passphrase, persist)
    
    if not result["ok"]:
        update_state_json("FAILED", wifi_error=result.get("error", "Connection failed"))
        return {"ok": False, "error": result.get("error"), "ts": time.time()}
    
    # Step 7: Get IP info
    ip_wlan = get_interface_ip(wlan_iface)
    ip_usb = get_interface_ip(usb_iface) if usb_iface else None
    gateway_ip = get_gateway_ip(wlan_iface)
    
    # Step 8: Connectivity checks
    checks = check_connectivity()
    captive_portal = detect_captive_portal(checks)
    internet_check = "OK" if checks["http_check"] == "OK" else "FAIL"
    
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
        ip_wlan=ip_wlan,
        ip_usb=ip_usb,
        gateway_ip=gateway_ip,
        usb_nat=usb_nat,
        internet_check=internet_check,
        captive_portal=captive_portal
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
