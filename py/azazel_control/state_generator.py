#!/usr/bin/env python3
"""
Azazel-Zero State Generator
Polls legacy API (port 8082) and writes state to /run/azazel/state.json
"""

import json
import time
import sys
import os
import logging
from pathlib import Path
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

def fetch_legacy_state():
    """Fetch state from legacy API on port 8082"""
    try:
        with urllib.request.urlopen(LEGACY_API_URL, timeout=5) as response:
            data = json.loads(response.read().decode('utf-8'))
            return data
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
        logger.warning(f"Failed to fetch from legacy API: {e}")
        return None

def write_state(state_data):
    """Write state JSON to file"""
    try:
        ensure_state_dir()
        STATE_FILE.write_text(json.dumps(state_data, indent=2))
        logger.debug(f"Wrote state: {state_data.get('state', 'unknown')}")
    except Exception as e:
        logger.error(f"Failed to write state.json: {e}")

def main():
    logger.info("Azazel-Zero State Generator started")
    
    # Initial state
    current_state = {
        'state': 'INIT',
        'suspicion': 0,
        'reason': 'Starting',
        'ts': time.time()
    }
    write_state(current_state)
    
    while True:
        try:
            # Fetch from legacy API
            state_data = fetch_legacy_state()
            
            if state_data:
                # Update timestamp
                state_data['ts'] = time.time()
                write_state(state_data)
                current_state = state_data
            else:
                # Fallback to cached state if fetch fails
                logger.debug("Using cached state")
            
            time.sleep(POLL_INTERVAL)
            
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            break
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            time.sleep(POLL_INTERVAL)

if __name__ == '__main__':
    main()
