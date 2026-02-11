#!/bin/bash
################################################################################
# Stage 20: Network Configuration
# 
# usb0 設定、NAT、ファイアウォール適用
# ⭐【重要】ネットワーク変更検出＆再起動対応
################################################################################

set -euo pipefail
source "$(dirname "$0")/../_lib.sh"

main() {
    log_info "════════════════════════════════════════════"
    log_info "Stage 20: Network Configuration"
    log_info "════════════════════════════════════════════"
    
    # 1. usb0 インターフェース確認
    log_info "usb0 インターフェースをセットアップ..."
    setup_usb0
    
    # 2. dnsmasq リース用ディレクトリ
    log_info "dnsmasq リース用ディレクトリを準備..."
    mkdir -p /var/lib/dnsmasq
    touch /var/lib/dnsmasq/dnsmasq.leases
    chown nobody:nogroup /var/lib/dnsmasq/dnsmasq.leases
    
    # 3. NAT ルール適用（iptables）
    log_info "NAT ルールを適用..."
    if [[ -f "$PROJECT_ROOT/configs/iptables-rules.v4" ]] || [[ -f "$DEFAULTS_DIR/iptables-rules.v4" ]]; then
        local iptables_src="${DEFAULTS_DIR}/iptables-rules.v4"
        if [[ -f "$iptables_src" ]]; then
            iptables-restore < "$iptables_src" >> "$LOG_FILE" 2>&1 || die "iptables ルール適用失敗"
            log_info "✓ iptables ルール適用完了"
        fi
    fi
    
    # 4. IP フォワーディング有効化
    log_info "IP フォワーディングを有効化..."
    sysctl -w net.ipv4.ip_forward=1 >> "$LOG_FILE" 2>&1 || die "IP フォワーディング有効化失敗"
    
    # 5. nftables ベース設定（後の Stage 40 で systemd 経由で適用）
    # ここでは、usb0 に対する入力ルールをテスト
    log_debug "nftables 準備は Stage 40 で行います"
    
    # 6. 【重要】ネットワーク変更検出
    log_info ""
    log_info "═══════════════════════════════════════════════════════════"
    log_info "ネットワーク構成をチェック中..."
    log_info "═══════════════════════════════════════════════════════════"
    
    local wlan0_ip_before=$(get_state "wlan0_ip_before")
    local wlan0_ip_after=$(get_interface_ip wlan0 || echo "unknown")
    
    log_info "wlan0 (upstream) IP:"
    log_info "  Before: $wlan0_ip_before"
    log_info "  After:  $wlan0_ip_after"
    log_info "usb0 (downstream) IP:"
    log_info "  現在: $(get_interface_ip usb0 || echo 'none')"
    
    # ネットワークが変わったか判定
    if [[ "$wlan0_ip_before" != "unknown" ]] && \
       [[ "$wlan0_ip_after" != "unknown" ]] && \
       [[ "$wlan0_ip_before" != "$wlan0_ip_after" ]]; then
        
        log_warn ""
        log_warn "⚠️  ネットワーク構成が変更された可能性があります"
        log_warn "    $wlan0_ip_before → $wlan0_ip_after"
        log_warn ""
        
        # 再起動をプロンプト
        prompt_reboot
        
        # 状態ファイルに記録
        set_state "stage" "20_NEEDS_REBOOT"
        
        log_info "再起動してください（再起動は自動化していません）"
        log_info "再起動後、以下を実行してください："
        log_info "  sudo ./install.sh --resume"
        
        exit 0  # 正常に終了（エラーではない）
    fi
    
    log_info ""
    log_info "✓ ネットワーク構成に大きな変化なし（再起動不要）"
    log_info ""
    
    log_info "════════════════════════════════════════════"
    log_info "✓ Stage 20 完了"
    log_info "════════════════════════════════════════════"
    mark_stage_passed "20"
    return 0
}

main "$@"
