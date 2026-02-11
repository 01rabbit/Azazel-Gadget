#!/bin/bash
################################################################################
# apply.sh - Azazel-Gadget Deterministic Installer
# Profile YAML を新機へ適用し、旧機と同一構成を再現
# 
# 絶対条件：
# - 冪等性（何度実行しても同じ結果）
# - USB経由SSH破壊禁止
# - managed areaのみ変更（FW全体flush禁止）
# - dry-runサポート
################################################################################

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

PROFILE_FILE=""
DRY_RUN=false
LOG_FILE=""

usage() {
    cat <<EOF
Usage: $0 --profile <profile.yaml> [--dry-run]

Options:
  --profile FILE    Profile YAML file to apply
  --dry-run         Show what would be done without making changes
  --help            Show this help

Example:
  sudo $0 --profile installer/profiles/gadget_profile_20260209.yaml --dry-run
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
        --dry-run)
            DRY_RUN=true
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
LOG_DIR="$SCRIPT_DIR/logs/apply_$TIMESTAMP"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/apply.log"

log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

run_cmd() {
    local cmd="$*"
    log "CMD: $cmd"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log "DRY-RUN: Would execute: $cmd"
        return 0
    fi
    
    if eval "$cmd" >> "$LOG_FILE" 2>&1; then
        log "SUCCESS: $cmd"
        return 0
    else
        log "FAILED: $cmd"
        return 1
    fi
}

create_failure_bundle() {
    local bundle_dir="$SCRIPT_DIR/logs/failure_bundle_$TIMESTAMP"
    mkdir -p "$bundle_dir"
    
    log "Creating failure bundle: $bundle_dir"
    
    # 診断情報収集
    ip addr > "$bundle_dir/ip_addr.txt" 2>&1 || true
    ip route > "$bundle_dir/ip_route.txt" 2>&1 || true
    ss -tlnp > "$bundle_dir/ss_tcp.txt" 2>&1 || true
    
    if command -v nft &>/dev/null; then
        nft list ruleset > "$bundle_dir/nft_ruleset.txt" 2>&1 || true
    fi
    
    tc qdisc show > "$bundle_dir/tc_qdisc.txt" 2>&1 || true
    
    systemctl status --no-pager > "$bundle_dir/systemctl_status.txt" 2>&1 || true
    
    for service in azazel-first-minute azazel-nat azazel-web opencanary suricata; do
        journalctl -u "$service" -n 100 --no-pager > "$bundle_dir/journal_${service}.txt" 2>&1 || true
    done
    
    # ログもコピー
    cp -r "$LOG_DIR" "$bundle_dir/apply_logs" 2>/dev/null || true
    
    log "Failure bundle created: $bundle_dir"
    echo
    echo "=== FAILURE BUNDLE ==="
    echo "診断情報を回収しました: $bundle_dir"
    echo "Macへ回収し、修正後に再実行してください"
}

trap 'create_failure_bundle' ERR

log "=== Azazel-Gadget Installer ==="
log "Profile: $PROFILE_FILE"
log "Dry-run: $DRY_RUN"
log "Log: $LOG_FILE"
log ""

# profileをパース（YAMLパーサーとしてPythonを使用）
PROFILE_JSON="$LOG_DIR/profile.json"
python3 -c "import yaml, json, sys; print(json.dumps(yaml.safe_load(open('$PROFILE_FILE'))))" > "$PROFILE_JSON"

# 必要なツールチェック
log "[Phase 0] Checking prerequisites..."
for tool in ip ss systemctl python3; do
    if ! command -v "$tool" &>/dev/null; then
        log "ERROR: Required tool not found: $tool"
        exit 1
    fi
done

# Profile値を抽出
INSIDE_IF=$(python3 -c "import json; print(json.load(open('$PROFILE_JSON'))['topology']['inside_if'])")
INSIDE_IP=$(python3 -c "import json; print(json.load(open('$PROFILE_JSON'))['topology']['inside_ip'])")
OUTSIDE_IF=$(python3 -c "import json; print(json.load(open('$PROFILE_JSON'))['topology']['outside_if'])")
NAT_ENABLED=$(python3 -c "import json; print(json.load(open('$PROFILE_JSON'))['network']['nat_enabled'])")
FW_BACKEND=$(python3 -c "import json; print(json.load(open('$PROFILE_JSON'))['network']['firewall_backend'])")

log "Topology: $INSIDE_IF ($INSIDE_IP) <-> $OUTSIDE_IF"
log "NAT: $NAT_ENABLED, Firewall: $FW_BACKEND"

# バックアップ作成（dry-runでない場合）
if [[ "$DRY_RUN" == "false" ]]; then
    log "[Phase 1] Creating backups..."
    
    # FWルールバックアップ
    if [[ "$FW_BACKEND" == "nftables" ]]; then
        nft list ruleset > "$LOG_DIR/nft_backup.txt" 2>&1 || true
    else
        iptables-save > "$LOG_DIR/iptables_backup.txt" 2>&1 || true
    fi
    
    # 設定ファイルバックアップ
    if [[ -d "$REPO_ROOT/configs" ]]; then
        cp -r "$REPO_ROOT/configs" "$LOG_DIR/configs_backup" 2>&1 || true
    fi
fi

# Phase 2: Network setup
log "[Phase 2] Configuring network..."

# usb0 static IP
if ! grep -q "interface $INSIDE_IF" /etc/dhcpcd.conf 2>/dev/null; then
    log "Adding $INSIDE_IF static IP to dhcpcd.conf"
    
    if [[ "$DRY_RUN" == "false" ]]; then
        cat >> /etc/dhcpcd.conf <<EOF

# Azazel-Gadget: Inside interface
interface $INSIDE_IF
static ip_address=$INSIDE_IP/24
EOF
    fi
else
    log "$INSIDE_IF already configured in dhcpcd.conf"
fi

# IP forwarding
log "Enabling IP forwarding..."
run_cmd "sysctl -w net.ipv4.ip_forward=1"
run_cmd "sysctl -w net.ipv6.conf.all.forwarding=0"

if [[ "$DRY_RUN" == "false" ]]; then
    # 永続化
    if ! grep -q "net.ipv4.ip_forward=1" /etc/sysctl.conf 2>/dev/null; then
        echo "net.ipv4.ip_forward=1" >> /etc/sysctl.conf
    fi
fi

# Phase 3: Firewall setup
log "[Phase 3] Configuring firewall..."

if [[ "$FW_BACKEND" == "nftables" ]]; then
    log "Using nftables backend"
    
    # templateレンダリング
    NFT_TEMPLATE="$REPO_ROOT/nftables/first_minute.nft"
    NFT_RENDERED="$LOG_DIR/first_minute_rendered.nft"
    
    if [[ -f "$NFT_TEMPLATE" ]]; then
        # トークン置換
        sed -e "s/@UPSTREAM@/$OUTSIDE_IF/g" \
            -e "s/@DOWNSTREAM@/$INSIDE_IF/g" \
            -e "s/@MGMT_IP@/$INSIDE_IP/g" \
            "$NFT_TEMPLATE" > "$NFT_RENDERED"
        
        # 構文チェック
        if nft -c -f "$NFT_RENDERED"; then
            log "nftables template validated"
            run_cmd "nft -f $NFT_RENDERED"
        else
            log "ERROR: nftables template validation failed"
            exit 1
        fi
    else
        log "WARNING: nftables template not found: $NFT_TEMPLATE"
    fi
    
else
    log "Using iptables backend"
    
    # iptables: AZAZEL_* chainsのみ管理
    run_cmd "iptables -t nat -N AZAZEL_NAT 2>/dev/null || true"
    run_cmd "iptables -t nat -F AZAZEL_NAT"
    run_cmd "iptables -t nat -A AZAZEL_NAT -o $OUTSIDE_IF -j MASQUERADE"
    run_cmd "iptables -t nat -A POSTROUTING -j AZAZEL_NAT"
    
    run_cmd "iptables -N AZAZEL_FORWARD 2>/dev/null || true"
    run_cmd "iptables -F AZAZEL_FORWARD"
    run_cmd "iptables -A AZAZEL_FORWARD -i $INSIDE_IF -o $OUTSIDE_IF -j ACCEPT"
    run_cmd "iptables -A AZAZEL_FORWARD -i $OUTSIDE_IF -o $INSIDE_IF -m state --state RELATED,ESTABLISHED -j ACCEPT"
    run_cmd "iptables -A FORWARD -j AZAZEL_FORWARD"
fi

# Phase 4: Python venv setup
log "[Phase 4] Setting up Python venv..."

VENV_DIR="/opt/azazel/.venv"
if [[ ! -d "$VENV_DIR" ]]; then
    log "Creating venv: $VENV_DIR"
    run_cmd "python3 -m venv $VENV_DIR"
fi

# requirements install
if [[ -f "$REPO_ROOT/requirements.txt" ]]; then
    log "Installing Python dependencies..."
    run_cmd "$VENV_DIR/bin/pip install -q -r $REPO_ROOT/requirements.txt"
fi

# Phase 5: systemd services
log "[Phase 5] Installing systemd services..."

for service_file in "$REPO_ROOT"/systemd/*.service; do
    if [[ ! -f "$service_file" ]]; then
        continue
    fi
    
    service_name=$(basename "$service_file")
    
    # ExecStartをvenv pythonに書き換え（必要に応じて）
    # ここでは単純にコピー（実際にはtemplateレンダリングが望ましい）
    
    log "Installing $service_name"
    run_cmd "cp $service_file /etc/systemd/system/"
done

run_cmd "systemctl daemon-reload"

# Profile記載のservicesを有効化
SERVICES=$(python3 -c "import json; services = json.load(open('$PROFILE_JSON')).get('services', []); print(' '.join([s['name'] for s in services if s.get('active_state') == 'active']))")

for service in $SERVICES; do
    if [[ -f "/etc/systemd/system/${service}.service" ]]; then
        log "Enabling $service"
        run_cmd "systemctl enable ${service}.service"
        
        if [[ "$DRY_RUN" == "false" ]]; then
            # 起動はvalidateフェーズで確認するため、ここではenableのみ
            : # systemctl start ${service}.service
        fi
    fi
done

# Phase 6: 完了
log ""
log "=== Apply Complete ==="

if [[ "$DRY_RUN" == "true" ]]; then
    log "DRY-RUN mode: No changes were made"
    log "Review log: $LOG_FILE"
else
    log "Changes applied successfully"
    log "Log: $LOG_FILE"
    log ""
    log "Next step:"
    log "  sudo $SCRIPT_DIR/validate.sh --profile $PROFILE_FILE"
fi

exit 0
