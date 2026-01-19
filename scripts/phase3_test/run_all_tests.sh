#!/bin/bash
# Phase 3 テスト全体実行スクリプト
# 使用方法: ./scripts/phase3_test/run_all_tests.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULT_FILE="/tmp/phase3_test_results.txt"

echo "================================================"
echo "  Phase 3 全テスト実行"
echo "================================================"
echo ""
echo "実行するテスト:"
echo "  1. 環境セットアップ"
echo "  2. ツール確認"
echo "  3. テスト2A: Suricata→CONTAIN遷移"
echo "  4. テスト3: CONTAIN復帰タイムライン"
echo "  5. テスト2B: Cooldown機構検証"
echo ""
echo "注意:"
echo "  - テスト1 (不審AP検知) は手動で実施してください"
echo "  - 全テスト完了まで約5-10分かかります"
echo ""
read -p "テストを開始しますか? [y/N]: " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
  echo "キャンセルしました"
  exit 0
fi

# 結果ログ初期化
echo "Phase 3 テスト結果" > "$RESULT_FILE"
echo "実行日時: $(date '+%Y-%m-%d %H:%M:%S')" >> "$RESULT_FILE"
echo "========================================" >> "$RESULT_FILE"
echo "" >> "$RESULT_FILE"

TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

run_test() {
  local test_name="$1"
  local test_script="$2"
  
  echo ""
  echo "================================================"
  echo "  実行中: $test_name"
  echo "================================================"
  
  ((TOTAL_TESTS++))
  
  if bash "$test_script"; then
    echo "✓ $test_name: PASS" >> "$RESULT_FILE"
    ((PASSED_TESTS++))
    return 0
  else
    echo "✗ $test_name: FAIL" >> "$RESULT_FILE"
    ((FAILED_TESTS++))
    return 1
  fi
}

# 環境セットアップ
echo ""
echo "Step 1: 環境セットアップ"
bash "$SCRIPT_DIR/setup_env.sh" || {
  echo "ERROR: 環境セットアップに失敗しました"
  exit 1
}

# ツール確認
echo ""
echo "Step 2: ツール確認"
bash "$SCRIPT_DIR/check_tools.sh" || {
  echo "ERROR: ツール確認に失敗しました"
  exit 1
}

# テスト2A: Suricata→CONTAIN
run_test "テスト2A: Suricata→CONTAIN遷移" "$SCRIPT_DIR/run_test2_suricata.sh"
TEST2A_RESULT=$?

if [ $TEST2A_RESULT -eq 0 ]; then
  # テスト3: CONTAIN復帰タイムライン
  echo ""
  echo "================================================"
  echo "  テスト3: CONTAIN復帰タイムライン測定"
  echo "================================================"
  echo ""
  echo "自動測定を開始します (70秒)..."
  echo "y" | bash "$SCRIPT_DIR/measure_contain_recovery.sh"
  echo "✓ テスト3: CONTAIN復帰タイムライン測定完了" >> "$RESULT_FILE"
  ((TOTAL_TESTS++))
  ((PASSED_TESTS++))
  
  # テスト2B: Cooldown (CONTAIN状態が必要)
  echo ""
  echo "CONTAIN状態への復帰を待機..."
  echo "テスト2Aを再度実行してCONTAIN状態にします..."
  bash "$SCRIPT_DIR/run_test2_suricata.sh" > /dev/null 2>&1
  
  run_test "テスト2B: Cooldown機構検証" "$SCRIPT_DIR/run_test2b_cooldown.sh"
else
  echo ""
  echo "テスト2Aが失敗したため、テスト3とテスト2Bはスキップします"
  echo "✗ テスト3: スキップ (テスト2A失敗)" >> "$RESULT_FILE"
  echo "✗ テスト2B: スキップ (テスト2A失敗)" >> "$RESULT_FILE"
fi

# 結果サマリー
echo "" >> "$RESULT_FILE"
echo "========================================" >> "$RESULT_FILE"
echo "テスト結果サマリー:" >> "$RESULT_FILE"
echo "  総テスト数: $TOTAL_TESTS" >> "$RESULT_FILE"
echo "  PASS: $PASSED_TESTS" >> "$RESULT_FILE"
echo "  FAIL: $FAILED_TESTS" >> "$RESULT_FILE"
echo "" >> "$RESULT_FILE"

if [ $FAILED_TESTS -eq 0 ]; then
  echo "判定: GO (全テストPASS)" >> "$RESULT_FILE"
else
  echo "判定: NO-GO (${FAILED_TESTS}件のテストが失敗)" >> "$RESULT_FILE"
fi

echo ""
echo "================================================"
echo "  全テスト完了"
echo "================================================"
echo ""
cat "$RESULT_FILE"
echo ""
echo "詳細結果: $RESULT_FILE"
echo "CONTAIN復帰ログ: /tmp/contain_recovery.log"
echo ""

if [ $FAILED_TESTS -eq 0 ]; then
  echo "✓✓✓ 全テスト PASS ✓✓✓"
  exit 0
else
  echo "✗✗✗ ${FAILED_TESTS}件のテストが失敗 ✗✗✗"
  exit 1
fi
