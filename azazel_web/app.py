#!/usr/bin/env python3
"""
Azazel-Gadget Web UI - Flask Application
非特権プロセスとして動作し、state.json を読み取り専用で提供。
アクションは Unix socket 経由で Control Daemon へ委譲。
AI Coding Spec v1 準拠
"""

from flask import Flask, jsonify, request, render_template, send_from_directory
import json
import os
import socket
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

app = Flask(__name__)

# Configuration
STATE_PATH = Path("/run/azazel/state.json")
CONTROL_SOCKET = Path("/run/azazel/control.sock")
TOKEN_FILE = Path.home() / ".azazel-zero" / "web_token.txt"
BIND_HOST = os.environ.get("AZAZEL_WEB_HOST", "0.0.0.0")
BIND_PORT = int(os.environ.get("AZAZEL_WEB_PORT", "8084"))

# Allowed actions
ALLOWED_ACTIONS = {
    "refresh", "reprobe", "contain", "details", "stage_open", "disconnect"
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
    
    req_token = request.headers.get('X-Auth-Token') or request.args.get('token')
    return req_token == token


def read_state() -> Dict[str, Any]:
    """Read state.json from filesystem"""
    try:
        if not STATE_PATH.exists():
            return {
                "ok": False,
                "error": "state.json not found",
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S")
            }
        
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        data["ok"] = True
        return data
    except Exception as e:
        return {
            "ok": False,
            "error": f"Failed to read state: {str(e)}",
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S")
        }


def send_control_command(action: str) -> Dict[str, Any]:
    """Send command to Control Daemon via Unix socket"""
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
