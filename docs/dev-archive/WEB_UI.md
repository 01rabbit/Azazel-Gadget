# Azazel-Zero Web UI

## 概要
Azazel-Zero の Web UI ダッシュボードです。リアルタイムでシステムの状態、疑わしさスコア、ネットワーク情報、検知シグナルを可視化します。

**リモートアクセス対応**：ラップトップやスマートフォンから Wi-Fi 経由でリモート監視可能。

## 機能

### 📊 ダッシュボード
- **現在のステージ**：INIT / NORMAL / PROBE / DEGRADED / CONTAIN / DECEPTION
- **疑わしさスコア**：0-100 のリアルタイム表示（プログレスバー付き）
- **ネットワーク情報**：SSID、BSSID、信号強度、インターフェース
- **トラフィック整形状態**：遅延追加、帯域制限の表示
- **検知シグナル**：Wi-Fi 安全性、プローブ失敗、DNS 不一致、Suricata アラート、証明書不一致
- **設定閾値**：DEGRADED、NORMAL、CONTAIN の閾値表示
- **ステージ遷移履歴**：最新50件の遷移ログ
- **アクセス情報**：リモートアクセス方式、クライアント IP、複数アクセス URL

### 🔄 リアルタイム更新
- 2秒ごとに自動更新
- スムーズなアニメーション効果
- ステージ変更時の色変化

## アクセス方法

### 通常運用時（複数の方法）
Azazel-Zero が稼働している場合、以下の URL でアクセス可能：

#### ローカル（Raspberry Pi 直接接続）
```
http://127.0.0.1:8083/
```

#### 管理ネットワーク経由（ダウンストリーム USB）
```
http://10.55.0.10:8083/
```

#### リモートアクセス（Wi-Fi 同一ネットワーク）
Raspberry Pi のアップストリーム Wi-Fi IP を確認してアクセス：
```
http://<Raspberry Pi の Wi-Fi IP>:8083/
```

**注**: リモートアクセスは設定ファイルで有効化（デフォルト有効）

## リモートアクセス設定

### デフォルト設定（すべてのインターフェースでリッスン）
[configs/first_minute.yaml](../configs/first_minute.yaml) に以下の設定があります：

```yaml
status_api:
  host: 10.55.0.10          # レガシー JSON API（管理ネットワークのみ）
  port: 8082
  web_host: 0.0.0.0         # Web UI バインド（全インターフェース）
  web_port: 8083
  enable_remote_access: true # リモートアクセス有効
```

### リモートアクセスを無効化
特定のインターフェースのみに限定する場合：

```yaml
status_api:
  web_host: 10.55.0.10  # 管理ネットワークのみ
```

設定後、サービスを再起動：
```bash
sudo systemctl restart azazel-first-minute
```

### ファイアウォール ルール
ファイアウォールで Web UI ポート（デフォルト 8083）が許可されています。
[nftables/first_minute.nft](../nftables/first_minute.nft) の `mgmt_ports` セットに自動追加。

## API エンドポイント

### `GET /api/status`
現在のシステム状態を JSON で返します。

**レスポンス例：**
```json
{
  "timestamp": 1706425200.0,
  "stage": "NORMAL",
  "suspicion": 15,
  "reason": "プローブテスト中",
  "uptime": 120.5,
  "upstream": {
    "interface": "wlan0",
    "ssid": "MyWiFi",
    "bssid": "AA:BB:CC:DD:EE:FF",
    "signal": -55
  },
  "downstream": {
    "interface": "usb0",
    "ip": "10.55.0.10"
  },
  "traffic_shaping": {
    "enabled": false,
    "rtt_ms": 0,
    "rate_mbps": 0
  }
}
```

### `GET /api/history`
ステージ遷移履歴を JSON で返します。

**レスポンス例：**
```json
{
  "history": [
    {
      "timestamp": 1706425100.0,
      "from_stage": "NORMAL",
      "to_stage": "PROBE",
      "suspicion": 12,
      "reason": "DNS 不一致検知"
    }
  ],
  "total": 5
}
```

### `GET /api/signals`
検知シグナルの詳細を JSON で返します。

**レスポンス例：**
```json
{
  "timestamp": 1706425200.0,
  "signals": {
    "wifi_tags": 0,
    "probe_fail": 0,
    "dns_mismatch": 1,
    "suricata_alert": 0,
    "cert_mismatch": 0
  }
}
```

### `GET /api/config`
設定情報（閾値、減衰率）を JSON で返します。

**レスポンス例：**
```json
{
  "thresholds": {
    "degrade": 20,
    "normal": 8,
    "contain": 50
  },
  "decay_per_sec": 3,
  "suricata_cooldown_sec": 30
}
```

### `GET /api/access` ⭐ (リモートアクセス用)
現在のアクセス情報（IP、アクセス方式、推奨 URL）を JSON で返します。

**レスポンス例：**
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

**用途**：
- UI が複数インターフェースでアクセス可能な場合、現在のアクセス IP を返す
- リモートアクセス確認、複数デバイスからのアクセス シナリオに対応
- JavaScript から自動検出して UI に表示

## アーキテクチャ

### バックエンド
- **モジュール**: [py/azazel_zero/first_minute/web_api.py](../py/azazel_zero/first_minute/web_api.py)
- **ベース**: Python 標準ライブラリ `http.server.HTTPServer`
- **統合**: [controller.py](../py/azazel_zero/first_minute/controller.py) の `start_status_api()` で起動
- **リモートアクセス**: `web_host: 0.0.0.0` で全インターフェースでリッスン

### フロントエンド
- **技術スタック**: Pure HTML + CSS + JavaScript（ライブラリ不要）
- **スタイル**: モダンなダークテーマ、グラデーション、アニメーション
- **更新方式**: `setInterval()` による2秒ごとのポーリング

### データフロー
1. **コントローラー** → `status_ctx` に状態を書き込み
2. **Web API** → `status_ctx` から読み取り、API レスポンス生成
3. **フロントエンド** → API を定期的にポーリング、DOM を更新

## 設定

### ポート変更
[configs/first_minute.yaml](../configs/first_minute.yaml) を編集：

```yaml
status_api:
  host: 10.55.0.10
  port: 8082      # レガシー JSON API
  web_port: 8083  # Web UI ダッシュボード（変更可能）
```

サービス再起動後に反映：
```bash
sudo systemctl restart azazel-first-minute
```

### 履歴保持件数
[py/azazel_zero/first_minute/web_api.py](../py/azazel_zero/first_minute/web_api.py) の `max_history` を変更：

```python
class WebAPIHandler(BaseHTTPRequestHandler):
    max_history = 100  # デフォルト100件
```

## トラブルシューティング

### ページが表示されない
1. サービスが起動しているか確認：
   ```bash
   sudo systemctl status azazel-first-minute
   ```

2. ポートがリッスンしているか確認：
   ```bash
   sudo netstat -tulpn | grep 8083
   ```

3. ファイアウォールルールを確認：
   ```bash
   sudo nft list table inet azazel_fmc
   ```

### データが更新されない
- ブラウザの開発者ツール（F12）でコンソールエラーを確認
- API エンドポイントに直接アクセスして JSON を確認：
  ```bash
  curl http://10.55.0.10:8083/api/status
  ```

## 開発

### カスタマイズ
- **スタイル変更**: [web_api.py](../py/azazel_zero/first_minute/web_api.py) の `<style>` セクションを編集
- **新規 API 追加**: `WebAPIHandler.do_GET()` に新しいエンドポイントを追加
- **グラフ追加**: Chart.js などのライブラリを `<head>` に追加

### 静的ファイル提供
将来的に CSS/JS を分離する場合：

1. `static/` ディレクトリを作成
2. `_serve_static()` メソッドを実装
3. HTML から `<link rel="stylesheet" href="/static/style.css">` で読み込み

## 関連ファイル

- **Web API 実装**: [py/azazel_zero/first_minute/web_api.py](../py/azazel_zero/first_minute/web_api.py)
- **コントローラー統合**: [py/azazel_zero/first_minute/controller.py](../py/azazel_zero/first_minute/controller.py)
- **設定ファイル**: [configs/first_minute.yaml](../configs/first_minute.yaml)

## スクリーンショット説明

- **ヘッダー**: Azazel-Zero ロゴと「身代わり結界セキュリティゲートウェイ」
- **カード1**: 現在のステージ、疑わしさスコア（プログレスバー）、理由、稼働時間
- **カード2**: ネットワーク情報（SSID、BSSID、信号強度、インターフェース）
- **カード3**: トラフィック整形状態（遅延、帯域制限）
- **カード4**: 検知シグナル（5種類のシグナルカウント）
- **カード5**: 設定閾値（DEGRADED、NORMAL、CONTAIN、減衰率）
- **カード6**: ステージ遷移履歴（時系列リスト）

## ライセンス
Azazel-Zero プロジェクトと同一ライセンス
