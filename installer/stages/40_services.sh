#!/bin/bash
################################################################################
# Stage 40: Systemd Services
# 
# systemd ユニット配置、サービス有効化＆起動
################################################################################

set -euo pipefail
source "$(dirname "$0")/../_lib.sh"

WITH_NTFY="${WITH_NTFY:-0}"
WITH_CANARY="${WITH_CANARY:-0}"
WITH_WEBUI="${WITH_WEBUI:-0}"

caddy_unit_exists() {
    systemctl list-unit-files caddy.service >/dev/null 2>&1
}

dnsmasq_unit_exists() {
    systemctl list-unit-files dnsmasq.service >/dev/null 2>&1
}

main() {
    log_info "════════════════════════════════════════════"
    log_info "Stage 40: Systemd Services Registration"
    log_info "════════════════════════════════════════════"
    
    # 1. 起動スクリプト配置
    log_info "システムスクリプトを配置..."
    mkdir -p /usr/local/sbin /usr/local/bin
    
    local scripts=(
        "scripts/usb0-static.sh:/usr/local/sbin/usb0-static.sh"
        "scripts/azazel-nat.sh:/usr/local/sbin/azazel-nat.sh"
        "bin/suri_epaper.sh:/usr/local/bin/"
        "bin/portal_detect.sh:/usr/local/bin/"
        "scripts/opencanary-start.sh:/usr/local/bin/opencanary-start"
    )
    
    for script_pair in "${scripts[@]}"; do
        local src="${script_pair%:*}"
        local dest="${script_pair#*:}"
        
        if [[ -f "$PROJECT_ROOT/$src" ]]; then
            install_script "$PROJECT_ROOT/$src" "$dest"
            log_debug "✓ $(basename "$src")"
        else
            log_warn "⚠️  スクリプトが見つかりません: $src"
        fi
    done
    
    # 2. systemd ユニット配置
    log_info "systemd ユニットを配置..."
    mkdir -p /etc/systemd/system
    
    local units=(
        "azazel-first-minute.service"
        "azazel-epd.service"
        "azazel-epd-portal.service"
        "azazel-epd-portal.timer"
        "azazel-control-daemon.service"
        "azazel-web.service"
        "usb0-static.service"
        "azazel-nat.service"
        "suri-epaper.service"
        "opencanary.service"
    )
    
    for unit in "${units[@]}"; do
        if [[ -f "$PROJECT_ROOT/systemd/$unit" ]]; then
            install_config "$PROJECT_ROOT/systemd/$unit" "/etc/systemd/system/$unit"
            log_debug "✓ $unit"
        else
            log_warn "⚠️  ユニットが見つかりません: $unit"
        fi
    done
    
    # 3. systemd drop-in ディレクトリ
    if [[ -d "$PROJECT_ROOT/systemd/azazel-epd.service.d" ]]; then
        mkdir -p /etc/systemd/system/azazel-epd.service.d
        cp "$PROJECT_ROOT/systemd/azazel-epd.service.d"/* /etc/systemd/system/azazel-epd.service.d/ 2>/dev/null || true
        log_debug "✓ azazel-epd.service.d drop-ins"
    fi
    
    # 4. NetworkManager dispatcher
    if [[ -f "$PROJECT_ROOT/scripts/opencanary-nm-dispatcher.sh" ]]; then
        mkdir -p /etc/NetworkManager/dispatcher.d
        install_script "$PROJECT_ROOT/scripts/opencanary-nm-dispatcher.sh" \
                       "/etc/NetworkManager/dispatcher.d/50-opencanary-wlan0"
        log_debug "✓ NetworkManager dispatcher"
    fi
    
    # 5. systemd daemon-reload
    log_info "systemd 設定を再読込..."
    systemctl daemon-reload >> "$LOG_FILE" 2>&1 || die "systemctl daemon-reload 失敗"

    # 6. 競合回避: 既定 dnsmasq サービスを停止（first-minute 管理に一本化）
    if dnsmasq_unit_exists; then
        log_info "既定 dnsmasq.service を停止・無効化..."
        systemctl stop dnsmasq >> "$LOG_FILE" 2>&1 || log_warn "⚠️  dnsmasq 停止失敗（継続）"
        systemctl disable dnsmasq >> "$LOG_FILE" 2>&1 || log_warn "⚠️  dnsmasq 無効化失敗（継続）"
    fi

    # 6.5 Suricata 軽量プロファイル適用（Pi Zero 2 向け）
    local suri_updater="$PROJECT_ROOT/bin/suricata_update.sh"
    if [[ -x "$suri_updater" ]]; then
        local detected_wan_if
        detected_wan_if="$(ip -4 route show default | awk '{for (i=1; i<=NF; i++) if ($i == "dev") {print $(i+1); exit}}')"
        detected_wan_if="${detected_wan_if:-wlan0}"
        log_info "Suricata 軽量ルールを適用..."
        if "$suri_updater" --profile pi-zero2-lite --wan-if "$detected_wan_if" >> "$LOG_FILE" 2>&1; then
            log_info "✓ Suricata 軽量プロファイル適用完了"
        else
            die "Suricata 軽量プロファイル適用に失敗: $suri_updater"
        fi
    else
        die "Suricata 更新スクリプトが見つかりません: $suri_updater"
    fi

    # Stage 20 で置いたブートストラップ設定は Stage 40 で撤去
    if [[ -f /etc/dnsmasq.d/azazel-usb0-bootstrap.conf ]]; then
        rm -f /etc/dnsmasq.d/azazel-usb0-bootstrap.conf
    fi
    
    # 7. 主要サービス有効化＆起動
    log_info "主要サービスを有効化中..."
    
    local primary_services=(
        "usb0-static.service"
        "azazel-nat.service"
        "azazel-first-minute.service"
        "azazel-control-daemon.service"
        "azazel-web.service"
        "suri-epaper.service"
        "azazel-epd-portal.timer"
    )

    if [[ "$WITH_WEBUI" == "1" ]]; then
        if caddy_unit_exists; then
            primary_services+=("caddy.service")
        else
            log_warn "⚠️  caddy.service が見つかりません（HTTPS 無効の可能性）"
        fi
    fi

    if [[ "$WITH_NTFY" == "1" ]]; then
        primary_services+=("ntfy.service")
    fi
    
    for service in "${primary_services[@]}"; do
        log_info "  サービス: $service"
        systemctl enable "$service" >> "$LOG_FILE" 2>&1 || {
            log_warn "⚠️  サービス有効化に失敗: $service（非致命的）"
        }
    done
    
    # 8. サービス起動テスト（usb0-static, azazel-nat, azazel-first-minute）
    log_info ""
    log_info "サービス起動をテスト中..."
    
    log_info "  • usb0-static.service を起動..."
    systemctl start usb0-static.service >> "$LOG_FILE" 2>&1 || {
        log_warn "⚠️  usb0-static 起動失敗"
    }
    
    log_info "  • azazel-nat.service を起動..."
    systemctl start azazel-nat.service >> "$LOG_FILE" 2>&1 || {
        log_warn "⚠️  azazel-nat 起動失敗"
    }
    
    # 競合していた dnsmasq を掃除してから first-minute を再起動
    pkill -f "dnsmasq.*dnsmasq-first_minute.conf" >> "$LOG_FILE" 2>&1 || true
    log_info "  • azazel-first-minute.service を再起動..."
    systemctl restart azazel-first-minute.service >> "$LOG_FILE" 2>&1 || {
        log_warn "⚠️  azazel-first-minute 再起動失敗"
    }

    if [[ "$WITH_WEBUI" == "1" ]]; then
        log_info "  • azazel-web.service を再起動..."
        systemctl restart azazel-web.service >> "$LOG_FILE" 2>&1 || {
            log_warn "⚠️  azazel-web.service 再起動失敗"
        }

        if caddy_unit_exists; then
            log_info "  • caddy.service を再起動..."
            systemctl restart caddy.service >> "$LOG_FILE" 2>&1 || {
                log_warn "⚠️  caddy.service 再起動失敗"
            }

            # Caddy internal CA を配布しやすい場所へコピー
            local caddy_root_ca="/var/lib/caddy/.local/share/caddy/pki/authorities/local/root.crt"
            if [[ -f "$caddy_root_ca" ]]; then
                mkdir -p /etc/azazel-zero/certs
                install -m 0644 "$caddy_root_ca" "/etc/azazel-zero/certs/azazel-webui-local-ca.crt"
                log_info "  ✓ Web UI ローカルCA: /etc/azazel-zero/certs/azazel-webui-local-ca.crt"
            else
                log_warn "⚠️  Caddy ローカルCAが見つかりません: $caddy_root_ca"
            fi
        fi
    fi

    if [[ "$WITH_NTFY" == "1" ]]; then
        log_info "  • ntfy.service を再起動..."
        systemctl restart ntfy.service >> "$LOG_FILE" 2>&1 || {
            log_warn "⚠️  ntfy.service 再起動失敗"
        }
    fi
    
    # 9. オプション: OpenCanary サービス
    if [[ "$WITH_CANARY" == "1" ]]; then
        if systemctl list-unit-files | grep -q "opencanary.service"; then
            log_info "  • opencanary.service を有効化..."
            systemctl enable opencanary.service >> "$LOG_FILE" 2>&1 || {
                log_warn "⚠️  opencanary.service 有効化失敗"
            }
            log_info "  • opencanary.service を再起動..."
            systemctl restart opencanary.service >> "$LOG_FILE" 2>&1 || {
                log_warn "⚠️  opencanary.service 起動失敗"
            }
        else
            log_warn "⚠️  opencanary.service が未登録です"
        fi
    else
        log_info "OpenCanary は未選択（--with-canary で有効化）"
    fi
    
    log_info ""
    log_info "════════════════════════════════════════════"
    log_info "✓ Stage 40 完了"
    log_info "════════════════════════════════════════════"
    mark_stage_passed "40"
    return 0
}

main "$@"
