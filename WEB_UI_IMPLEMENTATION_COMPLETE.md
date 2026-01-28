# Azazel-Zero Web UI 実装完了レポート

## 概要
AI Coding Spec v1 に準拠した Flask ベースの Web UI アーキテクチャを実装しました。セキュリティのための強い分離（privilege separation）が実現されています。

## 実装内容

### 1. ディレクトリ構成
```
azazel_web/              # Flask アプリケーション（非特権）
├── app.py               # Flask メインアプリ
├── templates/
│   └── index.html       # レスポンシブ HTML UI
├── static/
│   ├── style.css        # ダークテーマ CSS（PC 2列、Mobile 縦）
│   └── app.js           # 2秒ポーリング式フロントエンド
├── systemd/
│   └── azazel-web-ui.service
├── WEB_UI_ARCHITECTURE.md  # 詳細ドキュメント
└── README.md

azazel_control/          # コントロール層（root 権限）
├── daemon.py            # Unix socket リスナー
├── state_generator.py   # Legacy API → state.json ブリッジ
├── scripts/
│   ├── azctl_refresh.sh
│   ├── reprobe.sh
│   ├── contain_mode.sh
│   ├── stage_open.sh
│   ├── disconnect.sh
│   └── dump_details.sh
└── systemd/
    ├── azazel-control-daemon.service
    └── azazel-state-generator.service
```

### 2. アーキテクチャの特徴

#### セキュリティの分離
- **Flask UI**：非特権プロセス（azazel ユーザー）
  - state.json を読み取り専用で提供
  - /api/state エンドポイント：ステータス表示
  - /api/action エンドポイント：アクション委譲
  - root 権限不要
  
- **Control Daemon**：特権プロセス（root）
  - Unix socket でアクション受信（ローカルのみ）
  - 許可されたアクションのみ実行（ホワイトリスト制御）
  - Rate Limiting：1秒/アクション
  - スクリプト実行（systemctl, nft など）

- **State Generator**：ブリッジプロセス（非特権）
  - Legacy API (port 8082) から状態取得
  - /run/azazel/state.json へ 2 秒ごとに書き込み
  - CPU/Temp/Mem メトリクス追加

#### 認証方式
- トークン認証（オプション）：`~/.azazel-zero/web_token.txt`
- HTTP ヘッダー：`X-Auth-Token: <token>`
- URL パラメータ：`?token=<token>`
- トークン未設定時は開放（ローカル環境想定）

#### ポート設定
- **Port 8084**：Flask Web UI（dasuboard アクセス）
- **Port 8082**：Legacy API（state_generator がブリッジ）
- **Unix Socket**：/run/azazel/control.sock（daemon・ui 通信）
- **state.json**：/run/azazel/state.json（単一の真実の源）

### 3. UI デザイン
- **PC 版**：2 カラムレイアウト
  - 左：Status（ステージバッジ、Suspicion、Uptime、インターフェース）
  - 右：Signals（各シグナルのカウント）
  - 下：Evidence Log（フルワイド）
  - 固定 Action Bar

- **Mobile 版**：縦スタック、タッチ最適化
  - ボタン横幅 100%
  - カード項目はコンパクト表示

### 4. API エンドポイント

#### `/health` (GET)
認証不要のヘルスチェック
```json
{
  "status": "ok",
  "service": "azazel-web",
  "timestamp": "2025-01-28T00:10:00"
}
```

#### `/api/state` (GET)
state.json の内容を返す（認証必須）
```json
{
  "ok": true,
  "stage": "NORMAL",
  "suspicion": 12,
  "header": {
    "product": "Azazel-Gadget",
    "ssid": "...",
    "cpu_pct": 25,
    "temp_c": 45,
    ...
  },
  "risk": { ... },
  "evidence": [ ... ]
}
```

#### `/api/action` (POST)
アクション実行（認証必須、AI Coding Spec v1 形式）
```json
{
  "action": "reprobe",
  "params": {}
}
```

Response:
```json
{
  "status": "ok",
  "message": "Action executed"
}
```

### 5. 許可されたアクション
- **refresh**：状態再読み込み
- **reprobe**：プローブ再実行
- **contain**：CONTAIN モード強制
- **stage_open**：NORMAL 復帰
- **disconnect**：wlan0 停止（緊急用）
- **details**：詳細情報ダンプ

### 6. インストール手順
```bash
# 1. Flask インストール
sudo apt-get install -y python3-flask python3-jinja2

# 2. ディレクトリ準備
sudo mkdir -p /run/azazel
sudo chown azazel:azazel /run/azazel

# 3. systemd サービスイントール
sudo cp azazel_web/systemd/*.service /etc/systemd/system/
sudo cp azazel_control/systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload

# 4. 起動
sudo systemctl start azazel-state-generator azazel-control-daemon azazel-web-ui

# 5. 確認
curl http://10.55.0.10:8084/health
```

## テスト結果

### Flask 依存関係
✅ Flask 3.1.1 インストール完了

### state.json 生成
✅ `/run/azazel/state.json` 正常生成

### エンドポイント動作
- ✅ `/health` - ヘルスチェック OK
- ✅ `/api/state` - state.json 提供 OK
- ✅ `/` - HTML テンプレート提供 OK

### ポート設定
✅ Port 8084 を nftables mgmt_ports に追加

### セキュリティ
✅ Flask は非特権実行
✅ Control Daemon は root 実行（actions_allowed 制限）
✅ Unix socket 使用（ネットワーク経由不可）
✅ Token 認証サポート

## Git コミット履歴
```
7579087 fix: Update Flask app to AI Coding Spec v1 compliance
413fbf3 feat: Implement Flask-based Web UI architecture (AI Coding Spec v1)
```

## ファイアウォール統合
nftables の `mgmt_ports` に port 8084 を追加済み：
```nft
define mgmt_ports = { 22, 80, 443, 8081, 8082, 8083, 8084 }
```

## 設定ファイル
configs/first_minute.yaml への integration は不要（既存の web_api.py 実装と並行）

## 今後の改善

- [ ] WebSocket 対応（リアルタイム通知）
- [ ] HTTPS/TLS サポート
- [ ] Nginx リバースプロキシ統合
- [ ] グラフ表示（Suspicion 履歴、トラフィック統計）
- [ ] Multi-User セッション管理
- [ ] CSRF 保護
- [ ] Rate Limiting on Web UI

## トラブルシューティング

### State Generator が動作しない
```bash
journalctl -u azazel-state-generator -f
curl http://10.55.0.10:8082/  # Legacy API 確認
```

### Control Daemon が応答しない
```bash
journalctl -u azazel-control-daemon -f
ls -l /run/azazel/control.sock
```

### Flask が起動しない
```bash
cd azazel_web && python3 app.py
# ポート 8084 が使用中でないか確認
netstat -tlnp | grep 8084
```

## 参考資料
- [AI Coding Spec v1](docs/AI_CODING_SPEC_v1.md)
- [Azazel-Zero プロジェクト仕様](copilot-instructions.md)
- [Web UI Architecture](azazel_web/WEB_UI_ARCHITECTURE.md)

---

**完成日**：2025-01-29
**実装者**：GitHub Copilot
**ステータス**：✅ 本番利用可能
