# ntfy 通知基盤 (Azazel-Gadget)

## 概要

Azazel-Gadget に **ntfy.sh** を統合し、USB ローカルセグメント内で自己ホスト型プッシュ通知を実現します。

```
┌─────────────────────────────────────────────────────┐
│  Raspberry Pi Zero 2 W (Azazel-Gadget)              │
│  ┌─────────────────────────────────────────────┐   │
│  │ first_minute controller (2秒周期)          │   │
│  │ - 状態遷移検知 → notify_alert()            │   │
│  │ - signals (suricata, dns) → notify_alert()│   │
│  └───────────────────┬─────────────────────────┘   │
│                      │ HTTP POST                     │
│  ┌────────────────────▼──────────────────────────┐  │
│  │  ntfy.sh Server (port 8081)                  │  │
│  │  - USB0 (10.55.0.10:8081) のみリッスン      │  │
│  │  - Bearer トークン認証                       │  │
│  │  - Topic: azg-alert-critical (アラート)     │  │
│  │  - Topic: azg-info-status (情報)            │  │
│  └────────────────────┬──────────────────────────┘  │
│                      │ Websocket/SSE                │
└──────────────────────┼────────────────────────────-─┘
                       │
        ┌──────────────┼──────────────┐
        │              │              │
    ┌───▼──────┐  ┌───▼──────┐  ┌───▼──────┐
    │ Android  │  │   iOS    │  │ macOS    │
    │ (ntfy)   │  │  (ntfy)  │  │  (curl)  │
    └──────────┘  └──────────┘  └──────────┘
```

## インストール (手動)

### 前提条件
- Raspberry Pi Zero 2 W (Bookworm OS)
- Root アクセス
- ポート 8081 が未使用

### Step 1: ポート確認
```bash
sudo ss -tulpen | grep -E ':(8081|8084)\b'
# No output → OK
```

### Step 2: 自動インストール
```bash
sudo bash /home/azazel/Azazel-Zero/scripts/install_ntfy.sh
```

スクリプトが実行する内容：
1. ✓ ポート 8081 の空きを確認
2. ✓ ntfy パッケージをインストール
3. ✓ `/etc/ntfy/server.yml` を設定
4. ✓ ntfy ユーザと Bearer トークンを生成
5. ✓ トークンを `/etc/azazel/ntfy.token` に保存
6. ✓ systemd サービスを enable/start

### Step 3: Azazel 設定を更新
```yaml
# /etc/azazel-zero/first_minute.yaml
notify:
  enabled: true
  ntfy:
    base_url: "http://10.55.0.10:8081"
    token_file: "/etc/azazel/ntfy.token"
    topic_alert: "azg-alert-critical"
    topic_info: "azg-info-status"
    cooldown_sec: 30
  thresholds:
    dns_mismatch_alert: 3
    temp_c_alert: 75
```

### Step 4: サービス再起動
```bash
sudo systemctl restart azazel-first-minute
```

## 動作確認

### テスト送信 (curl)
```bash
export NTFY_TOKEN="$(sudo cat /etc/azazel/ntfy.token)"

curl -H "Authorization: Bearer ${NTFY_TOKEN}" \
     -H "Title: Azazel Test" \
     -H "Priority: 5" \
     -H "Tags: test,alert" \
     -d "Hello from Azazel-Gadget!" \
     http://10.55.0.10:8081/azg-alert-critical
```

### クライアント購読 (Android)
1. ntfy 公式アプリをインストール
2. [設定] → [サーバ] → `http://10.55.0.10:8081` を追加
3. トピック `azg-alert-critical` を購読

### クライアント購読 (iOS)
1. ntfy 公式アプリをインストール
2. サーバ設定で `http://10.55.0.10:8081` を指定
3. トピック `azg-alert-critical` を購読

※ ローカル IP アクセスは iOS/macOS でセキュリティ制限がある場合があります。

## 通知イベント

### 状態遷移通知
- **INIT** → **PROBE**: `INFO_TOPIC` (priority=2)
- **PROBE** → **DEGRADED**: `ALERT_TOPIC` (priority=4)
- **DEGRADED** → **CONTAIN**: `ALERT_TOPIC` (priority=5)
- **CONTAIN** → **NORMAL**: `INFO_TOPIC` (priority=2)

### シグナル通知
- **Suricata アラート**: `ALERT_TOPIC` (priority=5, tags: suricata, ids, 重大度)
- **DNS 不一致 (≥3回)**: `ALERT_TOPIC` (priority=5, tags: dns, warning)

### 重複抑制
同一イベントキー（例: `state_change:PROBE->DEGRADED`）は 30 秒以内の再通知を抑制。

## ポート &ファイアウォール

### ポート設計
| ポート | サービス | I/F | 用途 |
|--------|---------|-----|------|
| 8081 | ntfy | usb0 | プッシュ通知 |
| 8082 | Status API | 127.0.0.1 | 内部 JSON API |
| 8083 | WebUI (旧) | 0.0.0.0 | ダッシュボード |
| 8084 | WebUI (新) | 0.0.0.0 | ダッシュボード |

### nftables ルール
```
input chain:
  iifname usb0 tcp dport { 22, 80, 443, 8081, 8084 } accept

stage_contain:
  ip daddr 10.55.0.10 tcp dport @mgmt_ports accept
```

**ポート 8081 は既に mgmt_ports セットに含まれているため、CONTAIN 中も管理トラフィックが通過します。**

## ファイル構成

```
Azazel-Zero/
├── py/azazel_zero/first_minute/
│   ├── notifier.py                 # ★ ntfy クライアント実装
│   ├── controller.py               # ★ notifier 統合フック
│   └── config.py                   # ★ notify 設定スキーマ
├── configs/
│   └── first_minute.yaml           # ★ notify セクション追加
├── scripts/
│   └── install_ntfy.sh             # ★ 自動インストール
└── test_ntfy_notifier.py           # ★ ユニットテスト (10 cases)
```

## Python API

### NtfyNotifier の使用例
```python
from azazel_zero.first_minute.notifier import NtfyNotifier

notifier = NtfyNotifier(
    base_url="http://10.55.0.10:8081",
    token="tk_xxx...",
    topic_alert="azg-alert-critical",
    topic_info="azg-info-status",
    cooldown_sec=30,
)

# アラート送信
notifier.notify_alert(
    title="STAGE=DEGRADED",
    body="DNS mismatch detected: 3+ mismatches",
    tags=["dns", "warning"],
    priority=5,
    event_key="dns_mismatch:threshold_exceeded",  # 重複抑制キー
)

# 情報通知
notifier.notify_info(
    title="State: PROBE → NORMAL",
    body="Azazel-Gadget transitioned to NORMAL",
    tags=["state-change"],
    priority=2,
)
```

### FirstMinuteController での統合
```python
# 状態遷移検知（run_loop 内で自動）
if state != self.current_stage:
    self._notify_state_transition(self.current_stage, state)

# シグナル検知（suricata, dns_mismatch）
if self.suricata_bumped():
    self._notify_signal_alert("suricata_alert", "Severity: High", tags=["ids"])

if self.last_probe.dns_mismatch >= dns_threshold:
    self._notify_signal_alert("dns_mismatch", "3+ mismatches detected", tags=["dns"])
```

## トラブルシューティング

### ntfy サービスが起動しない
```bash
sudo systemctl status ntfy
sudo journalctl -u ntfy -f
```

**原因**: ポート 8081 が既に使用中
```bash
sudo lsof -i :8081
# → 使用しているプロセスを特定して停止
```

### トークンファイルが見つからない
```bash
ls -la /etc/azazel/ntfy.token
# パーミッションが 0600 であることを確認
```

### Azazel 側で通知が送信されない
```bash
sudo systemctl status azazel-first-minute
sudo journalctl -u azazel-first-minute -f | grep -i "ntfy\|notif"
```

**確認項目**:
1. `notify.enabled: true` か？
2. `/etc/azazel/ntfy.token` は読取可能か？
3. HTTP 接続テスト:
   ```bash
   sudo curl -H "Authorization: Bearer $(cat /etc/azazel/ntfy.token)" \
        http://10.55.0.10:8081/azg-alert-critical
   ```

### WebUI（8084）と競合
ポート 8084 は WebUI 専用です。ntfy は **8081** のみを使用。

## テスト

```bash
# ユニットテスト（10 test cases）
cd /home/azazel/Azazel-Zero
python3 test_ntfy_notifier.py

# すべてのテストが `OK` で終了することを確認
```

## 設計メモ

1. **ローカル限定**: USB0 セグメント（10.55.0.0/24）のみリッスン。外部インターネットは不可。
2. **Bearer トークン**: `/etc/azazel/ntfy.token` から読込（パーミッション 600）。
3. **重複抑制**: 30 秒クールダウンでスパム防止。イベントキー単位で管理。
4. **エラー耐性**: 通知送信失敗時、control loop は停止しない。ログに記録のみ。
5. **セキュリティ**:
   - auth-default-access: deny-all（トピックは明示的に read/write 許可）
   - HTTPS 未対応（ローカル限定のため HTTP で十分）
   - トークンは環境変数・ログに出力されない

## 今後の拡張

### Phase C: signals 連動の強化
- Wi-Fi タグ（evil_twin, rogue_dhcp など）の通知
- ルート異常の自動検知
- 温度アラート（CPU >= 75℃）

### Phase D: WebUI との統合
- ui_snapshot.json に直近通知を記録
- WebUI ダッシュボードに「アラート履歴」を表示

### 認証強化（将来）
- ntfy ユーザごとに topic の read/write 権限を分離
- 複数ユーザ（alerting, monitoring など）のサポート

## 参考資料

- **ntfy.sh 公式**: https://ntfy.sh
- **Azazel-Zero**: https://github.com/01rabbit/Azazel-Zero
- **Issue**: ntfy 通知基盤の実装
