# Azazel-Zero Web UI Installation Guide

## 概要

このガイドは、Azazel-Zero の Web UI を新しい Raspberry Pi Zero 2 W にインストールする手順を説明します。

## 前提条件

- Raspberry Pi Zero 2 W
- Raspberry Pi OS Lite (64-bit) インストール済み
- USB ガジェットモード設定済み（`dtoverlay=dwc2` および `modules-load=dwc2,g_ether`）
- Azazel-Zero コアシステムのインストール済み

## インストール方法

### オプション 1: 自動インストール（推奨）

完全なシステムセットアップ（Web UI 含む）を一括で実行：

```bash
cd ~/Azazel-Zero
sudo ./install.sh --with-webui
```

**オプション：**
- `--with-canary`: OpenCanary ハニーポットを追加
- `--with-epd`: Waveshare E-Paper ドライバを追加
- `--with-ntfy`: ntfy.sh 通知を追加
- `--all`: すべてのオプション機能を有効化
- `--dry-run`: 実行内容を表示のみ（テスト用）

### オプション 2: Web UI のみ追加

既存の Azazel-Zero システムに Web UI のみを追加する場合は、再度 `./install.sh` を実行してください：

```bash
cd ~/Azazel-Zero
sudo ./install.sh --with-webui
```

既存の設定は上書きされず、Web UI 関連のコンポーネントのみが追加・更新されます。

## インストール内容

### 1. Python パッケージ
- Flask 3.1.1+

### 2. ディレクトリ構造
```
~/Azazel-Zero/
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

### 4. ランタイムディレクトリ
- `/run/azazel/`: コントロールソケット用
- `/run/azazel-zero/`: 共有ステート用（`ui_snapshot.json`）

### 5. ファイアウォールルール
- nftables テンプレート (`nftables/first_minute.nft`) に port 8084 を追加

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
```

### 3. ファイアウォールの確認

```bash
# Port 8084 がファイアウォールで許可されているか確認
sudo nft list table inet azazel_fmc | grep 8084
```

出力例：
```
tcp dport { 22, 80, 443, 8081, 8084 } accept
```

### 4. Web UI へのアクセス

#### ローカル（Raspberry Pi 上）
```bash
curl http://127.0.0.1:8084/
```

#### USB ガジェット経由（MacBook から）
```bash
# MacBook のターミナルから
curl http://10.55.0.10:8084/

# ブラウザで開く
open http://10.55.0.10:8084
```

#### Wi-Fi 経由（同一ネットワーク）
```bash
# Raspberry Pi の IP アドレスを確認
ip addr show wlan0 | grep 'inet '

# ブラウザでアクセス
http://<raspberry-pi-ip>:8084
```

## トラブルシューティング

### 問題 1: Port 8084 にアクセスできない

**原因**: ファイアウォールで port 8084 が開いていない

**解決策**:
```bash
# nftables ルールを再適用
sudo systemctl restart azazel-first-minute

# ルールを確認
sudo nft list table inet azazel_fmc | grep 8084
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
ls -la ~/Azazel-Zero/py/azazel_control/daemon.py

# 手動起動でエラーを確認
sudo python3 ~/Azazel-Zero/py/azazel_control/daemon.py
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

### 問題 4: MacBook から ping は通るが HTTP アクセスできない

**原因**: Flask が起動していない、または nftables ルールが古い

**解決策**:
```bash
# Flask が listen しているか確認
sudo ss -tlnp | grep 8084

# nftables テンプレートを確認
grep 8084 ~/Azazel-Zero/nftables/first_minute.nft

# テンプレートと /etc の同期
sudo cp ~/Azazel-Zero/nftables/first_minute.nft /etc/azazel-zero/nftables/
sudo systemctl restart azazel-first-minute
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
curl -H "X-Auth-Token: $TOKEN" http://10.55.0.10:8084/api/state
```

### リモートアクセスの無効化

管理ネットワーク (usb0) のみに制限する場合：

```yaml
# configs/first_minute.yaml
status_api:
  web_host: 10.55.0.10  # 0.0.0.0 から変更
  web_port: 8084
  enable_remote_access: false
```

設定後、サービスを再起動：
```bash
sudo systemctl restart azazel-first-minute
```

## 参考資料

- [Web UI アーキテクチャ](../docs/WEB_UI.md)
- [Azazel-Zero セットアップガイド](../docs/setup-zero.md)
- [README](../README.md)

## 更新履歴

- 2026-01-29: 初版作成（feature/web-ui ブランチ）
