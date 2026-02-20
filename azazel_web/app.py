#!/usr/bin/env python3
"""
Azazel-Zero Web UI - Flask Application

Provides HTTP API for remote monitoring and control via USB gadget network.
- Reads: /run/azazel-zero/ui_snapshot.json (shared with TUI)
- Executes: Actions via Unix socket to control daemon
- Serves: HTML dashboard + JSON API endpoints
"""

from flask import Flask, jsonify, request, render_template, send_from_directory, has_request_context
import json
import os
import socket
import time
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
from urllib.request import urlopen
from urllib.parse import urlparse

app = Flask(__name__)

# Configuration
STATE_PATH = Path("/run/azazel-zero/ui_snapshot.json")  # Share TUI snapshot
FALLBACK_STATE_PATH = Path(".azazel-zero/run/ui_snapshot.json")  # Fallback for testing
CONTROL_SOCKET = Path("/run/azazel/control.sock")
TOKEN_FILE = Path.home() / ".azazel-zero" / "web_token.txt"
BIND_HOST = os.environ.get("AZAZEL_WEB_HOST", "0.0.0.0")
BIND_PORT = int(os.environ.get("AZAZEL_WEB_PORT", "8084"))
STATUS_API_HOSTS = ["10.55.0.10", "127.0.0.1"]
PORTAL_VIEWER_ENV_PATH = Path("/etc/azazel-zero/portal-viewer.env")

# Allowed actions
ALLOWED_ACTIONS = {
    "refresh", "reprobe", "contain", "release", "details", "stage_open", "disconnect",
    "wifi_scan", "wifi_connect", "portal_viewer_open"  # Wi-Fi + portal viewer actions
}

def load_token() -> Optional[str]:
    """Web UI 認証トークンをロード"""
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text().strip()
    return None

def verify_token() -> bool:
    """リクエストのトークン検証（ヘッダーまたはクエリパラメータ）"""
    token = load_token()
    if not token:
        return True  # トークン未設定の場合はスルー
    
    req_token = (
        request.headers.get('X-AZAZEL-TOKEN')
        or request.headers.get('X-Auth-Token')
        or request.args.get('token')
    )
    return req_token == token


def _pid_running(pid_path: Path) -> bool:
    """Check whether the pid in pid_path is running."""
    try:
        pid_text = pid_path.read_text().strip()
        if not pid_text:
            return False
        pid = int(pid_text)
    except Exception:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _service_active(service: str) -> bool:
    """Check systemd service status without requiring root."""
    try:
        result = subprocess.run(
            ["/bin/systemctl", "is-active", service],
            capture_output=True,
            text=True,
            timeout=2,
        )
        return result.returncode == 0 and result.stdout.strip() == "active"
    except Exception:
        return False


def _portal_viewer_config() -> Dict[str, Any]:
    """Resolve portal viewer bind/port from env file."""
    default_bind = os.environ.get("PORTAL_NOVNC_BIND", os.environ.get("MGMT_IP", "10.55.0.10"))
    default_port = int(os.environ.get("PORTAL_NOVNC_PORT", "6080"))
    config = {
        "bind": default_bind,
        "port": default_port,
    }
    try:
        if not PORTAL_VIEWER_ENV_PATH.exists():
            return config
        for raw in PORTAL_VIEWER_ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[7:].strip()
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key == "PORTAL_NOVNC_PORT":
                config["port"] = int(value)
            elif key == "PORTAL_NOVNC_BIND":
                config["bind"] = value
    except Exception:
        return config
    return config


def _probe_hosts_for_bind(bind_host: str) -> list:
    """Build probe host candidates from bind address."""
    host = str(bind_host or "").strip()
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    if host in {"", "0.0.0.0", "::", "*"}:
        return ["127.0.0.1", "::1"]
    if host in {"localhost", "127.0.0.1", "::1"}:
        return [host]
    return [host, "127.0.0.1"]


def _tcp_open(port: int, hosts: list, timeout_sec: float = 0.2) -> bool:
    """Check TCP availability on any candidate host."""
    seen = set()
    for host in hosts:
        if host in seen:
            continue
        seen.add(host)
        try:
            with socket.create_connection((host, int(port)), timeout=timeout_sec):
                return True
        except Exception:
            continue
    return False


def _url_host(host: str) -> str:
    """Format host part for URL (wrap IPv6 if needed)."""
    formatted = str(host or "").strip()
    if ":" in formatted and not (formatted.startswith("[") and formatted.endswith("]")):
        return f"[{formatted}]"
    return formatted


def _is_wildcard_bind(host: str) -> bool:
    host = str(host or "").strip()
    return host in {"", "0.0.0.0", "::", "*"}


def _request_host_or_default() -> str:
    if has_request_context():
        return request.host.split(":")[0] if request.host else "10.55.0.10"
    return "10.55.0.10"


def _request_scheme_or_default() -> str:
    if has_request_context():
        return request.scheme
    return "http"


def _normalize_http_url(candidate: Any) -> str:
    """Return normalized http(s) URL or empty string."""
    text = str(candidate or "").strip()
    if not text or any(ch in text for ch in ("\r", "\n")):
        return ""
    parsed = urlparse(text)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return ""
    return text


def _portal_start_url_from_state(state: Dict[str, Any]) -> str:
    """Infer the best portal start URL from latest captive probe state."""
    if not isinstance(state, dict):
        return ""
    conn = state.get("connection")
    if not isinstance(conn, dict):
        return ""

    status = str(conn.get("captive_portal", "") or "").upper()
    detail = conn.get("captive_portal_detail") if isinstance(conn.get("captive_portal_detail"), dict) else {}
    candidates = [
        detail.get("portal_url"),
        conn.get("captive_portal_url"),
        detail.get("location"),
        detail.get("effective_url"),
        conn.get("captive_location"),
        conn.get("captive_effective_url"),
        detail.get("probe_url"),
        conn.get("captive_probe_url"),
    ]
    for candidate in candidates:
        normalized = _normalize_http_url(candidate)
        if normalized:
            return normalized

    if status in {"YES", "SUSPECTED"}:
        return "http://connectivitycheck.gstatic.com/generate_204"
    return ""


def _portal_viewer_url_host(config_bind: str) -> str:
    """Choose host advertised to clients for noVNC URL."""
    override_host = os.environ.get("PORTAL_VIEWER_HOST", "").strip()
    if override_host:
        return override_host
    if not _is_wildcard_bind(config_bind):
        return config_bind
    return _request_host_or_default()


def _portal_viewer_state_from_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Build portal viewer state from resolved config + runtime checks."""
    bind_host = str(config.get("bind", "")).strip() or os.environ.get("MGMT_IP", "10.55.0.10")
    port = int(config.get("port", 6080))
    probe_hosts = _probe_hosts_for_bind(bind_host)
    active = _service_active("azazel-portal-viewer.service")
    ready = active and _tcp_open(port, probe_hosts)
    scheme = _request_scheme_or_default()
    host = _url_host(_portal_viewer_url_host(bind_host))
    url = f"{scheme}://{host}:{port}/vnc.html?autoconnect=true&resize=scale"
    return {
        "active": active,
        "ready": ready,
        "bind": bind_host,
        "probe_hosts": probe_hosts,
        "port": port,
        "url": url,
    }


def get_portal_viewer_state() -> Dict[str, Any]:
    """Return current noVNC portal viewer availability."""
    return _portal_viewer_state_from_config(_portal_viewer_config())


def _ntfy_health_ok() -> bool:
    """Check ntfy HTTP health endpoint."""
    mgmt_ip = os.environ.get("MGMT_IP", "10.55.0.10")
    ntfy_port = os.environ.get("NTFY_PORT", "8081")
    url = f"http://{mgmt_ip}:{ntfy_port}/v1/health"
    try:
        with urlopen(url, timeout=2) as resp:
            if resp.status != 200:
                return False
            body = resp.read(256).decode("utf-8", errors="ignore")
            return '"healthy":true' in body
    except Exception:
        return False


def get_monitoring_state() -> Dict[str, str]:
    """Return ON/OFF status for local monitoring daemons."""
    # Prefer systemd state to avoid pidfile permission issues
    opencanary_ok = _service_active("opencanary.service")
    suricata_ok = _service_active("suricata.service")
    ntfy_ok = _service_active("ntfy.service") and _ntfy_health_ok()
    opencanary_pid = Path("/home/azazel/canary-venv/bin/opencanaryd.pid")
    suricata_pid = Path("/run/suricata.pid")
    return {
        "opencanary": "ON" if (opencanary_ok or _pid_running(opencanary_pid)) else "OFF",
        "suricata": "ON" if (suricata_ok or _pid_running(suricata_pid)) else "OFF",
        "ntfy": "ON" if ntfy_ok else "OFF",
    }


def read_state() -> Dict[str, Any]:
    """Read state.json from filesystem (shared with TUI)"""
    try:
        # Try primary path (TUI snapshot)
        path = STATE_PATH
        if not path.exists():
            # Try fallback path (for dev/testing)
            path = FALLBACK_STATE_PATH
        
        if not path.exists():
            return {
                "ok": False,
                "error": "ui_snapshot.json not found",
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S")
            }
        
        data = json.loads(path.read_text(encoding="utf-8"))
        data["ok"] = True
        return data
    except Exception as e:
        return {
            "ok": False,
            "error": f"Failed to read state: {str(e)}",
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S")
        }


def execute_contain_action() -> Dict[str, Any]:
    """Execute contain action: activate CONTAIN stage via Status API"""
    try:
        # Try to reach Status API on first-minute service
        # Try both 127.0.0.1:8082 and 10.55.0.10:8082
        for host in ["10.55.0.10", "127.0.0.1"]:
            try:
                result = subprocess.run(
                    ["curl", "-s", "-X", "POST", f"http://{host}:8082/action/contain"],
                    capture_output=True,
                    timeout=2
                )
                if result.returncode == 0:
                    response_text = result.stdout.decode("utf-8").strip()
                    if response_text:
                        payload = json.loads(response_text)
                        if payload.get("status") == "ok" and "ok" not in payload:
                            payload["ok"] = True
                        return payload
                    return {"ok": True, "action": "contain", "message": "Containment activated"}
            except Exception:
                continue
        return {"ok": False, "action": "contain", "error": "Failed to reach Status API on any host"}
    except Exception as e:
        return {"ok": False, "action": "contain", "error": str(e)}

def execute_disconnect_action() -> Dict[str, Any]:
    """Execute disconnect action: disconnect downstream USB clients"""
    try:
        # Try to send to Status API first
        for host in ["10.55.0.10", "127.0.0.1"]:
            try:
                result = subprocess.run(
                    ["curl", "-s", "-X", "POST", f"http://{host}:8082/action/disconnect"],
                    capture_output=True,
                    timeout=2
                )
                if result.returncode == 0:
                    response_text = result.stdout.decode("utf-8").strip()
                    if response_text:
                        payload = json.loads(response_text)
                        if payload.get("status") == "ok" and "ok" not in payload:
                            payload["ok"] = True
                        return payload
            except Exception:
                continue
        
        # Fallback: attempt to bring down upstream Wi-Fi interface
        iface = os.environ.get("AZAZEL_UP_IF", "wlan0")
        down_result = subprocess.run(
            ["ip", "link", "set", iface, "down"],
            capture_output=True,
            timeout=5
        )
        if down_result.returncode != 0:
            stderr = down_result.stderr.decode("utf-8").strip() if down_result.stderr else "unknown error"
            return {
                "ok": False,
                "action": "disconnect",
                "error": f"Fallback disconnect failed: {iface} down failed: {stderr}"
            }
        
        return {"ok": True, "action": "disconnect", "message": f"Wi-Fi disconnected ({iface} down)"}
    except Exception as e:
        return {"ok": False, "action": "disconnect", "error": str(e)}

def _post_status_action(host: str, action: str) -> Optional[Dict[str, Any]]:
    """POST action to first-minute Status API and normalize response."""
    try:
        result = subprocess.run(
            ["curl", "-s", "-X", "POST", f"http://{host}:8082/action/{action}"],
            capture_output=True,
            timeout=2,
        )
        if result.returncode != 0:
            return None
        response_text = result.stdout.decode("utf-8").strip()
        if not response_text:
            return {"ok": True, "action": action}
        payload = json.loads(response_text)
        if payload.get("status") == "ok" and "ok" not in payload:
            payload["ok"] = True
        return payload
    except Exception:
        return None

def _read_status_state(host: str) -> Optional[Dict[str, Any]]:
    """GET current state from first-minute Status API."""
    try:
        result = subprocess.run(
            ["curl", "-s", f"http://{host}:8082/"],
            capture_output=True,
            timeout=2,
        )
        if result.returncode != 0:
            return None
        response_text = result.stdout.decode("utf-8").strip()
        if not response_text:
            return None
        payload = json.loads(response_text)
        if isinstance(payload, dict):
            return payload
        return None
    except Exception:
        return None

def execute_release_action() -> Dict[str, Any]:
    """Execute release action and verify that stage actually leaves CONTAIN."""
    try:
        for host in STATUS_API_HOSTS:
            first = _post_status_action(host, "release")
            if not first:
                continue
            if not first.get("ok", False):
                return {
                    "ok": False,
                    "action": "release",
                    "error": first.get("error", "Failed to send release command"),
                }

            second_sent = False
            last_reason = ""
            deadline = time.time() + 12.0

            while time.time() < deadline:
                state_payload = _read_status_state(host)
                if not state_payload:
                    time.sleep(0.25)
                    continue

                state_name = str(state_payload.get("stage") or state_payload.get("state") or "").upper()
                reason = str(state_payload.get("reason") or "").strip()
                if reason:
                    last_reason = reason

                if state_name and state_name != "CONTAIN":
                    return {
                        "ok": True,
                        "action": "release",
                        "message": "Containment released",
                        "state": state_name,
                        "reason": reason,
                    }

                reason_lower = reason.lower()
                if "minimum duration not reached" in reason_lower:
                    return {"ok": False, "action": "release", "error": reason}

                if ("confirmation required" in reason_lower) and not second_sent:
                    second = _post_status_action(host, "release")
                    if not second or not second.get("ok", False):
                        return {
                            "ok": False,
                            "action": "release",
                            "error": (second or {}).get("error", "Failed to send release confirmation"),
                        }
                    second_sent = True

                time.sleep(0.25)

            if last_reason:
                return {"ok": False, "action": "release", "error": f"Release timeout: {last_reason}"}
            return {"ok": False, "action": "release", "error": "Release timeout: stage stayed CONTAIN"}

        return {"ok": False, "action": "release", "error": "Failed to reach Status API on any host"}
    except Exception as e:
        return {"ok": False, "action": "release", "error": str(e)}

def execute_details_action() -> Dict[str, Any]:
    """Execute details action: get detailed threat analysis from Status API"""
    try:
        for host in ["10.55.0.10", "127.0.0.1"]:
            try:
                result = subprocess.run(
                    ["curl", "-s", f"http://{host}:8082/details"],
                    capture_output=True,
                    timeout=2,
                )
                if result.returncode == 0:
                    response_text = result.stdout.decode("utf-8").strip()
                    if response_text:
                        payload = json.loads(response_text)
                        if payload.get("status") == "ok" and "ok" not in payload:
                            payload["ok"] = True
                        return payload
                    return {"ok": True, "action": "details", "message": "No details available"}
            except Exception:
                continue
        return {"ok": False, "action": "details", "error": "Failed to reach Status API on any host"}
    except Exception as e:
        return {"ok": False, "action": "details", "error": str(e)}

def execute_stage_open_action() -> Dict[str, Any]:
    """Execute stage_open action: return to NORMAL stage via Status API"""
    try:
        for host in ["10.55.0.10", "127.0.0.1"]:
            try:
                result = subprocess.run(
                    ["curl", "-s", "-X", "POST", f"http://{host}:8082/action/stage_open"],
                    capture_output=True,
                    timeout=2,
                )
                if result.returncode == 0:
                    response_text = result.stdout.decode("utf-8").strip()
                    if response_text:
                        payload = json.loads(response_text)
                        if payload.get("status") == "ok" and "ok" not in payload:
                            payload["ok"] = True
                        return payload
                    return {"ok": True, "action": "stage_open", "message": "Stage opened"}
            except Exception:
                continue
        return {"ok": False, "action": "stage_open", "error": "Failed to reach Status API on any host"}
    except Exception as e:
        return {"ok": False, "action": "stage_open", "error": str(e)}

def send_control_command(action: str) -> Dict[str, Any]:
    """Send command to Control Daemon via Unix socket"""
    if action not in ALLOWED_ACTIONS:
        return {
            "ok": False,
            "action": action,
            "error": "Unknown action",
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S")
        }
    
    # Handle contain and disconnect directly
    if action == "contain":
        return execute_contain_action()
    if action == "release":
        return execute_release_action()
    if action == "disconnect":
        return execute_disconnect_action()
    if action == "details":
        return execute_details_action()
    if action == "stage_open":
        return execute_stage_open_action()
    if action == "portal_viewer_open":
        return send_control_command_with_params("portal_viewer_open", {"timeout_sec": 15})
    
    if not CONTROL_SOCKET.exists():
        return {
            "ok": False,
            "action": action,
            "error": "Control daemon not running",
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S")
        }
    
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        sock.connect(str(CONTROL_SOCKET))
        
        # Send JSON command
        command = json.dumps({"action": action, "ts": time.time()})
        sock.sendall(command.encode("utf-8") + b"\n")
        
        # Receive response
        response = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            response += chunk
            if b"\n" in chunk:
                break
        
        sock.close()
        
        if response:
            return json.loads(response.decode("utf-8"))
        else:
            return {
                "ok": False,
                "action": action,
                "error": "Empty response from daemon",
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S")
            }
    
    except socket.timeout:
        return {
            "ok": False,
            "action": action,
            "error": "Daemon timeout",
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S")
        }
    except Exception as e:
        return {
            "ok": False,
            "action": action,
            "error": str(e),
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S")
        }


def send_control_command_with_params(action: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Send command with parameters to Control Daemon via Unix socket"""
    if action not in ALLOWED_ACTIONS:
        return {
            "ok": False,
            "action": action,
            "error": "Unknown action",
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S")
        }
    
    if not CONTROL_SOCKET.exists():
        return {
            "ok": False,
            "action": action,
            "error": "Control daemon not running",
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S")
        }
    
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(30.0)  # Longer timeout for Wi-Fi operations
        sock.connect(str(CONTROL_SOCKET))
        
        # Send JSON command with params
        command = json.dumps({"action": action, "params": params, "ts": time.time()})
        sock.sendall(command.encode("utf-8") + b"\n")
        
        # Receive response
        response = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            response += chunk
            if b"\n" in chunk:
                break
        
        sock.close()
        
        if response:
            return json.loads(response.decode("utf-8"))
        else:
            return {
                "ok": False,
                "action": action,
                "error": "Empty response from daemon",
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S")
            }
    
    except socket.timeout:
        return {
            "ok": False,
            "action": action,
            "error": "Daemon timeout",
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S")
        }
    except Exception as e:
        return {
            "ok": False,
            "action": action,
            "error": str(e),
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S")
        }


# Web UI Routes

@app.route("/")
def index():
    """Main dashboard page"""
    return render_template("index.html")


@app.route("/api/state")
def api_state():
    """GET /api/state - Return current state.json"""
    if not verify_token():
        return jsonify({"error": "Unauthorized"}), 403
    
    state = read_state()
    # Add local monitoring status
    state["monitoring"] = get_monitoring_state()
    state["portal_viewer"] = get_portal_viewer_state()
    return jsonify(state)


@app.route("/api/portal-viewer")
def api_portal_viewer():
    """GET /api/portal-viewer - Return portal viewer status and URL."""
    if not verify_token():
        return jsonify({"error": "Unauthorized"}), 403
    return jsonify(get_portal_viewer_state())


@app.route("/api/portal-viewer/open", methods=["POST"])
def api_portal_viewer_open():
    """POST /api/portal-viewer/open - Ensure noVNC is up then return URL."""
    if not verify_token():
        return jsonify({"ok": False, "error": "Unauthorized"}), 403

    request_body = request.get_json(silent=True) or {}
    timeout_sec = request_body.get("timeout_sec", 15)
    start_url = _normalize_http_url(request_body.get("start_url", ""))
    if not start_url:
        state = read_state()
        if state.get("ok"):
            start_url = _portal_start_url_from_state(state)

    params = {"timeout_sec": timeout_sec}
    if start_url:
        params["start_url"] = start_url
    daemon_result = send_control_command_with_params(
        "portal_viewer_open",
        params,
    )

    if not daemon_result.get("ok"):
        return jsonify({
            "ok": False,
            "error": daemon_result.get("error", "Failed to start portal viewer"),
            "portal_viewer": get_portal_viewer_state(),
            "daemon": daemon_result,
        }), 500

    portal_state = get_portal_viewer_state()
    if not portal_state.get("ready"):
        return jsonify({
            "ok": False,
            "error": (
                "Portal viewer service started, but noVNC is not reachable "
                f"(bind={portal_state.get('bind')}, probe={portal_state.get('probe_hosts')})"
            ),
            "portal_viewer": portal_state,
            "daemon": daemon_result,
        }), 500

    resolved_start_url = start_url or str(daemon_result.get("start_url", "") or "")
    return jsonify({
        "ok": True,
        "url": portal_state.get("url"),
        "start_url": resolved_start_url,
        "portal_viewer": portal_state,
        "daemon": daemon_result,
    }), 200


@app.route("/api/action", methods=["POST"])
def api_action_new():
    """POST /api/action - Execute control action (AI Coding Spec v1 format)"""
    if not verify_token():
        return jsonify({"error": "Unauthorized"}), 403
    
    data = request.json
    if not data or 'action' not in data:
        return jsonify({
            "status": "error",
            "message": "Missing action"
        }), 400
    
    action = data['action']
    if action not in ALLOWED_ACTIONS:
        return jsonify({
            "status": "error",
            "message": f"Forbidden action: {action}"
        }), 403
    
    result = send_control_command(action)
    
    # Convert to AI Coding Spec format
    if result.get("ok"):
        return jsonify({"status": "ok", "message": result.get("message", "Action executed")}), 200
    else:
        return jsonify({"status": "error", "message": result.get("error", "Unknown error")}), 500


@app.route("/api/action/<action>", methods=["POST"])
def api_action(action: str):
    """POST /api/action/<action> - Execute control action (legacy format)"""
    if not verify_token():
        return jsonify({"ok": False, "error": "Unauthorized"}), 403
    
    # Validate action
    if action not in ALLOWED_ACTIONS:
        return jsonify({
            "ok": False,
            "error": f"Unknown action: {action}"
        }), 404
    
    # Forward to Control Daemon
    result = send_control_command(action)
    
    if result.get("ok"):
        return jsonify(result), 200
    else:
        return jsonify(result), 500


@app.route("/api/wifi/scan", methods=["GET"])
def api_wifi_scan():
    """GET /api/wifi/scan - Scan for Wi-Fi access points"""
    # No token required (read-only operation)
    
    result = send_control_command_with_params("wifi_scan", {})
    
    if result.get("ok"):
        return jsonify(result), 200
    else:
        return jsonify(result), 500


@app.route("/api/wifi/connect", methods=["POST"])
def api_wifi_connect():
    """POST /api/wifi/connect - Connect to Wi-Fi AP"""
    if not verify_token():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    
    data = request.json
    if not data:
        return jsonify({"ok": False, "error": "Missing request body"}), 400
    
    # Extract parameters
    ssid = data.get("ssid")
    security = data.get("security", "UNKNOWN")
    passphrase = data.get("passphrase")
    saved = bool(data.get("saved", False))
    persist = data.get("persist", False)
    
    # Validation
    if not ssid:
        return jsonify({"ok": False, "error": "Missing SSID"}), 400
    
    # For OPEN networks, discard passphrase if present
    if security == "OPEN":
        passphrase = None
    elif not passphrase and not saved:
        # Non-OPEN network requires passphrase unless already saved
        return jsonify({"ok": False, "error": "Passphrase required for protected network"}), 400
    
    # NEVER log request body for this endpoint
    app.logger.info(f"Wi-Fi connect request: SSID={ssid}, Security={security} (passphrase sanitized)")
    
    # Forward to Control Daemon
    params = {
        "ssid": ssid,
        "security": security,
        "passphrase": passphrase,
        "persist": persist,
        "saved": saved
    }
    
    result = send_control_command_with_params("wifi_connect", params)
    
    if result.get("ok"):
        return jsonify(result), 200
    else:
        return jsonify(result), 500


@app.route("/static/<path:filename>")
def static_files(filename):
    """Serve static files"""
    return send_from_directory("static", filename)


@app.route("/health")
def health():
    """ヘルスチェック（認証不要）"""
    return jsonify({
        "status": "ok",
        "service": "azazel-web",
        "timestamp": datetime.now().isoformat()
    })


# Error handlers

@app.errorhandler(404)
def not_found(e):
    return jsonify({"ok": False, "error": "Not found"}), 404


@app.errorhandler(500)
def server_error(e):
    return jsonify({"ok": False, "error": "Server error"}), 500


if __name__ == "__main__":
    print(f"🛡️ Azazel-Gadget Web UI starting...")
    print(f"   Bind: {BIND_HOST}:{BIND_PORT}")
    print(f"   State: {STATE_PATH}")
    print(f"   Control: {CONTROL_SOCKET}")
    
    if load_token():
        print(f"   🔒 Token authentication enabled")
    else:
        print(f"   ⚠️  WARNING: No token configured (open access)")
    
    app.run(
        host=BIND_HOST,
        port=BIND_PORT,
        debug=False,
        threaded=True
    )
