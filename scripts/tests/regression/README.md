# 回帰テストスクリプト (v3.0 対応)

このディレクトリには回帰テスト実施用のスクリプトが含まれています。

**対応テスト計画**: 回帰テスト計画 v3.0（実装準拠・パラメータスナップショット方式）

## 📁 ディレクトリ構成

```
scripts/tests/regression/
├── README.md                    # このファイル
├── check_tools.sh               # ツール確認スクリプト
├── setup_env.sh                 # 環境セットアップスクリプト
├── inject_suricata_alert.sh     # Suricataアラート注入ヘルパー
├── measure_contain_recovery.sh  # CONTAIN復帰測定スクリプト
├── run_test1_wifi.sh            # テスト1: 不審AP検知
├── run_test2_suricata.sh        # テスト2A: Suricata→CONTAIN遷移
├── run_test2b_cooldown.sh       # テスト2B: Cooldown機構検証
├── run_test7_router_regression.sh # テスト7: ルータ疎通回帰
└── run_all_tests.sh             # 全テスト一括実行
```

## 🚀 クイックスタート

### 1. ツール確認
```bash
./scripts/tests/regression/check_tools.sh
```

すべてのツールと依存関係が正常かチェックします。

### 2. 環境セットアップ
```bash
./scripts/tests/regression/setup_env.sh
```

テスト環境を初期化します（ログクリア、eve.json 準備など）。

### 3. 個別テスト実行

#### テスト1: 不審AP検知
```bash
./scripts/tests/regression/run_test1_wifi.sh "Known-Evil-SSID" "password123"
```

#### テスト2A: Suricata→CONTAIN遷移
```bash
./scripts/tests/regression/run_test2_suricata.sh
```

#### テスト3: CONTAIN復帰測定
```bash
./scripts/tests/regression/measure_contain_recovery.sh
```

#### テスト2B: Cooldown機構検証
```bash
./scripts/tests/regression/run_test2b_cooldown.sh
```

#### テスト7: ルータ疎通回帰
```bash
./scripts/tests/regression/run_test7_router_regression.sh
```

非対話モード:
```bash
./scripts/tests/regression/run_test7_router_regression.sh --non-interactive
```

### 4. 全テスト一括実行
```bash
./scripts/tests/regression/run_all_tests.sh
```

テスト2A、3、2B を自動実行します（テスト1は手動、テスト7は任意）。

## 📝 各スクリプト詳細

### check_tools.sh
必要なツールと設定ファイルを確認します。

**確認項目**:
- システムコマンド (python3, jq, curl, iw, etc.)
- Python パッケージ (pillow, waveshare-epd)
- テストスクリプト
- 設定ファイル
- systemd サービス
- Web API 疎通

**使用例**:
```bash
./scripts/tests/regression/check_tools.sh
# ✓ すべてのツール/設定が正常です → テスト実施可能
# ✗ X件の問題が見つかりました → 修正が必要
```

### setup_env.sh
テスト環境を初期化し、実装パラメータのスナップショットを取得します。

**実行内容**:
1. 構文チェック (test_redesign_verification.py)
2. systemd サービス確認
3. Web API 疎通確認
4. eve.json 準備
5. 既知悪質AP設定確認
6. EPD ドライバテスト
7. **実装パラメータ・スナップショット取得** (v3.0 追加)
   - Git コミット情報記録
   - first_minute.yaml バックアップ
   - API ベースライン保存
   - Journal ベースライン保存
8. ログ初期化
9. テスト開始時刻記録

**スナップショット保存先**: `/tmp/azazel_regression_artifacts/`

**使用例**:
```bash
./scripts/tests/regression/setup_env.sh
# [7/9] 実装パラメータ・スナップショット取得...
#   ✓ Git コミット: a1b2c3d4
#   ✓ first_minute.yaml スナップショット保存
#   主要パラメータ:
#     contain_threshold: 50
#     decay_per_sec: 3
#   ✓ スナップショット保存先: /tmp/azazel_regression_artifacts/
# [✓] セットアップ完了
```

### inject_suricata_alert.sh
Suricata アラートを eve.json に注入します。

**パラメータ**:
- `$1`: severity (1=Critical, 2=Major, 3=Minor)
- `$2`: メッセージ

**使用例**:
```bash
./scripts/tests/regression/inject_suricata_alert.sh 1 "Test Attack"
# ✓ アラート注入成功
```

### measure_contain_recovery.sh
CONTAIN状態の復帰タイムラインを測定します。

**測定内容**:
- 0-70秒まで5秒ごとに state と suspicion を記録
- 結果を `/tmp/contain_recovery.log` に保存

**使用例**:
```bash
./scripts/tests/regression/measure_contain_recovery.sh
# 測定を開始しますか? [y/N]: y
# T=0秒 [12:00:00] state=CONTAIN, suspicion=50.0
# ...
# 測定完了
```

### run_test1_wifi.sh
不審APへの接続テストを実行します。

**パラメータ**:
- `$1`: SSID
- `$2`: パスワード（オプション）

**判定基準**:
- user_state が警告状態へ遷移
- risk_score が増加
- wifi_tags が記録される

**使用例**:
```bash
./scripts/tests/regression/run_test1_wifi.sh "Known-Evil-SSID" "password123"
# ✓✓✓ テスト1: PASS ✓✓✓
```

### run_test2_suricata.sh
Suricataアラート検知からCONTAIN遷移をテストします。

**判定基準**:
- 15秒以内にCONTAIN状態へ遷移
- suspicion が50以上に達する

**使用例**:
```bash
./scripts/tests/regression/run_test2_suricata.sh
# ✓✓✓ テスト2A: PASS ✓✓✓
```

### run_test2b_cooldown.sh
Suricata Cooldown機構（30秒）を検証します。

**判定基準**:
- 5秒以内の追加アラートで suspicion 加算されない
- 30秒後の再アラートで suspicion 加算される

**使用例**:
```bash
./scripts/tests/regression/run_test2b_cooldown.sh
# ✓✓✓ テスト2B: PASS ✓✓✓
```

### run_test7_router_regression.sh
ルータ機能の回帰（FORWARD/NAT/stage mark）を検証します。

**判定基準**:
- `nftables/first_minute.nft` が `meta mark` ベースである
- 実行時ルールで `mark set` が `vmap` より前にある
- Pi 自身の上流疎通（ICMP/HTTPS）が成功
- クライアント通信後に FORWARD/NAT カウンタが増加

**使用例**:
```bash
./scripts/tests/regression/run_test7_router_regression.sh
# ✓✓✓ テスト7: PASS ✓✓✓
```

### run_all_tests.sh
テスト2A、3、2Bを自動実行します（テスト7は任意実行）。

**実行フロー**:
1. 環境セットアップ
2. ツール確認
3. テスト2A実行
4. テスト3実行（測定）
5. テスト2B実行

**結果出力**:
- `/tmp/azazel_regression_test_results.txt`
- `/tmp/contain_recovery.log`

**使用例**:
```bash
./scripts/tests/regression/run_all_tests.sh
# テストを開始しますか? [y/N]: y
# ...
# ✓✓✓ 全テスト PASS ✓✓✓
```

## 🔍 トラブルシューティング

### ツール確認で失敗する
```bash
./scripts/tests/regression/check_tools.sh
# ✗ jq (未インストール)
# → sudo apt install jq
```

### eve.json への書き込み権限エラー
```bash
sudo chmod 666 /var/log/suricata/eve.json
```

### Web API に接続できない
```bash
sudo systemctl status azazel-first-minute.service
# サービスが停止している場合:
sudo systemctl start azazel-first-minute.service
```

### テストが途中で失敗する
```bash
# ログ確認
journalctl -u azazel-first-minute -n 100

# 状態リセット
sudo systemctl restart azazel-first-minute.service

# 環境再セットアップ
./scripts/tests/regression/setup_env.sh
```

## 📊 テスト結果の確認

### コマンドライン出力
各スクリプトは実行結果を標準出力に表示します。

### ログファイル
- `/tmp/azazel_regression_artifacts/` - **スナップショット＆証跡保存ディレクトリ** (v3.0)
  - `git_commit.txt` - テスト実施時のコミットハッシュ
  - `first_minute.yaml` - 実装パラメータのスナップショット
  - `api_baseline.json` - テスト開始時の API 状態
  - `journal_baseline.log` - テスト開始時のログ
  - `test_start_time.txt` - テスト開始時刻
  - `contain_recovery_timeline.jsonl` - CONTAIN復帰測定データ
  - `epd_preview_*.png` - EPD プレビュー画像
- `/tmp/azazel_regression_test_results.txt` - テスト結果サマリー
- `/tmp/contain_recovery.log` - CONTAIN復帰測定ログ (旧形式)
- `journalctl -u azazel-first-minute` - システムログ

### スナップショット値の確認
v3.0 では期待値を固定せず、スナップショット値に基づいてテストを判定します。

```bash
# スナップショットの確認
cat /tmp/azazel_regression_artifacts/first_minute.yaml | grep -E "contain|decay|cooldown"

# 出力例:
#   contain_threshold: 50
#   contain_exit_threshold: 30
#   contain_min_duration_sec: 20
#   decay_per_sec: 3
#   suricata_cooldown_sec: 30
```

### 期待される結果
すべてのテストがPASSの場合、回帰テストは完了です。

```
✓✓✓ 全テスト PASS ✓✓✓

判定: GO (全テストPASS)
```

**証跡のアーカイブ** (推奨):
```bash
tar -czf /tmp/azazel_regression_artifacts_$(date +%Y%m%d_%H%M).tar.gz /tmp/azazel_regression_artifacts
```

## 🔗 関連ドキュメント

- 回帰テスト計画書 (v3.0)
- [test_redesign_verification.py](../../../test_redesign_verification.py) - ユニットテスト
- [azazel_test.py](../../../azazel_test.py) - 統合テスト

## ⚠️ 注意事項

1. **実機環境での実行**: これらのスクリプトは実機（Raspberry Pi Zero 2 W）での実行を前提としています
2. **ネットワーク接続**: テスト1は実際のWi-Fi接続を変更します
3. **権限**: 一部のスクリプトは sudo 権限が必要です
4. **テスト順序**: テスト2Bはテスト2Aの後に実行する必要があります

## 📅 作成日

2026年1月19日

## 📝 ライセンス

Azazel-Gadget プロジェクトに準拠
