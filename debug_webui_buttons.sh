#!/bin/bash
# Debug WebUI button operations

echo "=== WebUI Button Debug Test ==="
echo ""

# 1. Check if WebUI is running
echo "1. Checking WebUI service..."
if systemctl is-active --quiet azazel-web; then
    echo "✅ azazel-web is running"
else
    echo "❌ azazel-web is NOT running"
fi

# 2. Check if Control Daemon is running
echo ""
echo "2. Checking Control Daemon..."
if [ -S /run/azazel/control.sock ]; then
    echo "✅ Control socket exists: /run/azazel/control.sock"
else
    echo "❌ Control socket does NOT exist"
fi

# 3. Check if Status API is running
echo ""
echo "3. Checking Status API (port 8082)..."
if curl -s http://127.0.0.1:8082/ > /dev/null 2>&1; then
    echo "✅ Status API is responding on port 8082"
    echo "   Sample response:"
    curl -s http://127.0.0.1:8082/ | head -c 200
    echo "..."
else
    echo "❌ Status API is NOT responding on port 8082"
fi

# 4. Check if First-Minute service is running
echo ""
echo "4. Checking First-Minute service..."
if systemctl is-active --quiet azazel-first-minute; then
    echo "✅ azazel-first-minute is running"
else
    echo "❌ azazel-first-minute is NOT running"
fi

# 5. Test WebUI API endpoint directly
echo ""
echo "5. Testing WebUI API endpoint..."
echo "   Testing /api/state endpoint..."
if curl -s -H "X-Auth-Token: azazel-default-token-change-me" http://127.0.0.1:8084/api/state > /dev/null 2>&1; then
    echo "✅ /api/state endpoint is working"
else
    echo "❌ /api/state endpoint is NOT working"
fi

# 6. Test control action through Control Daemon (simulating Flask)
echo ""
echo "6. Testing control daemon socket..."
if [ -S /run/azazel/control.sock ]; then
    echo "   Sending test 'refresh' command..."
    echo '{"action": "refresh"}' | nc -U /run/azazel/control.sock 2>/dev/null | head -c 100 && echo ""
else
    echo "   Skipping - socket doesn't exist"
fi

# 7. Test Status API contain endpoint directly
echo ""
echo "7. Testing Status API contain endpoint..."
RESPONSE=$(curl -s -X POST http://127.0.0.1:8082/action/contain 2>/dev/null)
if [ -n "$RESPONSE" ]; then
    echo "✅ Status API /action/contain responded:"
    echo "   $RESPONSE"
else
    echo "❌ No response from Status API"
fi

# 8. Test Status API disconnect endpoint directly
echo ""
echo "8. Testing Status API disconnect endpoint..."
RESPONSE=$(curl -s -X POST http://127.0.0.1:8082/action/disconnect 2>/dev/null)
if [ -n "$RESPONSE" ]; then
    echo "✅ Status API /action/disconnect responded:"
    echo "   $RESPONSE"
else
    echo "❌ No response from Status API"
fi

# 9. Check logs for recent errors
echo ""
echo "9. Recent logs from WebUI..."
journalctl -u azazel-web -n 10 --no-pager 2>/dev/null || echo "   (journalctl not available)"

echo ""
echo "10. Recent logs from Control Daemon..."
journalctl -u azazel-control-daemon -n 10 --no-pager 2>/dev/null || echo "    (journalctl not available)"

echo ""
echo "=== Debug Test Complete ==="
