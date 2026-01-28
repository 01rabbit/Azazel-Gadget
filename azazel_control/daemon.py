#!/usr/bin/env python3
"""
Azazel Control Daemon
Unix socket listener for Web UI commands
Must run as root for system operations
"""

import json
import os
import socket
import subprocess
import sys
import time
import threading
from pathlib import Path
from typing import Dict, Any, Optional

# Configuration
SOCKET_PATH = Path("/run/azazel/control.sock")
STATE_PATH = Path("/run/azazel/state.json")
SCRIPTS_DIR = Path(__file__).parent / "scripts"

# Rate limiting
last_action_times: Dict[str, float] = {}
RATE_LIMIT_SEC = 1.0

# Script mapping
SCRIPT_MAP = {
    "refresh": "azctl_refresh.sh",
    "reprobe": "reprobe.sh",
    "contain": "contain_mode.sh",
    "details": "dump_details.sh",
    "stage_open": "stage_open.sh",
    "disconnect": "disconnect.sh",
}


def read_state() -> Dict[str, Any]:
    """Read current state.json"""
    try:
        if not STATE_PATH.exists():
            return {}
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_state(state: Dict[str, Any]) -> None:
    """Write state.json atomically"""
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(STATE_PATH)
    except Exception as e:
        print(f"Failed to write state: {e}", file=sys.stderr)


def check_policy(action: str, state: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """Policy constraints check"""
    evid = state.get("evidence", {})
    risk = state.get("risk", {})
    
    current_state = evid.get("state", "NORMAL")
    risk_status = risk.get("status", "SAFE")
    
    # LOCKDOWN: reject stage_open
    if current_state == "LOCKDOWN" and action == "stage_open":
        return False, "stage_open rejected: system in LOCKDOWN"
    
    # DANGER: reject stage_open
    if risk_status == "DANGER" and action == "stage_open":
        return False, "stage_open rejected: status is DANGER"
    
    # Rate limit
    now = time.time()
    last_time = last_action_times.get(action, 0)
    if now - last_time < RATE_LIMIT_SEC:
        return False, f"Rate limit: same action within {RATE_LIMIT_SEC}s"
    
    return True, None


def execute_script(action: str) -> Dict[str, Any]:
    """Execute mapped script"""
    script_name = SCRIPT_MAP.get(action)
    if not script_name:
        return {"ok": False, "error": f"Unknown action: {action}"}
    
    script_path = SCRIPTS_DIR / script_name
    if not script_path.exists():
        return {"ok": False, "error": f"Script not found: {script_name}"}
    
    try:
        result = subprocess.run(
            [str(script_path)],
            capture_output=True,
            text=True,
            timeout=10,
            check=False
        )
        
        return {
            "ok": result.returncode == 0,
            "exit_code": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip()
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Script timeout"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def handle_command(command: Dict[str, Any]) -> Dict[str, Any]:
    """Handle incoming command"""
    action = command.get("action")
    if not action:
        return {
            "ok": False,
            "error": "Missing action",
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S")
        }
    
    # Read current state
    state = read_state()
    
    # Policy check
    allowed, reason = check_policy(action, state)
    if not allowed:
        return {
            "ok": False,
            "action": action,
            "error": reason,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S")
        }
    
    # Execute script
    script_result = execute_script(action)
    
    # Update rate limit
    last_action_times[action] = time.time()
    
    # Update state if needed (example: increment action counter)
    if script_result.get("ok"):
        state.setdefault("action_history", [])
        state["action_history"].append({
            "action": action,
            "ts": time.time(),
            "ts_str": time.strftime("%Y-%m-%dT%H:%M:%S")
        })
        # Keep last 10 actions
        state["action_history"] = state["action_history"][-10:]
        write_state(state)
    
    # Return response
    return {
        "ok": script_result.get("ok", False),
        "action": action,
        "message": f"{action} executed" if script_result.get("ok") else "Failed",
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "details": script_result
    }


def handle_client(client_sock: socket.socket) -> None:
    """Handle single client connection"""
    try:
        # Receive JSON command (one line)
        data = b""
        while True:
            chunk = client_sock.recv(1024)
            if not chunk:
                break
            data += chunk
            if b"\n" in chunk:
                break
        
        if not data:
            return
        
        # Parse command
        command = json.loads(data.decode("utf-8"))
        
        # Handle command
        response = handle_command(command)
        
        # Send response
        client_sock.sendall(json.dumps(response).encode("utf-8") + b"\n")
    
    except json.JSONDecodeError:
        error = {"ok": False, "error": "Invalid JSON"}
        client_sock.sendall(json.dumps(error).encode("utf-8") + b"\n")
    except Exception as e:
        error = {"ok": False, "error": str(e)}
        try:
            client_sock.sendall(json.dumps(error).encode("utf-8") + b"\n")
        except:
            pass
    finally:
        client_sock.close()


def run_daemon() -> None:
    """Main daemon loop"""
    # Check root
    if os.geteuid() != 0:
        print("Error: Control Daemon must run as root", file=sys.stderr)
        sys.exit(1)
    
    # Remove old socket
    if SOCKET_PATH.exists():
        SOCKET_PATH.unlink()
    
    # Create socket
    SOCKET_PATH.parent.mkdir(parents=True, exist_ok=True)
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(str(SOCKET_PATH))
    sock.listen(5)
    
    # Set permissions
    SOCKET_PATH.chmod(0o666)  # Allow Web UI to connect
    
    print(f"✅ Control Daemon listening on {SOCKET_PATH}")
    
    try:
        while True:
            client_sock, _ = sock.accept()
            # Handle in thread for concurrent requests
            threading.Thread(target=handle_client, args=(client_sock,), daemon=True).start()
    
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        sock.close()
        if SOCKET_PATH.exists():
            SOCKET_PATH.unlink()


if __name__ == "__main__":
    run_daemon()
