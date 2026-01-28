# Azazel-Zero Web UI アーキテクチャ

このディレクトリ群は **AI Coding Spec v1** に基づく完全な Web UI 実装です。

## アーキテクチャ概要

```
┌─────────────┐
│   Browser   │
└──────┬──────┘
       │ HTTP (port 8084)
       ▼
┌──────────────────┐
│  Flask Web UI    │ (非特権プロセス)
│  azazel_web/     │
└──────┬───────────┘
       │ Unix Socket
       ▼
┌──────────────────┐
│ Control Daemon   │ (root プロセス)
│ azazel_control/  │
└──────┬───────────┘
       │ fork/exec
       ▼
┌──────────────────┐
│ Action Scripts   │ (systemctl, nft, etc.)
│ scripts/*.sh     │
└──────────────────┘
```

### 分離原則（Separation of Concerns）
- **Flask App**：state.json を **読み取り専用** で提供。root 権限不要。
- **Control Daemon**：Unix socket でアクションを受け取り、root 権限でスクリプト実行。
- **State Generator**：Legacy API (port 8082) から state.json を生成（ブリッジ層）。

## コンポーネント構成

### 1. Web UI (`azazel_web/`)
- **app.py**：Flask アプリケーション
  - `/api/state` - 現在の状態を JSON で返す
  - `/api/action` - アクションを Control Daemon へ委譲
  - `/health` - ヘルスチェック
- **templates/index.html**：レスポンシブ UI（PC: 2カラム、Mobile: 縦スタック）
- **static/style.css**：ダークテーマ CSS
- **static/app.js**：2秒ポーリングによる自動更新

### 2. Control Daemon (`azazel_control/`)
- **daemon.py**：Unix socket サーバー（`/run/azazel/control.sock`）
  - 許可されたアクション：refresh, reprobe, contain, disconnect, stage_open, details
  - Rate Limiting：1秒/アクション
  - セキュリティ：actions_allowed リストで制限
- **state_generator.py**：Legacy API → state.json ブリッジ
  - Legacy API (port 8082) から現在の状態を取得
  - `/run/azazel/state.json` へ2秒ごとに書き出し
  - システムメトリクス（CPU/Temp/Mem）を追加

### 3. Action Scripts (`azazel_control/scripts/`)
- **azctl_refresh.sh**：状態を再読み込み（mock：systemctl reload）
- **reprobe.sh**：プローブを再実行（mock：echo simulation）
- **contain_mode.sh**：CONTAIN モードへ強制遷移
- **stage_open.sh**：NORMAL モードへ復帰
- **disconnect.sh**：wlan0 を停止（緊急用）
- **dump_details.sh**：/tmp/azazel_details.json へ詳細ダンプ

## セットアップ手順

### 1. 依存関係インストール
```bash
pip3 install flask
```

### 2. ディレクトリ準備
```bash
sudo mkdir -p /run/azazel
sudo chown azazel:azazel /run/azazel
```

### 3. systemd サービスインストール
```bash
# Control Daemon (root 権限必要)
sudo cp azazel_control/systemd/azazel-control-daemon.service /etc/systemd/system/
sudo cp azazel_control/systemd/azazel-state-generator.service /etc/systemd/system/
sudo cp azazel_web/systemd/azazel-web-ui.service /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable azazel-state-generator azazel-control-daemon azazel-web-ui
sudo systemctl start azazel-state-generator azazel-control-daemon azazel-web-ui
```

### 4. 動作確認
```bash
# State Generator が state.json を生成しているか
cat /run/azazel/state.json

# Control Daemon が Unix socket を開いているか
ls -l /run/azazel/control.sock

# Flask UI が起動しているか
curl http://localhost:8084/health

# ブラウザから
http://10.55.0.10:8084/
```

### 5. トークン認証（オプション）
```bash
# トークンを生成して保存
echo "your-secret-token" > ~/.azazel-zero/web_token.txt
chmod 600 ~/.azazel-zero/web_token.txt

# ブラウザでトークン付きアクセス
http://10.55.0.10:8084/?token=your-secret-token
```

## API エンドポイント

### `/api/state` (GET)
現在の状態を返す（state.json の内容）

```json
{
  "stage": "NORMAL",
  "suspicion": 12,
  "uptime_sec": 3600,
  "upstream": "wlan0",
  "downstream": "usb0",
  "signals": {
    "probe_fail": 0,
    "dns_mismatch": 1,
    "wifi_tags": 0,
    "suricata_alert": 0
  },
  "evidence": [
    {"timestamp": "2025-01-28T23:45:00", "message": "Transitioned to NORMAL"}
  ],
  "metrics": {
    "cpu_pct": 25,
    "temp_c": 45,
    "mem_used_mb": 512,
    "mem_total_mb": 512
  }
}
```

### `/api/action` (POST)
アクションを実行

```bash
curl -X POST http://10.55.0.10:8084/api/action \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: your-secret-token" \
  -d '{"action": "reprobe", "params": {}}'
```

許可されたアクション：
- **refresh**：状態を再読み込み
- **reprobe**：プローブを再実行
- **contain**：CONTAIN モードへ強制遷移
- **stage_open**：NORMAL モードへ復帰
- **disconnect**：wlan0 を停止（緊急用）
- **details**：詳細情報をダンプ

### `/health` (GET)
ヘルスチェック（認証不要）

```json
{
  "status": "ok",
  "service": "azazel-web",
  "timestamp": "2025-01-28T23:50:00"
}
```

## ファイアウォール設定

nftables にポート 8084 を追加：

```nft
# /home/azazel/Azazel-Zero/nftables/first_minute.nft
define mgmt_ports = { 22, 80, 443, 8081, 8082, 8083, 8084 }
```

適用：
```bash
sudo nft -f nftables/first_minute.nft
```

## トラブルシューティング

### State Generator が動作しない
```bash
journalctl -u azazel-state-generator -f
# Legacy API (port 8082) が起動しているか確認
curl http://10.55.0.10:8082/
```

### Control Daemon に接続できない
```bash
journalctl -u azazel-control-daemon -f
# Unix socket のパーミッション確認
ls -l /run/azazel/control.sock
```

### Flask UI が起動しない
```bash
journalctl -u azazel-web-ui -f
# 手動起動でエラー確認
cd azazel_web
python3 app.py
```

## セキュリティ考慮事項

1. **Flask App は非特権**：state.json を読むだけ、書き込まない。
2. **Control Daemon は root**：ただしアクション一覧を厳格に制限。
3. **Rate Limiting**：各アクション1秒/回の制限。
4. **Token 認証**：`~/.azazel-zero/web_token.txt` でアクセス制御（オプション）。
5. **Unix Socket**：ローカル通信のみ、ネットワーク経由不可。

## 今後の拡張

- [ ] WebSocket 対応（リアルタイム通知）
- [ ] 複数アクションの一括実行（Tactics Engine 統合）
- [ ] グラフ表示（Suspicion 履歴、トラフィック統計）
- [ ] HTTPS 対応（Nginx リバースプロキシ経由）
- [ ] E-Paper ディスプレイ連携（現在の UI をミラー）

## ライセンス

本プロジェクトのライセンスに従います。
