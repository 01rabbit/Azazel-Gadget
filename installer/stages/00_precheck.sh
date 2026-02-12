#!/bin/bash
################################################################################
# Stage 00: Prerequisites Check
# 
# 環境チェック、既存インストール検出、基本条件確認
################################################################################

set -euo pipefail
source "$(dirname "$0")/../_lib.sh"

main() {
    log_info "════════════════════════════════════════════"
    log_info "Stage 00: Prerequisites Check"
    log_info "════════════════════════════════════════════"
    
    # 1. Root 権限チェック
    ensure_root
    log_info "✓ Root 権限確認"
    
    # 2. OS確認
    check_os
    log_info "✓ OS 情報確認"
    
    # 3. ディスク容量
    check_disk_space
    
    # 4. ネットワークインターフェース確認
    if check_interface wlan0; then
        log_info "✓ wlan0 インターフェース発見"
    else
        die "✗ wlan0 インターフェースが見つかりません（無線LAN接続が必要です）"
    fi
    
    if check_interface usb0; then
        log_info "✓ usb0 インターフェース発見"
    else
        die "✗ usb0 インターフェースが見つかりません（USB OTGカーネルモジュールが必要です）"
    fi
    
    # 5. 既存インストール検出
    if [[ -d /etc/azazel-zero ]]; then
        log_warn "⚠️  既存の Azazel-Zero インストールが検出されました"
        log_warn "   場所: /etc/azazel-zero"
        
        if systemctl is-active --quiet azazel-first-minute.service >/dev/null 2>&1; then
            log_warn "   状態: 現在実行中"
            read -p "   続行して上書きしますか？ (y/N): " -r
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                log_info "キャンセルされました"
                exit 0
            fi
        fi
    fi
    
    # 6. インストール状態ファイル初期化
    init_state_file "$@"
    
    # 7. 必要なコマンド確認（インストーラ実行に最低限必要なもののみ）
    # 注: jq, python3 等は Stage 10 でインストールされる
    local required_cmds=("systemctl" "ip" "apt-get")
    for cmd in "${required_cmds[@]}"; do
        if command -v "$cmd" >/dev/null 2>&1; then
            log_debug "✓ コマンド発見: $cmd"
        else
            die "✗ 必須コマンドが見つかりません: $cmd"
        fi
    done
    
    log_info "✓ 事前チェック完了（追加パッケージは Stage 10 でインストール）"
    
    log_info ""
    log_info "════════════════════════════════════════════"
    log_info "✓ Stage 00 完了"
    log_info "════════════════════════════════════════════"
    mark_stage_passed "00"
    return 0
}

main "$@"
