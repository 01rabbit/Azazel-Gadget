#!/bin/bash
# Phase 3 テスト環境セットアップスクリプト
# 使用方法: ./scripts/phase3_test/setup_env.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "================================================"
echo "  Phase 3 テスト環境セットアップ"
echo "================================================"
echo ""

cd "$PROJECT_ROOT"

# 1. 構文チェック
echo "[1/7] Python 構文チェック..."
python3 test_redesign_verification.py || {
  echo "ERROR: test_redesign_verification.py が失敗しました"
  exit 1
}
echo "  ✓ 構文チェック完了"

# 2. systemd サービス確認
echo "[2/7] systemd サービス確認..."
if sudo systemctl is-active azazel-first-minute.service > /dev/null 2>&1; then
  echo "  ✓ azazel-first-minute.service: active (running)"
else
  echo "  ✗ ERROR: azazel-first-minute.service が起動していません"
  echo "    起動コマンド: sudo systemctl start azazel-first-minute.service"
  exit 1
fi

# 3. Web API 疎通確認
echo "[3/7] Web API 疎通確認..."
if curl -s http://10.55.0.10:8081/ > /dev/null 2>&1; then
  CURRENT_STATE=$(curl -s http://10.55.0.10:8081/ | jq -r '.state')
  echo "  ✓ Web API 応答正常 (current state: $CURRENT_STATE)"
else
  echo "  ✗ ERROR: Web API に接続できません (http://10.55.0.10:8081/)"
  exit 1
fi

# 4. Suricata eve.json 準備
echo "[4/7] Suricata eve.json 準備..."
if [ ! -f /var/log/suricata/eve.json ]; then
  sudo mkdir -p /var/log/suricata
  sudo touch /var/log/suricata/eve.json
  echo "  ✓ eve.json 作成完了"
else
  echo "  ✓ eve.json 既に存在"
fi
sudo chmod 666 /var/log/suricata/eve.json
echo "  ✓ パーミッション設定完了 (666)"

# 5. 既知悪質AP設定確認
echo "[5/7] 既知悪質AP設定確認..."
if [ -f configs/known_wifi.json ]; then
  EVIL_COUNT=$(cat configs/known_wifi.json | jq '.evil_ssid | length' 2>/dev/null || echo "0")
  if [ "$EVIL_COUNT" -gt 0 ]; then
    echo "  ✓ 既知悪質SSID: $EVIL_COUNT 件登録済み"
  else
    echo "  ⚠ WARNING: known_wifi.json に悪質SSIDが登録されていません"
    echo "    テスト1 (不審AP検知) で問題が発生する可能性があります"
  fi
else
  echo "  ⚠ WARNING: configs/known_wifi.json が存在しません"
fi

# 6. EPD ドライバテスト
echo "[6/7] EPD ドライバテスト (dry-run)..."
sudo python3 py/azazel_epd.py --state normal --ssid "PhaseSetup" --ip "10.55.0.10" --signal -50 --dry-run > /dev/null 2>&1 || {
  echo "  ✗ ERROR: EPD ドライバテストが失敗しました"
  exit 1
}
if [ -f /tmp/azazel_epd_preview_normal_composite.png ]; then
  echo "  ✓ EPD プレビュー生成成功"
else
  echo "  ✗ ERROR: EPD プレビューファイルが生成されませんでした"
  exit 1
fi

# 7. 実装パラメータ・スナップショット取得 (v3.0 要件)
echo "[7/9] 実装パラメータ・スナップショット取得..."
mkdir -p /tmp/phase3_artifacts

# Git コミット情報
git rev-parse --abbrev-ref HEAD > /tmp/phase3_artifacts/git_branch.txt 2>/dev/null || echo "unknown" > /tmp/phase3_artifacts/git_branch.txt
git rev-parse HEAD > /tmp/phase3_artifacts/git_commit.txt 2>/dev/null || echo "unknown" > /tmp/phase3_artifacts/git_commit.txt
echo "  ✓ Git コミット: $(cat /tmp/phase3_artifacts/git_commit.txt | cut -c1-8)"

# 設定ファイルコピー
if [ -f configs/first_minute.yaml ]; then
  cp -a configs/first_minute.yaml /tmp/phase3_artifacts/first_minute.yaml
  echo "  ✓ first_minute.yaml スナップショット保存"
  
  # 主要パラメータ抽出
  echo "  主要パラメータ:"
  grep -E "contain_threshold|contain_min_duration|decay_per_sec|suricata_cooldown" configs/first_minute.yaml | sed 's/^/    /' || true
else
  echo "  ⚠ WARNING: configs/first_minute.yaml が見つかりません"
fi

# API ベースライン
curl -s http://10.55.0.10:8081/ | jq '.' > /tmp/phase3_artifacts/api_baseline.json 2>/dev/null
echo "  ✓ API ベースライン保存"

# Journal ベースライン
journalctl -u azazel-first-minute -n 80 --no-pager > /tmp/phase3_artifacts/journal_baseline.log 2>/dev/null
echo "  ✓ Journal ベースライン保存"

echo "  ✓ スナップショット保存先: /tmp/phase3_artifacts/"

# 8. ログ初期化
echo "[8/9] ログ初期化..."
echo "  - journalctl 古いログを削除中..."
sudo journalctl --vacuum-time=1d > /dev/null 2>&1
echo "  - eve.json をクリア中..."
sudo sh -c 'echo "" > /var/log/suricata/eve.json'
echo "  ✓ ログ初期化完了"

# 9. テスト開始時刻記録
echo "[9/9] テスト開始時刻記録..."
date '+%Y-%m-%d %H:%M:%S' > /tmp/phase3_artifacts/test_start_time.txt
echo "  ✓ 開始時刻: $(cat /tmp/phase3_artifacts/test_start_time.txt)"

echo ""
echo "================================================"
echo "  ✓ セットアップ完了 - テスト実施準備完了"
echo "================================================"
echo ""
echo "📁 スナップショット保存先:"
echo "   /tmp/phase3_artifacts/"
ls -lh /tmp/phase3_artifacts/ | tail -n +2 | awk '{print "   - " $9 " (" $5 ")"}'
echo ""
echo "次のコマンドでテスト開始:"
echo "  cd $PROJECT_ROOT"
echo "  # ターミナル1: ログ監視"
echo "  journalctl -u azazel-first-minute -f | grep -E 'state|suspicion|wifi_tags'"
echo ""
echo "  # ターミナル2: API監視"
echo "  watch -n 2 'curl -s http://10.55.0.10:8081/ | jq \".state, .suspicion\"'"
echo ""
echo "  # ターミナル3: テスト実行"
echo "  ./scripts/phase3_test/run_test1_wifi.sh  # 不審AP検知テスト"
echo ""
