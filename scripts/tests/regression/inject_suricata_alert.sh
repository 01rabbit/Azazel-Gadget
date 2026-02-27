#!/bin/bash
# Suricataアラート注入ヘルパースクリプト
# 使用方法: ./scripts/tests/regression/inject_suricata_alert.sh [severity] [message]

EVE_JSON="/var/log/suricata/eve.json"
SEVERITY=${1:-1}  # デフォルト: 1 (Critical)
MESSAGE=${2:-"Test Attack - Regression"}

echo "================================================"
echo "  Suricata アラート注入"
echo "================================================"
echo ""
echo "注入先: $EVE_JSON"
echo "Severity: $SEVERITY (1=Critical, 2=Major, 3=Minor)"
echo "Message: $MESSAGE"
echo ""

# eve.json 存在確認
if [ ! -f "$EVE_JSON" ]; then
  echo "ERROR: $EVE_JSON が存在しません"
  echo "作成コマンド: sudo touch $EVE_JSON && sudo chmod 666 $EVE_JSON"
  exit 1
fi

# 書き込み権限確認
if [ ! -w "$EVE_JSON" ]; then
  echo "ERROR: $EVE_JSON への書き込み権限がありません"
  echo "権限設定: sudo chmod 666 $EVE_JSON"
  exit 1
fi

# タイムスタンプ生成
TIMESTAMP=$(date -u '+%Y-%m-%dT%H:%M:%S+00:00')

# JSON生成
ALERT_JSON=$(cat <<EOF
{
  "timestamp": "$TIMESTAMP",
  "event_type": "alert",
  "src_ip": "192.168.1.100",
  "dest_ip": "10.55.0.1",
  "proto": "TCP",
  "alert": {
    "action": "allowed",
    "gid": 1,
    "signature_id": 2000001,
    "rev": 1,
    "signature": "$MESSAGE",
    "category": "Attempted Administrator Privilege Gain",
    "severity": $SEVERITY
  },
  "flow": {
    "pkts_toserver": 1,
    "pkts_toclient": 0,
    "bytes_toserver": 60,
    "bytes_toclient": 0
  }
}
EOF
)

# アラート注入
echo "$ALERT_JSON" >> "$EVE_JSON"

if [ $? -eq 0 ]; then
  echo "✓ アラート注入成功"
  echo ""
  echo "注入されたアラート:"
  echo "$ALERT_JSON" | jq '.'
  echo ""
  echo "確認コマンド:"
  echo "  tail -1 $EVE_JSON | jq '.'"
  echo "  journalctl -u azazel-first-minute -f | grep -E 'suspicion|CONTAIN'"
  echo ""
  echo "API状態確認:"
  echo "  curl -s http://10.55.0.10:8081/ | jq '.state, .suspicion'"
else
  echo "✗ ERROR: アラート注入失敗"
  exit 1
fi
