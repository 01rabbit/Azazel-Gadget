#!/bin/bash
# Contain: Activate containment mode
# Try both 10.55.0.10:8082 and 127.0.0.1:8082
for host in 10.55.0.10 127.0.0.1; do
    curl -s -X POST http://$host:8082/action/contain 2>/dev/null && exit 0
done
echo "Warning: Could not reach Status API" >&2
exit 1
