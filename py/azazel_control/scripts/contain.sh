#!/bin/bash
# Contain: Activate containment mode
curl -s http://127.0.0.1:8082/action/contain 2>/dev/null || true
echo "Containment activated"
