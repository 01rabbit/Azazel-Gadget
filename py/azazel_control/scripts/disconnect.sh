#!/bin/bash
# Disconnect: Disconnect all downstream clients
curl -s http://127.0.0.1:8082/action/disconnect 2>/dev/null || true
echo "Disconnect initiated"
