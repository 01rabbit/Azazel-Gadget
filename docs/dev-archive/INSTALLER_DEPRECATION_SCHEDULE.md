# 統合インストーラ - 廃止完了通知

## ✅ 廃止完了（2026年2月11日）

以下のスクリプトとディレクトリは **完全に削除されました**。

### 削除されたスクリプト

| スクリプト | 代替手段 |
|-----------|--------|
| `installer/collect_snapshot.sh` | `sudo ./install.sh` で直接インストール |
| `installer/mask.py` | テンプレート設定（installer/defaults/）で代替 |
| `installer/generate_profile.py` | 不要（プロファイルシステム廃止） |
| `installer/apply.sh` | `sudo ./install.sh` で直接インストール |
| `bin/install_dependencies.sh` | `sudo ./install.sh` |
| `bin/install_systemd.sh` | `sudo ./install.sh` |
| `bin/install_waveshare_epd.sh` | `sudo ./install.sh --with-epd` |
| `bin/install_webui.sh` | `sudo ./install.sh --with-webui` |
| `scripts/install_ntfy.sh` | `sudo ./install.sh --with-ntfy` |
| `tools/bootstrap_zero.sh` | `sudo ./install.sh` |

### 削除されたディレクトリ

| ディレクトリ | 理由 |
|------------|------|
| `installer/snapshot/` | スナップショットシステム廃止 |
| `installer/__pycache__/` | 不要なキャッシュ |
| `installer/phases/` | 古いステージシステム廃止 |
| `installer/profiles/` | プロファイルシステム廃止 |
| `installer/templates/` | installer/defaults/ に統合 |
| `installer/logs/` | 不要なログディレクトリ |

## 現在のインストール方法

### 基本インストール
```bash
cd ~/azazel
sudo ./install.sh
```

### オプション機能の有効化
```bash
sudo ./install.sh --with-webui --with-canary --with-epd --with-ntfy
# または
sudo ./install.sh --all
```

## ユーザーへの影響

### 既存ユーザー
- 古いスクリプトを使用している場合は、新しい `./install.sh` への移行を推奨
- 既存環境が安定している場合は、再インストールは不要

### 新規ユーザー
- **必須**: `sudo ./install.sh` を使用
- 古いドキュメントの手順は無効

## 廃止理由の詳細

### なぜプロファイルシステムは廃止か

Azazel-Gadget のインフラは **完全に固定** です：
- IP アドレス：10.55.0.10（ハードコード）
- インターフェース：usb0（ダウンストリーム）、wlan0（アップストリーム）
- ホスト名：raspberrypi（Raspberry Pi OS デフォルト）
- OS：Raspberry Pi OS Lite 64bit のみ

したがって、プロファイルを複数マシンで再利用する価値がありません。

### なぜスナップショット採取も不要か

本番環境でのマイグレーション用途（旧機 → 新機）では：
1. 環境がほぼ同一（固定インフラ）
2. テンプレート設定で十分対応可能
3. スナップショット採取の手間 > 直接セットアップ

**結論**: 統合インストーラが複数個別スクリプトより優れている

## 移行代替案

### ケース 1: 既存環境の保持（推奨）

```bash
# 既存環境のバックアップ
sudo bash bin/diagnose_dhcp.sh > backup_diagnosis.txt
cp /etc/azazel-zero/* ~/backup_config/

# 新規同等環境セットアップ
cd ~/azazel
sudo ./install.sh
```

### ケース 2: アップグレード

```bash
cd ~/azazel
git pull origin main
sudo ./install.sh  # 既存設定は上書き⚠️
```

### ケース 3: マイグレーション（同じ Raspberry Pi）

```bash
# 最新コード取得
cd ~/azazel
git pull origin main

# 既存設定をバックアップ
sudo cp -r /etc/azazel-zero ~/backup_old_config

# 再インストール（テンプレートから）
sudo ./install.sh

# 必要に応じて設定をマージ
# /etc/azazel-zero/first_minute.yaml を nano で編集
```

## FAQ

### Q: 既存の `install_dependencies.sh` で大量カスタマイズしている場合？

**A**: 統合インストーラは modularized なので、必要に応じて以下操作が可能：

```bash
# 個別ステージ再実行（例：Stage 40 のみ）
bash installer/stages/40_services.sh

# 全段階再実行
sudo ./install.sh
```

### Q: 古いプロファイルを保持したい場合？

**A**: **推奨しません**が、必要なら：

```bash
# プロファイル  ディレクトリをアーカイブ
tar czf ~/old_profiles.tar.gz installer/profiles/

# v3.0 へのアップグレード時も保持
# git checkout v2.x を使用（非推奨）
```

### Q: スナップショット採取機能は絶対不要？

**A**: 次のような場合は保持価値あり：
- 複数 Raspberry Pi への同一構成展開
- インフラ監査・ドキュメント化
- API 統合自動化

ただし Azazel-Gadget では固定インフラなため不要。

---

## 実装ステータス

| 項目 | ステータス　 |
|------|---------|
| 統合インストーラ実装 | ✅ 完了 |
| ドキュメント整備 | ✅ 完了 |
| 既存スクリプト並存 | ✅ 動作 |
| テスト | 🔄 進行中 |
| 廃止警告追加 | ⏳ 次フェーズ |
| 削除実行 | ⏳ v3.0 予定 |

