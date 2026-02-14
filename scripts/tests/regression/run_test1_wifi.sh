#!/bin/bash
# テスト1: 不審AP検知テスト実行スクリプト
# 使用方法: ./scripts/tests/regression/run_test1_wifi.sh [SSID] [PASSWORD]

SSID=${1:-""}
PASSWORD=${2:-""}

echo "================================================"
echo "  テスト1: 不審AP検知テスト"
echo "================================================"
echo ""

if [ -z "$SSID" ]; then
  echo "使用方法: $0 [SSID] [PASSWORD]"
  echo ""
  echo "例:"
  echo "  $0 \"Known-Evil-SSID\" \"password123\""
  echo ""
  echo "既知の悪質SSIDを確認:"
  if [ -f configs/known_wifi.json ]; then
    echo ""
    cat configs/known_wifi.json | jq '.evil_ssid[]' | head -5
  else
    echo "  configs/known_wifi.json が見つかりません"
  fi
  echo ""
  exit 1
fi

echo "接続先SSID: $SSID"
echo ""

# 初期状態確認
echo "[1/5] 初期状態確認..."
INITIAL_STATE=$(curl -s http://10.55.0.10:8081/ | jq -r '.user_state')
INITIAL_RISK=$(curl -s http://10.55.0.10:8081/ | jq '.risk_score')
echo "  user_state: $INITIAL_STATE"
echo "  risk_score: $INITIAL_RISK"
echo ""

# Wi-Fi接続
echo "[2/5] Wi-Fi接続中..."
if [ -n "$PASSWORD" ]; then
  sudo nmcli dev wifi connect "$SSID" password "$PASSWORD" || {
    echo "ERROR: Wi-Fi接続に失敗しました"
    exit 1
  }
else
  sudo nmcli dev wifi connect "$SSID" || {
    echo "ERROR: Wi-Fi接続に失敗しました"
    exit 1
  }
fi
echo "  ✓ 接続成功"
echo ""

# 接続確認
echo "[3/5] 接続情報確認..."
iw dev wlan0 link | grep -E "SSID|signal"
echo ""

# 30秒待機
echo "[4/5] 状態変化を監視 (30秒)..."
for i in {1..6}; do
  sleep 5
  CURRENT_STATE=$(curl -s http://10.55.0.10:8081/ | jq -r '.user_state')
  CURRENT_RISK=$(curl -s http://10.55.0.10:8081/ | jq '.risk_score')
  echo "  T=${i}×5秒: user_state=$CURRENT_STATE, risk_score=$CURRENT_RISK"
done
echo ""

# 最終状態確認
echo "[5/5] 最終状態確認..."
FINAL_DATA=$(curl -s http://10.55.0.10:8081/)
FINAL_STATE=$(echo "$FINAL_DATA" | jq -r '.user_state')
FINAL_RISK=$(echo "$FINAL_DATA" | jq '.risk_score')
WIFI_TAGS=$(echo "$FINAL_DATA" | jq '.wifi_tags // []')

echo "  user_state: $INITIAL_STATE → $FINAL_STATE"
echo "  risk_score: $INITIAL_RISK → $FINAL_RISK"
echo "  wifi_tags: $WIFI_TAGS"
echo ""

# 判定
echo "================================================"
echo "  テスト結果"
echo "================================================"

PASS=true

if [ "$FINAL_STATE" != "SAFE" ] && [ "$FINAL_STATE" != "NORMAL" ]; then
  echo "✓ user_state が警告状態へ遷移 ($FINAL_STATE)"
else
  echo "✗ user_state が警告状態へ遷移していません ($FINAL_STATE)"
  PASS=false
fi

if (( $(echo "$FINAL_RISK > $INITIAL_RISK" | bc -l) )); then
  echo "✓ risk_score が増加 ($INITIAL_RISK → $FINAL_RISK)"
else
  echo "✗ risk_score が増加していません ($INITIAL_RISK → $FINAL_RISK)"
  PASS=false
fi

if [ "$WIFI_TAGS" != "[]" ]; then
  echo "✓ wifi_tags が記録されています"
else
  echo "✗ wifi_tags が記録されていません"
  PASS=false
fi

echo ""
if [ "$PASS" = true ]; then
  echo "✓✓✓ テスト1: PASS ✓✓✓"
  exit 0
else
  echo "✗✗✗ テスト1: FAIL ✗✗✗"
  echo ""
  echo "ログ確認:"
  echo "  journalctl -u azazel-first-minute -n 50 | grep -E 'wifi_tags|user_state'"
  exit 1
fi
