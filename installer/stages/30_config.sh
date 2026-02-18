#!/bin/bash
################################################################################
# Stage 30: Configuration Files
# 
# 設定ファイル配置、テンプレート反映
###############################################################################

set -euo pipefail
source "$(dirname "$0")/../_lib.sh"

main() {
    log_info "════════════════════════════════════════════"
    log_info "Stage 30: Configuration Files"
    log_info "════════════════════════════════════════════"
    
    # 1. ディレクトリ作成
    log_info "設定ディレクトリを作成..."
    mkdir -p /etc/azazel-zero
    mkdir -p /etc/azazel-zero/nftables
    mkdir -p /etc/default
    mkdir -p /var/log/azazel-zero
    
    # 2. メイン設定ファイル配置
    log_info "設定テンプレートを配置..."
    
    local config_files=(
        "first_minute.yaml"
        "dnsmasq-first_minute.conf"
        "opencanary.conf"
        "known_wifi.json"
        "iptables-rules.v4"
    )
    
    for config in "${config_files[@]}"; do
        if [[ -f "$DEFAULTS_DIR/$config" ]]; then
            install_config "$DEFAULTS_DIR/$config" "/etc/azazel-zero/$config"
            log_debug "✓ $config"
        else
            log_warn "⚠️  テンプレルが見つかりません: $config"
        fi
    done
    
    # 3. nftables テンプレート（existing から symlink）
    if [[ -f "$PROJECT_ROOT/nftables/first_minute.nft" ]]; then
        log_info "nftables テンプレートをリンク..."
        ln -sf "$PROJECT_ROOT/nftables/first_minute.nft" "/etc/azazel-zero/nftables/first_minute.nft" || true
    fi
    
    # 4. 環境ファイル作成 (/etc/default/azazel-zero)
    log_info "環境ファイルを作成..."
    cat > /etc/default/azazel-zero <<EOF
# Azazel-Zero 統合環境設定
# このファイルは systemd サービスから source される

AZAZEL_ROOT=$PROJECT_ROOT
AZAZEL_CANARY_VENV=/home/azazel/canary-venv
AZAZEL_WEBUI_VENV=/home/azazel/azazel-webui-venv

# E-Paper 表示
EPD_PY=$PROJECT_ROOT/py/boot_splash_epd.py
EPD_LOCK=/run/azazel-epd.lock

# ネットワークインターフェース
WAN_IF=auto
USB_IF=usb0
MGMT_IP=10.55.0.10
MGMT_SUBNET=10.55.0.0/24

# サブネット（deprecated）
SUBNET=192.168.7.0/24
OUTIF=\${WAN_IF}
EOF
    log_info "✓ 環境ファイル作成: /etc/default/azazel-zero"

    # 4.5 Captive Portal Viewer 環境ファイル作成
    local portal_env="/etc/azazel-zero/portal-viewer.env"
    if [[ ! -f "$portal_env" ]]; then
        log_info "Captive Portal Viewer 用環境ファイルを作成..."
        local portal_password
        portal_password="$(od -An -N12 -tx1 /dev/urandom | tr -d ' \n')"
        cat > "$portal_env" <<EOF
# Captive Portal Viewer (noVNC) 設定
# PORTAL_VNC_PASSWORD は初期値です。運用前に変更してください。

PORTAL_START_URL=http://neverssl.com
PORTAL_DISPLAY=:99
PORTAL_SCREEN=1366x768x24
PORTAL_NOVNC_BIND=0.0.0.0
PORTAL_NOVNC_PORT=6080
PORTAL_VNC_PORT=5900
PORTAL_VNC_PASSWORD=$portal_password
PORTAL_BROWSER_CMD=auto
PORTAL_BROWSER_PROFILE=/home/azazel/.config/azazel-portal-browser
PORTAL_BROWSER_ARGS="--new-window --no-first-run --no-default-browser-check --disable-features=Translate,AutofillServerCommunication --start-maximized"
EOF
        chmod 0640 "$portal_env"
        chown root:azazel "$portal_env" 2>/dev/null || true
        log_info "✓ Portal Viewer 設定作成: $portal_env"
    else
        log_info "Portal Viewer 設定は既存ファイルを維持: $portal_env"
    fi
    
    # 5. OpenCanary 初期設定（optional）
    log_info "OpenCanary 初期設定を準備..."
    mkdir -p /etc/opencanaryd
    if [[ -f "$DEFAULTS_DIR/opencanary.conf" ]]; then
        install_config "$DEFAULTS_DIR/opencanary.conf" "/etc/opencanaryd/opencanary.conf"
    fi
    
    # 6. ログディレクトリ権限
    if [[ -d /var/log/azazel-zero ]]; then
        chmod 755 /var/log/azazel-zero
    fi
    
    # 7. 秘匿情報チェック（オプション警告）
    log_info "設定内容を確認中..."
    
    if grep -q "MASKED" /etc/azazel-zero/first_minute.yaml 2>/dev/null; then
        log_warn "⚠️  設定ファイルに秘匿情報（SSID, PSK）のマスク記号が含まれています"
        log_warn "   以下を編集して実際の値を設定してください："
        log_warn "   /etc/azazel-zero/first_minute.yaml"
        log_warn ""
        log_warn "   特に以下のセクションを確認："
        log_warn "   - known_wifi_ssids"
        log_warn "   - wpa_psk (if using WPA authentication)"
    fi
    
    # 8. dnsmasq 設定確認
    if ! grep -q "interface=usb0" /etc/azazel-zero/dnsmasq-first_minute.conf 2>/dev/null; then
        log_warn "⚠️  dnsmasq 設定が不完全な可能性があります"
        log_warn "   /etc/azazel-zero/dnsmasq-first_minute.conf を確認してください"
    fi
    
    log_info ""
    log_info "════════════════════════════════════════════"
    log_info "✓ Stage 30 完了"
    log_info "════════════════════════════════════════════"
    mark_stage_passed "30"
    return 0
}

main "$@"
