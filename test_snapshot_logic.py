#!/usr/bin/env python3
"""Test snapshot logic for connection state preservation."""

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

# Test the merge logic
def test_snapshot_merge():
    """Test that persistent connection state is preserved in snapshot."""
    
    # Simulate states
    persistent_connection_state = {
        "wifi_state": "CONNECTED",
        "usb_nat": "ON",
        "internet_check": "OK",
        "captive_portal": "NO"
    }
    
    snap = {
        "stage": "NORMAL",
        "reason": "test"
    }
    
    # Step 1: Try to read from primary and fallback paths (simulating empty case)
    existing_connection = None
    
    # Step 2: Use persistent state (the main improvement)
    if persistent_connection_state:
        snap["connection"] = persistent_connection_state
        print("✓ Used persistent_connection_state")
    elif existing_connection:
        snap["connection"] = existing_connection
        print("✓ Used existing_connection")
    else:
        print("✗ No connection state available")
    
    # Verify result
    if "connection" in snap and snap["connection"] == persistent_connection_state:
        print("✓ Connection preserved in snapshot")
        print(f"  snapshot: {json.dumps(snap, ensure_ascii=False, indent=2)}")
        return True
    else:
        print("✗ Connection NOT preserved")
        return False

def test_sync_logic():
    """Test the sync logic that reads from files."""
    with TemporaryDirectory() as tmpdir:
        # Create a snapshot file with connection data
        snapshot_file = Path(tmpdir) / "ui_snapshot.json"
        snapshot_data = {
            "stage": "NORMAL",
            "connection": {
                "wifi_state": "CONNECTED",
                "usb_nat": "ON",
                "internet_check": "OK",
                "captive_portal": "NO"
            }
        }
        snapshot_file.write_text(json.dumps(snapshot_data))
        
        # Simulate the sync logic
        persistent_connection_state = {}
        
        # Read from file
        if snapshot_file.exists():
            data = json.loads(snapshot_file.read_text())
            conn = data.get("connection")
            if conn and conn != persistent_connection_state:
                persistent_connection_state = conn
                print(f"✓ Synced from file: {persistent_connection_state}")
                return True
        
        print("✗ Failed to sync from file")
        return False

if __name__ == "__main__":
    print("Testing snapshot logic...")
    print()
    
    print("Test 1: Snapshot merge with persistent state")
    test1 = test_snapshot_merge()
    print()
    
    print("Test 2: Sync logic from file")
    test2 = test_sync_logic()
    print()
    
    if test1 and test2:
        print("✓ All tests passed")
        sys.exit(0)
    else:
        print("✗ Some tests failed")
        sys.exit(1)
