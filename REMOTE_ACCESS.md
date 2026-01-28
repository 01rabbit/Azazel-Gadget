# Web UI リモートアクセス設定ガイド

## 概要
Azazel-Zero Web UI がリモートアクセス対応されました。ラップトップやスマートフォンから Wi-Fi 経由で Raspberry Pi Zero 2 W のダッシュボードを監視できます。

## アクセス方法

### 1️⃣ ローカル直接接続（Raspberry Pi 直接）
```bash
http://127.0.0.1:8083/
```
- USB ケーブルで直接接続した場合

### 2️⃣ 管理ネットワーク経由（ダウンストリーム）
```bash
http://10.55.0.10:8083/
```
- USB OTG ガジェットモード経由
- 静的 IP、常に利用可能

### 3️⃣ リモートアクセス（Wi-Fi 経由）⭐
```bash
http://<Raspberry Pi の Wi-Fi IP>:8083/
```
- 同一 Wi-Fi ネットワーク内のラップトップ
- スマートフォンブラウザでの確認
- **完全にリモート対応**

## 実装内容

### アーキテクチャ
```
┌─────────────────┐
│  Azazel-Zero    │
│  (Raspberry Pi) │
└────────┬────────┘
         │
    ┌────┴─────────────────┐
    │                      │
┌───▼───────┐        ┌────▼──────┐
│ wlan0     │        │  usb0      │
│(Wi-Fi UP) │        │(OTG DOWN)  │
└───┬───────┘        └────┬──────┘
    │                     │
    │ 0.0.0.0:8083 リッスン
    │(全インターフェース)
    │                     │
┌───▼────────────┐   ┌───▼──────────┐
│ ラップトップ    │   │ ホストデバイス  │
│(Wi-Fi 同一NW)  │   │ (USB 直接)    │
└────────────────┘   └──────────────┘
```

### 設定パラメータ
[configs/first_minute.yaml](configs/first_minute.yaml):
```yaml
status_api:
  host: 10.55.0.10          # レガシー API（管理ネットワーク限定）
  port: 8082
  web_host: 0.0.0.0         # 🌐 全インターフェース対応
  web_port: 8083
  enable_remote_access: true # ✅ リモートアクセス有効
```

### ファイアウォール ルール
[nftables/first_minute.nft](nftables/first_minute.nft):
```nftables
set mgmt_ports {
  type inet_service
  elements = { 22, 80, 443, 8081, 8082, 8083 }
}
```
- ポート 8082, 8083 を管理ポートとして許可

### API エンドポイント
新規追加: `GET /api/access`
```bash
curl http://192.168.1.100:8083/api/access
```

レスポンス:
```json
{
  "access_urls": {
    "current": "http://192.168.1.100:8083/",
    "localhost": "http://127.0.0.1:8083/",
    "management": "http://10.55.0.10:8083/"
  },
  "client_ip": "192.168.1.50",
  "access_method": "remote"
}
```

## 使用シナリオ

### シナリオ1: 開発中のテスト
```bash
# Raspberry Pi で SSH ログイン
ssh pi@raspberry.local

# Web UI テストサーバー起動
cd Azazel-Zero
PYTHONPATH=py python3 test_web_ui.py

# ラップトップのブラウザで確認
# http://192.168.1.100:8083/
```

### シナリオ2: 本番運用での監視
```bash
# Azazel-Zero サービス起動（自動起動時）
sudo systemctl start azazel-first-minute

# ラップトップから Wi-Fi 経由でリモート監視
# http://azazel-zero.local:8083/
# または
# http://192.168.1.100:8083/
```

### シナリオ3: スマートフォンからの確認
QR コードなどで Web UI へのリンクを共有：
```
http://192.168.1.100:8083/
```
→ スマートフォンの Safari/Chrome で自動更新ダッシュボードを表示

## セキュリティに関する注意

⚠️ **重要**: 現在、Web UI は HTTP のみで HTTPS 非対応です。

### 対策方法

#### 方法1: ローカルネットワークのみに限定
```yaml
# 信頼できるローカルネットワーク内のみで運用
web_host: 10.55.0.10
```

#### 方法2: VPN/SSH トンネル経由でアクセス
```bash
# ラップトップから SSH トンネル経由
ssh -L 8083:localhost:8083 pi@192.168.1.100

# ローカルホストでアクセス
# http://localhost:8083/
```

#### 方法3: リバースプロキシ（nginx + SSL）
```bash
# nginx を Raspberry Pi にインストール
sudo apt-get install -y nginx

# /etc/nginx/sites-available/azazel-ui に SSL 設定
# Web UI をリバースプロキシ経由で HTTPS 公開
```

#### 方法4: 将来対応予定
- Self-signed certificate での HTTPS サポート
- API トークン認証
- IP ホワイトリスト

## トラブルシューティング

### リモートアクセスできない場合

#### 1. Raspberry Pi の Wi-Fi IP を確認
```bash
ssh pi@raspberry.local
ip addr show wlan0 | grep "inet "
# inet 192.168.1.100/24 brd 192.168.1.255 scope global dynamic wlan0
```

#### 2. ファイアウォール ルールを確認
```bash
sudo nft list table inet azazel_fmc | grep mgmt_ports
# elements = { 22, 80, 443, 8081, 8082, 8083 }
```

#### 3. Web サーバーがリッスン中か確認
```bash
sudo ss -tulpn | grep 8083
# tcp  LISTEN 0 128 0.0.0.0:8083 0.0.0.0:* users:(("python3",pid=1234,fd=3))
```

#### 4. ログを確認
```bash
journalctl -u azazel-first-minute -n 50 | grep -i "web ui\|web_host"
```

### 速度が遅い場合
- Wi-Fi 信号強度を確認
- 同一ネットワーク内の干渉チェック
- 更新間隔を変更（デフォルト 2秒）

### UI が真っ黒な場合
- ブラウザキャッシュをクリア（Ctrl+Shift+Delete）
- 別ブラウザで確認
- ブラウザコンソール（F12）でエラーを確認

## 設定変更手順

### リモートアクセスを無効化
特定ネットワークのみに限定：

```yaml
# configs/first_minute.yaml
status_api:
  web_host: 10.55.0.10  # 管理ネットワークのみ
```

設定反映：
```bash
sudo systemctl restart azazel-first-minute
```

### ポート番号を変更
```yaml
status_api:
  web_port: 9000  # 8083 → 9000 に変更
```

ファイアウォールルール更新（自動）、サービス再起動で反映。

## 関連ファイル

| ファイル | 説明 |
|---------|------|
| [py/azazel_zero/first_minute/web_api.py](py/azazel_zero/first_minute/web_api.py) | Web API サーバー実装 |
| [py/azazel_zero/first_minute/controller.py](py/azazel_zero/first_minute/controller.py) | コントローラー統合 |
| [configs/first_minute.yaml](configs/first_minute.yaml) | 設定ファイル |
| [nftables/first_minute.nft](nftables/first_minute.nft) | ファイアウォール ルール |
| [docs/WEB_UI.md](docs/WEB_UI.md) | 詳細ドキュメント |

## 今後の改善予定

- [ ] HTTPS/SSL サポート
- [ ] API トークン認証
- [ ] IP ホワイトリスト
- [ ] WebSocket でのリアルタイム push
- [ ] グラフ可視化（Chart.js 統合）
- [ ] ログダウンロード機能
- [ ] 多言語対応（英語）
- [ ] スマートフォン UI 最適化

## ライセンス
Azazel-Zero プロジェクトと同一
