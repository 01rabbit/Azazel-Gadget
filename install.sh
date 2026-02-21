#!/bin/bash
################################################################################
# Azazel-Gadget Unified Installer
#
# メインエントリーポイント - 統合インストーラ
# 
# 使用法:
#   sudo ./install.sh                              # 標準インストール
#   sudo ./install.sh --with-webui --with-canary  # オプション付き
#   sudo ./install.sh --dry-run                   # プレビュー
#   sudo ./install.sh --resume                    # 再開（再起動後用）
################################################################################

set -euo pipefail

# ============================================================================
# 初期化
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
INSTALLER_ROOT="$SCRIPT_DIR/installer"

# グローバル設定
WITH_CANARY=0
WITH_EPD=1  # デフォルトで E-Paper 有効
WITH_WEBUI=0
WITH_NTFY=0
WITH_PORTAL_VIEWER=0
DRY_RUN=0
RESUME=0
AUTO_REBOOT=0
DEBUG="${DEBUG:-0}"

# ============================================================================
# ユーティリティ関数（_lib.sh をロードする前）
# ============================================================================

print_usage() {
    cat <<EOF
Azazel-Gadget Unified Installer

使用法:
  sudo ./install.sh [OPTIONS]

オプション:
  --with-canary       OpenCanary（ハニーポット）をインストール
  --with-epd          Waveshare E-Paper (デフォルト有効)
  --with-webui        Web UI ダッシュボードをインストール（HTTPS/Caddy 含む）
  --with-ntfy         ntfy サーバ (TCP/8081) と通知連携をインストール
  --with-portal-viewer  Captive Portal 操作用 noVNC ビューアをインストール
  --all               --with-canary --with-epd --with-webui --with-ntfy --with-portal-viewer を有効化
  --dry-run           プレビュー（変更を加えない）
  --resume            前回の中断から再開（再起動後用）
  --auto-reboot       Stage 20 後に必要なら自動再起動
  --debug             デバッグログを有効化
  -h, --help          このヘルプを表示

例:
  sudo ./install.sh                                    # 標準チェーンシステム
  sudo ./install.sh --all                             # すべてのオプションを有効化
  sudo ./install.sh --with-canary --with-webui       # オプション付き
  sudo ./install.sh --with-ntfy                       # ntfy 通知連携を追加
  sudo ./install.sh --resume                         # 再起動後の再開

コンストレイント:
  - root 権限が必要
  - 初回実行時、ネットワーク構成変更による再起動が起こる可能性あり
  - 再起動後は --resume フラグで再実行
  - --resume は Stage 30 以降のみ実行（Stage 10 の依存インストールは再実行しない）

詳細:
  $PROJECT_ROOT/docs/INSTALLER_UNIFIED_DESIGN.md
  $PROJECT_ROOT/docs/DHCP_DNS_TROUBLESHOOTING.md
EOF
}

# ============================================================================
# 引数パース
# ============================================================================

while [[ $# -gt 0 ]]; do
    case "$1" in
        --with-canary)  WITH_CANARY=1; shift ;;
        --with-epd)     WITH_EPD=1; shift ;;
        --with-webui)   WITH_WEBUI=1; shift ;;
        --with-ntfy)    WITH_NTFY=1; shift ;;
        --with-portal-viewer) WITH_PORTAL_VIEWER=1; shift ;;
        --all)          WITH_CANARY=1; WITH_EPD=1; WITH_WEBUI=1; WITH_NTFY=1; WITH_PORTAL_VIEWER=1; shift ;;
        --dry-run)      DRY_RUN=1; shift ;;
        --resume)       RESUME=1; shift ;;
        --auto-reboot)  AUTO_REBOOT=1; shift ;;
        --debug)        DEBUG=1; shift ;;
        -h|--help)      print_usage; exit 0 ;;
        *)              echo "不明なオプション: $1"; print_usage; exit 1 ;;
    esac
done

# ============================================================================
# 共通ライブラリをロード
# ============================================================================

if [[ ! -f "$INSTALLER_ROOT/_lib.sh" ]]; then
    echo "ERROR: インストーラライブラリが見つかりません: $INSTALLER_ROOT/_lib.sh"
    exit 1
fi

# 環境変数をエクスポート
export WITH_CANARY WITH_EPD WITH_WEBUI WITH_NTFY WITH_PORTAL_VIEWER DRY_RUN RESUME AUTO_REBOOT DEBUG
export INSTALLER_ROOT PROJECT_ROOT

# ライブラリをロード
source "$INSTALLER_ROOT/_lib.sh"

# ============================================================================
# メインインストール処理
# ============================================================================

main() {
    init_installer
    
    # オプション表示
    echo "オプション:"
    echo "  OpenCanary:  $([[ $WITH_CANARY -eq 1 ]] && echo "有効" || echo "無効")"
    echo "  E-Paper:     $([[ $WITH_EPD -eq 1 ]] && echo "有効" || echo "無効")"
    echo "  Web UI:      $([[ $WITH_WEBUI -eq 1 ]] && echo "有効" || echo "無効")"
    echo "  ntfy:        $([[ $WITH_NTFY -eq 1 ]] && echo "有効" || echo "無効")"
    echo "  PortalView:  $([[ $WITH_PORTAL_VIEWER -eq 1 ]] && echo "有効" || echo "無効")"
    echo "  Dry-Run:     $([[ $DRY_RUN -eq 1 ]] && echo "有効" || echo "無効")"
    echo "  Resume:      $([[ $RESUME -eq 1 ]] && echo "有効" || echo "無効")"
    echo "  Auto-reboot: $([[ $AUTO_REBOOT -eq 1 ]] && echo "有効" || echo "無効")"
    echo ""
    
    # 確認
    if [[ $DRY_RUN -eq 0 ]]; then
        echo "⚠️  このスクリプトはシステムを変更します"
        read -p "続行してよろしいですか？ (y/N): " -r
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "キャンセルされました"
            exit 0
        fi
    fi
    
    echo ""
    
    # ============================================================================
    # Stage 実行
    # ============================================================================
    
    local stages=(
        "00_precheck"
        "10_dependencies"
        "20_network"
        "30_config"
        "40_services"
        "99_validate"
    )
    
    # --resume の場合、Stage 20 以前をスキップ
    local start_idx=0
    if [[ $RESUME -eq 1 ]]; then
        log_info "再開モード: Stage 30 以降を実行"
        start_idx=3  # Stage 30 から開始
    fi
    
    local failed=false
    for (( i=start_idx; i<${#stages[@]}; i++ )); do
        local stage="${stages[$i]}"
        local stage_script="$INSTALLER_ROOT/stages/${stage}.sh"
        
        if [[ ! -f "$stage_script" ]]; then
            log_error "Stage スクリプトが見つかりません: $stage_script"
            failed=true
            break
        fi
        
        # Stage スクリプト実行
        if ! bash "$stage_script"; then
            log_error "Stage $stage で失敗しました"
            failed=true
            break
        fi

        # Stage 20 の特殊ケース: 成功終了でも再起動が必要な場合がある
        if [[ "$stage" == "20_network" ]]; then
            if [[ "$(get_state "stage")" == "20_NEEDS_REBOOT" ]]; then
                log_warn "Stage 20 により再起動が必要です。"

                if [[ "$DRY_RUN" == "1" ]]; then
                    log_info "Dry-run のため再起動は実行しません。"
                    log_info "実運用では再起動後に次を実行してください: sudo ./install.sh --resume"
                    exit 0
                fi

                if [[ "$AUTO_REBOOT" == "1" ]]; then
                    log_warn "5秒後に自動再起動します..."
                    sleep 5
                    reboot
                    exit 0
                fi

                if [[ -t 0 ]]; then
                    read -p "今すぐ再起動しますか？ (Y/n): " -r
                    if [[ ! "${REPLY:-}" =~ ^[Nn]$ ]]; then
                        log_info "再起動を実行します..."
                        reboot
                        exit 0
                    fi
                fi

                log_info "再起動後にインストールを再開してください:"
                log_info "  sudo ./install.sh --resume"
                exit 0
            fi
        fi
        
        echo ""
    done
    
    if [[ "$failed" == "true" ]]; then
        log_error ""
        log_error "インストールが失敗しました"
        log_error "ログを確認: $LOG_FILE"
        exit 1
    fi
    
    # ============================================================================
    # 完了
    # ============================================================================
    
    echo ""
    echo "═══════════════════════════════════════════════════════════"
    echo "✓ Azazel-Gadget インストール完了"
    echo "═══════════════════════════════════════════════════════════"
    echo ""
    echo "ログファイル: $LOG_FILE"
    echo ""
}

main "$@"
