# Azazel-Gadget Infrastructure Migrator

**推測ゼロ、決定論的移行**: 旧機（既存環境）から新機（新環境）への Azazel-Gadget インフラ構成を自動採取し、完全再現します。

## 概要

このツールセットは以下のパイプラインを実現します：

```
旧機: Discovery → Snapshot → Profile → [Mac経由] → 新機: Apply → Validate
```

- **Discovery**: 実機の構成を証拠ベースで採取（推測なし）
- **Snapshot**: Raw データとして保存、秘匿情報をマスク
- **Profile**: YAML形式の決定論的デプロイ定義を生成
- **Apply**: 新機へProfile適用（冪等、dry-run対応）
- **Validate**: 適用結果を検証（PASS/FAIL判定、到達性テスト含む）

## 絶対条件

### 固定要件
- **OS**: Raspberry Pi OS Lite 64bit
- **内向きIF**: usb0, 10.55.0.10 固定
- **外向きIF**: wlan0, DHCP変動
- **NAT**: usb0 → wlan0
- **Suricata**: wlan0 のみ監視
- **OpenCanary**: wlan0 側へ公開（外向き）
- **管理UI**: usb0 側のみ（内向き）
- **SSH**: usb0 経由、鍵認証

### 運用原則
- **旧機では collect のみ実行**（稼働中環境を破壊しない）
- **新機で apply/validate を実行**
- **旧機と新機を同時に同一ネットワークで有効化しない**（IP衝突防止）

## ディレクトリ構造

```
installer/
├── collect_snapshot.sh   # Stage 1: 実機構成採取
├── mask.py               # 秘匿情報マスク
├── generate_profile.py   # Stage 2: Profile生成
├── apply.sh              # Stage 3: 新機へ適用
├── validate.sh           # Stage 4: 検証
├── README.md             # このファイル
├── snapshot/             # 採取データ保存先
│   └── <hostname>_<timestamp>/
├── profiles/             # 生成されたprofile YAML
│   └── gadget_profile_YYYYMMDD.yaml
├── logs/                 # apply/validate ログ
│   ├── apply_<timestamp>/
│   ├── validate_<timestamp>/
│   └── failure_bundle_<timestamp>/
├── templates/            # テンプレートファイル（予約）
└── phases/               # インストールフェーズ（予約）
```

## 移行手順（完全版）

### フェーズ0: 準備（Mac）

リポジトリを最新化し、installerツールをセットアップします。

```bash
# Mac上
cd ~/path/to/Azazel-Zero
git pull origin main
```

---

### フェーズ1: 旧機でSnapshot採取（collect のみ）

**重要**: 旧機では **絶対に apply.sh を実行しない** でください。

```bash
# 旧機へSSH
ssh azazel@10.55.0.10

# リポジトリへ移動
cd ~/Azazel-Zero

# Snapshot採取（root権限必要）
sudo installer/collect_snapshot.sh
```

**出力例**:
```
=== Azazel-Gadget Infrastructure Discovery ===
Hostname: raspberrypi
Timestamp: 20260209-143022
Output: /home/azazel/Azazel-Zero/installer/snapshot/raspberrypi_20260209-143022
```

Snapshot採取が完了したら、秘匿情報をマスクします。

```bash
# 秘匿情報マスク（SSID/PSK, API keys等を ***MASKED*** に置換）
python3 installer/mask.py --snapshot installer/snapshot/raspberrypi_20260209-143022
```

**Profileを生成**:

```bash
# Profile YAML生成
python3 installer/generate_profile.py \
  --snapshot installer/snapshot/raspberrypi_20260209-143022/snapshot.json \
  --out installer/profiles/gadget_profile_20260209.yaml
```

**出力例**:
```
=== Generating Profile ===
Source: installer/snapshot/raspberrypi_20260209-143022

Profile generated: installer/profiles/gadget_profile_20260209.yaml

Next steps:
  # 新機でdry-run:
  sudo installer/apply.sh --profile installer/profiles/gadget_profile_20260209.yaml --dry-run
  # 新機で適用:
  sudo installer/apply.sh --profile installer/profiles/gadget_profile_20260209.yaml
```

---

### フェーズ2: SnapshotとProfileをMacへ回収

```bash
# 旧機から Mac へ rsync
# Mac上で実行
rsync -avz --progress \
  azazel@10.55.0.10:~/Azazel-Zero/installer/snapshot/raspberrypi_20260209-143022 \
  ~/Azazel-Zero/installer/snapshot/

rsync -avz --progress \
  azazel@10.55.0.10:~/Azazel-Zero/installer/profiles/gadget_profile_20260209.yaml \
  ~/Azazel-Zero/installer/profiles/
```

**旧機での作業完了**。以降は新機で作業します。

---

### フェーズ3: 新機の基本セットアップ（必須前提条件）

新機に Raspberry Pi OS Lite 64bit をインストール後、**apply.sh を実行する前に**以下の基本セットアップが必須です。

#### Step 1: Raspberry Pi OS Lite 64bit インストール

Raspberry Pi Imager を使用して新機に OS をインストール：
- **OS**: Raspberry Pi OS Lite (64-bit)
- **Storage**: microSD card
- **Username/Password**: azazel / [your-password]
- **SSH**: Enabled, key-auth preferred

#### Step 2: USB Gadget Mode 有効化

新機の `/boot/firmware/config.txt` に以下を追加:

```ini
# USB Gadget Mode (usb0)
dtoverlay=dwc2
```

新機の `/boot/firmware/cmdline.txt` の末尾に以下を追加（1行に）:

```
modules-load=dwc2,g_ether g_ether.dev_addr=aa:bb:cc:dd:ee:01 g_ether.host_addr=aa:bb:cc:dd:ee:02
```

**再起動**:
```bash
sudo reboot
```

#### Step 3: usb0 の疎通確認

USB ケーブルで Mac と新機を接続後、Mac 側で確認:

```bash
# Mac上
ifconfig | grep -A5 usb0
# または
arp -a | grep -i raspberrypi
```

新機へ SSH 接続可能か確認:

```bash
# Mac上
ssh azazel@10.55.0.1  # または DHCP割り当てIP
```

**重要**: この時点で SSH key-auth が機能していることを確認してください。

#### Step 4: リポジトリと Profile を配置

新機でリポジトリをセットアップ:

```bash
# 新機上
git clone https://github.com/01rabbit/Azazel-Zero.git
cd Azazel-Zero
```

Mac から profile YAML を新機へコピー:

```bash
# Mac上
scp ~/Azazel-Zero/installer/profiles/gadget_profile_20260209.yaml \
  azazel@10.55.0.1:~/Azazel-Zero/installer/profiles/
```

**ここまでで基本セットアップ完了。次が apply.sh です。**

---

### フェーズ4: 新機で Apply（Dry-run → 本番）

**重要**: 以下を確認した上で、必ず最初に `--dry-run` で確認してください：
- ✓ USB gadget mode が有効（usb0 が存在）
- ✓ SSH で新機にアクセス可能
- ✓ Profile YAML が配置されている

```bash
# 新機へSSH
ssh azazel@10.55.0.10

cd ~/Azazel-Zero

# Dry-run（変更なし、ログのみ）
sudo installer/apply.sh \
  --profile installer/profiles/gadget_profile_20260209.yaml \
  --dry-run
```

Dry-runのログを確認し、問題がなければ本番適用します。

```bash
# 本番適用
sudo installer/apply.sh \
  --profile installer/profiles/gadget_profile_20260209.yaml
```

**出力例**:
```
=== Azazel-Gadget Installer ===
Profile: installer/profiles/gadget_profile_20260209.yaml
Dry-run: false
Log: installer/logs/apply_20260209-150022/apply.log

Topology: usb0 (10.55.0.10) <-> wlan0
NAT: True, Firewall: nftables

[Phase 1] Creating backups...
[Phase 2] Configuring network...
[Phase 3] Configuring firewall...
[Phase 4] Setting up Python venv...
[Phase 5] Installing systemd services...

=== Apply Complete ===
Changes applied successfully
Log: installer/logs/apply_20260209-150022/apply.log

Next step:
  sudo installer/validate.sh --profile installer/profiles/gadget_profile_20260209.yaml
```

### フェーズ5: 新機で Validate

適用後、構成が Profile と一致しているか検証します。

```bash
# 検証実行
sudo installer/validate.sh \
  --profile installer/profiles/gadget_profile_20260209.yaml
```

**PASS 例**:
```
=== Azazel-Gadget Configuration Validator ===
Profile: installer/profiles/gadget_profile_20260209.yaml

[1] Topology validation
  ✓ inside_if_ip: PASS
  ✓ outside_if: PASS

[2] Network configuration
  ✓ ip_forward: PASS
  ✓ default_route: PASS

[3] Firewall validation
  ✓ firewall_table: PASS
  ✓ nat_masquerade: PASS

[4] Service validation
  ✓ service_azazel-first-minute: PASS
  ✓ service_azazel-nat: PASS
  ✓ suricata_active: PASS
  ✓ suricata_eve_update: PASS

[5] Reachability validation
  ✓ mgmt_ui_inside: PASS
  ✓ mgmt_ui_bind: PASS

[6] Traffic Control validation
  ✓ tc_enabled: PASS

=== Validation Summary ===
Passed: 12
Failed: 0

✓ VALIDATION PASSED
新機は旧機と同一構成です。運用投入可能です。

Validation report: installer/logs/validate_20260209-150100/validation_result.json
```

**FAIL 例**:
```
=== Validation Summary ===
Passed: 8
Failed: 4

✗ VALIDATION FAILED
失敗した検証項目を修正し、再度applyしてください。
Failure bundle: installer/logs/failure_bundle_20260209-150100

Failure bundle created: installer/logs/failure_bundle_20260209-150100
```

失敗時は `failure_bundle` に診断情報が保存されます。Mac へ回収し、問題を修正後に再度 apply → validate を実行します。

### フェーズ6: カットオーバー

**Validate が PASS したら**:

1. 旧機を停止（`sudo shutdown -h now`）
2. 新機を運用投入
3. クライアントを新機へ接続

**Validate が FAIL したら**:

1. `failure_bundle` を Mac へ回収
2. 問題を修正（Profile や設定ファイルを調整）
3. 新機で再度 `apply.sh` → `validate.sh` を実行

---

## 主要コマンドリファレンス

### collect_snapshot.sh

**旧機で実行**: 実機構成を採取

```bash
sudo installer/collect_snapshot.sh
```

- **出力**: `installer/snapshot/<hostname>_<timestamp>/`
- **採取内容**: ip/route/rule, dhcpcd, resolv.conf, sysctl, ss, nft/iptables, tc, systemd, dpkg, config files

### mask.py

**旧機で実行**: 秘匿情報をマスク

```bash
python3 installer/mask.py --snapshot installer/snapshot/<dir>
```

- **機能**: SSID/PSK, API keys, passwords を `***MASKED***` に置換
- **出力**: 同一ディレクトリ内でファイルを上書き（バックアップ自動作成）

### generate_profile.py

**旧機 or Mac で実行**: Snapshot から Profile YAML 生成

```bash
python3 installer/generate_profile.py \
  --snapshot installer/snapshot/<dir>/snapshot.json \
  --out installer/profiles/gadget_profile_YYYYMMDD.yaml
```

- **出力**: `installer/profiles/gadget_profile_YYYYMMDD.yaml`
- **内容**: トポロジー、NAT、管理UI、Suricata、OpenCanary、services等の決定論的定義

### apply.sh

**新機で実行**: Profile を新機へ適用

```bash
# Dry-run（推奨：最初に実行）
sudo installer/apply.sh --profile <profile.yaml> --dry-run

# 本番適用
sudo installer/apply.sh --profile <profile.yaml>
```

- **機能**: ネットワーク、FW、venv、systemd services をセットアップ
- **冪等性**: 何度実行しても同じ結果
- **バックアップ**: 適用前に自動バックアップ作成
- **ログ**: `installer/logs/apply_<timestamp>/`

### validate.sh

**新機で実行**: 適用結果を検証

```bash
sudo installer/validate.sh --profile <profile.yaml>
```

- **検証項目**:
  - トポロジー（IF, IP）
  - NAT/Forward
  - 管理UI到達性（usb0: OK, wlan0: NG）
  - OpenCanary到達性（wlan0: OK, usb0: NG）
  - Suricata稼働とeve.json更新
  - TC（wlan0）
  - systemd services
- **出力**: JSON レポート（`installer/logs/validate_<timestamp>/validation_result.json`）
- **終了コード**: PASS=0, FAIL=1

---

## トラブルシューティング

### Apply/Validate失敗時

1. **Failure Bundle を確認**:
   ```bash
   cd installer/logs/failure_bundle_<timestamp>
   cat *.txt
   ```

2. **診断情報を Mac へ回収**:
   ```bash
   # Mac上
   rsync -avz azazel@10.55.0.10:~/Azazel-Zero/installer/logs/failure_bundle_* \
     ~/Azazel-Zero/installer/logs/
   ```

3. **問題を修正**:
   - Profile YAML を調整
   - 設定ファイルを修正
   - 手動で問題を解決

4. **再実行**:
   ```bash
   # 新機上
   sudo installer/apply.sh --profile <profile.yaml>
   sudo installer/validate.sh --profile <profile.yaml>
   ```

### USB経由SSH接続が切れた

- Apply中に usb0 設定が変更され、一時的に接続が切れる可能性があります
- 数秒待ってから再接続してください
- `dhcpcd` が usb0 の static IP を適用するまで待機

### nftables template validation failed

- `nftables/first_minute.nft` のトークン置換を確認
- 手動で構文チェック:
  ```bash
  sudo nft -c -f installer/logs/apply_<timestamp>/first_minute_rendered.nft
  ```

---

## 設計原則

### 証拠ベース採取
- **推測禁止**: 存在するだけの設定ファイルは無効
- **実際の参照証跡**: systemd ExecStart, ss, ps から実行中プロセスを特定
- **Raw データ保存**: 解釈前の生データを snapshot として保存

### 冪等性
- **Apply**: 何度実行しても同じ結果
- **Managed Area**: FWは `azazel_fmc` table または `AZAZEL_*` chains のみ変更
- **Flush禁止**: 既存ルールを全削除しない

### 到達性ベース検証
- **管理UI**: usb0 からアクセス可能、wlan0 からは不可
- **OpenCanary**: wlan0 へ公開、usb0 からもアクセス可（内部テスト用）
- **SSH**: usb0 経由のみ（破壊禁止）

---

## Profile YAML 構造例

```yaml
profile_version: '1.0'
generated_at: '2026-02-09T15:00:00+09:00'

source_snapshot:
  hostname: raspberrypi
  collected_at: '2026-02-09T14:30:22+09:00'

topology:
  inside_if: usb0
  inside_ip: 10.55.0.10
  outside_if: wlan0
  outside_ip_dhcp: true

network:
  nat_enabled: true
  ip_forward: true
  firewall_backend: nftables

management_ui:
  enabled: true
  port: 8081
  bind_inside_only: true

suricata:
  enabled: true
  monitor_interface: wlan0

opencanary:
  enabled: true
  expose_outside: true

traffic_control:
  enabled: true
  interface: wlan0

ntfy:
  mode: client

ssh:
  enabled: true
  key_only: true
  allow_inside: true

services:
  - name: azazel-first-minute
    active_state: active
  - name: azazel-nat
    active_state: active
  - name: azazel-web
    active_state: active
  - name: suricata
    active_state: active
  - name: opencanary
    active_state: active
```

---

## ライセンス

Azazel-Zero プロジェクトのライセンスに準拠します。

---

## 参考資料

- [.github/copilot-instructions.md](../.github/copilot-instructions.md): プロジェクト全体の設計方針
- [configs/first_minute.yaml](../configs/first_minute.yaml): ステートマシン設定
- [nftables/first_minute.nft](../nftables/first_minute.nft): FWルールテンプレート
- [systemd/](../systemd/): サービス定義

---

**最終更新**: 2026-02-09
