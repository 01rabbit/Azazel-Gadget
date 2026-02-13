# Azazel-Zero DHCP/DNS トラブルシューティングガイド

**問題**: ラップトップがAzazel-ZeroのusB経由のネットワーク接続を確立できず、DHCPでIPアドレスを取得できない。

## 原因分析

このプロジェクトでは、Raspberry Pi Zero 2 WのUSBガジェットモード（usb0）がラップトップと通信する際、以下のコンポーネントが正常に動作する必要があります：

1. **usb0 インターフェース**: 10.55.0.10/24 で UP していること
2. **dnsmasq**: DHCP サーバーとして動作し、10.55.0.50-200 のアドレスをクライアントに割り当てること
3. **DNS**: dnsmasq が DNS リクエストを 10.55.0.10:53 で受け取ること

## 新しい修正内容

### 1. systemd 依存関係の改善
- `azazel-first-minute.service` が `usb0-static.service` の完了を待つように変更
- `ExecStartPre` で usb0 UP を待機（タイムアウト 15 秒）

### 2. dnsmasq 起動の改善
- ファイル存在チェック
- usb0 インターフェース待機（最大 5 秒）
- ログ出力を DEBUG レベルでリアルタイム配信
- エラーハンドリング強化

### 3. dnsmasq 設定の補強
- DHCP ログ出力を有効化（`log-dhcp`）
- リースファイルパスを明示化
- キャッシュサイズなど重要設定をコメント化

## トラブルシューティング手順

### 第 1 ステップ：診断ツール実行

```bash
sudo bash /home/azazel/Azazel-Zero/bin/diagnose_dhcp.sh
```

このスクリプトが以下を確認します：
- usb0 インターフェース状態
- usb0-static.service ステータス  
- azazel-first-minute.service ステータス
- dnsmasq プロセス
- dnsmasq 設定ファイル
- dnsmasq ログ
- DHCP/DNS ポート開放状況

### 第 2 ステップ：インストール確認・再実行

```bash
# インストールスクリプトを再実行（設定ファイルと権限を修正）
sudo bash /home/azazel/Azazel-Zero/bin/install_systemd.sh

# systemd 設定を再読込
sudo systemctl daemon-reload
```

### 第 3 ステップ：サービス再起動

```bash
# 順番に再起動
sudo systemctl restart usb0-static.service
sleep 2
sudo systemctl restart azazel-first-minute.service

# ステータス確認
sudo systemctl status azazel-first-minute.service
```

### 第 4 ステップ：ログ確認

#### usb0-static ログ
```bash
journalctl -u usb0-static.service -n 20
```

#### azazel-first-minute ログ（syslog）
```bash
journalctl -u azazel-first-minute.service -f
```

#### dnsmasq ログ（詳細）
```bash
tail -f /var/log/azazel-dnsmasq.log
```

#### システムジャーナル JSON 形式
```bash
journalctl --output=json -u azazel-first-minute.service | jq '.MESSAGE'
```

## よくある問題と解決策

### 問題 1: usb0 インターフェースが見つからない

**症状**:
```
✗ usb0 interface NOT FOUND
```

**原因**: USB ガジェットカーネルモジュールが読み込まれていない

**解決策**:
```bash
# 手動で確認・設定
lsmod | grep dwc2      # USB OTG モジュール
sudo modprobe dwc2
sudo modprobe g_ether  # USB ガジェットモード

# 再起動
sudo reboot
```

### 問題 2: usb0 が存在するが UP していない

**症状**:
```
✓ usb0 exists and is DOWN
```

**解決策**:
```bash
sudo ip link set usb0 up
sudo ip addr add 10.55.0.10/24 dev usb0
```

その後、systemd サービスを再起動：
```bash
sudo systemctl restart azazel-first-minute.service
```

### 問題 3: dnsmasq が起動していない

**症状**:
```
✗ dnsmasq is NOT running
```

**原因①**: dnsmasq がインストールされていない
```bash
sudo apt-get install dnsmasq
```

**原因②**: 設定ファイルが見つからない
```bash
# ファイル確認
ls -la /etc/azazel-zero/dnsmasq-first_minute.conf

# なければインストール再実行
sudo bash /home/azazel/Azazel-Zero/bin/install_systemd.sh
```

**原因③**: ポートが既に使用中
```bash
# 他の DHCP/DNS サーバーを確認
sudo ss -ultn | grep -E ':53|:67'

# 競合サービスを停止
sudo systemctl stop systemd-resolved
sudo systemctl disable systemd-resolved
```

### 問題 4: dnsmasq が起動するが DHCP リースが配布されない

**ログ確認**:
```bash
tail -50 /var/log/azazel-dnsmasq.log | grep -i dhcp
```

**症状別対応**:

1. **"cannot bind DHCP socket"** → usb0 Up 確認、権限確認
   ```bash
   sudo ip link show usb0 | grep UP
   ps aux | grep dnsmasq
   ```

2. **クライアント接続なし** → ラップトップの DHCP 設定確認
   ```bash
   # ラップトップ側（Ubuntu/Debian）
   sudo dhclient -v usb0  # 手動 DHCP 要求
   ```

3. **リース配布されたがアドレスが異なる** → 設定確認
   ```bash
   grep dhcp-range /etc/azazel-zero/dnsmasq-first_minute.conf
   # 確認: dhcp-range=10.55.0.50,10.55.0.200,255.255.255.0,5m
   ```

### 問題 5: DNS が機能していない

**テスト**:
```bash
# ローカルから確認
nslookup example.com 10.55.0.10

# ラップトップから確認
nslookup example.com 10.55.0.10  # ラップトップからのテスト
```

**ファイアウォール確認**:
```bash
# DHCP/DNS のポート開放確認
sudo nft list table inet azazel_fmc | grep -i "53\|67\|68"

# リセット（DEBUG 用）
sudo nft flush table inet azazel_fmc 2>/dev/null || true
sudo systemctl restart azazel-first-minute.service
```

## デバッグモード

詳細なログを取得するため、以下の環境変数で起動：

```bash
# フォアグラウンド実行（DEBUG ログ出力）
AZAZEL_DEBUG=1 python3 /home/azazel/Azazel-Zero/py/azazel-first-minute.py start --config /etc/azazel-zero/first_minute.yaml --foreground
```

これで以下が表示されます：
- dnsmasq の全ログ出力
- State Machine 遷移ログ
- nftables/tc 適用ログ

## 手動修復（ラップトップ側）

まずは DHCP 再取得を優先（手動ルート追加の前に実施）：

```bash
# Linux
sudo dhclient -r usb0 || true
sudo dhclient -v usb0

# macOS
sudo ipconfig set en5 DHCP
```

それでも復旧しない場合のみ、暫定で手動設定：

```bash
# Linux
sudo ip addr add 10.55.0.100/24 dev usb0
sudo route add default gw 10.55.0.10
echo "nameserver 10.55.0.10" | sudo tee /etc/resolv.conf

# macOS
sudo ifconfig en5 inet 10.55.0.100 netmask 255.255.255.0
sudo route add default 10.55.0.10

# Windows PowerShell (Admin)
New-NetIPAddress -InterfaceAlias "Ethernet" -IPAddress 10.55.0.100 -PrefixLength 24 -DefaultGateway 10.55.0.10
Set-DnsClientServerAddress -InterfaceAlias "Ethernet" -ServerAddresses 10.55.0.10
```

## まとめ

これらの修正により、以下が実現されます：

✓ usb0 が確実に UP してから dnsmasq が起動  
✓ dnsmasq のエラーがジャーナルに記録される  
✓ 診断ツールで即座に問題を特定可能  
✓ ラップトップへの DHCP リース配布が正常化  

修正後、以下コマンドで再インストール・再起動：

```bash
sudo bash /home/azazel/Azazel-Zero/bin/install_systemd.sh
sudo systemctl daemon-reload
sudo systemctl restart usb0-static.service
sudo systemctl restart azazel-first-minute.service
```
