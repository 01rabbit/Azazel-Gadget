#!/bin/bash
# テスト3: CONTAIN リカバリータイミング検証スクリプト
# 使用方法: ./scripts/tests/regression/run_test3_contain_recovery.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
CONFIG_FILE="/etc/azazel-gadget/first_minute.yaml"
if [ ! -f "$CONFIG_FILE" ]; then
  CONFIG_FILE="/etc/azazel-zero/first_minute.yaml"
fi
if [ ! -f "$CONFIG_FILE" ]; then
  CONFIG_FILE="${REPO_ROOT}/configs/first_minute.yaml"
fi

echo "================================================"
echo "  テスト3: CONTAIN リカバリータイミング検証"
echo "================================================"
echo ""

# API ポート設定
API_HOST="10.55.0.10"
API_PORT=$(grep -A 2 "status_api:" "$CONFIG_FILE" | grep "port:" | awk '{print $NF}' || echo "8082")

# セットアップ: CONTAIN状態に準備
echo "[セットアップ] CONTAIN状態を準備中..."
python3 << 'PYTHON_SETUP'
import json, time
from datetime import datetime, timezone
from pathlib import Path
import subprocess

eve_path = Path('/var/log/suricata/eve.json')
eve_path.write_text('')

# 現在のUTC時刻で Critical アラート注入
ts = datetime.now(timezone.utc).isoformat()
alert = {
    "timestamp": ts,
    "event_type": "alert",
    "alert": {"severity": 1, "signature": "Test3 Setup Alert", "category": "Test", "action": "allowed", "gid": 1, "signature_id": 3000001, "rev": 1},
    "src_ip": "192.168.1.100",
    "dest_ip": "10.55.0.1",
    "proto": "TCP",
    "flow": {"pkts_toserver":1,"pkts_toclient":0,"bytes_toserver":60,"bytes_toclient":0}
}
eve_path.write_text(json.dumps(alert) + "\n")

# CONTAIN になるまで待機
max_wait = 10
for i in range(max_wait):
    try:
        result = subprocess.run(["curl", "-s", "http://10.55.0.10:8082/"], capture_output=True, text=True, timeout=2)
        data = json.loads(result.stdout)
        if data.get('state') == 'CONTAIN':
            print(f"  ✓ CONTAIN状態確認 (suspicion: {data.get('suspicion')})")
            break
    except:
        pass
    if i < max_wait - 1:
        time.sleep(1)
else:
    print("  ✗ CONTAIN状態に到達できません")
    exit(1)
PYTHON_SETUP

if [ $? -ne 0 ]; then
  exit 1
fi

# 初期状態確認
CURRENT_STATE=$(curl -s http://${API_HOST}:${API_PORT}/ | jq -r '.state')
CONTAIN_SUSPICION=$(curl -s http://${API_HOST}:${API_PORT}/ | jq '.suspicion')
echo ""

echo "================================================"
echo "  テスト内容"
echo "================================================"
echo ""
echo "1. CONTAIN に入った直後から 15 秒間監視（最小継続時間 = 20秒）"
echo "   → CONTAIN は継続（最小継続時間中）"
echo ""
echo "2. さらに 10 秒待機（合計 25 秒）"
echo "   → 最小継続時間を超過し、疑わしさが減衰"
echo "   → DEGRADED へ自動遷移"
echo ""

# テスト1: CONTAIN 最小継続時間内
echo "[1/2] CONTAIN 最小継続時間中の状態確認 (T=0-15秒)..."
echo ""

CONTAIN_15_STATE="CONTAIN"
CONTAINS_15_COUNT=0

for i in {1..6}; do
  sleep 2.5
  STATE=$(curl -s http://${API_HOST}:${API_PORT}/ | jq -r '.state')
  SUSP=$(curl -s http://${API_HOST}:${API_PORT}/ | jq '.suspicion')
  T=$((i * 2 + i / 2))
  echo "  [T=${T}秒] state=$STATE suspicion=$SUSP"
  
  if [ "$STATE" = "CONTAIN" ]; then
    ((CONTAINS_15_COUNT++))
  fi
done

if [ $CONTAINS_15_COUNT -ge 5 ]; then
  echo "  ✓ CONTAIN が最小継続時間内で継続"
  TEST1_PASS=true
else
  echo "  ✗ CONTAIN が途中で解放"
  TEST1_PASS=false
fi
echo ""

# テスト2: 最小継続時間超過後の回復
echo "[2/2] 最小継続時間超過後のリカバリー (T=15-35秒)..."
echo ""

DEGRADED_DETECTED=false
RECOVERY_TIME=0

for i in {1..8}; do
  sleep 2.5
  STATE=$(curl -s http://${API_HOST}:${API_PORT}/ | jq -r '.state')
  SUSP=$(curl -s http://${API_HOST}:${API_PORT}/ | jq '.suspicion')
  T=$((15 + i * 2 + i / 2))
  echo "  [T=${T}秒] state=$STATE suspicion=$SUSP"
  
  if [ "$STATE" != "CONTAIN" ] && [ "$DEGRADED_DETECTED" = false ]; then
    DEGRADED_DETECTED=true
    RECOVERY_TIME=$T
    echo "    → リカバリー完了 (CONTAIN → $STATE at T=${RECOVERY_TIME}秒)"
  fi
done

echo ""

# 判定
echo "================================================"
echo "  テスト結果"
echo "================================================"
echo ""

PASS=true

echo "1. CONTAIN 最小継続時間内 (最初の 15 秒):"
if [ "$TEST1_PASS" = true ]; then
  echo "  ✓ CONTAIN が継続（最小継続時間 20秒を保持）"
else
  echo "  ✗ CONTAIN が途中で解放された"
  PASS=false
fi

echo ""
echo "2. 最小継続時間超過後のリカバリー:"
if [ "$DEGRADED_DETECTED" = true ] && [ $RECOVERY_TIME -ge 20 ] && [ $RECOVERY_TIME -le 35 ]; then
  echo "  ✓ リカバリー完了 (T=${RECOVERY_TIME}秒で CONTAIN → DEGRADED へ遷移)"
else
  if [ "$DEGRADED_DETECTED" = false ]; then
    echo "  ✗ リカバリーが発生しなかった（CONTAIN 継続）"
  else
    echo "  ✗ リカバリータイミングが不適切 (T=${RECOVERY_TIME}秒)"
  fi
  PASS=false
fi

echo ""
if [ "$PASS" = true ]; then
  echo "✓✓✓ テスト3: PASS ✓✓✓"
  echo ""
  echo "CONTAIN 最小継続時間 (20秒) と自動リカバリーが正常に動作しています"
  exit 0
else
  echo "✗✗✗ テスト3: FAIL ✗✗✗"
  echo ""
  echo "ログ確認:"
  echo "  journalctl -u azazel-first-minute --since '3 min ago' | grep -E 'CONTAIN|DEGRADED|contain_min'"
  exit 1
fi
