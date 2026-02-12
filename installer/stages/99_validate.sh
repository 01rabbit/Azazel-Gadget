#!/bin/bash
################################################################################
# Stage 99: Validation & Completion  
#
# 全サービスの起動確認、ネットワーク疎通確認、完了メッセージ
################################################################################

set -euo pipefail
source "$(dirname "$0")/../_lib.sh"

main() {
    log_info "════════════════════════════════════════════"
    log_info "Stage 99: Validation & Completion"
    log_info "════════════════════════════════════════════"
    
    local all_passed=true
    
    # 1. インターフェース確認
    log_info ""
    log_info "【1】ネットワークインターフェース確認:"
    
    if is_interface_up wlan0; then
        local ip=$(get_interface_ip wlan0)
        log_info "  ✓ wlan0 UP: $ip"
    else
        log_error "  ✗ wlan0 が UP していません"
        all_passed=false
    fi
    
    if is_interface_up usb0; then
        local ip=$(get_interface_ip usb0)
        log_info "  ✓ usb0 UP: $ip"
    else
        log_error "  ✗ usb0 が UP していません"
        all_passed=false
    fi
    
    # 2. サービス起動確認
    log_info ""
    log_info "【2】サービス起動確認:"
    
    local critical_services=(
        "usb0-static.service"
        "azazel-first-minute.service"
    )
    
    local optional_services=(
        "azazel-control-daemon.service"
        "azazel-web.service"
        "azazel-nat.service"
        "suri-epaper.service"
    )
    
    for service in "${critical_services[@]}"; do
        if check_service "$service"; then
            log_info "  ✓ $service"
        else
            log_error "  ✗ $service が起動していません"
            all_passed=false
        fi
    done
    
    for service in "${optional_services[@]}"; do
        if systemctl is-enabled --quiet "$service" 2>/dev/null; then
            if check_service "$service"; then
                log_info "  ✓ $service"
            else
                log_warn "  ⚠️  $service が有効だが起動していません"
            fi
        else
            log_debug "  - $service (未有効化)"
        fi
    done

    # 2.5 dnsmasq 競合チェック
    if systemctl is-active --quiet dnsmasq.service 2>/dev/null; then
        log_error "  ✗ 既定 dnsmasq.service が起動中（first-minute 管理 dnsmasq と競合）"
        all_passed=false
    else
        log_info "  ✓ 既定 dnsmasq.service は停止済み"
    fi
    
    # 3. ポート確認
    log_info ""
    log_info "【3】ネットワークポート確認:"

    local mgmt_ip="10.55.0.10"
    if [[ -f /etc/default/azazel-zero ]]; then
        # shellcheck disable=SC1091
        source /etc/default/azazel-zero
        if [[ -n "${MGMT_IP:-}" ]]; then
            mgmt_ip="$MGMT_IP"
        fi
    fi

    if pgrep -af "dnsmasq.*dnsmasq-first_minute.conf" >/dev/null 2>&1; then
        log_info "  ✓ first-minute 管理 dnsmasq プロセスを確認"
    else
        log_error "  ✗ first-minute 管理 dnsmasq プロセスが見つかりません"
        all_passed=false
    fi

    if ss -ulnH 2>/dev/null | grep -Eq ':67[[:space:]]'; then
        log_info "  ✓ DHCP (UDP/67) がリッスン中"
    else
        log_error "  ✗ DHCP (UDP/67) がリッスンしていません"
        all_passed=false
    fi

    if ss -ulnH 2>/dev/null | grep -Eq ':53[[:space:]]'; then
        log_info "  ✓ DNS (UDP/53) がリッスン中"
    else
        log_error "  ✗ DNS (UDP/53) がリッスンしていません"
        all_passed=false
    fi

    if systemctl is-enabled --quiet ntfy.service 2>/dev/null; then
        if check_service "ntfy.service"; then
            if ss -ltnH 2>/dev/null | grep -Eq ':8081[[:space:]]'; then
                log_info "  ✓ ntfy (TCP/8081) がリッスン中"
            else
                log_error "  ✗ ntfy は有効だが TCP/8081 がリッスンしていません"
                all_passed=false
            fi
        else
            log_error "  ✗ ntfy.service が起動していません"
            all_passed=false
        fi
    fi
    
    # 4. ファイアウォール確認
    log_info ""
    log_info "【4】ファイアウォール確認:"
    
    if command -v nft >/dev/null && nft list tables | grep -q "azazel_fmc"; then
        log_info "  ✓ nftables テーブル azazel_fmc が存在"
    else
        log_warn "  ⚠️  nftables テーブル azazel_fmc が見つかりません（後で設定可能）"
    fi
    
    # 5. ログ確認
    log_info ""
    log_info "【5】最近のログ（azazel-first-minute）:"
    
    if journalctl -u azazel-first-minute.service -n 5 --no-pager 2>/dev/null | tail -3; then
        log_info "  ✓ ログ取得成功"
    else
        log_warn "  ⚠️  ログが見つかりません（サービス初回実行の可能性）"
    fi
    
    # 6. dnsmasq ログ確認
    log_info ""
    log_info "【6】dnsmasq ログ確認:"
    
    if [[ -f /var/log/azazel-dnsmasq.log ]]; then
        local recent_lines=$(tail -3 /var/log/azazel-dnsmasq.log 2>/dev/null || echo "ログなし")
        log_info "  $recent_lines"
    else
        log_warn "  ⚠️  /var/log/azazel-dnsmasq.log が見つかりません"
    fi
    
    # 7. 設定確認
    log_info ""
    log_info "【7】設定ファイル確認:"
    
    local config_files=(
        "/etc/azazel-zero/first_minute.yaml"
        "/etc/azazel-zero/dnsmasq-first_minute.conf"
        "/etc/default/azazel-zero"
    )
    
    for conf in "${config_files[@]}"; do
        if [[ -f "$conf" ]]; then
            log_info "  ✓ $conf"
        else
            log_error "  ✗ $conf が見つかりません"
            all_passed=false
        fi
    done
    
    # 8. 完了メッセージ
    log_info ""
    log_info "════════════════════════════════════════════"
    
    if [[ "$all_passed" == "true" ]]; then
        log_info "✓✓✓ INSTALLATION SUCCESSFUL ✓✓✓"
        log_info ""
        log_info "Azazel-Zero のインストールが完了しました！"
        log_info ""
        log_info "【次のステップ】"
        log_info ""
        log_info "1) ラップトップを接続:"
        log_info "   USB ガジェット (usb0, 10.55.0.10) 経由で接続"
        log_info "   IP は自動ダウンロード (DHCP) されます"
        log_info ""
        log_info "2) 設定をカスタマイズ（必要に応じて）:"
        log_info "   /etc/azazel-zero/first_minute.yaml"
        log_info "   - 既知 SSID リスト"
        log_info "   - 状態遷移閾値"
        log_info ""
        log_info "3) OpenCanary 有効化（ハニーポット）:"
        log_info "   sudo systemctl enable --now opencanary.service"
        log_info ""
        log_info "4) Web UI へアクセス:"
        log_info "   http://10.55.0.10:8083 (別途インストール必要)"
        log_info ""
        log_info "【ログ確認】"
        log_info "  tail -f /var/log/azazel-zero/first_minute.log"
        log_info "  tail -f /var/log/azazel-dnsmasq.log"
        log_info ""
        log_info "インストール詳細ログ:"
        log_info "  $LOG_FILE"
        log_info ""
        log_info "════════════════════════════════════════════"
        
    else
        log_error "⚠️  いくつかのチェックに失敗しました"
        log_error ""
        log_error "トラブルシューティング:"
        log_error "  • ログを確認: tail -50 $LOG_FILE"
        log_error "  • dnsmasq: tail -50 /var/log/azazel-dnsmasq.log"
        log_error "  • 競合確認: systemctl status dnsmasq azazel-first-minute.service"
        log_error "  • サービスステータス: systemctl status azazel-first-minute.service"
        log_error ""
        log_error "詳細は以下を参照:"
        log_error "  /home/azazel/Azazel-Zero/docs/DHCP_DNS_TROUBLESHOOTING.md"
        log_error ""
        return 1
    fi
    
    mark_stage_passed "99"
    return 0
}

main "$@"
