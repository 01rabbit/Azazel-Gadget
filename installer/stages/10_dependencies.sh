#!/bin/bash
################################################################################
# Stage 10: Package Installation
# 
# APT パッケージ、Python venv、オプション機能のインストール
################################################################################

set -euo pipefail
source "$(dirname "$0")/../_lib.sh"

WITH_CANARY="${WITH_CANARY:-0}"
WITH_EPD="${WITH_EPD:-0}"
WITH_WEBUI="${WITH_WEBUI:-0}"
WITH_NTFY="${WITH_NTFY:-0}"
WITH_PORTAL_VIEWER="${WITH_PORTAL_VIEWER:-0}"

main() {
    log_info "════════════════════════════════════════════"
    log_info "Stage 10: Package Installation"
    log_info "════════════════════════════════════════════"
    
    # 1. Apt 更新
    log_info "APT リポジトリを更新..."
    apt-get update -y >> "$LOG_FILE" 2>&1 || die "apt-get update 失敗"
    
    # 2. 基本パッケージのインストール
    log_info "基本パッケージをインストール..."
    local base_packages=(
        # ネットワーク
        iproute2 iptables iptables-persistent nftables dnsmasq
        # 管理&ツール
        python3 python3-venv python3-pip python3-yaml python3-requests python3-jq
        # 脅威検知
        suricata suricata-update
        # その他
        git curl jq tmux ca-certificates wireless-tools iw network-manager
        util-linux zram-tools
    )
    
    install_packages "${base_packages[@]}"
    log_info "✓ 基本パッケージ完了"
    
    # 3. iptables-persistent 有効化
    log_info "iptables-persistent を有効化..."
    systemctl enable netfilter-persistent >> "$LOG_FILE" 2>&1 || true
    
    # 4. ユーザー作成（azazel）
    if ! id -u azazel >/dev/null 2>&1; then
        log_info "azazel ユーザーを作成..."
        useradd -m -s /bin/bash azazel >> "$LOG_FILE" 2>&1 || true
    else
        log_debug "azazel ユーザーは既に存在"
    fi
    
    # 5. オプション: OpenCanary
    if [[ "$WITH_CANARY" == "1" ]]; then
        log_info "OpenCanary をインストール..."
        if [[ ! -d /home/azazel/canary-venv ]]; then
            sudo -u azazel python3 -m venv /home/azazel/canary-venv >> "$LOG_FILE" 2>&1 || die "canary-venv 作成失敗"
            sudo -u azazel /home/azazel/canary-venv/bin/pip install --upgrade pip wheel >> "$LOG_FILE" 2>&1 || true
            sudo -u azazel /home/azazel/canary-venv/bin/pip install opencanary >> "$LOG_FILE" 2>&1 || die "OpenCanary インストール失敗"
            log_info "✓ OpenCanary インストール完了"
        else
            log_debug "OpenCanary venv は既に存在"
        fi
    fi
    
    # 6. オプション: Waveshare E-Paper
    if [[ "$WITH_EPD" == "1" ]]; then
        log_info "Waveshare E-Paper 依存をインストール..."
        local epd_packages=(
            python3-dev python3-numpy python3-pil python3-spidev
            python3-rpi.gpio python3-gpiozero wget unzip p7zip-full
            fonts-noto-cjk
        )
        install_packages "${epd_packages[@]}"
        
        # Waveshare リポジトリクローン
        if [[ ! -d /opt/waveshare-epd ]]; then
            log_info "Waveshare e-Paper リポジトリをクローン..."
            mkdir -p /opt
            git clone https://github.com/waveshare/e-Paper /opt/waveshare-epd >> "$LOG_FILE" 2>&1 || die "Waveshare クローン失敗"
        fi
        log_info "✓ E-Paper 依存インストール完了"
    fi
    
    # 7. オプション: Web UI
    if [[ "$WITH_WEBUI" == "1" ]]; then
        log_info "Web UI 環境を準備..."
        log_info "HTTPS リバースプロキシ (Caddy) をインストール..."
        apt-get install -y caddy >> "$LOG_FILE" 2>&1 || die "caddy インストール失敗"

        if [[ ! -d /home/azazel/azazel-webui-venv ]]; then
            sudo -u azazel python3 -m venv /home/azazel/azazel-webui-venv >> "$LOG_FILE" 2>&1 || die "webui-venv 作成失敗"
            sudo -u azazel /home/azazel/azazel-webui-venv/bin/pip install --upgrade pip wheel >> "$LOG_FILE" 2>&1 || true
            sudo -u azazel /home/azazel/azazel-webui-venv/bin/pip install Flask==3.1.1 >> "$LOG_FILE" 2>&1 || die "Flask インストール失敗"
            log_info "✓ Web UI 環境準備完了"
        else
            log_debug "Web UI venv は既に存在"
        fi
    fi
    
    # 8. オプション: ntfy
    if [[ "$WITH_PORTAL_VIEWER" == "1" ]]; then
        log_info "Captive Portal Viewer 依存をインストール..."
        local portal_packages=(
            novnc websockify x11vnc xvfb openbox
        )
        install_packages "${portal_packages[@]}"

        if ! command -v chromium >/dev/null 2>&1 && ! command -v chromium-browser >/dev/null 2>&1; then
            if ! install_package chromium; then
                install_package chromium-browser || true
            fi
        fi
        log_info "✓ Captive Portal Viewer 依存インストール完了"
    fi

    # 8. オプション: ntfy
    if [[ "$WITH_NTFY" == "1" ]]; then
        log_info "ntfy サーバをインストール..."
        local ntfy_installer="$PROJECT_ROOT/scripts/install_ntfy.sh"
        if [[ ! -x "$ntfy_installer" ]]; then
            die "ntfy インストーラスクリプトが見つかりません: $ntfy_installer"
        fi
        "$ntfy_installer" >> "$LOG_FILE" 2>&1 || die "ntfy インストール失敗"
        log_info "✓ ntfy サーバ設定完了"
    fi
    
    # 9. Locale 設定
    if ! locale -a | grep -q 'en_US.utf8'; then
        log_info "en_US.UTF-8 locale を生成..."
        localedef -i en_US -f UTF-8 en_US.UTF-8 >> "$LOG_FILE" 2>&1 || true
    fi
    
    log_info ""
    log_info "════════════════════════════════════════════"
    log_info "✓ Stage 10 完了"
    log_info "════════════════════════════════════════════"
    mark_stage_passed "10"
    return 0
}

main "$@"
