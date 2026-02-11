# 統合インストーラ - 廃止スケジュール

## 廃止対象ツール

以下のスクリプトは元のプロファイルシステムに関連するため、**廃止予定**となります：

| スクリプト | 廃止理由 | 代替手段 |
|-----------|--------|--------|
| `installer/collect_snapshot.sh` | スナップショット採取は本番運用では不要 | `sudo ./install.sh` で直接インストール |
| `installer/mask.py` | プロファイルシステムとともに廃止 | テンプレート設定で事足りる |
| `installer/generate_profile.py` | プロファイル層は冗長（固定インフラ） | 不要 |
| `installer/apply.sh --profile` | プロファイル適用は廃止 | ダイレクトインストール |
| `bin/install_dependencies.sh` | 統合インストーラに吸収 | `sudo ./install.sh` |
| `bin/install_systemd.sh` | 統合インストーラに吸収 | `sudo ./install.sh` |
| `bin/install_waveshare_epd.sh` | 統合インストーラに吸収 | `sudo ./install.sh --with-epd` |
| `bin/install_webui.sh` | 統合インストーラに吸収 | `sudo ./install.sh --with-webui` |
| `scripts/install_ntfy.sh` | 統合インストーラに吸収 | `sudo ./install.sh --with-ntfy` |

## 廃止スケジュール

### Phase 1: 移行期（v2.0 - v2.1） ✅ 現在地
- ✅ 統合インストーラ `install.sh` リリース
- ✅ 新しいドキュメント公開
- ⚠️ **古いスクリプトは並存（廃止警告を表示）**
- 推奨：新規ユーザーは統合インストーラを使用

### Phase 2: 廃止通知期（v2.2 - v2.3） 予定
- 古いスクリプトの先頭に deprecated 警告を追加
- 機能不具合の修正は受け付けない（セキュリティパッチのみ）
- ドキュメントから古い手順を削除

### Phase 3: 削除（v3.0 以降） 予定
- 古いスクリプト完全削除
- `installer/profiles/`、`installer/snapshot/` ディレクトリ削除

## ユーザーへの影響

### 既存ユーザー（古いインストーラ使用中）
**推奨アクション**:
1. 新しい `install.sh` でのインストール再実行を検討
2. 既存環境が安定している場合は、そのまま運用可能

### 新規ユーザー
**必須**:
- `sudo ./install.sh` を使用
- 古いスクリプトは使用しないこと

## 廃止理由の詳細

### なぜプロファイルシステムは廃止か

Azazel-Zero のインフラは **完全に固定** です：
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
cd ~/Azazel-Zero
sudo ./install.sh
```

### ケース 2: アップグレード

```bash
cd ~/Azazel-Zero
git pull origin main
sudo ./install.sh  # 既存設定は上書き⚠️
```

### ケース 3: マイグレーション（同じ Raspberry Pi）

```bash
# 最新コード取得
cd ~/Azazel-Zero
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

ただし Azazel-Zero では固定インフラなため不要。

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

