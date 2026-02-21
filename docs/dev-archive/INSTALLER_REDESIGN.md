# インストーラ設計の再検討：プロファイル層の必要性分析

## 現在の問題点

ユーザーの指摘が正当です。現在のパイプラインは：

```
旧機: collect_snapshot.sh
  ↓ (raw機密情報付き)
mask.py (秘匿情報マスク)
  ↓ (masked snapshot JSON)
[Mac経由転送]
generate_profile.py (プロファイル YAML 生成)
  ↓ (YAML profile)
新機: apply.sh --profile profile.yaml
  ↓
validate.sh (検証)
```

### なぜプロファイル層が冗長か

1. **Azazel-Zero は固定インフラ**
   - IP アドレス：10.55.0.10（固定）
   - インターフェース：usb0（固定）、wlan0（固定）
   - ホスト名：raspberrypi（Raspberry Pi OS デフォルト）
   - OS：Raspberry Pi OS Lite 64bit のみ対応

2. **スナップショットが既に「完全」**
   - `collect_snapshot.sh` は以下を採取：
     - ネットワーク設定（ip addr, ip route）
     - ファイアウォール（nftables ruleset）
     - サービス状態（systemd）
     - 設定ファイル（/etc/azazel-zero/ など）
   - つまり、スナップショットには「新機に必要な**すべての情報**」が含まれている

3. **プロファイルが「追加」するもの**
   - YAML パース・生成という処理時間
   - 中間層（JSON → YAML 変換）という複雑性
   - スナップショットとプロファイルの二重保守
   - ユーザーへの手順説明の複雑化

4. **利用パターンの実態**
   - 「旧機（稼働環境）から新機（置き換え先）への migration」
   - つまり、**一度きりの適用**
   - 複数マシンへの繰り返し適用ではない
   - プロファイルの再利用性はない

## 改善案

### 案 1: ダイレクト適用モード（推奨）

**流れ**:
```
旧機: collect_snapshot.sh
  ↓
mask.py (秘匿情報マスク)
  ↓
[転送]
  ↓
新機: apply_snapshot.sh --snapshot <snapshot_dir>
  ↓
validate.sh
```

**メリット**:
- ステップ削減（generate_profile 不要）
- スナップショット JSON を直接 apply
- シンプルで理解しやすい
- 実行時間短縮

**実装方法**:
1. `apply_snapshot.sh` を新規作成
2. スナップショット JSON を直接パース
3. 秘匿情報マスク済みのデータを即座に反映
4. `generate_profile.py` は廃止（または --legacy フラグ化）

**対応コマンド例**:
```bash
# 旧機：capture
sudo installer/collect_snapshot.sh
python3 installer/mask.py --snapshot installer/snapshot/raspberrypi_20260211-120000

# 新機：apply directly
sudo installer/apply_snapshot.sh --snapshot installer/snapshot/raspberrypi_20260211-120000 --dry-run
sudo installer/apply_snapshot.sh --snapshot installer/snapshot/raspberrypi_20260211-120000
sudo installer/validate.sh
```

### 案 2: ハイブリッドモード（慎重な運用向け）

**流れ**:
```
旧機: collect_snapshot.sh → mask.py
  ↓
(dev/audit 用途のみ)
新機: apply_snapshot.sh OR apply.sh --profile
```

**メリット**:
- 現在のプロファイルシステムも並存
- 必要に応じてプロファイルで監査
- 移行時間が短い（両方の方法をサポート）
- legacy コードを完全削除しない

**実装方法**:
1. `apply_snapshot.sh` を追加
2. `apply.sh` はそのまま （deprecated として扱う）
3. README で「推奨は apply_snapshot」と記載
4. テストで両方をサポート

### 案 3: テンプレート化モード（単一ソース・オブ・トゥルース）

**流れ**:
```
リポジトリの config base templates
  ↓
旧機: collect_snapshot.sh （オプション）
  ↓
新機: direct_install.sh --repo-only
  OR
新機: install_from_snapshot.sh --snapshot <snapshot_dir>
```

**メリット**:
- スナップショット採取さえ不要な場合もある
- リポジトリのテンプレート設定で事足りる
- CI/CD パイプライン対応
- 新機セットアップが最短化

**実装方法**:
1. `/etc/azazel-zero/` 配下の固定テンプレートを用意
2. 移行時は「このテンプレートをベースに、スナップショット上書き」
3. スナップショット省略時は「テンプレート as-is」で install

---

## 推奨：ダイレクト適用モード + ドキュメント修正

Azazel-Zero の文脈では、**案 1（ダイレクト適用モード）** が最適です。理由：

| 観点 | ダイレクト | プロファイル |
|------|-----------|----------|
| ステップ数 | 3（collect→mask→apply） | 4（+generate）|
| 理解難易度 | 簡易（JSON直接） | 中程度（YAML生成） |
| 一度きり移行 | ✓優秀 | 過剰機能 |
| 複数マシン | × | ✓ |
| 監査性 | 中（JSON） | ◎（YAML） |
| **本プロジェクトの適性** | **◎推奨** | △不要 |

### 移行計画

#### Phase 1: `apply_snapshot.sh` 実装（1.0版）
```bash
# 新規作成
installer/apply_snapshot.sh

# 機能:
# - スナップショットディレクトリを読込
# - JSON から各設定を直接パース
# - nftables/tc/dnsmasq を apply
# - dry-run サポート
# - 秘匿情報チェック（***MASKED***）
```

#### Phase 2: ドキュメント更新（README.md）
```markdown
## クイックスタート（推奨）
旧機 → 新機への最短移行

1. 旧機で snapshot 採取
   sudo installer/collect_snapshot.sh
   python3 installer/mask.py --snapshot <snapshot_dir>

2. 新機で適用
   sudo installer/apply_snapshot.sh --snapshot <snapshot_dir>
   sudo installer/validate.sh

## 従来の方法（プロファイル YAML）
複数マシンへの適用や監査が必要な場合：
generate_profile.py で YAML を生成し、
apply.sh で個別選択適用
```

#### Phase 3: `generate_profile.py` のステータス変更
- README で「advanced/optional」として記載
- コメント追加：「単一機械の移行なら不要」
- テストは両方式維持

---

## 実装アプローチ

### Case A: 完全移行（推奨、破壊的変更）
- apply_snapshot.sh を実装
- generate_profile.py を deprecated
- README から削除（ドキュメント簡素化）
- **デメリット**: legacy ユーザーの混乱

### Case B: 段階移行（保守的、互換性維持）
- apply_snapshot.sh を追加
- generate_profile.py は並存
- README で「推奨」明記
- 数バージョン後に deprecated
- **メリット**: 既存ユーザーへの影響最小

**推奨: Case B**（段階移行）

---

## まとめ

| 質問 | 回答 |
|------|------|
| **プロファイル層は本当に必要か？** | Azazel-Zero の文脈では**不要**。スナップショットで十分。 |
| **スナップショットから直接適用できるか？** | **はい**。情報がすべて含まれているため可能。 |
| **いつプロファイルが有用か？** | 複数マシンへの繰り返し適用、監査が必要な場合のみ。本プロジェクトでは該当しない。 |
| **推奨アクション** | ダイレクト適用モード実装 + README 簡素化 |

---

## 参考：現在の複雑性

### 現在のファイル群
```
installer/
├── collect_snapshot.sh    # 採取（必須）
├── mask.py                # マスク（必須）
├── generate_profile.py    # プロファイル生成（不要）←
├── apply.sh              # YAML 適用（不要）←
└── validate.sh           # 検証（必須）
```

### 改善後
```
installer/
├── collect_snapshot.sh        # 採取（必須）
├── mask.py                    # マスク（必須）
├── apply_snapshot.sh          # JSON 直接適用（推奨）
├── apply.sh                   # YAML 適用（deprecated）
├── generate_profile.py        # プロファイル生成（deprecated）
└── validate.sh               # 検証（必須）
```

ファイル数は増加していたが、実は「廃止すべき」コンポーネントを発見したということです。

