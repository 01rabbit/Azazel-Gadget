# Azazel-Zero Copilot インストラクション

## プロジェクト概要
**Azazel-Zero** は Raspberry Pi Zero 2 W 上で動作する「身代わり結界」セキュリティゲートウェイです。ステートマシン駆動のファイアウォール制御、DNS スプーフィング、トラフィック整形、Wi-Fi 安全検知を組み合わせた**遅延防御戦略**を実装しています。

このシステムはアップストリーム Wi-Fi (wlan0) からダウンストリーム USB ガジェットモード (usb0) へブリッジし、脅威検知に基づいてトラフィックを傍受し、セキュリティポリシーを実施します。

## アーキテクチャ：5ステージ状態マシン
コアは [py/azazel_zero/first_minute/state_machine.py](py/azazel_zero/first_minute/state_machine.py) の**有限状態機械**です：

1. **INIT** → 初期起動状態
2. **PROBE** → 疑わしいシグナルを検知；検証プローブ実行 (TCP/TLS/DNS/キャプティブポータル)
3. **DEGRADED** → 軽度の懸念；トラフィック整形を適用 (RTT +180ms、スループット 1-2 Mbps) [py/azazel_zero/first_minute/tc.py](py/azazel_zero/first_minute/tc.py) 経由
4. **NORMAL** → クリーン状態；フル帯域幅
5. **CONTAIN** → 高信頼攻撃検知；大部分の送信トラフィックをブロック
6. **DECEPTION** → （稀）ハニーポット/OpenCanary 連携

**状態遷移**は以下により駆動されます：
- **疑わしさスコア** (0-100)：シグナルソース (プローブ失敗、DNS 不一致、証明書不一致、Wi-Fi 安全タグ、ルート異常、Suricata IDS アラート) によってインクリメント
- **設定可能な閾値**：デグレード (20)、正常 (8)、隔離 (50) [configs/first_minute.yaml](configs/first_minute.yaml) 参照
- **パッシブ減衰**：安定状態で疑わしさが毎秒 3 ポイント減衰（設定可能）

## 重要なコンポーネント＆データフロー

### 1. シグナル集約 → ステートマシン → nftables
- **シグナル源**は複数のセンサー（Wi-Fi 安全性、DNS オブザーバー、プローブ、Suricata）：
  - [py/azazel_zero/sensors/wifi_safety.py](py/azazel_zero/sensors/wifi_safety.py) は iw + tcpdump で悪質な AP、MITM、DNS/DHCP スプーフィングを検知
  - [py/azazel_zero/first_minute/probes.py](py/azazel_zero/first_minute/probes.py) は TLS/DNS/キャプティブポータルテストを実行
  - [py/azazel_zero/first_minute/dns_observer.py](py/azazel_zero/first_minute/dns_observer.py) は dnsmasq ログを監視
  - Suricata IDS 統合（設定で有効化時）

- **ステートマシン** `step()` はシグナルを統合し、以下を適用：
  - **Suricata クールダウン** (デフォルト 30s)：重複アラートの二重カウント防止
  - **CONTAIN リカバリー** (最小継続時間 20s、疑わしさ < 30 で終了)
  - **減衰ロジック** で自然に疑わしさをダウングレード

- **コントローラー** [py/azazel_zero/first_minute/controller.py](py/azazel_zero/first_minute/controller.py) は状態変更を [py/azazel_zero/first_minute/nft.py](py/azazel_zero/first_minute/nft.py) 経由で nftables ルールに変換

### 2. ファイアウォール (nftables)
テンプレート：[nftables/first_minute.nft](nftables/first_minute.nft)

- **Input チェーン（入力）**：管理トラフィック (SSH ポート 22、HTTP 80/443/8081) の高速パス、wlan0・usb0 両方からのリモートデバッグを許可
- **フォワーディング**：ステージ固有ルールを ct mark で適用 (PROBE=1、DEGRADED=2、NORMAL=3、CONTAIN=4)
- **管理サブネット分離**：10.55.0.0/24（設定可能）は運用用にポート 22/80/443/8081 を常に受け入れ

### 3. トラフィック整形 (tc - Linux トラフィック制御)
[py/azazel_zero/first_minute/tc.py](py/azazel_zero/first_minute/tc.py) は usb0 ダウンストリームにキューイング規律を適用：
- **PROBE**：+180ms RTT、1 Mbps レート制限
- **DEGRADED**：+180ms RTT、2 Mbps レート制限
- **NORMAL/CONTAIN**：整形なし (CONTAIN は nftables でトラフィックをブロック)

**設計メモ**：tc (HTB + iptables fwmark) は多層制御のため nftables とペアリング；将来改善：nftables ネイティブ `limit` ルールへ移行予定。

### 4. DNS スプーフィング
[configs/dnsmasq-first_minute.conf](configs/dnsmasq-first_minute.conf) で設定：
- アップストリーム DNS を Quad9 + Cloudflare に強制（設定可能）
- DoH SNI (cloudflare-dns.com、dns.google など) を CNAME フィルターでブロック
- 10.55.0.10:53 で透過 DNS プロキシとして動作

## 設定構造
[configs/first_minute.yaml](configs/first_minute.yaml) はすべての実行時パラメータを定義：
- **interfaces**：アップストリーム (wlan0)、ダウンストリーム (usb0)、管理 IP (10.55.0.10)
- **state_machine**：閾値、減衰率/秒、クールダウン期間
- **probes**：テスト設定 (TLS サイト、DNS ターゲット、キャプティブポータル確認)
- **dnsmasq**：アップストリームサーバー、ブロック DoH SNI、キャッシュ設定
- **suricata**：有効/無効、ルールパス（存在時）
- **status_api**：HTTP エンドポイント（デフォルト 10.55.0.10:8081）UI スナップショット用

## プロジェクト規約

### モジュール構成
- **py/azazel_zero/first_minute/**：メイン制御ループ (config、controller、state_machine、シグナルハンドラー)
- **py/azazel_zero/sensors/**：検知モジュール (Wi-Fi、DNS、ネットワーク分析)
- **py/azazel_zero/app/**：高度な脅威判定（ML/LLM 統合予定）
- **py/azazel_zero/core/**：モック LLM バックエンド (MockLLMCore) テスト用；app/ で実装予定

### 戻り値シグネチャ
- **state_machine.step()** は `(Stage, Dict[str, Any])` を返す、キー：`suspicion`、`reason`、`changed`
- **controller.run_loop()** はイベント駆動で動作；2 秒ループ間隔で非同期シグナルポーリング
- **Signals**：Dict[str, float|int|bool]、キー例：`probe_fail`、`dns_mismatch`、`suricata_alert`、`wifi_tags`

### ログ出力
- **INFO ログ**：状態遷移のみ（2 秒ポーリングループのノイズ回避）
- **DEBUG ログ**：毎ループ反復、詳細なシグナル処理
- 全体で `logging.getLogger("first_minute")` を使用
- ログ表示：`journalctl -u azazel-first-minute --output=json`

### テスト
- **test_redesign_verification.py**：ステートマシンロジック (クールダウン、CONTAIN リカバリー、減衰) を検証
- コミット前に実行：`python3 test_redesign_verification.py`
- テストはシミュレーション型（nftables/tc 不要）；time.time() で systemd タイマーをモック

## 一般的なワークフロー

### 新しい脅威シグナルを追加
1. [py/azazel_zero/sensors/](py/azazel_zero/sensors/) に検知ロジックを作成、または [dns_observer.py](py/azazel_zero/first_minute/dns_observer.py) を拡張
2. [controller.py](py/azazel_zero/first_minute/controller.py) の `run_loop()` で signals 辞書にメトリクスを入力
3. [state_machine.py](py/azazel_zero/first_minute/state_machine.py) の `_apply_signals()` で疑わしさ増分を追加（例：Suricata は `+15`）
4. 新しいパラメータが必要なら [configs/first_minute.yaml](configs/first_minute.yaml) を更新
5. [test_redesign_verification.py](test_redesign_verification.py) でテスト

### 状態閾値を調整
[configs/first_minute.yaml](configs/first_minute.yaml) を編集：
```yaml
state_machine:
  degrade_threshold: 20      # DEGRADED に入る疑わしさ
  normal_threshold: 8        # PROBE から下げる疑わしさ
  contain_threshold: 50      # CONTAIN に入る疑わしさ
  decay_per_sec: 3           # 自然減衰率
  suricata_cooldown_sec: 30  # アラート重複排除ウィンドウ
```
コード変更不要；サービス再起動で設定が再読込。

### nftables ルールを修正
1. [nftables/first_minute.nft](nftables/first_minute.nft) をテンプレートトークン (@UPSTREAM@、@DOWNSTREAM@、@MGMT_IP@ など) で編集
2. 構文をテスト：`nft -f nftables/first_minute.nft --check`
3. コントローラーが起動時に `NftManager.apply_base()` でレンダリング・適用
4. ステージ別ルール：コントローラーが遷移時に `NftManager.set_stage(stage)` を呼び出し

## 主要ファイルリファレンス
- **[py/azazel_zero/first_minute/state_machine.py](py/azazel_zero/first_minute/state_machine.py)**：状態遷移、疑わしさロジック、減衰
- **[py/azazel_zero/first_minute/controller.py](py/azazel_zero/first_minute/controller.py)**：メインループ、シグナル集約、ライフサイクル
- **[py/azazel_zero/first_minute/nft.py](py/azazel_zero/first_minute/nft.py)**：nftables テンプレートレンダリングとルール適用
- **[nftables/first_minute.nft](nftables/first_minute.nft)**：ファイアウォールルール (入力高速パス、フォワーディングステージ、マークルール)
- **[configs/first_minute.yaml](configs/first_minute.yaml)**：すべての実行時設定
- **[py/azazel_zero/sensors/wifi_safety.py](py/azazel_zero/sensors/wifi_safety.py)**：Wi-Fi 悪質 AP/MITM 検知
- **[systemd/azazel-first-minute.service](systemd/azazel-first-minute.service)**：サービス定義；`py/azazel-first-minute.py start` を実行

## 既知の設計パターン＆落とし穴

1. **減衰 vs. 遷移タイミング**：`last_transition` は状態の*変更*のみを記録、毎ループ反復ではない。減衰はパッシブで継続的。
2. **Suricata アラート重複排除**：クールダウンなしの場合、30s 以内の重複アラートは疑わしさをインクリメントしない。これはアラート嵐を回避する意図的な仕様。
3. **CONTAIN 最小継続時間**：疑わしさが下がっても、CONTAIN は ≥20s 継続し、フラッピングを防止。
4. **管理トラフィック高速パス**：管理サブネットへの SSH/HTTP/HTTPS はステージルールをバイパス。CONTAIN 中の遠隔操作に必須。
5. **設定フォールバック**：YAML パースに失敗またはキー欠落時は、[config.py](py/azazel_zero/first_minute/config.py) のハードコード化デフォルトを適用；非 root 時は `.azazel-zero/` にフォールバック。

## テスト＆デバッグコマンド
```bash
# ステートマシンロジックを検証
python3 test_redesign_verification.py

# nftables 構文をチェック
nft -f nftables/first_minute.nft --check

# ファイアウォールルールを表示
nft list table inet azazel_fmc

# 状態遷移を監視（INFO ログのみ）
journalctl -u azazel-first-minute -f | grep "transitioned"

# 詳細なループログを表示（DEBUG）
journalctl -u azazel-first-minute --output=json | jq '.MESSAGE'

# ステータス API をクエリ（実行中の場合）
curl http://10.55.0.10:8081/

# usb0 の tc qdisc をチェック
tc qdisc show dev usb0
```

## Git ブランチ＆デプロイ
- **現在のブランチ**：feature/epd-tui-tuning (UI/E-Paper 改善)
- **デフォルト/main**：安定版
- systemd サービスは `systemctl restart azazel-first-minute` で設定を再読込
