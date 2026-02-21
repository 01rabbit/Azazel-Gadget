#!/bin/bash
# 回帰テストツール確認スクリプト
# 使用方法: ./scripts/tests/regression/check_tools.sh

echo "================================================"
echo "  回帰テストツール確認"
echo "================================================"
echo ""

# カラーコード
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

check_cmd() {
  if command -v $1 &> /dev/null; then
    VERSION=$($1 --version 2>&1 | head -1 || echo "")
    echo -e "${GREEN}✓${NC} $1 ${VERSION}"
    return 0
  else
    echo -e "${RED}✗${NC} $1 (未インストール)"
    return 1
  fi
}

check_python_pkg() {
  if pip3 show $1 &> /dev/null; then
    VERSION=$(pip3 show $1 | grep Version | awk '{print $2}')
    echo -e "${GREEN}✓${NC} $1 (v$VERSION)"
    return 0
  else
    echo -e "${RED}✗${NC} $1 (未インストール)"
    return 1
  fi
}

check_file() {
  if [ -f "$1" ]; then
    echo -e "${GREEN}✓${NC} $1"
    return 0
  else
    echo -e "${RED}✗${NC} $1 (存在しません)"
    return 1
  fi
}

check_service() {
  if sudo systemctl is-active $1 > /dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} $1 (active)"
    return 0
  else
    echo -e "${YELLOW}⚠${NC} $1 (inactive)"
    return 1
  fi
}

FAIL_COUNT=0

# 1. システムコマンド確認
echo "=== システムコマンド ==="
check_cmd python3 || ((FAIL_COUNT++))
check_cmd jq || ((FAIL_COUNT++))
check_cmd curl || ((FAIL_COUNT++))
check_cmd iw || ((FAIL_COUNT++))
check_cmd ip || ((FAIL_COUNT++))
check_cmd nmcli || ((FAIL_COUNT++))
check_cmd nft || ((FAIL_COUNT++))
check_cmd journalctl || ((FAIL_COUNT++))
check_cmd watch || ((FAIL_COUNT++))

echo ""
echo "=== Python パッケージ ==="
check_python_pkg pillow || ((FAIL_COUNT++))
check_python_pkg waveshare-epd || {
  echo -e "${YELLOW}  ℹ${NC} EPD ハードウェアがない環境では不要な場合があります"
  ((FAIL_COUNT++))
}

echo ""
echo "=== テストスクリプト ==="
check_file "test_redesign_verification.py" || ((FAIL_COUNT++))
check_file "azazel_test.py" || ((FAIL_COUNT++))
check_file "py/azazel_epd.py" || ((FAIL_COUNT++))
check_file "py/azazel_gadget/cli_unified.py" || ((FAIL_COUNT++))
check_file "scripts/tests/regression/run_test7_router_regression.sh" || ((FAIL_COUNT++))

echo ""
echo "=== 設定ファイル ==="
check_file "configs/first_minute.yaml" || ((FAIL_COUNT++))
check_file "configs/known_wifi.json" || ((FAIL_COUNT++))
check_file "nftables/first_minute.nft" || ((FAIL_COUNT++))

echo ""
echo "=== システムサービス ==="
check_service "azazel-first-minute.service" || {
  echo -e "${YELLOW}  ℹ${NC} 起動コマンド: sudo systemctl start azazel-first-minute.service"
  ((FAIL_COUNT++))
}

echo ""
echo "=== ネットワーク疎通確認 ==="
if curl -s http://10.55.0.10:8081/ > /dev/null 2>&1; then
  STATE=$(curl -s http://10.55.0.10:8081/ | jq -r '.state' 2>/dev/null || echo "UNKNOWN")
  echo -e "${GREEN}✓${NC} Web API (http://10.55.0.10:8081/) - State: $STATE"
else
  echo -e "${RED}✗${NC} Web API (http://10.55.0.10:8081/) - 接続失敗"
  ((FAIL_COUNT++))
fi

echo ""
echo "=== Suricata eve.json ==="
if [ -f /var/log/suricata/eve.json ]; then
  if [ -w /var/log/suricata/eve.json ]; then
    echo -e "${GREEN}✓${NC} /var/log/suricata/eve.json (読み書き可能)"
  else
    echo -e "${YELLOW}⚠${NC} /var/log/suricata/eve.json (書き込み権限なし)"
    echo -e "${YELLOW}  ℹ${NC} 修正: sudo chmod 666 /var/log/suricata/eve.json"
    ((FAIL_COUNT++))
  fi
else
  echo -e "${YELLOW}⚠${NC} /var/log/suricata/eve.json (ファイルなし)"
  echo -e "${YELLOW}  ℹ${NC} 作成: sudo touch /var/log/suricata/eve.json && sudo chmod 666 /var/log/suricata/eve.json"
fi

echo ""
echo "================================================"
if [ $FAIL_COUNT -eq 0 ]; then
  echo -e "${GREEN}✓ すべてのツール/設定が正常です${NC}"
  echo ""
  echo "テスト実施可能です。次のコマンドでセットアップ:"
  echo "  ./scripts/tests/regression/setup_env.sh"
  exit 0
else
  echo -e "${RED}✗ $FAIL_COUNT 件の問題が見つかりました${NC}"
  echo ""
  echo "上記の問題を修正してから再度実行してください"
  exit 1
fi
