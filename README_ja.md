# Azazel-Zero

[English](/README.md) | 日本語

## コンセプト

**Azazel-Zero** は Raspberry Pi Zero 2 W 上で動作する **「身代わり防壁（Substitute Barrier）」** のプロトタイプです。  
Azazel System の**遅滞防御（delaying action）**を実用的に具現化しつつ、**身代わり防壁**と**防壁迷路（Barrier Maze）**という原点に立ち返ります。

### Azazel-Pi との比較

- **Azazel-Pi**  
  - Raspberry Pi 5 をベースにした **Portable Security Gateway (Cyber Scapegoat Gateway)**  
  - **一時的に構築する小規模ネットワーク** を低コストで守るための **コンセプトモデル**  
  - 複数の技術要素を試験するための実験色が強い

- **Azazel-Zero**  
  - **用途を絞り、不要機能をそぎ落とした軽量版**。実運用を前提に設計  
  - **携帯性と実用性を重視した物理的バリア**  
  - コンセプトモデルの Azazel-Pi と異なり、**現場投入を想定した実用モデル**

---

## 設計方針

- **携帯性**: 胸ポケットに収まるサイズ  
- **不可避性**: 端末と外部ネットワークの間に強制的に割り込む  
- **シンプルさ**: USB を挿すだけでファイアウォールが成立  
- **遅延防御**: 攻撃者の時間を浪費させる（Azazel System の中核）

---

## 実装

### ベース

- **Raspberry Pi Zero 2 W**

### ネットワーク

- **USB OTG ガジェットモード**  
  - 1 本の USB ケーブルで給電と仮想ネットワークを同時に提供  
  - ノート PC に挿すだけで即起動

### 防御機能（軽量）

- **iptables/nftables** によるブロック・遅延  
- **tc (Traffic Control)** で遅延・ジッターを注入  
- **カスタム Python スクリプト** による動的制御と通知  
- **Wi-Fi セーフティセンサー**（Python + `iw` + `tcpdump`）で Evil AP / MITM / DNS・DHCP スプーフィングを検出し、危険タグを発行して自動切断へ接続

### ステータス表示

- **E-Paper（電子ペーパー）**  
  - 2.13 インチ モノクロ（250×122）  
  - 脅威レベル/アクション/RTT/キュー状態/キャプティブポータル検出を簡潔に表示

---

## Threat Evaluation Pipeline

Pi Zero 2 W でも動作する決定論的な 2 層構成の判定エンジンを採用しています。

- **第1層: Wi-Fi セーフティセンサー**  
  - `py/azazel_zero/sensors/wifi_safety.py` が `iw dev … link` と短時間の `tcpdump` から ARP/DHCP/DNS の異常を検出。  
  - `evil_ap`, `mitm`, `arp_spoof`, `dhcp_spoof`, `dns_spoof`, `tls_downgrade`, `captive_portal`, `phish` などのタグとメタ情報を生成。

- **第2層: Mock-LLM Core**  
  - `py/azazel_zero/core/mock_llm_core.py` が入力を従来カテゴリ（`scan`, `bruteforce`, `exploit`, `malware`, `sqli`, `dos`, `unknown`）へマッピング。  
  - 正規表現 + ランダムから、ハッシュに基づく決定論リプライへ刷新し、リスク（1–5）と理由文を安定出力。  
  - プロファイル `"zero"` は Wi-Fi タグに Evil AP / MITM があれば自動でリスクを引き上げ、Danger/Disconnect 判定を確実化。

- **Threat Judge ラッパー**  
  - `py/azazel_zero/app/threat_judge.py` がタグと最終判定をまとめ、UI や自動化が扱いやすい JSON を返却（例: `risk >= 4` または `evil_ap` タグで即切断）。

重量級 ML は将来の研究テーマとして残しつつ、現状の決定論的スタックだけで携帯シールドに必要な自動判定を実現しています。

---

## Operator Console & Automation

- **TUI（ターミナルユーザーインターフェース）**  
  - `py/azazel_zero/cli_unified.py` は統合監視TUI。WiFi状態、脅威レベル、チャンネル混雑度、制御ルールなどをリアルタイム表示。
  - カラフルなアイコンと色分けで直感的に状態を把握可能。
  - 手動更新モード（[U]キーで更新）。
  
- **tmux コンソール**  
  - `py/azazel_menu.py` は Wi-Fi セレクタ、Portal/Shield/Lockdown スクリプト、OpenCanary 制御、E-Paper テストをまとめた curses メニュー。  
  - `py/azazel_status.py` は SSID/BSSID、USB ガジェット IP、RSSI、キャプティブポータル指標などを表示するテレメトリパネル。

---

## TUI（統合監視インターフェース）の見方

### 起動方法

```bash
sudo python3 py/azazel_zero/cli_unified.py
```

### 画面構成

```
┌─────────────────────────────────────────────────────────────┐
│ Azazel-Zero | 📶 SSID: MyWiFi | ⬇️ usb0 | ⬆️ wlan0 | 🕐 12:34:56 │  ← ステータスバー
│ View: SNAPSHOT (manual)  Age: 🟢 00:00:15                   │  ← データ新鮮度
├─────────────────────────────────────────────────────────────┤
│ ✅ 安全          推奨：このまま継続                          │  ← 状態バッジ（反転表示）
│ 理由：プローブ成功 / DNS正常                                │
│ 脅威度: [🟢🟢⚪⚪⚪] Low                                     │  ← 脅威レベル
│ 次：再評価を待機                                            │
├──────────────────────┬──────────────────────────────────────┤
│ Connection           │ Control / Safety                     │
│ BSSID: aa:bb:cc:...  │ QUIC(UDP/443): ⛔ BLOCKED           │
│ Channel: 🟢 Ch124    │ DoH(TCP/443): ⛔ BLOCKED            │
│    - Low (31 APs)    │ Degrade: ✓ OFF                      │
│ Signal: 🟩🟩🟩 -55dBm │ Probe: ✓ 5/5 ALL OK                │
│ Gateway: 🏠 192.168… │ Stats: DNS: ✅ 45 ⚠️ 3 🔴 2         │
├──────────────────────┴──────────────────────────────────────┤
│ Evidence (last 90s)                                         │
│ 🟢 Normal probe completed                                   │
│ 🟡 DNS query to suspicious domain                          │
│ 💠 action: reprobe command sent                             │
│ ↳ decision: state=NORMAL suspicion=5 decay=0.9             │
├─────────────────────────────────────────────────────────────┤
│ Flow: PROBE → DEGRADED → NORMAL → ✅ SAFE                   │
│ [U] Refresh  [A] Stage-Open  [R] Re-Probe  [C] Contain  [L] Details  [Q] Quit │
│ Hint: この画面は自動更新しません。必要時に [U] で更新してください。 │
└─────────────────────────────────────────────────────────────┘
```

### アイコンと色の意味

#### 🎯 状態バッジ（メインステータス）

| アイコン | 状態 | 色 | 意味 |
|---------|------|-----|------|
| ⟳ | 確認中 | シアン（反転） | 初期スキャン中 |
| ✅ | **安全** | **緑（反転・太字）** | ネットワークは安全 |
| ⚠️ | 制限中 | 黄（反転） | 帯域制限などの制約あり |
| ⛔ | 隔離 | 赤（反転） | 危険と判定、隔離モード |
| 👁 | 観測誘導 | 紫（反転） | デセプション（囮）モード |

#### 🎯 脅威レベルインジケーター

```
脅威度: [🟢🟢⚪⚪⚪] Low      ← 安全
脅威度: [🟡🟡🟡⚪⚪] Med      ← 注意
脅威度: [🔴🔴🔴🔴🔴] Critical ← 危険
```

#### 🎯 経過時間（Age）

- 🟢 **0-30秒** : 最新データ、信頼できる
- 🟡 **30秒-2分** : やや古い、確認推奨
- 🔴 **2分以上** : 古い、[U]キーで更新が必要

#### 🎯 Signal強度（電波強度）

| 表示 | 強度 | 意味 |
|------|------|------|
| 🟩🟩🟩🟩 | -50dBm以上 | 非常に良好 |
| 🟩🟩🟩 | -50〜-60dBm | 良好 |
| 🟨🟨 | -60〜-70dBm | 普通 |
| 🟧 | -70〜-80dBm | 弱い |
| 🟥 | -80dBm以下 | 非常に弱い |

#### 🎯 Channel混雑度（実測）

| 表示 | 混雑度 | AP数 | 意味 |
|------|--------|------|------|
| 🟢 Clear/Low | 低い | 0-2台 | 空いている（快適） |
| 🟡 Medium | 中程度 | 3-5台 | 普通 |
| 🟧 High | 高い | 6-10台 | 混雑 |
| 🔴 Critical | 非常に高い | 11台以上 | 非常に混雑 |

※ [U]キーで更新時に周囲のAPをスキャンして実測

#### 🎯 Gateway IP

- 🏠 **緑** : プライベートIP（正常）
- ⚠️ **黄** : パブリックIP（要確認）

#### 🎯 制御ルール

| 項目 | アイコン | 色 | 意味 |
|------|---------|-----|------|
| QUIC | ⛔ | 赤 | ブロック中 |
| QUIC | ✓ | 緑 | 許可 |
| Degrade | ⚡ | 黄 | 帯域制限中 |
| Degrade | ✓ | 緑 | 制限なし |
| Probe | ⚠ | 赤 | ブロック検出 |
| Probe | ✓ | 緑 | 全て正常 |

#### 🎯 DNS統計

- ✅ 正常クエリ数
- ⚠️ 異常クエリ数
- 🔴 ブロックされたクエリ数

#### 🎯 Evidence（証拠ログ）

| アイコン | 色 | 意味 |
|---------|-----|------|
| 🔴 | 赤（太字） | 異常・エラー（blocked, fail, hijack等） |
| 🟡 | 黄 | 警告・注意（portal, dns, probe等） |
| 🟢 | 緑 | 正常・成功（ok, safe, normal等） |
| 💠 | シアン | アクション（command, transition等） |
| ⚪ | 白 | その他 |

### キー操作

| キー | 機能 | 説明 |
|------|------|------|
| **[U]** | Refresh | データを手動更新（WiFiスキャン実行） |
| **[A]** | Stage-Open | 制限状態から通常モードへ移行指示 |
| **[R]** | Re-Probe | 再度プローブテストを実行 |
| **[C]** | Contain | 隔離モードへ移行 |
| **[L]** | Details | 詳細情報画面（Evidence履歴30件、内部状態） |
| **[Q]** | Quit | 終了 |

### Details画面（[L]キーで遷移）

- **Evidence履歴**: 過去30件の証拠ログを表示
- **内部状態**:
  - `State`: ステートマシンの現在状態（PROBE/NORMAL/DEGRADED/CONTAIN/DECEPTION）
  - `Suspicion`: 疑わしさスコア（0-100）
  - `Decay`: 減衰値
  - `Rules`: 制御ルール詳細
- **[B]キー**でメイン画面に戻る

### 色の基本ルール

| 色 | 意味 | 使用箇所 |
|----|------|---------|
| 🟢 緑 | 良好・正常・安全 | SAFE状態、信号強度良、空きチャンネル、正常ログ |
| 🟡 黄 | 注意・警告・中程度 | LIMITED状態、信号弱、混雑中、警告ログ |
| 🔴 赤 | 危険・エラー・異常 | CONTAINED状態、信号非常に弱、超混雑、エラーログ |
| 🟣 紫 | 特殊状態 | DECEPTION状態 |
| 🔵 シアン | 情報・技術的データ | CHECKING状態、アクションログ、技術情報 |
| ⚪ 白 | 中立・不明 | その他のログ、不明な状態 |

---

## インストール手順

**統合インストーラーで完全セットアップが完了します。** 詳細は [installer/README.md](installer/README.md) を参照してください。

### 前提条件

- **Raspberry Pi Zero 2 W** 上で Raspberry Pi OS Lite 64-bit を実行中
- **USB ガジェットモード** を設定済み：
  - `/boot/config.txt` に `dtoverlay=dwc2` を追記
  - `/boot/cmdline.txt` に `modules-load=dwc2,g_ether` を追記
  - 再起動後、`usb0` が使用可能
- リポジトリを `/home/azazel/Azazel-Zero` に展開

### クイックスタート（推奨）

```bash
cd ~/Azazel-Zero
sudo ./install.sh
```

**それだけです。** 以下が自動化されます：

✅ **Stage 00**: 前提条件確認（root、OS、ディスク、インターフェース）  
✅ **Stage 10**: 依存パッケージ導入（nftables、dnsmasq、Python venv など）  
✅ **Stage 20**: ネットワーク設定（usb0、NAT、iptables）  
  - **ネットワーク変更を自動検出** → 再起動を要求 → `--resume` で再開可能  
✅ **Stage 30**: 設定ファイルをデプロイ（/etc/azazel-zero/）  
✅ **Stage 40**: systemd ユニットを登録・有効化  
✅ **Stage 99**: 全サービスを検証・完了

### ネットワーク変更時の対応

インストール中に wlan0 の IP が変わった場合（DHCP 再割り当てなど）：

1. **Stage 20** でネットワーク変更を検出
2. 再起動を促すメッセージが表示される
3. 状態を保存して安全に終了
4. 再起動後、以下を実行：
   ```bash
   sudo ./install.sh --resume
   ```
5. **Stage 30** から続行

### オプション機能の有効化

```bash
# Web UI + OpenCanary + E-Paper デモを含める
sudo ./install.sh --with-webui --with-canary --with-epd

# すべてのオプション機能を含める
sudo ./install.sh --all

# 実行内容を確認のみ（変更しない）
sudo ./install.sh --dry-run
```

**利用可能なオプション：**

| オプション | 説明 |
|----------|------|
| `--with-webui` | Flask ベースの Web UI（ポート 8084）を有効化 |
| `--with-canary` | OpenCanary ハニーポット機能を有効化 |
| `--with-epd` | Waveshare E-Paper ドライバを導入 |
| `--with-ntfy` | ntfy 通知機能を有効化 |
| `--all` | すべてのオプションを有効化 |
| `--dry-run` | 実行内容を表示（変更なし） |
| `--resume` | 中断された場所から再開 |

### セットアップ後

インストール完了後：

1. **Web UI にアクセス**（MacBook 側から usb0 経由）：
   ```
   http://10.55.0.10:8084
   ```

2. **systemd サービスの状態確認**：
   ```bash
   systemctl status azazel-first-minute
   systemctl status azazel-nat
   systemctl status usb0-static
   ```

3. **ログ確認**（リアルタイム監視）：
   ```bash
   journalctl -u azazel-first-minute -f
   ```

詳細な設定変更やトラブルシューティングについては [installer/README.md](installer/README.md) を参照してください。
