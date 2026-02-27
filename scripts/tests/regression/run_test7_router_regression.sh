#!/bin/bash
# テスト7: ルータ疎通回帰テスト（FORWARD/NAT + stage mark 経路）
# 使用方法:
#   ./scripts/tests/regression/run_test7_router_regression.sh
#   ./scripts/tests/regression/run_test7_router_regression.sh --non-interactive

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

CFG_CANDIDATES=(
  "/etc/azazel-gadget/first_minute.yaml"
  "/etc/azazel-zero/first_minute.yaml"
  "$PROJECT_ROOT/configs/first_minute.yaml"
)

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASS_COUNT=0
FAIL_COUNT=0
WARN_COUNT=0

INTERACTIVE=1
if [ "${1:-}" = "--non-interactive" ]; then
  INTERACTIVE=0
fi

pass() {
  echo -e "${GREEN}✓${NC} $1"
  PASS_COUNT=$((PASS_COUNT + 1))
}

fail() {
  echo -e "${RED}✗${NC} $1"
  FAIL_COUNT=$((FAIL_COUNT + 1))
}

warn() {
  echo -e "${YELLOW}⚠${NC} $1"
  WARN_COUNT=$((WARN_COUNT + 1))
}

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    fail "必要コマンド不足: $1"
    return 1
  fi
  return 0
}

pick_cfg() {
  local p
  for p in "${CFG_CANDIDATES[@]}"; do
    if [ -f "$p" ]; then
      echo "$p"
      return 0
    fi
  done
  return 1
}

yaml_value() {
  local key="$1"
  local file="$2"
  local raw val
  raw="$(grep -E "^[[:space:]]*${key}:[[:space:]]*" "$file" | head -1)"
  val="${raw#*:}"
  val="${val%%#*}"
  echo "$val" | sed -E 's/^[[:space:]]+|[[:space:]]+$//g'
}

sudo_n() {
  sudo -n "$@"
}

get_forward_pkts() {
  local down_if="$1"
  local subnet="$2"
  sudo_n iptables -x -v -n -L FORWARD 2>/dev/null | \
    awk -v down="$down_if" -v subnet_cidr="$subnet" '$3=="ACCEPT" && $6==down && $7 ~ /^!/ && $8==subnet_cidr {print $1; exit}'
}

get_nat_pkts() {
  local down_if="$1"
  local subnet="$2"
  sudo_n iptables -t nat -x -v -n -L POSTROUTING 2>/dev/null | \
    awk -v down="$down_if" -v subnet_cidr="$subnet" '$3=="MASQUERADE" && $7 ~ /^!/ && $8==subnet_cidr {print $1; exit}'
}

get_stage_normal_pkts() {
  sudo_n nft list chain inet azazel_fmc stage_normal 2>/dev/null | \
    awk '/counter packets/ {for (i=1; i<=NF; i++) if ($i=="packets") {print $(i+1); exit}}'
}

echo "================================================"
echo "  テスト7: ルータ疎通回帰テスト"
echo "================================================"
echo ""

cd "$PROJECT_ROOT" || exit 1

need_cmd sudo || exit 1
need_cmd nft || exit 1
need_cmd iptables || exit 1
need_cmd curl || exit 1
need_cmd jq || exit 1
need_cmd ping || exit 1
need_cmd rg || exit 1

if ! sudo -n true >/dev/null 2>&1; then
  echo "sudo -n が使えません。先に sudo 権限を有効化してください。"
  exit 1
fi

CFG_PATH="$(pick_cfg)"
if [ -z "${CFG_PATH:-}" ]; then
  fail "first_minute.yaml が見つかりません"
  exit 1
fi
pass "設定ファイル検出: $CFG_PATH"

DOWN_IF="$(yaml_value downstream "$CFG_PATH")"
MGMT_SUBNET="$(yaml_value mgmt_subnet "$CFG_PATH")"
MGMT_IP="$(yaml_value mgmt_ip "$CFG_PATH")"

[ -n "$DOWN_IF" ] || DOWN_IF="usb0"
[ -n "$MGMT_SUBNET" ] || MGMT_SUBNET="10.55.0.0/24"
[ -n "$MGMT_IP" ] || MGMT_IP="10.55.0.10"

API_URL="http://${MGMT_IP}:8082/"

if sudo_n systemctl is-active azazel-first-minute.service >/dev/null 2>&1; then
  pass "azazel-first-minute.service: active"
else
  fail "azazel-first-minute.service が inactive"
fi

API_RESP="$(curl -s --max-time 3 "$API_URL" 2>/dev/null || true)"
if [ -n "$API_RESP" ] && echo "$API_RESP" | jq . >/dev/null 2>&1; then
  STAGE="$(echo "$API_RESP" | jq -r '.stage // "unknown"')"
  UP_IF="$(echo "$API_RESP" | jq -r '.upstream_if // "unknown"')"
  pass "Status API応答: stage=$STAGE upstream_if=$UP_IF"
else
  fail "Status API応答失敗: $API_URL"
fi

if rg -n "meta mark set" nftables/first_minute.nft >/dev/null 2>&1; then
  pass "テンプレート: stage_switch が meta mark set"
else
  fail "テンプレート: stage_switch が meta mark set になっていない"
fi

if rg -n "ct mark vmap" nftables/first_minute.nft >/dev/null 2>&1; then
  fail "テンプレート: forward に ct mark vmap が残っています"
else
  pass "テンプレート: forward は ct mark vmap 非依存"
fi

if rg -n 'stage_switch.*meta", "mark", "set"' py/azazel_gadget/first_minute/nft.py >/dev/null 2>&1; then
  pass "実装: set_stage() は meta mark set を使用"
else
  fail "実装: set_stage() が meta mark set を使用していません"
fi

STAGE_SWITCH_CHAIN="$(sudo_n nft list chain inet azazel_fmc stage_switch 2>/dev/null || true)"
FORWARD_CHAIN="$(sudo_n nft list chain inet azazel_fmc forward 2>/dev/null || true)"

if echo "$STAGE_SWITCH_CHAIN" | grep -q "meta mark set"; then
  pass "実行時ルール: stage_switch=meta mark set"
else
  fail "実行時ルール: stage_switch が meta mark set ではない"
fi

SET_POS="$(echo "$FORWARD_CHAIN" | nl -ba | grep -E "meta mark set meta mark map" | awk '{print $1}' | head -1)"
VMAP_POS="$(echo "$FORWARD_CHAIN" | nl -ba | grep -E "meta mark vmap" | awk '{print $1}' | head -1)"
if [ -n "$SET_POS" ] && [ -n "$VMAP_POS" ] && [ "$SET_POS" -lt "$VMAP_POS" ]; then
  pass "実行時ルール: mark初期化がvmapより前（順序正常）"
else
  fail "実行時ルール: forward の mark 初期化順序が不正"
fi

if ping -c 1 -W 2 1.1.1.1 >/dev/null 2>&1; then
  pass "Pi自身の上流疎通(1.1.1.1): OK"
else
  fail "Pi自身の上流疎通(1.1.1.1): NG"
fi

if curl -sI --max-time 5 https://example.com >/dev/null 2>&1; then
  pass "Pi自身のHTTPS到達: OK"
else
  fail "Pi自身のHTTPS到達: NG"
fi

FWD_BEFORE="$(get_forward_pkts "$DOWN_IF" "$MGMT_SUBNET")"
NAT_BEFORE="$(get_nat_pkts "$DOWN_IF" "$MGMT_SUBNET")"
STAGE_BEFORE="$(get_stage_normal_pkts)"

[ -n "$FWD_BEFORE" ] || FWD_BEFORE=0
[ -n "$NAT_BEFORE" ] || NAT_BEFORE=0
[ -n "$STAGE_BEFORE" ] || STAGE_BEFORE=0

echo ""
echo "現在カウンタ:"
echo "  FORWARD(usb->up): $FWD_BEFORE"
echo "  NAT(MASQUERADE): $NAT_BEFORE"
echo "  stage_normal:    $STAGE_BEFORE"

if [ "$INTERACTIVE" -eq 1 ] && [ -t 0 ]; then
  echo ""
  echo "クライアント側で次を実行してから Enter を押してください:"
  echo "  ping -c 3 1.1.1.1"
  echo "  curl -I --max-time 8 https://example.com"
  read -r -p "Enterで計測を続行 > " _
  sleep 1
else
  warn "non-interactive モード: カウンタ差分確認は既存トラフィック依存です"
  sleep 2
fi

FWD_AFTER="$(get_forward_pkts "$DOWN_IF" "$MGMT_SUBNET")"
NAT_AFTER="$(get_nat_pkts "$DOWN_IF" "$MGMT_SUBNET")"
STAGE_AFTER="$(get_stage_normal_pkts)"

[ -n "$FWD_AFTER" ] || FWD_AFTER=0
[ -n "$NAT_AFTER" ] || NAT_AFTER=0
[ -n "$STAGE_AFTER" ] || STAGE_AFTER=0

FWD_DELTA=$((FWD_AFTER - FWD_BEFORE))
NAT_DELTA=$((NAT_AFTER - NAT_BEFORE))
STAGE_DELTA=$((STAGE_AFTER - STAGE_BEFORE))

echo ""
echo "差分カウンタ:"
echo "  FORWARD(usb->up): ${FWD_BEFORE} -> ${FWD_AFTER} (delta=${FWD_DELTA})"
echo "  NAT(MASQUERADE): ${NAT_BEFORE} -> ${NAT_AFTER} (delta=${NAT_DELTA})"
echo "  stage_normal:    ${STAGE_BEFORE} -> ${STAGE_AFTER} (delta=${STAGE_DELTA})"

if [ "$FWD_DELTA" -gt 0 ]; then
  pass "FORWARDカウンタ増分を確認"
else
  if [ "$INTERACTIVE" -eq 1 ]; then
    fail "FORWARDカウンタ増分なし（クライアント転送が観測できません）"
  else
    warn "FORWARDカウンタ増分なし（non-interactiveのため警告扱い）"
  fi
fi

if [ "$NAT_DELTA" -gt 0 ]; then
  pass "NAT(MASQUERADE)カウンタ増分を確認"
else
  if [ "$INTERACTIVE" -eq 1 ]; then
    fail "NAT(MASQUERADE)カウンタ増分なし"
  else
    warn "NAT(MASQUERADE)カウンタ増分なし（non-interactiveのため警告扱い）"
  fi
fi

if [ "$STAGE_DELTA" -gt 0 ]; then
  pass "stage_normalカウンタ増分を確認"
else
  warn "stage_normalカウンタ増分なし（ステージ遷移またはトラフィック種別要確認）"
fi

echo ""
echo "================================================"
echo "  テスト7 結果"
echo "================================================"
echo "  PASS: $PASS_COUNT"
echo "  WARN: $WARN_COUNT"
echo "  FAIL: $FAIL_COUNT"
echo ""

if [ "$FAIL_COUNT" -eq 0 ]; then
  echo -e "${GREEN}✓✓✓ テスト7: PASS ✓✓✓${NC}"
  exit 0
else
  echo -e "${RED}✗✗✗ テスト7: FAIL ✗✗✗${NC}"
  exit 1
fi
