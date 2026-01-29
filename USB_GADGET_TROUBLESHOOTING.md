# MacBook での接続確認手順

以下を MacBook のターミナルで実行してください：

## 1. USB インターフェースの確認
```bash
ifconfig | grep -E "^usb0|RUNNING" -A 2
```
**期待される結果:**
- `usb0` インターフェースが存在すること
- `inet 10.55.x.x` など、10.55.0.0/24 ネットワークの IP が割り当てられていること

## 2. ルーティング確認
```bash
netstat -rn | grep "10.55"
```
**期待される結果:**
- `10.55.0.0/24` へのルートが `usb0` インターフェース経由で設定されていること

例：
```
10.55.0.0/24        link#XX            UCS            usb0
10.55.0.10          8e:d8:6a:15:65:bb UHLWIir2       usb0
```

## 3. Ping テスト（ICMP 確認）
```bash
ping -c 3 10.55.0.10
```

**ここでタイムアウトが発生する場合：**
- A) USB ケーブルが接続されていない
- B) Mac 側が usb0 インターフェースを認識していない
- C) ラズパイ側の USB ガジェットモードが正常に動作していない

## 4. HTTP 接続テスト
```bash
curl -v http://10.55.0.10:8084/health
```

---

## トラブルシューティング

### USB インターフェースが見当たらない場合

**Mac での確認:**
```bash
system_profiler SPUSBDataType | grep -A 20 "Raspberry"
```

**Mac での設定:**
ケーブルを再接続するか、ネットワーク設定をリセット：
```bash
networksetup -setv4off usb0 2>/dev/null || echo "usb0 not yet recognized"
```

### ラズパイ側での USB ガジェットモード確認
```bash
# ラズパイで実行
lsmod | grep g_ether
sudo dmesg | tail -20
```

---

## 現在のラズパイ側設定

✅ nftables ルール更新済み：
- ICMP (ping) 許可
- usb0 からの TCP (22, 80, 443, 8081, 8084) 許可
- usb0 からの UDP (53, 67, 68) 許可
- wlan0 からのアクセス拒否

✅ Flask サーバー稼働中：
```
tcp        0      0 0.0.0.0:8084            0.0.0.0:*               LISTEN
```

---

---

## MacBook での問題が見られた場合

### 症状：ARP は成功しているが Ping が失敗

**原因：** MacBook のネットワークキャッシュに古い MAC アドレスが存在

**解決手順（MacBook で実行）：**

```bash
# 1. ARP キャッシュをクリア
sudo arp -d 10.55.0.10

# 2. en17 インターフェースをリセット
sudo networksetup -setv4off en17 2>/dev/null || true
sleep 2
sudo networksetup -setv4on en17 dhcp 2>/dev/null || true

# 3. ラズパイの USB ケーブルを物理的に抜いて再挿入（30秒待機）

# 4. 再度テスト
arp -a | grep 10.55
ping -c 3 10.55.0.10
```

### Ping が成功後の HTTP テスト

```bash
curl -v http://10.55.0.10:8084/health
curl http://10.55.0.10:8084/api/state | jq '.ok'
```

---

## ラズパイ側の最終確認

nftables ルール（ICMP 対応版）：

```bash
sudo nft -nn list chain inet azazel_fmc input
```

**期待される出力：**
```
icmp type 8 accept comment "icmp echo-request"
icmp type 0 accept comment "icmp echo-reply"
iifname "usb0" tcp dport { 22, 80, 443, 8081, 8084 } accept
iifname "usb0" udp dport { 53, 67, 68 } accept
iifname "wlan0" drop comment "wlan0 blocked (production mode)"
```

usb0 インターフェース統計：

```bash
ip -s link show usb0
```

**確認項目：**
- `<UP, LOWER_UP>` フラグが有効
- RX/TX パケット数が 0 ではない（データが流れている）
- MAC アドレス: `ce:7c:09:24:48:cb`

---

## 完全なデバッグフロー

1. ラズパイ側でこのコマンドで IP + MAC を取得：
   ```bash
   ip addr show usb0 | grep -E "link/ether|inet "
   ```
   出力例：
   ```
   link/ether ce:7c:09:24:48:cb
   inet 10.55.0.10/24 scope global usb0
   ```

2. MacBook で ARP テーブルを確認：
   ```bash
   arp -a | grep 10.55
   ```
   **正しい出力例：**
   ```
   10.55.0.10 (10.55.0.10) at ce:7c:9:24:48:cb on en17
   ```
   （16進法なので、上記と完全に一致）

3. Ping テスト：
   ```bash
   ping -c 3 10.55.0.10
   ```
   **成功例：**
   ```
   PING 10.55.0.10 (10.55.0.10): 56 data bytes
   64 bytes from 10.55.0.10: icmp_seq=0 ttl=64 time=2.345 ms
   ```

4. HTTP テスト：
   ```bash
   curl http://10.55.0.10:8084/api/state | jq '.ok'
   ```
   **期待される出力：** `true`

---

## HTTP 接続問題の診断（2026/01/29 新規）

### 症状
- ✅ Ping 成功（ICMP エコー正常）
- ❌ HTTP (8084) 接続タイムアウト
- ✅ ラズパイ側 Flask 稼働（0.0.0.0:8084）
- ✅ ラズパイ側 nftables ルール正常

### 原因推定
MacBook 側の en17 インターフェースか、Mac のファイアウォール設定に問題

### MacBook での詳細確認

**【最優先】** Mac ファイアウォール確認：
```bash
# ファイアウォール状態
sudo pfctl -s state | head -20

# ファイアウォール有効/無効確認
networksetup -getfirewallenabled

# 必要に応じて一時的に無効化（テスト用）
sudo defaults write /Library/Preferences/com.apple.alf globalstate -int 0
sudo killall -HUP socketfilterfw
```

**en17 インターフェースの詳細確認：**
```bash
# インターフェース詳細
ifconfig en17

# 期待される出力：
#   inet 10.55.0.xxx netmask 0xffffff00 broadcast 10.55.0.255
```

**ルーティングテーブル：**
```bash
netstat -rn | grep "10.55"

# 期待される出力：
#   10.55.0.0/24        link#39            UCS                  en17
```

**ARP テーブル（ラズパイ MAC確認）：**
```bash
arp -a | grep 10.55

# 期待される出力：
#   10.55.0.10 (10.55.0.10) at ce:7c:9:24:48:cb on en17
```

---

## HTTP 接続がタイムアウトする場合の対応

### Step 1: Tcpdump でトラフィック確認

**MacBook ターミナル1（監視）:**
```bash
sudo tcpdump -i en17 "host 10.55.0.10 and port 8084" -vv
```

**MacBook ターミナル2（テスト）:**
```bash
curl -v http://10.55.0.10:8084/health
```

**期待される出力:**
```
10.55.0.114.xxxxx > 10.55.0.10.8084: Flags [S], seq xxx
10.55.0.10.8084 > 10.55.0.114.xxxxx: Flags [S.], seq yyy
```

### Step 2: ファイアウォール無効化テスト

```bash
# 一時的に無効化（セキュリティ注意）
sudo /bin/launchctl unload /Library/LaunchDaemons/com.apple.alf.agent.plist 2>/dev/null

# テスト実行
ping -c 3 10.55.0.10
curl http://10.55.0.10:8084/health

# 再度有効化
sudo /bin/launchctl load /Library/LaunchDaemons/com.apple.alf.agent.plist 2>/dev/null
```

### Step 3: ネットワーク設定リセット

```bash
# 古い設定を削除
sudo networksetup -setv4off en17
sleep 3

# 再度有効化
sudo networksetup -setv4on en17 dhcp
sleep 5

# 確認
ifconfig en17
netstat -rn | grep "10.55"
```

---

## ラズパイ側の確認コマンド

Flask と nftables の完全な状態確認：

```bash
# Flask リスニング確認
ss -tlnp | grep 8084

# 期待される出力：
# LISTEN 0 128 0.0.0.0:8084 0.0.0.0:* users:(("python3",...))

# nftables ルール確認
sudo nft -nn list chain inet azazel_fmc input

# nftables カウンター確認（パケットが到達しているか）
sudo nft -nn list chain inet azazel_fmc input | grep counter

# usb0 統計
ip -s link show usb0
```

---

実行結果をお知らせください！
