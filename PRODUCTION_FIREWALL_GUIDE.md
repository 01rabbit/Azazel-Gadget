# 本運用向けファイアウォール設定ガイド

## 概要
Azazel-Zero は以下のネットワークアーキテクチャで動作します：

| インターフェース | ネットワーク | 役割 | 運用モード |
|---|---|---|---|
| **usb0** (downstream) | 10.55.0.0/24 | USB ガジェット（PC側）| **許可** ✅ |
| **wlan0** (upstream) | 192.168.40.0/24 | Wi-Fi（アップストリーム） | **拒否** ❌ |

## 現在の状態（開発中）
- **wlan0 からのアクセス**: 全て許可（テスト用）
- **usb0 からのアクセス**: 全て許可（テスト用）

## 本運用への移行（このドキュメント後のセクション参照）

### 変更内容
1. **nftables input チェーン** を修正
   - usb0 からのアクセスのみ許可
   - wlan0 からのアクセスを完全遮断
2. **ポート 8084 (Web UI)** の修限定
   - 開発中: 全インターフェースで許可
   - 本運用: usb0 のみで許可

---

## nftables ルール - 本運用版

### Input チェーン（変更後）

```nftables
chain input {
  type filter hook input priority 0; policy accept;
  iifname "lo" accept
  ct state established,related accept
  
  # ★ usb0 (downstream) トラフィック許可
  # - 管理通信: SSH(22), HTTP(80), HTTPS(443), StatusAPI(8081), WebUI(8084)
  # - ネットワーク: DHCP(67/68), DNS(53)
  iifname $DOWNSTREAM tcp dport { 22, 80, 443, 8081, 8084 } accept comment "usb0 management"
  iifname $DOWNSTREAM udp dport { 53, 67, 68 } accept comment "usb0 DHCP/DNS"
  
  # ★ wlan0 (upstream) トラフィック拒否
  # 本運用では wlan0 からのアクセスは一切受け付けない
  iifname $UPSTREAM drop comment "wlan0 blocked (production mode)"
  
  # ★ その他の入力トラフィック（デフォルト拒否）
  counter drop comment "default drop"
}
```

---

## テスト結果

### usb0 からのアクセス ✅ 成功
```bash
$ curl -m 5 http://10.55.0.10:8084/api/state
# 200 OK、レスポンス時間 < 100ms
```

### wlan0 からのアクセス ❌ 拒否
```bash
$ curl -m 3 http://192.168.40.10:8084/api/state
# curl: (28) Connection timed out after 3002 milliseconds
```

---

## 設定ファイル修正詳細

### ファイル: `nftables/first_minute.nft`

**問題点（修正前）:**
1. Input チェーン内に古いルールが残存
2. usb0 からのポート 8084 アクセスが明示的に許可されていない
3. wlan0 からのアクセスが制限されていない

**修正内容:**
- Input チェーンを再構成：usb0 許可 → wlan0 拒否 → デフォルト拒否
- テンプレート変数の明示的な使用

**適用方法:**
```bash
# 1. 既存テーブルを削除（新しいルールを適用するため）
sudo nft delete table inet azazel_fmc

# 2. テンプレート置換を実施
cat nftables/first_minute.nft | \
  sed 's/@UPSTREAM@/wlan0/g; \
       s/@DOWNSTREAM@/usb0/g; \
       s/@MGMT_IP@/10.55.0.10/g; \
       s/@MGMT_SUBNET@/10.55.0.0\/24/g; \
       s/@PROBE_TTL@/10s/g; \
       s/@DYNAMIC_TTL@/5m/g' | \
  sudo nft -f -

# 3. ルール確認
sudo nft list chain inet azazel_fmc input
```

---

## トラブルシューティング

### usb0 からのアクセスが遅い場合

1. **nftables ルール確認**
   ```bash
   sudo nft list chain inet azazel_fmc input
   ```
   - `iifname "usb0" drop` が早い段階にあると、usb0 トラフィックが遮断される
   - 修正: drop ルール を最後に移動

2. **Flask サーバー確認**
   ```bash
   ps aux | grep "AZAZEL_WEB_HOST"
   # Flask が 0.0.0.0 ではなく 127.0.0.1 で起動していないか確認
   ```

3. **ルーティング確認**
   ```bash
   ip route show
   # usb0 ネットワークが正しくルーティングされているか確認
   ```

### wlan0 からのアクセスが許可される場合

1. **古いルールの残存**
   ```bash
   sudo nft list table inet azazel_fmc
   ```
   - 古いルール（例: `tcp dport 8084 accept` が無条件）が残存していないか確認

2. **テーブルをリセット**
   ```bash
   sudo nft delete table inet azazel_fmc
   # その後、新しいルールを適用
   ```

---

## Forward チェーンについて

Forward チェーンは **ステージベースのトラフィック整形** に使用されます：
- **PROBE**: DNS/DHCP プローブのみ許可
- **DEGRADED**: レート制限あり（1-2 Mbps）
- **NORMAL**: フル帯域幅
- **CONTAIN**: 大部分の送信トラフィックをブロック
- **DECEPTION**: ハニーポット（稀）

現在の input チェーン修正は forward チェーンに **影響しません**。

---

## セキュリティに関する注意

### 開発中（現在）
- Web UI は外部からも完全にアクセス可能
- テスト用なので、セキュリティ考慮は最小限

### 本運用への移行時
1. **nftables ルール** を上記の通り適用
2. **Flask トークン認証** の有効化推奨
   - [py/azazel_zero/web/app.py](py/azazel_web/app.py) で `verify_token()` 実装済み
3. **USB ガジェット** への物理的アクセス制御
   - usb0 ネットワークはローカルのみ到達可能

---

## Git コミット

本運用向けの修正をコミット：

```bash
git add nftables/first_minute.nft
git commit -m "fix(nftables): Production firewall rules - usb0 only, wlan0 blocked"
```

---

## 参考資料

- [py/azazel_zero/first_minute/nft.py](py/azazel_zero/first_minute/nft.py) - nftables コントローラー
- [py/azazel_web/app.py](py/azazel_web/app.py) - Flask Web UI
- [REMOTE_ACCESS_GUIDE.md](REMOTE_ACCESS_GUIDE.md) - リモートアクセスガイド（開発中用）
