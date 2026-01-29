#!/bin/bash
# Refresh: Force state probe
curl -s http://127.0.0.1:8082/action/probe 2>/dev/null || true
echo "Probe refresh initiated"
