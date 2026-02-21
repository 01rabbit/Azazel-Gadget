# 統合インストーラ設計書 (Unified Installer Design)

## 現状分析

### 既存インストーラの分散構成
現在、以下のインストーラが複数箇所に点在：

| スクリプト | 場所 | 役割 | 設定ファイル |
|-----------|------|------|-----------|
| install_dependencies.sh | bin/ | APT パッケージ + venv | - |
| install_systemd.sh | bin/ | systemd ユニット + 設定配置 | configs/, systemd/, scripts/ |
| install_waveshare_epd.sh | bin/ | E-Paper ライブラリ | - |
| install_webui.sh | bin/ | Web UI venv とサービス | - |
| install_ntfy.sh | scripts/ | ntfy.sh サーバー | - |
| collect_snapshot.sh | installer/ | スナップショット採取（移行用） | - |
| generate_profile.py | installer/ | プロファイル生成（移行用） | - |
| apply.sh | installer/ | プロファイル適用（移行用） | - |

**問題点**:
1. ユーザーが 4～5 個のスクリプトを順番に実行する必要
2. 手順が複雑で、ステップごとに詳細ドキュメントが必要
3. ネットワーク設定変更（IP 割り当て）のタイミングが不明確
4. 再起動タイミング、再起動後の再実行が仕様化されていない
5. 設定ファイルが複数箇所に散在（configs/, systemd/, scripts/）

### 新しい要件
1. **ワンコマンドインストール**: 単一スクリプトで全機能セットアップ
2. **ネットワーク変更対応**: インストール中の IP 割り当て変更を検出・対応
3. **再起動判定**: ネットワーク構成変更時に再起動促促し、再起動後の再実行をサポート
4. **設定統合**: 全設定ファイルを統一管理
5. **プロファイル廃止**: snapshot/migrate/generate_profile/apply の廃止

---

## 目標アーキテクチャ

### 新しいディレクトリ構造

```
project-root/
├── install.sh ★              # メインインストーラ（唯一のエントリーポイント）
├── bin/
│   ├── _installer_lib.sh      # インストーラ共通ライブラリ（内部）
│   └── [その他の既存スクリプト]
├── installer/
│   ├── README.md              # インストール手順（簡素化）
│   ├── defaults/              # デフォルト設定テンプレート
│   │   ├── first_minute.yaml
│   │   ├── dnsmasq-first_minute.conf
│   │   ├── opencanary.conf
│   │   └── ...
│   ├── profiles/              # 廃止予定（互換性のため保持）
│   ├── stages/                # インストールフェーズ（新規）
│   │   ├── 00_precheck.sh
│   │   ├── 10_dependencies.sh
│   │   ├── 20_network.sh
│   │   ├── 30_config.sh
│   │   ├── 40_services.sh
│   │   └── 99_validate.sh
│   └── logs/
│       └── [install_TIMESTAMP.log]
├── configs/                   # 設定テンプレート
│   ├── first_minute.yaml
│   ├── dnsmasq-first_minute.conf
│   ├── opencanary.conf
│   ├── known_wifi.json
│   └── iptables-rules.v4
└── [その他]
```

### インストーラの実行フロー

```
$ sudo ./install.sh [OPTIONS]
  │
  ├─► [Stage 00] 環境チェック（root, OS, ディスク容量）
  │    └─► 既存インストール検出
  │    └─► ネットワーク構成確認（wlan0 SSID, usb0 状態）
  │
  ├─► [Stage 10] 依存パッケージインストール
  │    └─► APT 更新
  │    └─► 基本パッケージ（nftables, dnsmasq, tc など）
  │    └─► オプション（--with-canary, --with-epd, --with-webui, --with-ntfy）
  │
  ├─► [Stage 20] ネットワーク構成変更 ⭐ 【重要】
  │    └─► usb0 物理インターフェース確認
  │    └─► usb0 を 10.55.0.10 に UP
  │    └─► NAT、ファイアウォール適用
  │    └─► ⚠️ この時点でラップトップ接続が変わる
  │    └─► ネットワーク変更を検出 → ユーザーに再起動促促
  │    │   * "ネットワーク構成が変わりました。再起動してください: reboot"
  │    │   * "再起動後、このスクリプトを再実行してください"
  │    │   * exit 0
  │    └─► 再起動後、Stage 30 から再実行
  │
  ├─► [Stage 30] 設定ファイル配置・管理
  │    └─► /etc/azazel-zero/ へ設定テンプレートコピー
  │    └─► YAML パース・修正（例：実際の SSID を埋め込み）
  │    └─► 秘匿情報マスク確認
  │
  ├─► [Stage 40] systemd サービス登録＆起動
  │    └─► systemd ユニット配置
  │    └─► サービス有効化
  │    └─► 起動テスト
  │
  └─► [Stage 99] 検証＆完了
       └─► 各サービスの起動確認
       └─► ネットワーク疎通確認（DNS, DHCP）
       └─► 初期化成功ログ出力
       └─► 完了メッセージ
```

---

## 詳細設計

### 1. メインエントリーポイント: `install.sh`

```bash
#!/bin/bash
# install.sh - Azazel-Gadget Unified Installer
# 
# 使用法:
#   sudo ./install.sh                              # 標準インストール
#   sudo ./install.sh --with-webui --with-canary  # オプション付き
#   sudo ./install.sh --dry-run                   # プレビュー
#   sudo ./install.sh --resume                    # 前回の中断から再開

OPTIONS="--with-webui --with-canary --with-epd --with-ntfy --dry-run --resume"
```

**機能**:
- オプションパース
- ステージ 00 実行
- ネットワーク変更検出
- 再起動判定＆ユーザー通知
- ステージ順序実行
- エラー復帰＆再開

**出力**: `installer/logs/install_YYYYMMDD-HHMMSS.log`

### 2. インストール段階フェーズ

#### Stage 00: Prerequisites Check

```bash
# 実行内容
- root 権限確認
- OS (Raspberry Pi OS Bullseye/Trixie 64-bit) 確認
- ディスク容量確認（最小 2GB 自由容量）
- wlan0 インターフェース確認
- usb0 インターフェース確認（存在チェックのみ、UP 未要求）
- 既存インストール検出

# 出力: STAGE_00_PASSED=1 または abort with error
```

#### Stage 10: Package Installation

```bash
# 実行内容
- apt-get update
- 基本パッケージ群:
  * ネットワーク: iproute2, iptables, nftables, dnsmasq
  * 管理: python3, python3-venv, python3-yaml, python3-requests
  * 脅威検知: suricata
  * 雑多: git, curl, jq, tmux, wireless-tools

# オプション分岐:
- --with-canary: OpenCanary venv (/home/azazel/canary-venv)
- --with-epd: Waveshare E-Paper deps
- --with-webui: Flask Web UI deps
- --with-ntfy: ntfy.sh サーバー

# 出力: STAGE_10_PASSED=1
```

#### Stage 20: Network Configuration ⭐【重要】

```bash
# 実行内容
1. usb0 物理インターフェース確認 → なければ abort
2. usb0 を UP、10.55.0.10/24 アドレス設定
3. iptables NAT ルール適用 (wlan0 → usb0)
4. nftables ベースルール適用
5. dnsmasq 起動テスト

# ネットワーク変更検出ロジック:
- インストール前の ip addr show wlan0 を記録
- インストール後の ip addr show wlan0 を確認
- IF：DHCP リース再取得、IP 割り当て変更されたか
  → YES: Stage 20_NETWORK_CHANGED=1 をセット
        ユーザーに再起動促促して exit 0

# 再起動後の再実行:
- `install.sh --resume` で Stage 30 以降を実行
- Stage 20 をスキップ

# 出力: STAGE_20_PASSED=1 または STAGE_20_NETWORK_CHANGED=1
```

#### Stage 30: Configuration Files

```bash
# 実行内容
1. /etc/azazel-zero/ ディレクトリ作成
2. テンプレートコピー:
   - first_minute.yaml
   - dnsmasq-first_minute.conf
   - opencanary.conf
   - known_wifi.json
   - iptables-rules.v4
3. オプション：実機環境の自動検出＆反映
   - wlan0 の現在の DHCP 設定を読み込み
   - dnsmasq ローカルドメイン設定最適化
4. 秘匿情報チェック:
   - SSID, PSK はテンプレートで示し、手動編集促促

# 出力: /etc/azazel-zero/* 配置完了
```

#### Stage 40: Systemd Services

```bash
# 実行内容
1. systemd ユニット配置:
   - azazel-first-minute.service
   - azazel-epd.service
   - opencanary.service
   - azazel-web.service (--with-webui の場合)
2. 起動スクリプト配置:
   - /usr/local/sbin/usb0-static.sh
   - /usr/local/sbin/azazel-nat.sh
3. /etc/default/azazel-zero 作成
4. サービス有効化：
   systemctl daemon-reload
   systemctl enable --now azazel-first-minute.service
   systemctl enable --now usb0-static.service
   ...

# 出力: systemctl status
```

#### Stage 99: Validation

```bash
# 実行内容
1. 各サービスの起動確認:
   - azazel-first-minute
   - usb0-static
   - dnsmasq
   - (optional) azazel-web, opencanary
2. ネットワーク疎通確認:
   - usb0 が UP しているか
   - DHCP ポート (67) が開いているか
   - DNS ポート (53) が開いているか
3. ログチェック:
   - journalctl -u azazel-first-minute -n 20
   - /var/log/azazel-dnsmasq.log

# 出力: 成功/失敗判定
```

### 3. ネットワーク再起動対応メカニズム

**仕様**:
- Stage 20 実行時に、wlan0 の IP が変わったか検出
- 変わった場合、ユーザーに再起動を促促
- `install.sh --resume` で Stage 30 以降を再実行

**実装方法**:
```bash
# install.sh 内に以下を保存:
INSTALL_STATE_FILE="/tmp/azazel-install-state-$UID.json"

# Stage 00 後、状態ファイルに記録:
{
  "timestamp": "2026-02-11T12:00:00Z",
  "stage": 00,
  "wlan0_ip_before": "192.168.1.100",
  "options": "--with-webui --with-canary"
}

# Stage 20 実行前後で IP 比較:
WLAN0_IP_AFTER=$(ip -4 addr show wlan0 | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | head -1)
if [[ "$WLAN0_IP_BEFORE" != "$WLAN0_IP_AFTER" ]]; then
  echo "⚠️  Network configuration changed: $WLAN0_IP_BEFORE → $WLAN0_IP_AFTER"
  echo "Please reboot: sudo reboot"
  echo "After reboot, run: sudo ./install.sh --resume"
  jq '.stage = 29' "$INSTALL_STATE_FILE" > "$INSTALL_STATE_FILE.tmp"
  mv "$INSTALL_STATE_FILE.tmp" "$INSTALL_STATE_FILE"
  exit 0
fi

# --resume フラグで Stage 30 以降スキップ
if [[ "${RESUME:-0}" == "1" ]]; then
  STAGE=30  # Stage 30 から開始
fi
```

### 4. 設定ファイル統合管理

**新しい構造**:
```
installer/defaults/
├── first_minute.yaml          # ステートマシン設定
├── dnsmasq-first_minute.conf  # DHCP/DNS プロキシ
├── opencanary.conf            # ハニーポット
├── known_wifi.json            # 既知 SSID DB
├── iptables-rules.v4          # NAT ルール
└── nftables-first_minute.nft  # ファイアウォール（symlink）
```

**配置ロジック**:
1. インストール時、`installer/defaults/*` → `/etc/azazel-zero/*` コピー
2. 秘匿情報（SSID, PSK）は Template comment 化
3. ユーザーが `/etc/azazel-zero/first_minute.yaml` を編集
4. 再起動時は serviceが `/etc/azazel-zero/` を読込

---

## プロファイルシステムの廃止

### 廃止対象
1. ✗ `installer/generate_profile.py`
2. ✗ `installer/apply.sh --profile`
3. ✗ `installer/profiles/` ディレクトリ
4. ✗ `installer/collect_snapshot.sh` （マイグレーション機能）

### 保持対象
- `installer/validate.sh`: スナップショット検証ツールとして単体保持

### 棄却根拠
- Azazel-Gadget は固定インフラ（IP, IF 固定）
- プロファイル は複数マシン適用ユースケース向け（本プロジェクトに不要）
- スナップショット採取も本番運用では不要（基本テンプレートで事足りる）

### 移行計画
- 現在のプロファイルユーザーへの通知
- `installer/README.md` で新しい手順に更新
- 1-2 バージョン待つ　→　完全削除

---

## 実装スケジュール

### Phase 1: 設計＆テンプレート準備 (2-3 日)
- [ ] installer/defaults/ テンプレート作成
- [ ] installer/stages/ ディレクトリ構造作成
- [ ] Stage 00-99 スクリプト骨組み
- [ ] インストーラ共通ライブラリ作成

### Phase 2: コア実装 (1 週間)
- [ ] install.sh メインループ実装
- [ ] Stage 00-99 各段階の実装
- [ ] ネットワーク変更検出ロジック
- [ ] 再起動判定＆再開メカニズム

### Phase 3: テスト＆検証 (3-5 日)
- [ ] 開発環境でのテスト
- [ ] Pi Zero での実機テスト
- [ ] 再起動シナリオテスト
- [ ] ロールバック手順確認

### Phase 4: ドキュメント＆廃止 (3 日)
- [ ] README 更新（シンプル化）
- [ ] 旧インストーラ廃止通知
- [ ] 詳細なインストール手順ドキュメント

---

## ユーザー体験（UX）

### 新しい操作
```bash
# 初回インストール（最初）
$ sudo ./install.sh --with-webui --with-canary

# ネットワーク構成警告
  ⚠️  Network configuration changed. Restarting required.
  $ sudo reboot

# 再起動後
$ sudo ./install.sh --resume
  (Stage 30 以降が実行される)
```

### 既存環境の更新
```bash
# アップグレード時
$ git pull origin main
$ sudo ./install.sh --upgrade
  (既存設定を保持しつつアップデート)
```

---

## 利点

| 観点 | 現在 | 改善後 |
|------|------|--------|
| ユーザー実行コマンド数 | 4-5 個 | **1 個** |
| インストール時間 | 15-20 分（手作業多） | **8-12 分**（自動化） |
| ネットワーク再起動対応 | なし(手動) | **自動検出＆再開** |
| 設定ファイル管理 | 分散（3 箇所） | **統合（1 箇所）** |
| トラブルシューティング | 複雑 | **シンプル** |
| テスト容易性 | 低 | **高** |

---

## リスク＆ミティゲーション

| リスク | 対策 |
|--------|------|
| スクリプト複雑化 | モジュール化（_lib.sh）、関数化 |
| ネットワーク変更検出ミス | 複数条件併用（IP, GW, DNS） |
| systemd 依存関係破壊 | Requires/After を厳格に |
| 既存ユーザーへの影響 | 旧スクリプトも1-2バージョン並存 |

