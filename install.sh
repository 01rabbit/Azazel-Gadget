#!/bin/bash
################################################################################
# Azazel-Zero Unified Installer
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
DRY_RUN=0
RESUME=0
DEBUG="${DEBUG:-0}"

# ============================================================================
# ユーティリティ関数（_lib.sh をロードする前）
# ============================================================================

print_usage() {
    cat <<EOF
Azazel-Zero Unified Installer

使用法:
  sudo ./install.sh [OPTIONS]

オプション:
  --with-canary       OpenCanary（ハニーポット）をインストール
  --with-epd          Waveshare E-Paper (デフォルト有効)
  --with-webui        Web UI ダッシュボードをインストール
  --with-ntfy         ntfy.sh push notification をインストール
  --all               すべてのオプションを有効化
  --dry-run           プレビュー（変更を加えない）
  --resume            前回の中断から再開（再起動後用）
  --debug             デバッグログを有効化
  -h, --help          このヘルプを表示

例:
  sudo ./install.sh                                    # 標準チェーンシステム
  sudo ./install.sh --with-canary --with-webui       # オプション付き
  sudo ./install.sh --resume                         # 再起動後の再開

コンストレイント:
  - root 権限が必要
  - 初回実行時、ネットワーク構成変更による再起動が起こる可能性あり
  - 再起動後は --resume フラグで再実行

詳細:
  /home/azazel/Azazel-Zero/docs/INSTALLER_UNIFIED_DESIGN.md
  /home/azazel/Azazel-Zero/docs/DHCP_DNS_TROUBLESHOOTING.md
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
        --all)          WITH_CANARY=1; WITH_EPD=1; WITH_WEBUI=1; WITH_NTFY=1; shift ;;
        --dry-run)      DRY_RUN=1; shift ;;
        --resume)       RESUME=1; shift ;;
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
export WITH_CANARY WITH_EPD WITH_WEBUI WITH_NTFY DRY_RUN DEBUG
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
    echo "  Dry-Run:     $([[ $DRY_RUN -eq 1 ]] && echo "有効" || echo "無効")"
    echo "  Resume:      $([[ $RESUME -eq 1 ]] && echo "有効" || echo "無効")"
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
        bash "$stage_script" || {
            # Stage 20 の特殊ケース：ネットワーク変更サイン
            if [[ "$stage" == "20_network" ]] && [[ $? -eq 0 ]]; then
                # exit code 0 だが再起動が必要なケースもある
                if grep -q "NEEDS_REBOOT" "$INSTALL_STATE_FILE" 2>/dev/null; then
                    log_info "再起動が必要です。プロンプトを確認してください。"
                    exit 0  # 正常終了
                fi
            fi
            
            # その他のステージは失敗扱い
            log_error "Stage $stage で失敗しました"
            failed=true
            break
        }
        
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
    echo "✓ Azazel-Zero インストール完了"
    echo "═══════════════════════════════════════════════════════════"
    echo ""
    echo "ログファイル: $LOG_FILE"
    echo ""
}

main "$@"
