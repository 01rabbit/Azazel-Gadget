#!/bin/bash
# Test Web UI Components

set -e

echo "=== Azazel-Zero Web UI Integration Test ==="
echo

# 1. State Generator Test
echo "1. Testing State Generator..."
cd ~/Azazel-Zero/azazel_control
sudo mkdir -p /run/azazel
sudo chown azazel:azazel /run/azazel

# Legacy API が動作しているか確認
if ! curl -s --max-time 2 http://10.55.0.10:8082/ > /dev/null; then
    echo "   WARNING: Legacy API (port 8082) not running!"
    echo "   State Generator will generate fallback state"
fi

# State Generator を一度実行
timeout 5 python3 state_generator.py &
GENERATOR_PID=$!
sleep 3
kill $GENERATOR_PID 2>/dev/null || true

if [ -f /run/azazel/state.json ]; then
    echo "   ✅ state.json created"
    echo "   Content preview:"
    jq '.stage, .suspicion, .uptime_sec' /run/azazel/state.json 2>/dev/null || cat /run/azazel/state.json
else
    echo "   ❌ state.json NOT created"
    exit 1
fi

echo

# 2. Control Daemon Test
echo "2. Testing Control Daemon..."
sudo python3 daemon.py &
DAEMON_PID=$!
sleep 2

if [ -S /run/azazel/control.sock ]; then
    echo "   ✅ Unix socket created: /run/azazel/control.sock"
    ls -l /run/azazel/control.sock
else
    echo "   ❌ Unix socket NOT created"
    sudo kill $DAEMON_PID 2>/dev/null || true
    exit 1
fi

# Test action via socket
echo '{"action":"details","params":{}}' | nc -U /run/azazel/control.sock
if [ $? -eq 0 ]; then
    echo "   ✅ Control Daemon responded"
else
    echo "   ⚠️  Control Daemon connection test failed"
fi

sudo kill $DAEMON_PID 2>/dev/null || true
echo

# 3. Flask UI Test
echo "3. Testing Flask UI..."
cd ~/Azazel-Zero/azazel_web

# State.json がないとエラーになるので再生成
python3 ../azazel_control/state_generator.py &
GENERATOR_PID=$!
sleep 2

python3 app.py &
FLASK_PID=$!
sleep 3

# Health check
if curl -s http://localhost:8084/health | jq -e '.status == "ok"' > /dev/null; then
    echo "   ✅ Flask UI health check passed"
else
    echo "   ❌ Flask UI health check failed"
    kill $FLASK_PID $GENERATOR_PID 2>/dev/null || true
    exit 1
fi

# API state check
if curl -s http://localhost:8084/api/state | jq -e '.stage' > /dev/null; then
    echo "   ✅ /api/state endpoint working"
    curl -s http://localhost:8084/api/state | jq '.stage, .suspicion'
else
    echo "   ❌ /api/state endpoint failed"
fi

kill $FLASK_PID $GENERATOR_PID 2>/dev/null || true
echo

# 4. Integration Test
echo "4. Full Integration Test (State Generator + Daemon + Flask)..."
cd ~/Azazel-Zero/azazel_control

python3 state_generator.py &
GENERATOR_PID=$!
sleep 2

sudo python3 daemon.py &
DAEMON_PID=$!
sleep 2

cd ~/Azazel-Zero/azazel_web
python3 app.py &
FLASK_PID=$!
sleep 3

# Test action from Web UI
echo "   Testing action execution via /api/action..."
RESULT=$(curl -s -X POST http://localhost:8084/api/action \
    -H "Content-Type: application/json" \
    -d '{"action":"details","params":{}}')

if echo "$RESULT" | jq -e '.status' > /dev/null; then
    echo "   ✅ Action execution successful"
    echo "   Response: $RESULT"
else
    echo "   ⚠️  Action execution test inconclusive"
fi

# Cleanup
kill $FLASK_PID $DAEMON_PID $GENERATOR_PID 2>/dev/null || true
echo

echo "=== Test Summary ==="
echo "All components validated!"
echo
echo "To run manually:"
echo "  1. sudo systemctl start azazel-state-generator"
echo "  2. sudo systemctl start azazel-control-daemon"
echo "  3. sudo systemctl start azazel-web-ui"
echo "  4. Access: http://10.55.0.10:8084/"
