# Phase 3 テストスクリプト

このディレクトリには Phase 3 テスト実施用のスクリプトが含まれています。

## 📁 ディレクトリ構成

```
scripts/phase3_test/
├── README.md                    # このファイル
├── check_tools.sh               # ツール確認スクリプト
├── setup_env.sh                 # 環境セットアップスクリプト
├── inject_suricata_alert.sh     # Suricataアラート注入ヘルパー
├── measure_contain_recovery.sh  # CONTAIN復帰測定スクリプト
├── run_test1_wifi.sh            # テスト1: 不審AP検知
├── run_test2_suricata.sh        # テスト2A: Suricata→CONTAIN遷移
├── run_test2b_cooldown.sh       # テスト2B: Cooldown機構検証
└── run_all_tests.sh             # 全テスト一括実行
```

## 🚀 クイックスタート

### 1. ツール確認
```bash
./scripts/phase3_test/check_tools.sh
```

すべてのツールと依存関係が正常かチェックします。

### 2. 環境セットアップ
```bash
./scripts/phase3_test/setup_env.sh
```

テスト環境を初期化します（ログクリア、eve.json 準備など）。

### 3. 個別テスト実行

#### テスト1: 不審AP検知
```bash
./scripts/phase3_test/run_test1_wifi.sh "Known-Evil-SSID" "password123"
```

#### テスト2A: Suricata→CONTAIN遷移
```bash
./scripts/phase3_test/run_test2_suricata.sh
```

#### テスト3: CONTAIN復帰測定
```bash
./scripts/phase3_test/measure_contain_recovery.sh
```

#### テスト2B: Cooldown機構検証
```bash
./scripts/phase3_test/run_test2b_cooldown.sh
```

### 4. 全テスト一括実行
```bash
./scripts/phase3_test/run_all_tests.sh
```

テスト2A、3、2B を自動実行します（テスト1は手動）。

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
./scripts/phase3_test/check_tools.sh
# ✓ すべてのツール/設定が正常です → テスト実施可能
# ✗ X件の問題が見つかりました → 修正が必要
```

### setup_env.sh
テスト環境を初期化します。

**実行内容**:
1. 構文チェック (test_redesign_verification.py)
2. systemd サービス確認
3. Web API 疎通確認
4. eve.json 準備
5. 既知悪質AP設定確認
6. EPD ドライバテスト
7. ログ初期化

**使用例**:
```bash
./scripts/phase3_test/setup_env.sh
# [✓] セットアップ完了 - テスト実施準備完了
```

### inject_suricata_alert.sh
Suricata アラートを eve.json に注入します。

**パラメータ**:
- `$1`: severity (1=Critical, 2=Major, 3=Minor)
- `$2`: メッセージ

**使用例**:
```bash
./scripts/phase3_test/inject_suricata_alert.sh 1 "Test Attack"
# ✓ アラート注入成功
```

### measure_contain_recovery.sh
CONTAIN状態の復帰タイムラインを測定します。

**測定内容**:
- 0-70秒まで5秒ごとに state と suspicion を記録
- 結果を `/tmp/contain_recovery.log` に保存

**使用例**:
```bash
./scripts/phase3_test/measure_contain_recovery.sh
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
./scripts/phase3_test/run_test1_wifi.sh "Known-Evil-SSID" "password123"
# ✓✓✓ テスト1: PASS ✓✓✓
```

### run_test2_suricata.sh
Suricataアラート検知からCONTAIN遷移をテストします。

**判定基準**:
- 15秒以内にCONTAIN状態へ遷移
- suspicion が50以上に達する

**使用例**:
```bash
./scripts/phase3_test/run_test2_suricata.sh
# ✓✓✓ テスト2A: PASS ✓✓✓
```

### run_test2b_cooldown.sh
Suricata Cooldown機構（30秒）を検証します。

**判定基準**:
- 5秒以内の追加アラートで suspicion 加算されない
- 30秒後の再アラートで suspicion 加算される

**使用例**:
```bash
./scripts/phase3_test/run_test2b_cooldown.sh
# ✓✓✓ テスト2B: PASS ✓✓✓
```

### run_all_tests.sh
テスト2A、3、2Bを自動実行します。

**実行フロー**:
1. 環境セットアップ
2. ツール確認
3. テスト2A実行
4. テスト3実行（測定）
5. テスト2B実行

**結果出力**:
- `/tmp/phase3_test_results.txt`
- `/tmp/contain_recovery.log`

**使用例**:
```bash
./scripts/phase3_test/run_all_tests.sh
# テストを開始しますか? [y/N]: y
# ...
# ✓✓✓ 全テスト PASS ✓✓✓
```

## 🔍 トラブルシューティング

### ツール確認で失敗する
```bash
./scripts/phase3_test/check_tools.sh
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
./scripts/phase3_test/setup_env.sh
```

## 📊 テスト結果の確認

### コマンドライン出力
各スクリプトは実行結果を標準出力に表示します。

### ログファイル
- `/tmp/phase3_test_results.txt` - テスト結果サマリー
- `/tmp/contain_recovery.log` - CONTAIN復帰測定ログ
- `journalctl -u azazel-first-minute` - システムログ

### 期待される結果
すべてのテストがPASSの場合、Phase 3 は完了です。

```
✓✓✓ 全テスト PASS ✓✓✓

判定: GO (全テストPASS)
```

## 🔗 関連ドキュメント

- [PHASE3_TEST_PLAN.md](../../PHASE3_TEST_PLAN.md) - 詳細テスト計画書
- [test_redesign_verification.py](../../test_redesign_verification.py) - ユニットテスト
- [azazel_test.py](../../azazel_test.py) - 統合テスト

## ⚠️ 注意事項

1. **実機環境での実行**: これらのスクリプトは実機（Raspberry Pi Zero 2 W）での実行を前提としています
2. **ネットワーク接続**: テスト1は実際のWi-Fi接続を変更します
3. **権限**: 一部のスクリプトは sudo 権限が必要です
4. **テスト順序**: テスト2Bはテスト2Aの後に実行する必要があります

## 📅 作成日

2026年1月19日

## 📝 ライセンス

Azazel-Zero プロジェクトに準拠
