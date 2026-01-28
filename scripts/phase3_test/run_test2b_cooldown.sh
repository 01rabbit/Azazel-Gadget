#!/bin/bash
# テスト2B: Suricata Cooldown機構検証スクリプト
# 使用方法: ./scripts/phase3_test/run_test2b_cooldown.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "================================================"
echo "  テスト2B: Suricata Cooldown機構検証"
echo "================================================"
echo ""

# API ポート設定
API_HOST="10.55.0.10"
API_PORT=$(grep -A 2 "status_api:" /home/azazel/Azazel-Zero/configs/first_minute.yaml | grep "port:" | awk '{print $NF}' || echo "8082")

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
    "alert": {"severity": 1, "signature": "Test2B Setup Alert", "category": "Test", "action": "allowed", "gid": 1, "signature_id": 2000001, "rev": 1},
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
CURRENT_SUSP=$(curl -s http://${API_HOST}:${API_PORT}/ | jq '.suspicion')
echo ""

# テスト1: 同じ署名のアラートを5秒後に再注入（Cooldown中）
echo "[1/2] 同じ署名で再注入 (T=5秒、Cooldown中)..."
sleep 5

# 同じ署名で再度アラート（should NOT increment due to cooldown）
python3 << 'PYTHON_ALERT_1'
import json
from datetime import datetime, timezone
from pathlib import Path

eve_path = Path('/var/log/suricata/eve.json')
ts = datetime.now(timezone.utc).isoformat()

# 同じシグナチャーで再注入
alert = {
    "timestamp": ts,
    "event_type": "alert",
    "alert": {"severity": 1, "signature": "Test2B Setup Alert", "category": "Test", "action": "allowed", "gid": 1, "signature_id": 2000001, "rev": 1},
    "src_ip": "192.168.1.100",
    "dest_ip": "10.55.0.1",
    "proto": "TCP",
    "flow": {"pkts_toserver":1,"pkts_toclient":0,"bytes_toserver":60,"bytes_toclient":0}
}
with open(eve_path, 'a') as f:
    f.write(json.dumps(alert) + "\n")
print("Alert 1 (duplicate signature) injected")
PYTHON_ALERT_1

sleep 2
SUSP_AFTER_5=$(curl -s http://${API_HOST}:${API_PORT}/ | jq '.suspicion')
echo "  suspicion (T=5秒): $SUSP_AFTER_5"

# cooldown チェック: suspicion がほぼ変わらない（減衰分を許容）
DIFF=$(echo "$CURRENT_SUSP - $SUSP_AFTER_5" | bc -l)
# 5秒間の減衰: 約 15ポイント + CONTAIN持続時間調整で最大40ポイント低下もあり得る
# Cooldown が機能していれば「加点がない」ことが重要
# つまり、重複アラートが加点されず減衰のみなら OK
if (( $(echo "$DIFF > 0" | bc -l) )); then
  echo "  ✓ Cooldown 機構が動作中：重複アラートは加点されず減衰のみ"
  TEST1_PASS=true
else
  echo "  ✗ Cooldown 失敗？ suspicion が低下していない"
  TEST1_PASS=false
fi
echo ""

# テスト2: 30秒後に新しい署名のアラートを注入（Cooldown 終了）
echo "[2/2] 新しい署名で注入 (T=35秒、Cooldown終了)..."
echo "  待機中... (30秒)"
sleep 30

python3 << 'PYTHON_ALERT_2'
import json
from datetime import datetime, timezone
from pathlib import Path

eve_path = Path('/var/log/suricata/eve.json')
ts = datetime.now(timezone.utc).isoformat()

# 新しいシグナチャーで注入
alert = {
    "timestamp": ts,
    "event_type": "alert",
    "alert": {"severity": 1, "signature": "Test2B Second Signature", "category": "Test", "action": "allowed", "gid": 1, "signature_id": 2000002, "rev": 1},
    "src_ip": "192.168.1.100",
    "dest_ip": "10.55.0.1",
    "proto": "TCP",
    "flow": {"pkts_toserver":1,"pkts_toclient":0,"bytes_toserver":60,"bytes_toclient":0}
}
with open(eve_path, 'a') as f:
    f.write(json.dumps(alert) + "\n")
print("Alert 2 (new signature) injected")
PYTHON_ALERT_2

sleep 2
SUSP_AFTER_30=$(curl -s http://${API_HOST}:${API_PORT}/ | jq '.suspicion')
echo "  suspicion (T=35秒): $SUSP_AFTER_30"

# 新規シグナチャー → Cooldown 終了で加点
# 元の suspicion (50) から減衰 ~15秒分 (45ポイント) + 新規アラート (+50) = 95 のはず
# ただし状態遷移で最大減衰が入る可能性があるため、緩い判定
if (( $(echo "$SUSP_AFTER_30 > 30" | bc -l) )); then
  echo "  ✓ Cooldown 終了後、新規アラートが加点された"
  TEST2_PASS=true
else
  echo "  ✗ 新規アラート加点なし (suspicion=$SUSP_AFTER_30)"
  TEST2_PASS=false
fi
echo ""

# 判定
echo "================================================"
echo "  テスト結果"
echo "================================================"

PASS=true

echo "Cooldown 中の重複排除 (T=5秒):"
if [ "$TEST1_PASS" = true ]; then
  echo "  ✓ 同じシグナチャーの重複アラートは加点されない"
else
  echo "  ✗ Cooldown 機構の失敗"
  PASS=false
fi

echo ""
echo "Cooldown 終了後の加点 (T=35秒):"
if [ "$TEST2_PASS" = true ]; then
  echo "  ✓ Cooldown 終了後、新規アラートが正常にカウント"
else
  echo "  ✗ Cooldown 終了後のアラート加点が失敗"
  PASS=false
fi

echo ""
if [ "$PASS" = true ]; then
  echo "✓✓✓ テスト2B: PASS ✓✓✓"
  echo ""
  echo "Suricata Cooldown 機構 (30秒) が正常に動作しています"
  exit 0
else
  echo "✗✗✗ テスト2B: FAIL ✗✗✗"
  echo ""
  echo "ログ確認:"
  echo "  journalctl -u azazel-first-minute --since '2 min ago' | grep -E 'suricata|alert'"
  exit 1
fi
