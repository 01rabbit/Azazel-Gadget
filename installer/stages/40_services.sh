#!/bin/bash
################################################################################
# Stage 40: Systemd Services
# 
# systemd ユニット配置、サービス有効化＆起動
################################################################################

set -euo pipefail
source "$(dirname "$0")/../_lib.sh"

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
    
    # 6. 主要サービス有効化＆起動
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
    
    for service in "${primary_services[@]}"; do
        log_info "  サービス: $service"
        systemctl enable "$service" >> "$LOG_FILE" 2>&1 || {
            log_warn "⚠️  サービス有効化に失敗: $service（非致命的）"
        }
    done
    
    # 7. サービス起動テスト（usb0-static, azazel-nat）
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
    
    # ファースト・ミニッツの起動は後の Stage 99 で確認
    log_info "  • azazel-first-minute.service は後で確認"
    
    # 8. オプション: OpenCanary サービス
    if systemctl list-unit-files | grep -q "opencanary.service"; then
        log_info "OpenCanary サービスは登録済み（手動有効化が必要）"
        log_info "  有効化: sudo systemctl enable --now opencanary.service"
    fi
    
    log_info ""
    log_info "════════════════════════════════════════════"
    log_info "✓ Stage 40 完了"
    log_info "════════════════════════════════════════════"
    mark_stage_passed "40"
    return 0
}

main "$@"
