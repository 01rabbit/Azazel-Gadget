#!/bin/bash
# Stage Open: Open all traffic (return to NORMAL)
curl -s http://127.0.0.1:8082/action/stage_open 2>/dev/null || true
echo "Stage opened - returning to NORMAL"
