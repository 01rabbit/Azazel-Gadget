#!/bin/bash
################################################################################
# Stage 30: Configuration Files
# 
# 設定ファイル配置、テンプレート反映
###############################################################################

set -euo pipefail
source "$(dirname "$0")/../_lib.sh"

WITH_WEBUI="${WITH_WEBUI:-0}"

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
    local mgmt_ip="10.55.0.10"
    local web_backend_host="127.0.0.1"
    local web_backend_port="8084"
    local web_https_port="443"

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
MGMT_IP=${mgmt_ip}
MGMT_SUBNET=10.55.0.0/24

# Web UI バックエンド (Flask)
AZAZEL_WEB_HOST=${web_backend_host}
AZAZEL_WEB_PORT=${web_backend_port}
AZAZEL_WEB_PUBLIC_HOST=${mgmt_ip}
AZAZEL_WEB_HTTPS_PORT=${web_https_port}
AZAZEL_WEB_HTTPS_ENABLED=1

# サブネット（deprecated）
SUBNET=192.168.7.0/24
OUTIF=\${WAN_IF}
EOF
    log_info "✓ 環境ファイル作成: /etc/default/azazel-zero"

    # 4.5 Web UI HTTPS (Caddy) 設定
    if [[ "$WITH_WEBUI" == "1" ]]; then
        log_info "Caddy HTTPS 設定を配置..."
        mkdir -p /etc/caddy
        cat > /etc/caddy/Caddyfile <<EOF
{
    admin off
    auto_https disable_redirects
}

# Azazel Web UI (HTTPS endpoint)
https://${mgmt_ip} {
    tls internal
    encode zstd gzip
    reverse_proxy ${web_backend_host}:${web_backend_port}
}

# Localhost HTTPS for on-device browser/debug
https://localhost {
    tls internal
    encode zstd gzip
    reverse_proxy ${web_backend_host}:${web_backend_port}
}
EOF
        chmod 0644 /etc/caddy/Caddyfile
        log_info "✓ Caddyfile 配置: /etc/caddy/Caddyfile"
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
