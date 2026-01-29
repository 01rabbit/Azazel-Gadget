#!/usr/bin/env python3
"""
Azazel-Zero State Generator
Polls system metrics and legacy API, writes comprehensive state to /run/azazel/state.json
"""

import json
import time
import sys
import os
import logging
import subprocess
import re
from pathlib import Path
from datetime import datetime
import urllib.request
import urllib.error

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('azazel-state-gen')

STATE_FILE = Path('/run/azazel/state.json')
LEGACY_API_URL = 'http://127.0.0.1:8082/'
POLL_INTERVAL = 2.0

def ensure_state_dir():
    """Create /run/azazel if needed"""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

def get_wifi_ssid():
    """Get connected WiFi SSID from wlan0"""
    try:
        result = subprocess.run(
            ['iw', 'dev', 'wlan0', 'link'],
            capture_output=True,
            text=True,
            timeout=2
        )
        # Look for: SSID: Example Network
        match = re.search(r'SSID:\s+(.+)', result.stdout)
        if match:
            return match.group(1).strip()
    except Exception as e:
        logger.debug(f"Failed to get SSID: {e}")
    return None

def get_wifi_ip():
    """Get IP address from wlan0 (assigned by upstream AP)"""
    try:
        result = subprocess.run(
            ['ip', 'addr', 'show', 'wlan0'],
            capture_output=True,
            text=True,
            timeout=2
        )
        # Look for: inet 192.168.x.x/24
        match = re.search(r'inet\s+(\d+\.\d+\.\d+\.\d+)', result.stdout)
        if match:
            return match.group(1)
    except Exception as e:
        logger.debug(f"Failed to get WiFi IP: {e}")
    return None

def get_cpu_temp():
    """Get CPU temperature in Celsius"""
    try:
        with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
            temp_millidegrees = int(f.read().strip())
            return round(temp_millidegrees / 1000, 1)
    except Exception as e:
        logger.debug(f"Failed to get CPU temp: {e}")
    return None

def get_cpu_usage():
    """Get CPU usage percentage"""
    try:
        result = subprocess.run(
            ['top', '-bn1'],
            capture_output=True,
            text=True,
            timeout=2
        )
        # Look for: %Cpu(s): X.X us
        match = re.search(r'%Cpu\(s\):\s+([\d.]+)\s+us', result.stdout)
        if match:
            return round(float(match.group(1)), 1)
    except Exception as e:
        logger.debug(f"Failed to get CPU usage: {e}")
    return None

def get_memory_usage():
    """Get memory usage percentage"""
    try:
        result = subprocess.run(
            ['free', '-b'],
            capture_output=True,
            text=True,
            timeout=2
        )
        lines = result.stdout.split('\n')
        # Line 1: Mem: total used free...
        mem_line = lines[1].split()
        total = int(mem_line[1])
        used = int(mem_line[2])
        percentage = round((used / total) * 100, 1)
        return percentage
    except Exception as e:
        logger.debug(f"Failed to get memory usage: {e}")
    return None

def fetch_legacy_state():
    """Fetch state from legacy API on port 8082"""
    try:
        with urllib.request.urlopen(LEGACY_API_URL, timeout=2) as response:
            data = json.loads(response.read().decode('utf-8'))
            return data
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
        logger.debug(f"Failed to fetch from legacy API: {e}")
        return None

def write_state(state_data):
    """Write state JSON to file"""
    try:
        ensure_state_dir()
        STATE_FILE.write_text(json.dumps(state_data, indent=2))
        logger.debug(f"Wrote state: {state_data.get('state', 'unknown')}")
    except Exception as e:
        logger.error(f"Failed to write state.json: {e}")

def build_comprehensive_state(base_state=None):
    """Build comprehensive state with system metrics"""
    if base_state is None:
        base_state = {
            'state': 'INIT',
            'suspicion': 0,
            'reason': 'Starting'
        }
    
    # Add system metrics
    state = {
        **base_state,
        'ts': time.time(),
        'system': {
            'wifi': {
                'ssid': get_wifi_ssid(),
                'ip': get_wifi_ip()
            },
            'cpu': {
                'temp_c': get_cpu_temp(),
                'usage_percent': get_cpu_usage()
            },
            'memory': {
                'usage_percent': get_memory_usage()
            }
        }
    }
    return state

def main():
    logger.info("Azazel-Zero State Generator started")
    
    # Initial state
    current_state = {
        'state': 'INIT',
        'suspicion': 0,
        'reason': 'Starting',
        'ts': time.time()
    }
    write_state(build_comprehensive_state(current_state))
    
    while True:
        try:
            # Fetch from legacy API if available
            state_data = fetch_legacy_state()
            
            if state_data:
                # Legacy API provided state
                state_data['ts'] = time.time()
                write_state(build_comprehensive_state(state_data))
                current_state = state_data
            else:
                # Use cached state but update system metrics
                write_state(build_comprehensive_state(current_state))
            
            time.sleep(POLL_INTERVAL)
            
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            break
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            time.sleep(POLL_INTERVAL)

if __name__ == '__main__':
    main()
