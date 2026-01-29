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

実行結果をお知らせください！
