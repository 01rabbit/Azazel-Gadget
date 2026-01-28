# ラップトップからの Web UI アクセスガイド

## 接続パターン

### パターン 1: USB ガジェット接続（推奨・開発用）
Raspberry Pi Zero 2 W を USB ケーブルでラップトップに直接接続した場合

**アクセスポイント**: `10.55.0.10:8084`

```bash
# ブラウザで:
http://10.55.0.10:8084/

# curl テスト:
curl http://10.55.0.10:8084/health
```

**セットアップ手順**:
1. Raspberry Pi を USB ケーブルで接続
2. Mac/Linux: 自動でネットワークが設定される（通常は `10.55.0.0/24` サブネット）
3. Windows: ドライバ設定が必要な場合あり

### パターン 2: Wi-Fi 経由（リモートネットワーク）
Raspberry Pi と同じ Wi-Fi ネットワークに接続した場合

**アクセスポイント**: `192.168.40.184:8084`（または `192.168.40.x`）

```bash
# ブラウザで:
http://192.168.40.184:8084/

# curl テスト:
curl http://192.168.40.184:8084/health
```

**注意**: Wi-Fi の IP は DHCP で変わる可能性があるため、固定 IP 設定を推奨

## トラブルシューティング

### 接続できない場合

#### 1. Raspberry Pi の Web サーバーが起動しているか確認
```bash
# Raspberry Pi 側で実行:
ps aux | grep "python.*app.py" | grep -v grep
ss -tlnp | grep 8084
```

**起動していない場合**:
```bash
cd ~/Azazel-Zero/azazel_web
AZAZEL_WEB_HOST=0.0.0.0 AZAZEL_WEB_PORT=8084 python3 app.py
```

#### 2. ファイアウォール（nftables）の確認
```bash
# Raspberry Pi 側で実行:
sudo nft list chain inet azazel_fmc input | grep 8084
```

**出力例**:
```
tcp dport 8084 accept comment "web ui (remote access)"
```

問題がない場合は以下を実行:
```bash
cd ~/Azazel-Zero && cat nftables/first_minute.nft | \
  sed 's/@UPSTREAM@/wlan0/g' | \
  sed 's/@DOWNSTREAM@/usb0/g' | \
  sed 's/@MGMT_IP@/10.55.0.10/g' | \
  sed 's/@MGMT_SUBNET@/10.55.0.0\/24/g' | \
  sed 's/@PROBE_TTL@/10s/g' | \
  sed 's/@DYNAMIC_TTL@/300s/g' | \
  sudo nft -f -
```

#### 3. ネットワーク接続の確認
```bash
# ラップトップ側で実行:

# USB ガジェット接続の場合:
ping 10.55.0.10

# Wi-Fi の場合:
ping 192.168.40.184
```

**ping が通らない場合**:
- USB ケーブルが正しく接続されているか確認
- Wi-Fi の SSID/IP を確認: `arp -a` で Raspberry Pi を検索

#### 4. curl でディバッグ
```bash
# 詳細なエラーログを表示:
curl -v http://10.55.0.10:8084/health

# タイムアウト設定:
curl --connect-timeout 3 http://10.55.0.10:8084/health

# HTTP header のみ表示:
curl -I http://10.55.0.10:8084/
```

#### 5. ポート 8084 が実際にリッスンしているか確認
```bash
# ラップトップ側で実行:
nmap -p 8084 10.55.0.10

# または:
nc -zv 10.55.0.10 8084
```

## 状態確認 API

Web サーバーが起動している場合、以下のエンドポイントで状態確認可能です：

### ヘルスチェック（認証不要）
```bash
curl http://10.55.0.10:8084/health
```

**レスポンス例**:
```json
{
  "service": "azazel-web",
  "status": "ok",
  "timestamp": "2026-01-29T00:15:00.123456"
}
```

### 状態取得（認証なし）
```bash
curl http://10.55.0.10:8084/api/state
```

### Token 認証あり
```bash
TOKEN="your-secret-token"
curl -H "X-Auth-Token: $TOKEN" http://10.55.0.10:8084/api/state
```

## ブラウザでのアクセス

1. **Chrome/Safari/Firefox** で以下にアクセス:
   ```
   http://10.55.0.10:8084/
   ```

2. **ステータス画面が表示**されます:
   - Status Card（ステージバッジ、Suspicion スコア）
   - Signals パネル（各シグナル）
   - Evidence Log（イベント履歴）
   - アクションボタン（Refresh, Re-probe, Contain, Details）

3. **リアルタイム更新**（2 秒ごと）が自動で行われます

## systemd サービスで自動起動

本番運用では systemd サービスで自動起動します：

```bash
# サービスをインストール:
sudo cp ~/Azazel-Zero/azazel_web/systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload

# 起動:
sudo systemctl start azazel-state-generator
sudo systemctl start azazel-control-daemon
sudo systemctl start azazel-web-ui

# 自動起動有効化:
sudo systemctl enable azazel-state-generator
sudo systemctl enable azazel-control-daemon
sudo systemctl enable azazel-web-ui

# ログ確認:
journalctl -u azazel-web-ui -f
```

## パフォーマンス目標

- **応答時間**: < 100 ms
- **ポーリング間隔**: 2 秒
- **メモリ使用量**: ~ 50-100 MB（Flask）
- **TCP ポート**: 8084（Web UI）

---

**トラブルシューティング時のログ確認**:
```bash
journalctl -u azazel-web-ui -n 50 --no-pager
dmesg | tail -20
sudo nft list table inet azazel_fmc
```

質問や問題があれば、上記の確認項目を実施した上で報告してください！
