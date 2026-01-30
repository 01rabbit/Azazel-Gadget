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

# Import Wi-Fi modules
sys.path.insert(0, str(Path(__file__).parent))
from wifi_scan import scan_wifi
from wifi_connect import connect_wifi

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('azazel-daemon')

SOCKET_PATH = Path('/run/azazel/control.sock')
ACTION_SCRIPTS = {
    'refresh': '/home/azazel/Azazel-Zero/py/azazel_control/scripts/refresh.sh',
    'reprobe': '/home/azazel/Azazel-Zero/py/azazel_control/scripts/reprobe.sh',
    'contain': '/home/azazel/Azazel-Zero/py/azazel_control/scripts/contain.sh',
    'stage_open': '/home/azazel/Azazel-Zero/py/azazel_control/scripts/stage_open.sh',
    'disconnect': '/home/azazel/Azazel-Zero/py/azazel_control/scripts/disconnect.sh',
    'details': '/home/azazel/Azazel-Zero/py/azazel_control/scripts/details.sh',
}

# Rate limiting
last_action_time = {}
RATE_LIMITS = {
    'wifi_scan': 1.0,      # 1 second
    'wifi_connect': 3.0,   # 3 seconds
}

def ensure_socket_dir():
    """Create /run/azazel if needed"""
    SOCKET_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Remove old socket if exists
    if SOCKET_PATH.exists():
        SOCKET_PATH.unlink()
    
    # Set directory permissions so any user can access
    os.chmod(str(SOCKET_PATH.parent), 0o777)

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
    ensure_socket_dir()
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
