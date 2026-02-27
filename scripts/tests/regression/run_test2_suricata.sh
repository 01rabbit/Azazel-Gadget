#!/bin/bash
# テスト2: Suricata→CONTAIN遷移テスト実行スクリプト
# 使用方法: ./scripts/tests/regression/run_test2_suricata.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# API ホスト・ポート設定ファイルから取得
API_HOST=$(grep -A 2 "status_api:" "$PROJECT_ROOT/configs/first_minute.yaml" | grep "host:" | awk '{print $NF}' || echo "10.55.0.10")
API_PORT=$(grep -A 2 "status_api:" "$PROJECT_ROOT/configs/first_minute.yaml" | grep "port:" | awk '{print $NF}' || echo "8082")
API_URL="http://${API_HOST}:${API_PORT}/"

echo "================================================"
echo "  テスト2: Suricata→CONTAIN遷移テスト"
echo "================================================"
echo ""

# 初期状態確認
echo "[1/4] 初期状態確認..."
INITIAL_STATE=$(curl -s "$API_URL" | jq -r '.state')
INITIAL_SUSP=$(curl -s "$API_URL" | jq '.suspicion')
echo "  state: $INITIAL_STATE"
echo "  suspicion: $INITIAL_SUSP"
echo ""

if [ "$INITIAL_STATE" = "CONTAIN" ]; then
  echo "ERROR: 既に CONTAIN 状態です。テストを実施できません"
  echo "復帰を待つか、サービスを再起動してください:"
  echo "  sudo systemctl restart azazel-first-minute.service"
  exit 1
fi

# Suricataアラート注入
echo "[2/4] Suricataアラート注入..."
"$SCRIPT_DIR/inject_suricata_alert.sh" 1 "Critical Attack - Test Regression" || exit 1
echo ""

# 遷移監視（15秒）
echo "[3/4] CONTAIN遷移監視 (最大15秒)..."
CONTAIN_REACHED=false
for i in {1..15}; do
  sleep 1
  CURRENT_STATE=$(curl -s "$API_URL" | jq -r '.state')
  CURRENT_SUSP=$(curl -s "$API_URL" | jq '.suspicion')
  
  echo "  T=${i}秒: state=$CURRENT_STATE, suspicion=$CURRENT_SUSP"
  
  if [ "$CURRENT_STATE" = "CONTAIN" ]; then
    CONTAIN_REACHED=true
    CONTAIN_TIME=$i
    echo ""
    echo "  ✓ CONTAIN状態に到達 (${i}秒)"
    break
  fi
done
echo ""

# 最終状態確認
echo "[4/4] 最終状態確認..."
FINAL_STATE=$(curl -s "$API_URL" | jq -r '.state')
FINAL_SUSP=$(curl -s "$API_URL" | jq '.suspicion')
echo "  state: $INITIAL_STATE → $FINAL_STATE"
echo "  suspicion: $INITIAL_SUSP → $FINAL_SUSP"
echo ""

# 判定
echo "================================================"
echo "  テスト結果"
echo "================================================"

PASS=true

if [ "$CONTAIN_REACHED" = true ]; then
  echo "✓ CONTAIN状態に遷移しました (${CONTAIN_TIME}秒)"
  
  if [ $CONTAIN_TIME -le 15 ]; then
    echo "✓ 遷移時間が期待値以内 (${CONTAIN_TIME}秒 ≤ 15秒)"
  else
    echo "✗ 遷移時間が期待値を超過 (${CONTAIN_TIME}秒 > 15秒)"
    PASS=false
  fi
else
  echo "✗ 15秒以内にCONTAIN状態に遷移しませんでした"
  PASS=false
fi

# bc コマンドがない場合の簡易比較
if command -v bc &> /dev/null; then
  if (( $(echo "$FINAL_SUSP >= 50" | bc -l) )); then
    echo "✓ suspicion が50以上に達しました ($FINAL_SUSP)"
  else
    echo "✗ suspicion が50未満です ($FINAL_SUSP)"
    PASS=false
  fi
else
  # bc なしでの数値比較（整数のみ）
  FINAL_SUSP_INT=${FINAL_SUSP%.*}
  if [ "$FINAL_SUSP_INT" -ge 50 ]; then
    echo "✓ suspicion が50以上に達しました ($FINAL_SUSP)"
  else
    echo "✗ suspicion が50未満です ($FINAL_SUSP)"
    PASS=false
  fi
fi

echo ""
if [ "$PASS" = true ]; then
  echo "✓✓✓ テスト2A: PASS ✓✓✓"
  echo ""
  echo "次のステップ:"
  echo "  - テスト3 (CONTAIN復帰) を実施"
  echo "    ./scripts/tests/regression/measure_contain_recovery.sh"
  echo ""
  echo "  - テスト2B (Cooldown検証) を実施"
  echo "    ./scripts/tests/regression/run_test2b_cooldown.sh"
  exit 0
else
  echo "✗✗✗ テスト2A: FAIL ✗✗✗"
  echo ""
  echo "ログ確認:"
  echo "  journalctl -u azazel-first-minute -n 50 | grep -E 'suspicion|CONTAIN|suricata'"
  exit 1
fi
