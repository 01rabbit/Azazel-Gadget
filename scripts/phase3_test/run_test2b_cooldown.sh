#!/bin/bash
# テスト2B: Suricata Cooldown機構検証スクリプト
# 使用方法: ./scripts/phase3_test/run_test2b_cooldown.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "================================================"
echo "  テスト2B: Suricata Cooldown機構検証"
echo "================================================"
echo ""

# 初期状態確認
echo "[前提確認] CONTAIN状態であることを確認..."
CURRENT_STATE=$(curl -s http://10.55.0.10:8081/ | jq -r '.state')
CURRENT_SUSP=$(curl -s http://10.55.0.10:8081/ | jq '.suspicion')

if [ "$CURRENT_STATE" != "CONTAIN" ]; then
  echo "ERROR: CONTAIN状態ではありません (現在: $CURRENT_STATE)"
  echo "先にテスト2Aを実施してください:"
  echo "  ./scripts/phase3_test/run_test2_suricata.sh"
  exit 1
fi

echo "  ✓ CONTAIN状態確認 (suspicion: $CURRENT_SUSP)"
echo ""

# アラート1回目（5秒後）
echo "[1/3] アラート1回目注入 (T=5秒後)..."
sleep 5
"$SCRIPT_DIR/inject_suricata_alert.sh" 1 "Second Attack - Cooldown Test" > /dev/null 2>&1
SUSP_AFTER_5=$(curl -s http://10.55.0.10:8081/ | jq '.suspicion')
echo "  suspicion (T=5秒): $SUSP_AFTER_5"
echo ""

# suspicion変化確認
echo "[2/3] Cooldown動作確認 (T=5秒)..."
if (( $(echo "$SUSP_AFTER_5 == $CURRENT_SUSP" | bc -l) )); then
  echo "  ✓ suspicion 変化なし (cooldown機構動作中)"
  COOLDOWN_5_PASS=true
else
  echo "  ✗ suspicion が変化しました ($CURRENT_SUSP → $SUSP_AFTER_5)"
  echo "    期待: cooldown期間中は加算されない"
  COOLDOWN_5_PASS=false
fi
echo ""

# 30秒待機
echo "[3/3] Cooldown期限待機 (30秒経過まで待機)..."
echo "  待機中... (25秒)"
sleep 25

# アラート2回目（T=30秒後）
echo "  アラート2回目注入 (T=30秒後)..."
SUSP_BEFORE_30=$(curl -s http://10.55.0.10:8081/ | jq '.suspicion')
"$SCRIPT_DIR/inject_suricata_alert.sh" 1 "Third Attack - After Cooldown" > /dev/null 2>&1
sleep 2
SUSP_AFTER_30=$(curl -s http://10.55.0.10:8081/ | jq '.suspicion')
echo "  suspicion (T=30秒前): $SUSP_BEFORE_30"
echo "  suspicion (T=30秒後): $SUSP_AFTER_30"
echo ""

# 変化確認
echo "Cooldown期限後の動作確認..."
EXPECTED_INCREASE=15
ACTUAL_INCREASE=$(echo "$SUSP_AFTER_30 - $SUSP_BEFORE_30" | bc -l)

if (( $(echo "$ACTUAL_INCREASE >= $EXPECTED_INCREASE - 5 && $ACTUAL_INCREASE <= $EXPECTED_INCREASE + 5" | bc -l) )); then
  echo "  ✓ suspicion が増加しました (+${ACTUAL_INCREASE}, 期待: ±${EXPECTED_INCREASE})"
  COOLDOWN_30_PASS=true
else
  echo "  ✗ suspicion の増加が期待値と異なります (+${ACTUAL_INCREASE}, 期待: ±${EXPECTED_INCREASE})"
  COOLDOWN_30_PASS=false
fi
echo ""

# 判定
echo "================================================"
echo "  テスト結果"
echo "================================================"

PASS=true

echo "Cooldown期間中 (T=5秒):"
if [ "$COOLDOWN_5_PASS" = true ]; then
  echo "  ✓ 重複カウント防止が動作"
else
  echo "  ✗ 重複カウント防止が失敗"
  PASS=false
fi

echo ""
echo "Cooldown期限後 (T=30秒):"
if [ "$COOLDOWN_30_PASS" = true ]; then
  echo "  ✓ 新規アラートが正常にカウント"
else
  echo "  ✗ 新規アラートのカウントが失敗"
  PASS=false
fi

echo ""
if [ "$PASS" = true ]; then
  echo "✓✓✓ テスト2B: PASS ✓✓✓"
  echo ""
  echo "Cooldown機構 (30秒) が正常に動作しています"
  exit 0
else
  echo "✗✗✗ テスト2B: FAIL ✗✗✗"
  echo ""
  echo "ログ確認:"
  echo "  journalctl -u azazel-first-minute --since '2 min ago' | grep -E 'suricata|cooldown'"
  exit 1
fi
