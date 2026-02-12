#!/usr/bin/env python3
"""
Azazel-Zero Web UI - Flask Application

Provides HTTP API for remote monitoring and control via USB gadget network.
- Reads: /run/azazel-zero/ui_snapshot.json (shared with TUI)
- Executes: Actions via Unix socket to control daemon
- Serves: HTML dashboard + JSON API endpoints
"""

from flask import Flask, jsonify, request, render_template, send_from_directory
import json
import os
import socket
import time
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
from urllib.request import urlopen

app = Flask(__name__)

# Configuration
STATE_PATH = Path("/run/azazel-zero/ui_snapshot.json")  # Share TUI snapshot
FALLBACK_STATE_PATH = Path(".azazel-zero/run/ui_snapshot.json")  # Fallback for testing
CONTROL_SOCKET = Path("/run/azazel/control.sock")
TOKEN_FILE = Path.home() / ".azazel-zero" / "web_token.txt"
BIND_HOST = os.environ.get("AZAZEL_WEB_HOST", "0.0.0.0")
BIND_PORT = int(os.environ.get("AZAZEL_WEB_PORT", "8084"))

# Allowed actions
ALLOWED_ACTIONS = {
    "refresh", "reprobe", "contain", "release", "details", "stage_open", "disconnect",
    "wifi_scan", "wifi_connect"  # Wi-Fi control actions
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

def execute_release_action() -> Dict[str, Any]:
    """Execute release action: clear manual CONTAIN override via Status API"""
    try:
        for host in ["10.55.0.10", "127.0.0.1"]:
            try:
                result = subprocess.run(
                    ["curl", "-s", "-X", "POST", f"http://{host}:8082/action/release"],
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
                    return {"ok": True, "action": "release", "message": "Containment released"}
            except Exception:
                continue
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
    return jsonify(state)


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
