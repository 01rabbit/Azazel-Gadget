#!/bin/bash
# Extended debug test for WebUI button operations via Flask

echo "=== Extended WebUI Button Test (via Flask) ==="
echo ""

# Test contain action via Flask
echo "1. Testing contain action via Flask..."
RESPONSE=$(curl -s -X POST http://127.0.0.1:8084/api/action/contain \
    -H "X-Auth-Token: azazel-default-token-change-me" \
    -H "Content-Type: application/json")
echo "   Response: $RESPONSE"
echo ""

# Test disconnect action via Flask
echo "2. Testing disconnect action via Flask..."
RESPONSE=$(curl -s -X POST http://127.0.0.1:8084/api/action/disconnect \
    -H "X-Auth-Token: azazel-default-token-change-me" \
    -H "Content-Type: application/json")
echo "   Response: $RESPONSE"
echo ""

# Test reprobe action via Flask (for comparison)
echo "3. Testing reprobe action via Flask (for comparison)..."
RESPONSE=$(curl -s -X POST http://127.0.0.1:8084/api/action/reprobe \
    -H "X-Auth-Token: azazel-default-token-change-me" \
    -H "Content-Type: application/json")
echo "   Response: $RESPONSE"
echo ""

echo "=== Extended Test Complete ==="
