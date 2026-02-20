#!/usr/bin/env python3
"""
Azazel-Zero Control Daemon
Listens on Unix socket /run/azazel/control.sock and executes actions
"""

import json
import time
import sys
import os
import logging
import socket
import subprocess
import threading
from pathlib import Path
from urllib.parse import urlparse
try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None

# Import Wi-Fi modules
sys.path.insert(0, str(Path(__file__).parent))
from wifi_scan import scan_wifi, get_wireless_interface, check_networkmanager
from wifi_connect import connect_wifi, update_state_json

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('azazel-daemon')

SOCKET_PATH = Path('/run/azazel/control.sock')
PORTAL_VIEWER_SERVICE = "azazel-portal-viewer.service"
PORTAL_VIEWER_ENV = Path("/etc/azazel-zero/portal-viewer.env")
PORTAL_START_URL_RUNTIME_PATH = Path("/run/azazel/portal-viewer-start-url")
ACTION_SCRIPTS = {
    'refresh': '/home/azazel/Azazel-Zero/py/azazel_control/scripts/refresh.sh',
    'reprobe': '/home/azazel/Azazel-Zero/py/azazel_control/scripts/reprobe.sh',
    'contain': '/home/azazel/Azazel-Zero/py/azazel_control/scripts/contain.sh',
    'stage_open': '/home/azazel/Azazel-Zero/py/azazel_control/scripts/stage_open.sh',
    'disconnect': '/home/azazel/Azazel-Zero/py/azazel_control/scripts/disconnect.sh',
    'details': '/home/azazel/Azazel-Zero/py/azazel_control/scripts/details.sh',
    'shutdown': '/home/azazel/Azazel-Zero/py/azazel_control/scripts/shutdown.sh',
    'reboot': '/home/azazel/Azazel-Zero/py/azazel_control/scripts/reboot.sh',
}

# Rate limiting
last_action_time = {}
RATE_LIMITS = {
    'wifi_scan': 1.0,      # 1 second
    'wifi_connect': 3.0,   # 3 seconds
    'shutdown': 10.0,      # Prevent accidental repeated shutdown requests
    'reboot': 10.0,        # Prevent accidental repeated reboot requests
}
PORTAL_DEFAULT_START_URL = "http://neverssl.com"


def _read_portal_viewer_env() -> dict[str, str]:
    """Read /etc/azazel-zero/portal-viewer.env into a dict."""
    parsed: dict[str, str] = {}
    try:
        if not PORTAL_VIEWER_ENV.exists():
            return parsed
        for raw in PORTAL_VIEWER_ENV.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[7:].strip()
            key, value = line.split("=", 1)
            parsed[key.strip()] = value.strip().strip('"').strip("'")
    except Exception as e:
        logger.debug(f"Failed to read {PORTAL_VIEWER_ENV}: {e}")
    return parsed


def _normalize_http_url(candidate: object) -> str:
    """Return normalized http(s) URL or empty string."""
    text = str(candidate or "").strip()
    if not text or any(ch in text for ch in ("\r", "\n")):
        return ""
    parsed = urlparse(text)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return ""
    return text


def _write_runtime_start_url(url: str) -> tuple[bool, str]:
    """Write transient portal start URL for next portal-viewer launch."""
    try:
        PORTAL_START_URL_RUNTIME_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = PORTAL_START_URL_RUNTIME_PATH.with_suffix(".tmp")
        tmp.write_text(url + "\n", encoding="utf-8")
        os.chmod(tmp, 0o644)
        os.replace(tmp, PORTAL_START_URL_RUNTIME_PATH)
        return True, ""
    except Exception as e:
        return False, str(e)


def _service_is_active(service: str) -> bool:
    try:
        active = subprocess.run(
            ["/bin/systemctl", "is-active", service],
            capture_output=True,
            text=True,
            timeout=2,
        )
        return active.returncode == 0 and (active.stdout or "").strip() == "active"
    except Exception:
        return False


def _load_portal_viewer_endpoint(default_port: int = 6080) -> tuple[str, int]:
    """Read PORTAL_NOVNC_BIND/PORT from env file if present."""
    env = _read_portal_viewer_env()
    bind = str(env.get("PORTAL_NOVNC_BIND") or os.environ.get("PORTAL_NOVNC_BIND") or os.environ.get("MGMT_IP") or "10.55.0.10")
    try:
        port = int(env.get("PORTAL_NOVNC_PORT") or os.environ.get("PORTAL_NOVNC_PORT") or default_port)
    except Exception:
        port = default_port
    return bind, port


def _load_portal_start_url(default: str = PORTAL_DEFAULT_START_URL) -> str:
    env = _read_portal_viewer_env()
    url = _normalize_http_url(env.get("PORTAL_START_URL", ""))
    if url:
        return url
    fallback = _normalize_http_url(os.environ.get("PORTAL_START_URL", ""))
    return fallback or default


def _probe_hosts_for_bind(bind_host: str) -> list[str]:
    """Build probe host candidates from bind address."""
    host = str(bind_host or "").strip()
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    if host in {"", "0.0.0.0", "::", "*"}:
        return ["127.0.0.1", "::1"]
    if host in {"localhost", "127.0.0.1", "::1"}:
        return [host]
    return [host, "127.0.0.1"]


def _tcp_open(port: int, hosts: list[str], timeout_sec: float = 0.2) -> bool:
    """Check TCP availability on any candidate host."""
    seen = set()
    for host in hosts:
        if host in seen:
            continue
        seen.add(host)
        try:
            with socket.create_connection((host, port), timeout=timeout_sec):
                return True
        except Exception:
            continue
    return False


def ensure_portal_viewer_ready(timeout_sec: float = 15.0, start_url: str | None = None) -> dict:
    """Start portal viewer service and wait until noVNC TCP port is reachable."""
    bind, port = _load_portal_viewer_endpoint()
    probe_hosts = _probe_hosts_for_bind(bind)
    requested_start_url = _normalize_http_url(start_url or "")
    if start_url and not requested_start_url:
        return {
            "ok": False,
            "error": "Invalid start_url (must be absolute http/https URL)",
            "service": PORTAL_VIEWER_SERVICE,
            "bind": bind,
            "probe_hosts": probe_hosts,
            "port": port,
            "ts": time.time(),
        }
    try:
        service_action = "start"
        if requested_start_url:
            ok, err = _write_runtime_start_url(requested_start_url)
            if not ok:
                return {
                    "ok": False,
                    "error": f"Failed to stage runtime portal URL: {err}",
                    "service": PORTAL_VIEWER_SERVICE,
                    "bind": bind,
                    "probe_hosts": probe_hosts,
                    "port": port,
                    "start_url": requested_start_url,
                    "ts": time.time(),
                }
            # Restart when URL is requested so Chromium always lands on the target page.
            service_action = "restart" if _service_is_active(PORTAL_VIEWER_SERVICE) else "start"

        start = subprocess.run(
            ["/bin/systemctl", service_action, PORTAL_VIEWER_SERVICE],
            capture_output=True,
            text=True,
            timeout=6,
        )
        if start.returncode != 0:
            err = (start.stderr or start.stdout or "").strip() or "systemctl start failed"
            return {
                "ok": False,
                "error": err,
                "service": PORTAL_VIEWER_SERVICE,
                "bind": bind,
                "probe_hosts": probe_hosts,
                "port": port,
                "service_action": service_action,
                "start_url": requested_start_url or _load_portal_start_url(),
                "ts": time.time(),
            }

        deadline = time.time() + max(1.0, timeout_sec)
        last_active = ""
        while time.time() < deadline:
            active = subprocess.run(
                ["/bin/systemctl", "is-active", PORTAL_VIEWER_SERVICE],
                capture_output=True,
                text=True,
                timeout=2,
            )
            last_active = (active.stdout or "").strip()
            if active.returncode == 0 and last_active == "active" and _tcp_open(port, probe_hosts):
                return {
                    "ok": True,
                    "service": PORTAL_VIEWER_SERVICE,
                    "active": True,
                    "ready": True,
                    "bind": bind,
                    "probe_hosts": probe_hosts,
                    "port": port,
                    "service_action": service_action,
                    "start_url": requested_start_url or _load_portal_start_url(),
                    "ts": time.time(),
                }
            time.sleep(0.25)

        return {
            "ok": False,
            "error": (
                f"Portal viewer not ready within {timeout_sec:.0f}s "
                f"(is-active={last_active or 'unknown'}, bind={bind}, probe={probe_hosts})"
            ),
            "service": PORTAL_VIEWER_SERVICE,
            "active": last_active == "active",
            "ready": False,
            "bind": bind,
            "probe_hosts": probe_hosts,
            "port": port,
            "service_action": service_action,
            "start_url": requested_start_url or _load_portal_start_url(),
            "ts": time.time(),
        }
    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
            "service": PORTAL_VIEWER_SERVICE,
            "bind": bind,
            "probe_hosts": probe_hosts,
            "port": port,
            "start_url": requested_start_url or _load_portal_start_url(),
            "ts": time.time(),
        }


def load_control_flags() -> dict:
    flags = {"suppress_auto_wifi": True}
    if yaml is None:
        return flags

    repo_cfg = Path(__file__).resolve().parents[2] / "configs" / "first_minute.yaml"
    candidates = []
    for env_key in ("AZAZEL_FIRST_MINUTE_CONFIG", "AZAZEL_CONFIG"):
        env_path = os.environ.get(env_key)
        if env_path:
            candidates.append(Path(env_path))
    candidates.extend([Path("/etc/azazel-zero/first_minute.yaml"), repo_cfg])

    for path in candidates:
        try:
            if not path.exists():
                continue
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if isinstance(data, dict) and "suppress_auto_wifi" in data:
                flags["suppress_auto_wifi"] = bool(data.get("suppress_auto_wifi"))
                logger.info(f"Loaded control flag from {path}: suppress_auto_wifi={flags['suppress_auto_wifi']}")
                return flags
        except Exception as e:
            logger.debug(f"Failed to read control config {path}: {e}")
    return flags

def ensure_socket_dir():
    """Create /run/azazel if needed"""
    SOCKET_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Remove old socket if exists
    if SOCKET_PATH.exists():
        SOCKET_PATH.unlink()
    
    # Set directory permissions so any user can access
    os.chmod(str(SOCKET_PATH.parent), 0o777)

def suppress_auto_wifi(enabled: bool = True):
    """Disable Wi-Fi auto-connect and disconnect existing session on startup."""
    if not enabled:
        logger.info("suppress_auto_wifi disabled by config; keeping existing Wi-Fi session")
        return
    try:
        iface = get_wireless_interface()
        if not iface:
            return

        # NetworkManager: disable autoconnect for all Wi-Fi connections and disconnect
        if check_networkmanager(iface):
            try:
                result = subprocess.run(
                    ["nmcli", "-t", "-f", "NAME,TYPE", "con", "show"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                for line in result.stdout.splitlines():
                    parts = line.split(":", 1)
                    if len(parts) == 2 and parts[1] == "802-11-wireless":
                        subprocess.run(
                            ["nmcli", "con", "mod", parts[0], "connection.autoconnect", "no"],
                            capture_output=True,
                            timeout=5
                        )
                subprocess.run(
                    ["nmcli", "dev", "disconnect", iface],
                    capture_output=True,
                    timeout=5
                )
                logger.info("suppress_auto_wifi enabled: disconnected Wi-Fi and disabled autoconnect profiles")
            except Exception as e:
                logger.debug(f"Failed to disable NetworkManager auto-connect: {e}")
        else:
            logger.warning("NetworkManager not found or not managing interface")

        # Update UI snapshot to reflect disconnected state
        update_state_json(
            "DISCONNECTED",
            wifi_error=None,
            ssid="",
            ip_wlan="",
            gateway_ip="",
            bssid="",
            usb_nat="OFF",
            internet_check="N/A",
            captive_probe_iface="",
            captive_portal="NA",
            captive_portal_reason="SUPPRESSED_AT_BOOT",
            captive_checked_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )
    except Exception as e:
        logger.debug(f"suppress_auto_wifi failed: {e}")

def check_rate_limit(action: str) -> bool:
    """Check if action is rate-limited"""
    if action not in RATE_LIMITS:
        return True
    
    limit = RATE_LIMITS[action]
    now = time.time()
    last_time = last_action_time.get(action, 0)
    
    if now - last_time < limit:
        return False
    
    last_action_time[action] = now
    return True

def execute_wifi_action(action_name: str, params: dict) -> dict:
    """Execute Wi-Fi-specific actions (Python modules)"""
    if action_name == "wifi_scan":
        if not check_rate_limit("wifi_scan"):
            return {"ok": False, "error": "Rate limit exceeded (1 req/sec)", "ts": time.time()}
        return scan_wifi()
    
    elif action_name == "wifi_connect":
        if not check_rate_limit("wifi_connect"):
            return {"ok": False, "error": "Rate limit exceeded (1 req/3sec)", "ts": time.time()}
        
        # Extract parameters
        ssid = params.get("ssid")
        security = params.get("security", "UNKNOWN")
        passphrase = params.get("passphrase")
        persist = params.get("persist", False)
        
        if not ssid:
            return {"ok": False, "error": "Missing SSID parameter", "ts": time.time()}
        
        # NEVER log passphrase
        logger.info(f"Wi-Fi connect request: SSID={ssid}, Security={security}, Persist={persist}")
        
        return connect_wifi(ssid, security, passphrase, persist)
    
    return {"ok": False, "error": f"Unknown Wi-Fi action: {action_name}"}

def execute_action(action_name, params=None):
    """Execute action script and return result"""
    # Handle Wi-Fi actions via Python modules
    if action_name in ["wifi_scan", "wifi_connect"]:
        return execute_wifi_action(action_name, params or {})

    if action_name == "shutdown":
        if not check_rate_limit("shutdown"):
            return {"ok": False, "error": "Rate limit exceeded (1 req/10sec)", "ts": time.time()}
    if action_name == "reboot":
        if not check_rate_limit("reboot"):
            return {"ok": False, "error": "Rate limit exceeded (1 req/10sec)", "ts": time.time()}

    if action_name == "portal_viewer_open":
        timeout_raw = (params or {}).get("timeout_sec", 15)
        try:
            timeout_sec = float(timeout_raw)
        except Exception:
            timeout_sec = 15.0
        timeout_sec = max(1.0, min(timeout_sec, 30.0))
        start_url_raw = (params or {}).get("start_url", "")
        start_url = str(start_url_raw).strip() if isinstance(start_url_raw, str) else ""
        return ensure_portal_viewer_ready(timeout_sec=timeout_sec, start_url=start_url or None)
    
    # Handle shell script actions
    script_path = ACTION_SCRIPTS.get(action_name)
    
    if not script_path:
        return {'ok': False, 'error': f'Unknown action: {action_name}'}
    
    if not Path(script_path).exists():
        return {'ok': False, 'error': f'Script not found: {script_path}'}
    
    try:
        result = subprocess.run(
            ['/bin/bash', script_path],
            timeout=10,
            capture_output=True,
            text=True
        )
        
        return {
            'ok': result.returncode == 0,
            'stdout': result.stdout,
            'stderr': result.stderr if result.returncode != 0 else None,
            'ts': time.time()
        }
    except subprocess.TimeoutExpired:
        return {'ok': False, 'error': 'Action timeout', 'ts': time.time()}
    except Exception as e:
        return {'ok': False, 'error': str(e), 'ts': time.time()}

def handle_client(conn, addr):
    """Handle incoming client connection"""
    try:
        data = conn.recv(4096).decode('utf-8')  # Increased buffer for wifi_connect with passphrase
        request = json.loads(data)
        action = request.get('action')
        params = request.get('params', {})
        
        # Special handling: NEVER log wifi_connect params (contains passphrase)
        if action == 'wifi_connect':
            logger.info(f"Received action: wifi_connect (params sanitized)")
        else:
            logger.info(f"Received action: {action}")
        
        result = execute_action(action, params)
        
        response = json.dumps(result)
        conn.send(response.encode('utf-8'))
    except json.JSONDecodeError:
        conn.send(b'{"ok": false, "error": "Invalid JSON"}')
    except Exception as e:
        logger.error(f"Error handling client: {e}")
        conn.send(json.dumps({'ok': False, 'error': str(e)}).encode('utf-8'))
    finally:
        conn.close()

def main():
    flags = load_control_flags()
    ensure_socket_dir()
    suppress_auto_wifi(enabled=bool(flags.get("suppress_auto_wifi", True)))
    logger.info("Azazel-Zero Control Daemon started")
    
    # Create Unix socket
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(str(SOCKET_PATH))
    # Make socket world-readable/writable for other processes
    os.chmod(str(SOCKET_PATH), 0o666)
    sock.listen(1)
    logger.info(f"Listening on {SOCKET_PATH}")
    
    try:
        while True:
            conn, _ = sock.accept()
            # Handle in thread to allow concurrent connections
            thread = threading.Thread(target=handle_client, args=(conn, _))
            thread.daemon = True
            thread.start()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        sock.close()
        if SOCKET_PATH.exists():
            SOCKET_PATH.unlink()

if __name__ == '__main__':
    main()
