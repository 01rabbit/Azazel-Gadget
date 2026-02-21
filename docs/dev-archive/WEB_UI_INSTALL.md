# Azazel-Gadget Web UI Installation Guide

## 概要

このガイドは、Azazel-Gadget の Web UI を新しい Raspberry Pi Zero 2 W にインストールする手順を説明します。

## 前提条件

- Raspberry Pi Zero 2 W
- Raspberry Pi OS Lite (64-bit) インストール済み
- USB ガジェットモード設定済み（`dtoverlay=dwc2` および `modules-load=dwc2,g_ether`）
- Azazel-Gadget コアシステムのインストール済み

## インストール方法

### オプション 1: 自動インストール（推奨）

完全なシステムセットアップ（Web UI 含む）を一括で実行：

```bash
cd ~/azazel
sudo ./install.sh --with-webui
```

**オプション：**
- `--with-canary`: OpenCanary ハニーポットを追加
- `--with-epd`: Waveshare E-Paper ドライバを追加
- `--with-ntfy`: ntfy.sh 通知を追加
- `--all`: すべてのオプション機能を有効化
- `--dry-run`: 実行内容を表示のみ（テスト用）

### オプション 2: Web UI のみ追加

既存の Azazel-Gadget システムに Web UI のみを追加する場合は、再度 `./install.sh` を実行してください：

```bash
cd ~/azazel
sudo ./install.sh --with-webui
```

既存の設定は上書きされず、Web UI 関連のコンポーネントのみが追加・更新されます。

## インストール内容

### 1. Python パッケージ
- Flask 3.1.1+

### 2. ディレクトリ構造
```
~/azazel/
├── azazel_web/
│   ├── app.py                    # Flask アプリケーション
│   ├── templates/
│   │   └── index.html            # ダッシュボード UI
│   └── static/
│       ├── app.js                # フロントエンド JavaScript
│       └── style.css             # スタイル
├── py/azazel_control/
│   ├── daemon.py                 # コントロール・デーモン
│   └── scripts/
│       ├── azctl_refresh.sh      # アクション: 再読込
│       ├── reprobe.sh            # アクション: 再プローブ
│       ├── contain_mode.sh       # アクション: 隔離モード
│       ├── stage_open.sh         # アクション: ステージ開放
│       ├── disconnect.sh         # アクション: 切断
│       └── dump_details.sh       # アクション: 詳細表示
└── systemd/
    └── azazel-control-daemon.service
```

### 3. systemd サービス
- `azazel-control-daemon.service`: Unix ソケットリスナー（アクション実行用）
- `azazel-web.service`: Flask バックエンド（`127.0.0.1:8084`）
- `caddy.service`: HTTPS 終端（`https://10.55.0.10`）

### 4. ランタイムディレクトリ
- `/run/azazel/`: コントロールソケット用
- `/run/azazel-zero/`: 共有ステート用（`ui_snapshot.json`）

### 5. ファイアウォールルール
- nftables テンプレート (`nftables/first_minute.nft`) に Web UI 用ポート（443, 8084）を追加

## インストール後の確認

### 1. サービスの起動

```bash
# Control Daemon を起動
sudo systemctl start azazel-control-daemon

# 自動起動を有効化（まだの場合）
sudo systemctl enable azazel-control-daemon
```

### 2. サービス状態の確認

```bash
# Control Daemon の状態確認
sudo systemctl status azazel-control-daemon

# First-Minute の状態確認（Web UI のデータ源）
sudo systemctl status azazel-first-minute

# HTTPS プロキシの状態確認
sudo systemctl status caddy
```

### 3. ファイアウォールの確認

```bash
# Port 443 がファイアウォールで許可されているか確認
sudo nft list table inet azazel_fmc | grep 443
```

出力例：
```
tcp dport { 22, 80, 443, 8081, 8084 } accept
```

### 4. Web UI へのアクセス

#### ローカル（Raspberry Pi 上）
```bash
curl http://127.0.0.1:8084/        # Flask バックエンド
curl -k https://10.55.0.10/health  # HTTPS エンドポイント
```

#### USB ガジェット経由（MacBook から）
```bash
# MacBook のターミナルから
curl -k https://10.55.0.10/health

# ブラウザで開く
open https://10.55.0.10
```

### 5. ローカルCA証明書の配布（推奨）

ブラウザ警告なしで運用するには、Caddy のローカルCAをクライアントに信頼させます。

```bash
# Pi 側（配布用の証明書）
ls -l /etc/azazel-zero/certs/azazel-webui-local-ca.crt
```

- クライアント端末に `azazel-webui-local-ca.crt` を転送して信頼済み証明書として登録
- 未登録でも `https://10.55.0.10` は開けますが、警告回避操作が必要になる場合があります

Web UI から直接配布する場合：

- メタ情報（SHA256 指紋）：`https://10.55.0.10/api/certs/azazel-webui-local-ca/meta`
- 証明書ダウンロード：`https://10.55.0.10/api/certs/azazel-webui-local-ca.crt`
- ダッシュボードの `Live Notifications` カードにも「CA証明書をダウンロード」ボタンを表示

## リアルタイム通知（SSEブリッジ）手動テスト

### 1. Web UI でストリーム接続を確認
1. ブラウザで `https://10.55.0.10/` を開く
2. `Live Notifications` カードで `Event Stream` が `CONNECTED` になることを確認

### 2. ntfy publish から Web UI 受信を確認
別ターミナルで以下を実行：

```bash
export NTFY_TOKEN="$(sudo cat /etc/azazel/ntfy.token)"
curl -H "Authorization: Bearer ${NTFY_TOKEN}" \
     -H "Title: WebUI SSE Test" \
     -H "Priority: 5" \
     -H "Tags: test,webui" \
     -d "SSE bridge notification test" \
     http://10.55.0.10:8081/azg-alert-critical
```

期待結果：
- Web UI にトースト通知が表示される
- `Unread` バッジが増える
- `Live Notifications` のログに1件追記される

### 3. Browser Notification のベストエフォート確認
1. `通知を有効化` ボタンをクリック
2. 権限が `granted` かつ HTTPS/secure context 条件を満たす場合は OS 通知が表示される
3. 拒否・未対応・HTTP 条件不足の場合は OS 通知なしで、画面内通知（トースト/ログ/バッジ）のみ継続する

## トラブルシューティング

### 問題 1: HTTPS (443) にアクセスできない

**原因**: ファイアウォールで port 443 が開いていない / caddy が停止している

**解決策**:
```bash
# nftables ルールを再適用
sudo systemctl restart azazel-first-minute

# ルールを確認
sudo nft list table inet azazel_fmc | grep 443

# caddy 状態確認
sudo systemctl status caddy
```

### 問題 2: Control Daemon が起動しない

**原因**: Python パッケージの不足、またはファイルパーミッション

**解決策**:
```bash
# Flask がインストールされているか確認
python3 -c "import flask; print(flask.__version__)"

# ログを確認
journalctl -u azazel-control-daemon -n 50

# パーミッションを確認
ls -la ~/azazel/py/azazel_control/daemon.py

# 手動起動でエラーを確認
sudo python3 ~/azazel/py/azazel_control/daemon.py
```

### 問題 3: システムメトリクスが表示されない

**原因**: first-minute コントローラーが ui_snapshot.json を生成していない

**解決策**:
```bash
# first-minute サービスを再起動
sudo systemctl restart azazel-first-minute

# ui_snapshot.json が生成されているか確認
ls -la /run/azazel-zero/ui_snapshot.json

# ログを確認
journalctl -u azazel-first-minute -n 50
```

### 問題 4: MacBook から ping は通るが HTTPS アクセスできない

**原因**: caddy が起動していない、または証明書警告でブロックされている

**解決策**:
```bash
# Flask バックエンドが listen しているか確認
sudo ss -tlnp | grep 8084

# caddy が listen しているか確認
sudo ss -tlnp | grep 443

# caddy 再起動
sudo systemctl restart caddy

# TLS 応答確認（証明書検証をスキップして疎通確認）
curl -kI https://10.55.0.10/
```

## アンインストール

Web UI を削除する場合：

```bash
# サービスを停止・無効化
sudo systemctl stop azazel-control-daemon
sudo systemctl disable azazel-control-daemon

# systemd サービスファイルを削除
sudo rm /etc/systemd/system/azazel-control-daemon.service
sudo systemctl daemon-reload

# Python パッケージを削除（オプション）
pip3 uninstall Flask
```

## セキュリティ設定（オプション）

### 認証トークンの設定

Web UI にアクセス制限をかける場合：

```bash
# トークンを生成
TOKEN=$(head /dev/urandom | tr -dc A-Za-z0-9 | head -c 32)
echo "$TOKEN" > ~/.azazel-zero/web_token.txt
chmod 600 ~/.azazel-zero/web_token.txt

# トークン付きでアクセス
curl -k -H "X-Auth-Token: $TOKEN" https://10.55.0.10/api/state
```

### リモートアクセスの無効化

HTTPS 提供先を管理ネットワーク (`10.55.0.10`) のみに制限する場合は `/etc/caddy/Caddyfile` を編集：

```caddy
https://10.55.0.10 {
    tls internal
    reverse_proxy 127.0.0.1:8084
}
```

設定後、サービスを再起動：
```bash
sudo systemctl restart caddy
```

## 参考資料

- [Web UI アーキテクチャ](./WEB_UI.md)
- [Azazel-Gadget セットアップガイド](./setup-zero.md)
- [README](../README.md)

## 更新履歴

- 2026-01-29: 初版作成（feature/web-ui ブランチ）
