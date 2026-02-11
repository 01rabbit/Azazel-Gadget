#!/bin/bash
################################################################################
# validate.sh - Azazel-Gadget Configuration Validator
# Profile YAML と実機状態を比較し、PASS/FAIL判定
# 
# 検証項目：
# - トポロジー（IF, IP）
# - NAT/Forward
# - 管理UI到達性（usb0: OK, wlan0: NG）
# - OpenCanary到達性（wlan0: OK, usb0: NG）
# - Suricata稼働とeve.json更新
# - TC（wlan0）
# - systemd services
################################################################################

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PROFILE_FILE=""
VERBOSE=false

usage() {
    cat <<EOF
Usage: $0 --profile <profile.yaml> [--verbose]

Options:
  --profile FILE    Profile YAML file to validate against
  --verbose         Show detailed validation steps
  --help            Show this help

Example:
  sudo $0 --profile installer/profiles/gadget_profile_20260209.yaml
EOF
    exit 1
}

# 引数パース
while [[ $# -gt 0 ]]; do
    case $1 in
        --profile)
            PROFILE_FILE="$2"
            shift 2
            ;;
        --verbose)
            VERBOSE=true
            shift
            ;;
        --help)
            usage
            ;;
        *)
            echo "Unknown option: $1"
            usage
            ;;
    esac
done

if [[ -z "$PROFILE_FILE" ]]; then
    echo "ERROR: --profile is required"
    usage
fi

if [[ ! -f "$PROFILE_FILE" ]]; then
    echo "ERROR: Profile file not found: $PROFILE_FILE"
    exit 1
fi

# root権限チェック
if [[ $EUID -ne 0 ]]; then
   echo "ERROR: このスクリプトはroot権限で実行する必要があります"
   exit 1
fi

# ログディレクトリ
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
LOG_DIR="$SCRIPT_DIR/logs/validate_$TIMESTAMP"
mkdir -p "$LOG_DIR"

# Profile JSON化
PROFILE_JSON="$LOG_DIR/profile.json"
python3 -c "import yaml, json; print(json.dumps(yaml.safe_load(open('$PROFILE_FILE'))))" > "$PROFILE_JSON"

# 検証結果
VALIDATION_RESULT="$LOG_DIR/validation_result.json"
CHECKS_PASSED=0
CHECKS_FAILED=0
CHECKS=()

log() {
    echo "$@"
    if [[ "$VERBOSE" == "true" ]]; then
        echo "$@" >> "$LOG_DIR/validate.log"
    fi
}

check() {
    local name="$1"
    local result="$2"
    local message="$3"
    
    if [[ "$result" == "PASS" ]]; then
        echo "  ✓ $name: PASS"
        CHECKS_PASSED=$((CHECKS_PASSED + 1))
    else
        echo "  ✗ $name: FAIL - $message"
        CHECKS_FAILED=$((CHECKS_FAILED + 1))
    fi
    
    CHECKS+=("{\"name\": \"$name\", \"result\": \"$result\", \"message\": \"$message\"}")
}

log "=== Azazel-Gadget Configuration Validator ==="
log "Profile: $PROFILE_FILE"
log "Timestamp: $TIMESTAMP"
log ""

# Profile値を抽出
INSIDE_IF=$(python3 -c "import json; print(json.load(open('$PROFILE_JSON'))['topology']['inside_if'])")
INSIDE_IP=$(python3 -c "import json; print(json.load(open('$PROFILE_JSON'))['topology']['inside_ip'])")
OUTSIDE_IF=$(python3 -c "import json; print(json.load(open('$PROFILE_JSON'))['topology']['outside_if'])")
NAT_ENABLED=$(python3 -c "import json; print(json.load(open('$PROFILE_JSON'))['network']['nat_enabled'])")
FW_BACKEND=$(python3 -c "import json; print(json.load(open('$PROFILE_JSON'))['network']['firewall_backend'])")
MGMT_UI_PORT=$(python3 -c "import json; print(json.load(open('$PROFILE_JSON'))['management_ui']['port'])")
SURICATA_ENABLED=$(python3 -c "import json; print(json.load(open('$PROFILE_JSON'))['suricata']['enabled'])")
OPENCANARY_ENABLED=$(python3 -c "import json; print(json.load(open('$PROFILE_JSON'))['opencanary']['enabled'])")

log "[1] Topology validation"
# INSIDE_IF存在確認
if ip link show "$INSIDE_IF" &>/dev/null; then
    # IPアドレス確認
    if ip addr show "$INSIDE_IF" | grep -q "$INSIDE_IP"; then
        check "inside_if_ip" "PASS" "$INSIDE_IF has $INSIDE_IP"
    else
        check "inside_if_ip" "FAIL" "$INSIDE_IF does not have $INSIDE_IP"
    fi
else
    check "inside_if_ip" "FAIL" "$INSIDE_IF does not exist"
fi

# OUTSIDE_IF存在確認
if ip link show "$OUTSIDE_IF" &>/dev/null; then
    check "outside_if" "PASS" "$OUTSIDE_IF exists"
else
    check "outside_if" "FAIL" "$OUTSIDE_IF does not exist"
fi

log ""
log "[2] Network configuration"

# IP forwarding
if sysctl net.ipv4.ip_forward | grep -q "= 1"; then
    check "ip_forward" "PASS" "IP forwarding enabled"
else
    check "ip_forward" "FAIL" "IP forwarding disabled"
fi

# Default route
if ip route | grep -q "^default.*dev $OUTSIDE_IF"; then
    check "default_route" "PASS" "Default route via $OUTSIDE_IF"
else
    check "default_route" "FAIL" "Default route not via $OUTSIDE_IF"
fi

log ""
log "[3] Firewall validation"

if [[ "$FW_BACKEND" == "nftables" ]]; then
    # nftables table存在確認
    if nft list table inet azazel_fmc &>/dev/null; then
        check "firewall_table" "PASS" "nftables table 'azazel_fmc' exists"
        
        # NAT rule確認
        if nft list table inet azazel_fmc | grep -q "masquerade"; then
            check "nat_masquerade" "PASS" "NAT masquerade rule found"
        else
            check "nat_masquerade" "FAIL" "NAT masquerade rule not found"
        fi
    else
        check "firewall_table" "FAIL" "nftables table 'azazel_fmc' not found"
    fi
else
    # iptables NAT確認
    if iptables -t nat -L | grep -q "MASQUERADE"; then
        check "nat_masquerade" "PASS" "iptables MASQUERADE rule found"
    else
        check "nat_masquerade" "FAIL" "iptables MASQUERADE rule not found"
    fi
fi

log ""
log "[4] Service validation"

# systemd services
for service in azazel-first-minute azazel-nat azazel-web; do
    if systemctl is-active --quiet "$service"; then
        check "service_$service" "PASS" "$service is active"
    else
        # profileで有効化されていない可能性もあるため、WARNING扱い
        check "service_$service" "WARN" "$service is not active (may be intentional)"
    fi
done

# Suricata
if [[ "$SURICATA_ENABLED" == "True" || "$SURICATA_ENABLED" == "true" ]]; then
    if systemctl is-active --quiet suricata; then
        check "suricata_active" "PASS" "Suricata is active"
        
        # eve.json更新確認（直近1分以内）
        EVE_JSON="/var/log/suricata/eve.json"
        if [[ -f "$EVE_JSON" ]]; then
            LAST_MODIFIED=$(stat -c %Y "$EVE_JSON" 2>/dev/null || echo 0)
            NOW=$(date +%s)
            AGE=$((NOW - LAST_MODIFIED))
            
            if [[ $AGE -lt 300 ]]; then
                check "suricata_eve_update" "PASS" "eve.json updated within 5 minutes"
            else
                check "suricata_eve_update" "WARN" "eve.json not updated recently (${AGE}s ago)"
            fi
        else
            check "suricata_eve_update" "FAIL" "eve.json not found"
        fi
    else
        check "suricata_active" "FAIL" "Suricata is not active"
    fi
fi

# OpenCanary
if [[ "$OPENCANARY_ENABLED" == "True" || "$OPENCANARY_ENABLED" == "true" ]]; then
    if systemctl is-active --quiet opencanary; then
        check "opencanary_active" "PASS" "OpenCanary is active"
    else
        check "opencanary_active" "FAIL" "OpenCanary is not active"
    fi
fi

log ""
log "[5] Reachability validation"

# 管理UI: usb0側からのみアクセス可能
if timeout 2 curl -s -o /dev/null "http://$INSIDE_IP:$MGMT_UI_PORT/" 2>/dev/null; then
    check "mgmt_ui_inside" "PASS" "Management UI reachable from inside ($INSIDE_IP:$MGMT_UI_PORT)"
else
    check "mgmt_ui_inside" "FAIL" "Management UI not reachable from inside"
fi

# 外向きIP取得（DHCP）
OUTSIDE_IP=$(ip addr show "$OUTSIDE_IF" | grep 'inet ' | awk '{print $2}' | cut -d/ -f1 | head -1)
if [[ -n "$OUTSIDE_IP" && "$OUTSIDE_IP" != "$INSIDE_IP" ]]; then
    # 管理UIは外向きからアクセス不可であるべき（FWでブロック）
    # ただし、同一ホストからのテストは難しいため、リスニング状態で確認
    if ss -tlnp | grep ":$MGMT_UI_PORT" | grep -q "$INSIDE_IP"; then
        check "mgmt_ui_bind" "PASS" "Management UI bound to inside IP only"
    else
        # 0.0.0.0 bindの場合はFWで制御
        if ss -tlnp | grep ":$MGMT_UI_PORT" | grep -q "0.0.0.0"; then
            check "mgmt_ui_bind" "WARN" "Management UI bound to 0.0.0.0 (should be FW-protected)"
        else
            check "mgmt_ui_bind" "FAIL" "Management UI not listening"
        fi
    fi
fi

# OpenCanary: wlan0側へ露出（外向き公開）
if [[ "$OPENCANARY_ENABLED" == "True" || "$OPENCANARY_ENABLED" == "true" ]]; then
    # OpenCanaryは0.0.0.0 bindが標準
    if ss -tlnp | grep -q "opencanary"; then
        check "opencanary_listening" "PASS" "OpenCanary is listening"
    else
        check "opencanary_listening" "FAIL" "OpenCanary not listening"
    fi
fi

log ""
log "[6] Traffic Control validation"

TC_ENABLED=$(python3 -c "import json; print(json.load(open('$PROFILE_JSON'))['traffic_control']['enabled'])")
if [[ "$TC_ENABLED" == "True" || "$TC_ENABLED" == "true" ]]; then
    if tc qdisc show dev "$OUTSIDE_IF" | grep -qE "(htb|netem|tbf)"; then
        check "tc_enabled" "PASS" "Traffic control configured on $OUTSIDE_IF"
    else
        check "tc_enabled" "FAIL" "Traffic control not configured on $OUTSIDE_IF"
    fi
else
    check "tc_enabled" "PASS" "Traffic control not required"
fi

# 検証結果JSON生成
log ""
log "=== Validation Summary ==="
log "Passed: $CHECKS_PASSED"
log "Failed: $CHECKS_FAILED"

if [[ $CHECKS_FAILED -eq 0 ]]; then
    OVERALL="PASS"
    log ""
    log "✓ VALIDATION PASSED"
    log "新機は旧機と同一構成です。運用投入可能です。"
else
    OVERALL="FAIL"
    log ""
    log "✗ VALIDATION FAILED"
    log "失敗した検証項目を修正し、再度applyしてください。"
    log "Failure bundle: installer/logs/failure_bundle_$TIMESTAMP"
fi

# JSON出力
cat > "$VALIDATION_RESULT" <<EOF
{
  "overall": "$OVERALL",
  "timestamp": "$(date -Iseconds)",
  "profile": "$PROFILE_FILE",
  "checks_passed": $CHECKS_PASSED,
  "checks_failed": $CHECKS_FAILED,
  "checks": [
    $(IFS=,; echo "${CHECKS[*]}")
  ]
}
EOF

log ""
log "Validation report: $VALIDATION_RESULT"

if [[ "$OVERALL" == "FAIL" ]]; then
    # failure bundle作成
    BUNDLE_DIR="$SCRIPT_DIR/logs/failure_bundle_$TIMESTAMP"
    mkdir -p "$BUNDLE_DIR"
    
    ip addr > "$BUNDLE_DIR/ip_addr.txt" 2>&1
    ip route > "$BUNDLE_DIR/ip_route.txt" 2>&1
    ss -tlnp > "$BUNDLE_DIR/ss_tcp.txt" 2>&1
    
    if command -v nft &>/dev/null; then
        nft list ruleset > "$BUNDLE_DIR/nft_ruleset.txt" 2>&1 || true
    fi
    
    tc qdisc show > "$BUNDLE_DIR/tc_qdisc.txt" 2>&1 || true
    systemctl status --no-pager > "$BUNDLE_DIR/systemctl_status.txt" 2>&1 || true
    
    cp "$VALIDATION_RESULT" "$BUNDLE_DIR/"
    
    log "Failure bundle created: $BUNDLE_DIR"
    exit 1
fi

exit 0
