#!/bin/bash
# CONTAIN状態復帰タイムライン測定スクリプト
# 使用方法: ./scripts/tests/regression/measure_contain_recovery.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_FILE="/tmp/contain_recovery.log"
API_URL="http://10.55.0.10:8081/"

echo "================================================"
echo "  CONTAIN復帰タイムライン測定"
echo "================================================"
echo ""
echo "出力ファイル: $OUTPUT_FILE"
echo "測定間隔: 5秒ごと (0-70秒)"
echo ""
echo "測定開始前に以下を確認してください:"
echo "  1. システムが CONTAIN 状態であること"
echo "  2. suspicion が 50 以上であること"
echo ""
read -p "測定を開始しますか? [y/N]: " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
  echo "キャンセルしました"
  exit 0
fi

echo ""
echo "測定開始..."
echo ""

# ログファイル初期化
echo "CONTAIN復帰タイムライン測定" > "$OUTPUT_FILE"
echo "開始時刻: $(date '+%Y-%m-%d %H:%M:%S')" >> "$OUTPUT_FILE"
echo "API URL: $API_URL" >> "$OUTPUT_FILE"
echo "----------------------------------------" >> "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"

START_TIME=$(date +%s)

# ヘッダー
printf "%-8s %-10s %-10s %-12s\n" "経過時間" "時刻" "State" "Suspicion" | tee -a "$OUTPUT_FILE"
printf "%-8s %-10s %-10s %-12s\n" "--------" "----------" "----------" "------------" | tee -a "$OUTPUT_FILE"

# 0-70秒まで5秒ごとに測定
for i in {0..70..5}; do
  ELAPSED=$i
  CURRENT_STATE=$(curl -s "$API_URL" | jq -r '.state' 2>/dev/null || echo "ERROR")
  SUSPICION=$(curl -s "$API_URL" | jq '.suspicion' 2>/dev/null || echo "ERROR")
  TIMESTAMP=$(date '+%H:%M:%S')
  
  # 画面とログファイルに出力
  printf "T=%-6s %-10s %-10s %-12s\n" "${ELAPSED}秒" "$TIMESTAMP" "$CURRENT_STATE" "$SUSPICION" | tee -a "$OUTPUT_FILE"
  
  # 最後のループ以外はスリープ
  if [ $i -lt 70 ]; then
    sleep 5
  fi
done

# 終了時刻を記録
echo "" >> "$OUTPUT_FILE"
echo "----------------------------------------" >> "$OUTPUT_FILE"
echo "終了時刻: $(date '+%Y-%m-%d %H:%M:%S')" >> "$OUTPUT_FILE"

END_TIME=$(date +%s)
TOTAL_TIME=$((END_TIME - START_TIME))

echo ""
echo "================================================"
echo "  測定完了"
echo "================================================"
echo ""
echo "総測定時間: ${TOTAL_TIME}秒"
echo "結果ファイル: $OUTPUT_FILE"
echo ""
echo "結果を確認:"
echo "  cat $OUTPUT_FILE"
echo ""
echo "グラフ化 (gnuplot がある場合):"
echo "  grep 'T=' $OUTPUT_FILE | awk '{print \$1, \$4}' | sed 's/T=//' | sed 's/秒//' > /tmp/suspicion_data.txt"
echo "  gnuplot -e 'set terminal dumb; plot \"/tmp/suspicion_data.txt\" with lines'"
echo ""
