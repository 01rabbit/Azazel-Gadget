# Phase 3 テスト計画書

**作成日**: 2026年1月19日  
**対象バージョン**: feature/epd-tui-tuning ブランチ  
**フェーズ**: Phase 3 - 脅威検知・応答テスト（実機環境）  
**ステータス**: 計画書（実施予定）

---

## 📋 目次

1. [概要](#概要)
2. [テスト目的と範囲](#テスト目的と範囲)
3. [テスト環境構成](#テスト環境構成)
4. [テストツール・依存関係](#テストツール依存関係)
5. [テスト項目詳細](#テスト項目詳細)
6. [テスト実施手順](#テスト実施手順)
7. [合格基準](#合格基準)
8. [トラブルシューティング](#トラブルシューティング)

---

# **概要**

## Phase 3 の位置付け

```
Phase 1 (2026-01-17)
├─ 基本機能テスト（SSH/HTTP接続、ログ出力）
├─ 単体テスト（state_machine検証）
└─ 結果: GO判定 → Phase 2着手許可

Phase 2 (2026-01-18)
├─ nftables再設計実装
├─ State Machine改善（Suricata cooldown, CONTAIN復帰）
├─ ログデバウンス
└─ 結果: 実装完了 → Phase 3開始

Phase 3 (2026-01-19~)
├─ [このドキュメント] 脅威検知・応答テスト
├─ 実機環境での動作検証
├─ Wi-Fi安全性判定の実検証
├─ CONTAIN状態の応答確認
├─ EPDユーザー通知の確認
└─ 結果: 本番環境デプロイの可否判断
```

## テスト実施期間

- **計画期間**: 2026年1月19日～23日（3-4日で完了可能）
- **実施者**: Raspberry Pi Zero 2 W + Waveshare EPD環境
- **テスト環境**: 実機（セキュアなネットワーク環境を推奨）
- **並行実行**: テスト1B と テスト2B は独立 → 同一タイムスロットで実施可
- **総推定時間**: 10-12時間（6テスト項目）

---

# **テスト目的と範囲**

## 主目的

1. **脅威検知の実効性確認**
   - 不審APへの接続時に正しく警告表示されるか
   - Wi-Fi安全性スコアが正確に算出されるか
   - ログに脅威情報が適切に記録されるか

2. **攻撃応答の動作確認**
   - Suricataアラート → CONTAIN状態への遷移が確実か
   - CONTAIN状態での管理通信は継続しているか
   - EPDにDANGER表示が正確に出現するか

3. **状態復帰の正確性確認**
   - CONTAIN状態が最小20秒継続するか
   - suspicion減衰メカニズムが正常に機能するか
   - 自動復帰が期待時間内に完了するか

4. **ユーザー通知の有効性確認**
   - EPD表示が迅速かつ正確か
   - TUI表示がリアルタイムで更新されるか
   - 推奨アクション（Web UI確認）が明確か

## テスト範囲

### ✅ 対象（テスト実施）
- `py/azazel_zero/sensors/wifi_safety.py` - Wi-Fi安全性判定
- `py/azazel_zero/app/threat_judge.py` - 脅威スコアリング
- `py/azazel_zero/first_minute/state_machine.py` - CONTAIN遷移・復帰
- `py/azazel_zero/first_minute/controller.py` - EPD更新トリガ
- `py/azazel_epd.py` - EPD描画（DANGER表示）
- `nftables/first_minute.nft` - CONTAIN中の管理通信fast-path

### ❌ 対象外（Phase 2で検証済み）
- 基本ネットワーク接続（SSH/HTTP）
- ログファイル生成（journalctl記録）
- nftables構文チェック
- トラフィック整形（tc）動作

---

# **テスト環境構成**

## ハードウェア要件

### 主要機器
| 機器 | 仕様 | 用途 |
|-----|------|------|
| **Raspberry Pi Zero 2 W** | BCM2710 + 1GB RAM | ゲートウェイ本体 |
| **Waveshare EPD 2.13"** | 250x122px, 3色 | ユーザー通知表示 |
| **USB Wi-Fi Adapter** | 802.11ac以上 | アップストリーム接続 |
| **USB Ethernet/HUB** | Fast Ethernet | ダウンストリーム管理 |
| **Test PC** | Mac/Linux/Windows | テスト操作・監視用 |

### ネットワーク構成
```
Test PC
  ↓ [SSH接続: 192.168.40.184]
  ↓
Raspberry Pi Zero 2 W (azazel)
  ├─ wlan0 (upstream): テスト用AP or 実AP接続
  └─ usb0 (downstream): Test PC から SSH/HTTP接続
       ├─ 10.55.0.10 (IP): Web Status API
       ├─ ポート22 (SSH): リモート管理
       └─ ポート8081 (Web): Status Dashboard
```

### オプション（テスト効率化）
- **外部ネットワーク**: Suricata実アラート生成用（オプション）
- **モニタリング機器**: 別のRasPi or PC（ログ収集・分析用、オプション）

---

# **テストツール・依存関係**

## システム依存関係（既にインストール済み）

```bash
# 確認コマンド
python3 --version              # 3.7以上
pip3 show pillow               # EPD描画
pip3 show waveshare-epd       # E-Paper制御
journalctl --version          # ログ収集
nft --version                  # ファイアウォール確認
```

## テスト実行に必要なコマンド

### 1. ネットワーク操作
```bash
# Wi-Fi接続情報確認
iw dev wlan0 link

# Wi-Fi APスキャン
sudo iw dev wlan0 scan | grep -E "SSID|signal"

# インターフェース情報
ip -4 addr show
ip route show

# DNS確認
cat /etc/resolv.conf
dig @10.55.0.10 example.com
```

### 2. ログ収集・分析
```bash
# systemd ジャーナルから最新ログ
journalctl -u azazel-first-minute -n 50

# JSON形式のログ抽出
journalctl -u azazel-first-minute -o json | jq '.'

# 特定キーワード検索
journalctl -u azazel-first-minute | grep "CONTAIN\|suspicion\|wifi_tags"

# リアルタイム監視
journalctl -u azazel-first-minute -f

# ログ時間範囲指定
journalctl -u azazel-first-minute --since "10 min ago"
```

### 3. Web API確認
```bash
# Status API クエリ
curl http://10.55.0.10:8081/

# JSON整形表示
curl -s http://10.55.0.10:8081/ | jq '.'

# 特定フィールド抽出
curl -s http://10.55.0.10:8081/ | jq '.state, .user_state, .risk_score'

# 継続監視
watch -n 2 'curl -s http://10.55.0.10:8081/ | jq ".state"'
```

### 4. EPD描画確認
```bash
# Dry-run プレビュー生成
sudo python3 py/azazel_epd.py --state danger --msg "ATTACK DETECTED" --dry-run

# プレビュー画像確認
ls -la /tmp/azazel_epd_preview_danger_*.png

# 画像内容確認（Linuxの場合）
file /tmp/azazel_epd_preview_danger_composite.png
```

### 5. ファイアウォール確認
```bash
# nftables ルール一覧
sudo nft list table inet azazel_fmc

# 特定チェーンの詳細
sudo nft list chain inet azazel_fmc input
sudo nft list chain inet azazel_fmc stage_contain

# カウンター情報（パケット数）
sudo nft list ruleset | grep counter
```

### 6. 脅威ログ確認
```bash
# Wi-Fi安全性スナップショット
cat /run/azazel-zero/wifi_health.json 2>/dev/null || cat ~/.azazel-zero/run/wifi_health.json

# EPD スナップショット（TUI計算データ）
cat /tmp/epd_snapshot.json | jq '.risk_score, .user_state'

# Suricata eve.json
tail -f /var/log/suricata/eve.json
```

## テストスクリプト

### 既存テストスクリプト
- **azazel_test.py**: Phase 1/2の統合テスト（SSH/HTTP/CONTAIN検証）
- **test_redesign_verification.py**: State Machineのユニットテスト

### Phase 3用テストスクリプト（新規作成推奨）
```bash
# Phase 3用テスト実行スクリプト
py/azazel_zero/test_phase3_wifi_threat.py    # Wi-Fi脅威検知テスト
py/azazel_zero/test_phase3_suricata.py       # Suricataアラートテスト
py/azazel_zero/test_phase3_epd_display.py    # EPD表示確認テスト
```

---

# **テスト項目詳細**

## テスト1: 不審AP検知テスト

### 目的
不審なWi-Fiアクセスポイントへの接続時、システムが正しく警告を表示し、ユーザーに通知するか確認。

### テスト前提条件
- azazel-first-minute.service が稼働中
- TUI (`py/azazel_zero/cli_unified.py`) が起動可能
- EPD（Waveshare）が接続可能

### テストパターン

#### パターン1A: 既知悪質AP接続
**前提**: `configs/known_wifi.json` に登録済みの悪質APが範囲内に存在

```bash
# 手順
1) 初期状態確認（クリーン環境）
   curl -s http://10.55.0.10:8081/ | jq '.user_state, .risk_score'
   # 期待: user_state = "SAFE" or "NORMAL", risk_score < 30

2) wlan0 を悪質APへ切り替え
   sudo nmcli dev wifi connect "Known-Evil-SSID" password "test123"
   
   # または手動で:
   sudo iwctl device wlan0 set-property Powered on
   sudo iwctl station wlan0 connect "Known-Evil-SSID"

3) ゲートウェイ再起動（オプション：状態リセット）
   sudo systemctl restart azazel-first-minute

4) 状態遷移を監視（ターミナル1）
   journalctl -u azazel-first-minute -f | grep -E "user_state|wifi_tags|suspicion"

5) TUI起動（ターミナル2）
   sudo python3 py/azazel_zero/cli_unified.py --enable-epd

6) 約30秒待機 → TUI/EPD表示変化を確認

7) API状態確認（ターミナル3）
   watch -n 2 'curl -s http://10.55.0.10:8081/ | jq ".user_state, .risk_score"'
```

**期待される動作**:
- ✅ ログに `"wifi_tags": ["evil_twin"]` or similar が記録
- ✅ TUI: user_state が LIMITED/DEGRADED へ遷移
- ✅ EPD: 警告表示（黄色背景 + "WARNING"）
- ✅ risk_score が 30-50 のレンジ
- ⏱️ 遷移時間: 接続から30秒以内

**期待値（出力例）**:
```json
{
  "user_state": "LIMITED",
  "risk_score": 45,
  "reason": "Suspicious WiFi detected",
  "recommendation": "Check WEB UI for details",
  "wifi_tags": ["evil_twin", "weak_encryption"]
}
```

#### パターン1B: 未検証AP接続（新規SSID）
**前提**: 未登録の新規SSID、信頼スコア不確定

```bash
# 手順（1Aと同様だが SSID は未登録）
1) 初期化
   curl -s http://10.55.0.10:8081/ | jq '.user_state'

2) 未検証APへ接続
   sudo nmcli dev wifi connect "New-Unknown-SSID" password "test123"

3) 約60秒監視（プローブ検証実行）
   journalctl -u azazel-first-minute -f

4) user_state の遷移パターンを確認
   # 期待: CHECKING → PROBE → DEGRADED or LIMITED
```

**期待値**:
- ✅ 初期: CHECKING → PROBE（検証実行）
- ✅ プローブ結果に応じて: NORMAL（信頼） or LIMITED（疑いあり）
- ✅ ログに "probe_results": {...} が記録

---

## テスト2: Suricataアラート→CONTAIN遷移テスト

### 目的
Suricataが攻撃シグネチャを検知した時、システムが即座にCONTAIN状態へ遷移し、パケット遮断と通知を実施するか確認。

### テスト前提条件
- `/var/log/suricata/eve.json` が存在・書き込み可能
- azazel-first-minute.service が稼働中
- TUI + EPD が起動中

### テストパターン

#### パターン2A: Suricataアラート偽装注入

```bash
# 手順
1) 初期状態確認
   curl -s http://10.55.0.10:8081/ | jq '.state, .suspicion'
   # 期待: state = "NORMAL", suspicion = 0-5

2) ログ監視開始（ターミナル1）
   journalctl -u azazel-first-minute -f | grep -E "state|suspicion|transitioned"

3) Suricataアラート偽装（Critical レベル）
   ALERT_JSON='{
     "timestamp":"2026-01-19T12:00:00+00:00",
     "alert":{
       "severity":1,
       "signature":"Simulated Critical Attack",
       "gid":1,
       "sid":1000001
     }
   }'
   echo "$ALERT_JSON" | sudo tee -a /var/log/suricata/eve.json

4) 即座にAPI確認（アラート注入直後 0-5秒）
   curl -s http://10.55.0.10:8081/ | jq '.state, .suspicion'

5) 待機（最大15秒でCONTAIN到達を期待）
   for i in {1..15}; do
     echo "=== $i秒 ==="
     curl -s http://10.55.0.10:8081/ | jq '.state, .suspicion'
     sleep 1
   done

6) CONTAIN到達後（状態確認）:
   - 赤いEPD表示を確認
   - SSH接続仍続確認（管理通信fast-path）
   - Web UI継続アクセス確認
```

**期待される動作**:
```
時刻        state       suspicion   説明
---         ----        ---------   ------
T=0秒       NORMAL      5.0
T=0秒+      PROBE       20.0        アラート検知、疑わしさ+15
T=3秒       CONTAIN     50.0        閾値50超過でCONTAIN遷移
T=5秒       CONTAIN     50.0        cooldown機構で重複カウント防止
```

**期待値（ログ出力例）**:
```json
{
  "timestamp": "2026-01-19T12:00:03+00:00",
  "state": "CONTAIN",
  "suspicion": 50.0,
  "reason": "Suricata alert: Simulated Critical Attack",
  "transitioned": true
}
```

**実際のログ出力確認（journalctl）**:
```bash
# リアルタイム監視で以下のような行が出現することを確認
journalctl -u azazel-first-minute -f | grep -E "CONTAIN|suspicion|transitioned"

# 期待出力:
# Jan 19 12:00:01 azazel systemd[1]: State transition: NORMAL -> PROBE (suspicion: 5.0 -> 20.0)
# Jan 19 12:00:03 azazel systemd[1]: State transition: PROBE -> CONTAIN (suspicion: 20.0 -> 50.0)
# Jan 19 12:00:03 azazel systemd[1]: Suricata cooldown started (expires at T+30s)
```

#### パターン2B: Suricataアラート連続（Cooldown検証）

```bash
# 目的: Suricata cooldown機構（30秒間隔）の動作確認

# 手順
1) パターン2Aを実行して CONTAIN到達

2) suspicion タイムライン記録開始
   journalctl -u azazel-first-minute --since "now" -f | tee /tmp/suricata_test.log &

3) アラート追加注入（5秒後）
   sleep 5
   echo '{"timestamp":"2026-01-19T12:00:05+00:00","alert":{"severity":1,"signature":"Second Attack"}}' \
     | sudo tee -a /var/log/suricata/eve.json

4) suspicion 変化を監視（期待: +15 されない）
   curl -s http://10.55.0.10:8081/ | jq '.suspicion'
   # 期待: 50.0（変化なし）

5) 30秒経過後にアラート再度注入
   sleep 30
   echo '{"timestamp":"2026-01-19T12:00:35+00:00","alert":{"severity":1,"signature":"Third Attack"}}' \
     | sudo tee -a /var/log/suricata/eve.json

6) suspicion 確認（期待: 65.0 = 50 + 15）
   curl -s http://10.55.0.10:8081/ | jq '.suspicion'
```

**期待値（Cooldown動作）**:
```
T=0秒   alert1 注入: suspicion = 50.0 (15+35)
T=5秒   alert2 注入: suspicion = 50.0 (cooldown内, 加算なし)
T=35秒  alert3 注入: suspicion = 65.0 (cooldown終了, 15加算)
```

---

## テスト3: CONTAIN状態復帰テスト

### 目的
CONTAIN状態が最小20秒継続し、その後suspicion減衰で自動復帰するか検証。

### テストパターン

```bash
# 手順
1) パターン2Aで CONTAIN状態へ遷移（T=0秒とする）

2) suspicion タイムライン記録（15秒ごとにAPI呼び出し）
   for i in {0..180..15}; do
     echo "=== $((i))秒 ==="
     curl -s http://10.55.0.10:8081/ | jq '.state, .suspicion'
     sleep 15
   done

3) 期待される遷移パターン:
   T=0-20秒    state = CONTAIN, suspicion = 50.0 (最小継続)
   T=20-60秒   state = CONTAIN, suspicion 減衰 (50.0 → 0.0)
   T=60秒+     state = DEGRADED or NORMAL, suspicion < 30

4) Suricataアラートクリア（念のため）
   sudo rm /var/log/suricata/eve.json

5) ログで遷移確認
   journalctl -u azazel-first-minute --since "5 min ago" | grep "transitioned"
```

**期待値（復帰タイムライン）**:
```
時刻        state       suspicion   備考
---         ----        ---------   ------
T=0秒       CONTAIN     50.0        CONTAIN遷移
T=20秒      CONTAIN     50.0        最小継続時間経過
T=35秒      CONTAIN     35.0        減衰開始 (decay 3/sec)
T=50秒      CONTAIN     20.0
T=62秒      DEGRADED    2.0         suspicion < 30 で DEGRADED遷移
T=70秒      NORMAL      0.0         自動復帰完了
```

**測定スクリプト（自動記録）**:
```bash
#!/bin/bash
# measure_contain_recovery.sh

echo "CONTAIN復帰タイムライン測定開始 (T=0秒)" > /tmp/contain_recovery.log
START_TIME=$(date +%s)

for i in {0..70..5}; do
  ELAPSED=$i
  CURRENT_STATE=$(curl -s http://10.55.0.10:8081/ | jq -r '.state')
  SUSPICION=$(curl -s http://10.55.0.10:8081/ | jq '.suspicion')
  TIMESTAMP=$(date '+%H:%M:%S')
  
  echo "T=$((ELAPSED))秒 [$TIMESTAMP] state=$CURRENT_STATE, suspicion=$SUSPICION" >> /tmp/contain_recovery.log
  
  if [ $i -lt 70 ]; then
    sleep 5
  fi
done

echo "\n測定完了. 結果: /tmp/contain_recovery.log"
cat /tmp/contain_recovery.log
```

**log出力例**:
```
T=0秒 [12:00:03] state=CONTAIN, suspicion=50.0
T=5秒 [12:00:08] state=CONTAIN, suspicion=45.0
T=10秒 [12:00:13] state=CONTAIN, suspicion=40.0
T=15秒 [12:00:18] state=CONTAIN, suspicion=35.0
T=20秒 [12:00:23] state=CONTAIN, suspicion=30.0
T=25秒 [12:00:28] state=CONTAIN, suspicion=25.0
T=30秒 [12:00:33] state=DEGRADED, suspicion=20.0
```

---

## テスト4: EPD表示動作確認テスト

### 目的
EPDが各状態で正確な表示を行い、ユーザーが脅威を直感的に理解できるか確認。

### テストパターン

#### パターン4A: 各状態のEPD表示確認

```bash
# NORMAL状態（緑/安全）
1) wlan0 を信頼できるAPへ接続
2) user_state = SAFE or NORMAL 確認
3) EPD表示: Wi-Fiアイコン + SSID + IP（白背景）
4) 実機確認: 画像で検証
   file /tmp/azazel_epd_preview_normal_composite.png

# LIMITED状態（黄/注意）
1) パターン1A（不審AP接続）実行
2) user_state = LIMITED 確認
3) EPD表示: "WARNING" + メッセージ（白背景）
4) ドライラン確認:
   sudo python3 py/azazel_epd.py --state warning --msg "SUSPICIOUS AP" --dry-run
   file /tmp/azazel_epd_preview_warning_composite.png

# CONTAINED状態（赤/危険）
1) パターン2A（Suricataアラート）実行
2) state = CONTAIN 確認
3) EPD表示: "DANGER" + "ATTACK DETECTED"（赤背景）
4) ドライラン確認:
   sudo python3 py/azazel_epd.py --state danger --msg "ATTACK DETECTED" --dry-run
   file /tmp/azazel_epd_preview_danger_composite.png
```

**チェックリスト**:
- ✅ NORMAL: Wi-Fiアイコン表示、信号強度反映
- ✅ LIMITED: 警告アイコン×2、黄色テーマ
- ✅ CONTAINED: 赤背景全面、白文字、警告アイコン
- ✅ 遷移時間: 状態変化から3秒以内に表示切り替え

#### パターン4B: EPD更新頻度確認（Fingerprint比較）

```bash
# 目的: 不要な更新を抑制し、ちらつきを防ぐ

# 手順
1) EPD更新ログを監視
   strace -f -e openat sudo python3 py/azazel_zero/cli_unified.py 2>&1 | grep "azazel_epd.py"

2) 同一状態を30秒保持
   # EPD更新が発生しないことを確認

3) 状態変化（NORMAL → LIMITED）
   # EPD更新が即座に発生することを確認

4) 同じ LIMITED 状態を継続
   # 重複更新が発生しないことを確認（fingerprint比較）
```

---

## テスト5: 管理通信継続確認テスト

### 目的
CONTAIN状態でもSSH/Web UIへのアクセスが確保されているか確認（nftables fast-path動作）。

### テストパターン

```bash
# 手順
1) 初期SSH接続確認（基準値）
   time ssh azazel@192.168.40.184 'echo OK'
   # 期待: 接続成功、平均 < 1秒

2) CONTAIN状態へ遷移（パターン2A実行）

3) CONTAIN中のSSH接続試行
   for i in {1..5}; do
     echo "=== Try $i ==="
     time ssh azazel@192.168.40.184 'curl -s http://10.55.0.10:8081/ | jq .state'
     sleep 2
   done
   
   # 期待: すべて接続成功

4) Web Status API への HTTP アクセス
   while true; do
     curl -s http://10.55.0.10:8081/ | jq '.state, .suspicion'
     sleep 5
   done
   
   # CONTAIN中も継続アクセス可能

5) その他管理通信確認
   - VSCode Remote-SSH: 接続可能か
   - scp でのファイル転送: 可能か
```

**期待値（性能）**:
- ✅ SSH接続レイテンシ: 基準値 ±200ms（遅延なし）
- ✅ Web API レスポンス時間: 500ms 以内
- ✅ パケット損失: 0%
- ✅ スループット: 影響なし（data traffic は制限されるが管理通信は優先）

---

## テスト6: 脅威スコアリング統合確認テスト

### 目的
Wi-Fi品質、攻撃検知、ユーザー状態から総合的にリスクスコア（0-100）が算出されるか確認。

### テストパターン

```bash
# 手順
1) リスク要因ごとのスコア確認

# Case A: 安全状態（SAFE + 強い信号）
状態: NORMAL, 信号: -45dBm
期待: risk_score < 30 (緑表示)

# Case B: 軽度リスク（LIMITED + 弱い信号）
状態: LIMITED, 信号: -75dBm
期待: risk_score 30-50 (黄表示)

# Case C: 高リスク（CONTAINED + Suricata alert）
状態: CONTAINED, suspicion: 50+
期待: risk_score 70+ (赤表示)

2) 各ケースのスコア値を記録
   for state in "SAFE" "LIMITED" "CONTAINED"; do
     curl -s http://10.55.0.10:8081/ | jq '.user_state, .risk_score'
     echo "--- $state ---"
     sleep 5
   done

3) スコアロジックの妥当性確認
   - Threat Level が high → スコア加算されているか
   - Suricata alert count が多い → スコア加算されているか
   - Wi-Fi signal が弱い → スコア加算されているか
   - 複合要因時のスコア → 合算が適切か
```

**期待値（スコアマッピング）**:
| 状態 | 信号強度 | Suricata | risk_score | 色 |
|-----|---------|----------|------------|-----|
| SAFE | 強(-45) | 0 | 0-10 | 🟢 |
| NORMAL | 中(-65) | 0 | 10-30 | 🟢 |
| LIMITED | 弱(-80) | 0 | 30-50 | 🟡 |
| DEGRADED | 中(-65) | 0-1 | 40-60 | 🟡 |
| CONTAINED | 任意 | 1+ | 70-100 | 🔴 |

---

# **テスト実施手順**

## 事前準備（必須チェックリスト）

### 環境確認
```bash
# 1. ワークスペースに移動
cd /home/azazel/Azazel-Zero

# 2. 構文チェック
python3 test_redesign_verification.py
# 期待: すべてのテストが PASS

# 3. systemd サービス確認
systemctl status azazel-first-minute.service
# 期待: ● azazel-first-minute.service - active (running)

# 4. ネットワーク確認
ip addr show
iw dev wlan0 link
# 期待: wlan0 が接続済み（どのAP でも可）

# 5. Web API疎通確認
curl -s http://10.55.0.10:8081/ | jq '.state'
# 期待: "NORMAL" or "PROBE" などstate が返る
```

### テストデータ確認
```bash
# 6. eve.json パス確認（Suricataテスト用）
ls -la /var/log/suricata/eve.json
# なければ作成: sudo touch /var/log/suricata/eve.json

# 7. 既知悪質AP設定確認（テスト1用）
cat configs/known_wifi.json | jq '.evil_ssid' | head -3
# 期待: 少なくとも3つ以上の悪質SSID登録

# 8. EPDドライバ確認
sudo python3 py/azazel_epd.py --state normal --ssid "Setup" --ip "10.55.0.10" --signal -50 --dry-run
# 期待: /tmp/azazel_epd_preview_normal_composite.png 生成

# 9. ログの初期化
sudo journalctl --vacuum-time=1d
sudo sh -c 'echo "" > /var/log/suricata/eve.json'
```

### ワンショットセットアップ
```bash
# 上記をまとめて実行するスクリプト例
#!/bin/bash
set -e
echo "[*] Phase 3 テスト環境セットアップ開始"
cd /home/azazel/Azazel-Zero

echo "[1/6] 構文チェック..."
python3 test_redesign_verification.py || exit 1

echo "[2/6] systemd 確認..."
sudo systemctl is-active azazel-first-minute.service > /dev/null || exit 1

echo "[3/6] Web API 確認..."
curl -s http://10.55.0.10:8081/ | jq '.state' > /dev/null || exit 1

echo "[4/6] eve.json 準備..."
sudo touch /var/log/suricata/eve.json && sudo chmod 666 /var/log/suricata/eve.json

echo "[5/6] EPD ドライバテスト..."
sudo python3 py/azazel_epd.py --state normal --ssid "Setup" --ip "10.55.0.10" --signal -50 --dry-run

echo "[6/6] ログ初期化..."
sudo journalctl --vacuum-time=1d
sudo sh -c 'echo "" > /var/log/suricata/eve.json'

echo ""
echo "[✓] セットアップ完了 - テスト実施準備完了"
echo "次のコマンドでテスト実施:"
echo "  journalctl -u azazel-first-minute -f  # ターミナル1"
echo "  watch -n 2 'curl http://10.55.0.10:8081/ | jq .state'  # ターミナル2"
```

## テスト実施スケジュール（推奨パターン：集約型3-4時間完了）

### Day 1: 核心機能テスト（2-3時間）
```
09:00-09:15  環境セットアップ (15分)
             ├─ setup_phase3_env.sh 実行
             └─ 全ての前提条件確認

09:15-10:00  テスト1A: 既知悪質AP接続 (45分)
             ├─ ターミナル1: journalctl -f
             ├─ ターミナル2: TUI起動
             ├─ ターミナル3: watch curl API
             └─ WiFi tag ログ確認

10:00-10:30  テスト2A: Suricata→CONTAIN遷移 (30分)
             ├─ eve.json へアラート注入
             ├─ CONTAIN到達時間計測
             └─ EPD DANGER表示確認

10:30-11:00  テスト3: CONTAIN復帰 (30分)
             ├─ measure_contain_recovery.sh 実行
             ├─ suspicion減衰測定
             └─ 復帰時間記録 (70秒程度)

11:00-11:30  テスト4A: EPD表示確認 (30分)
             ├─ dry-run で各状態表示生成
             ├─ 実機EPD で確認
             └─ 赤/黄/白背景の正確性

11:30-12:00  テスト5: 管理通信継続 (30分)
             ├─ CONTAIN中 SSH 接続試行
             ├─ Web API レスポンス計測
             └─ レイテンシ記録

12:00-12:30  テスト6: リスク統合スコア (30分)
             ├─ 複数状態でのリスク値比較
             └─ スコア範囲検証

12:30-13:00  結果集計・レポート作成 (30分)
             └─ PHASE3_TEST_RESULTS.md 完成
```

### 並行実行の推奨組み合わせ
- **テスト1B と テスト2B** (同タイムスロット可) 
  - 異なる AP へ接続するため競合なし
  - Wi-Fi adapter 1個なら順序実行
- **テスト4B と テスト5** (同時並行可)
  - EPD 表示確認とSSH 接続は独立
  - 同一RaspPi だが処理は非同期

---

# **合格基準**

## 全体合格基準

| テスト | 最小要件 | 合格 | 注記 |
|--------|---------|------|------|
| テスト1 | 不審AP検知: user_state遷移 + ログ記録 | 必須 | TUI表示まで確認 |
| テスト2A | Suricataアラート → CONTAIN遷移（15秒以内） | 必須 | 即応性確認 |
| テスト2B | Cooldown機構: 重複カウント防止 | 必須 | メカニズム検証 |
| テスト3 | CONTAIN復帰: 40-80秒（20秒最小継続+減衰） | 必須 | タイミング検証 |
| テスト4 | EPD表示: DANGER表示正確性（赤+白文字） | 必須 | ユーザー通知確認 |
| テスト5 | 管理通信: CONTAIN中も SSH/Web API 継続 | 必須 | 運用保証 |
| テスト6 | リスク統合: スコア値が状態に応じた範囲 | 推奨 | 総合判定 |

## 各テストの詳細合格基準

### テスト1: 不審AP検知
```
✅ PASS 条件:
  - user_state が SAFE/NORMAL → LIMITED 以上へ遷移
  - ログに "wifi_tags" フィールド記録
  - TUI で警告表示（LIMITED状態表示）
  - EPD: WARNING表示（黄色背景）
  - 遷移時間: 接続から30秒以内

❌ FAIL 条件:
  - user_state が変化しない
  - wifi_tags が記録されない
  - EPD表示が変わらない
```

### テスト2A/2B: Suricataアラート
```
✅ PASS 条件:
  - state が NORMAL → CONTAIN へ遷移（15秒以内）
  - suspicion が 50以上に達する
  - ログに "transitioned": true が記録
  - Cooldown: 5秒以内の追加アラートで加算されない
  - 30秒後の再アラートで加算される

❌ FAIL 条件:
  - CONTAIN遷移が遅い（15秒超過）
  - suspicion が 50未満のまま
  - transitioned フラグが出力されない
  - Cooldown機構が動作しない
```

### テスト3: CONTAIN復帰
```
✅ PASS 条件:
  - CONTAIN状態が最低20秒継続
  - suspicion が毎秒3ポイント減衰
  - suspicion < 30 で DEGRADED へ遷移
  - 総復帰時間が40-80秒（目標60秒以内）

❌ FAIL 条件:
  - 20秒以内に CONTAIN から脱出
  - suspicion が増加する（減衰しない）
  - 遷移が遅い（120秒超過）
```

### テスト4: EPD表示
```
✅ PASS 条件:
  - DANGER表示: 赤背景全面、白文字で "DANGER" と "ATTACK DETECTED"
  - WARNING表示: 白背景、黒文字で "WARNING" と警告メッセージ
  - NORMAL表示: Wi-Fiアイコン、SSID、IP、信号強度表示
  - 遷移時間: 状態変化から3秒以内に表示更新
  - 文字崩れ: なし、フォント適用正常

❌ FAIL 条件:
  - 表示内容が不正確（色違い、文字違い）
  - 更新が遅い（3秒超過）
  - 画面崩れ、文字欠け
```

### テスト5: 管理通信継続
```
✅ PASS 条件:
  - CONTAIN中も SSH 接続可能
  - Web API レスポンスタイム < 500ms
  - パケット損失率 = 0%
  - 通信遮断なし

❌ FAIL 条件:
  - SSH接続タイムアウト
  - Web API が応答なし
  - パケット損失 > 0%
```

### テスト6: リスク統合スコアリング
```
✅ PASS 条件:
  - SAFE状態: risk_score < 30（緑）
  - LIMITED状態: 30 ≤ risk_score < 70（黄）
  - CONTAINED状態: risk_score ≥ 70（赤）
  - スコア値が単調増減（不正な急上昇なし）

❌ FAIL 条件:
  - スコア範囲が不正確
  - 値の跳躍が大きい（10ポイント以上）
```

---

# **トラブルシューティング**

## テスト1: 不審AP検知が機能しない

### 症状: user_state が変わらない

```bash
# 原因調査1: wifi_safety.py が実行されているか
journalctl -u azazel-first-minute | grep "evaluate_wifi_safety"

# 原因調査2: 既知悪質APデータベースが読み込まれているか
cat configs/known_wifi.json | jq '.evil_ssid, .weak_crypto'

# 原因調査3: Wi-Fi接続情報が正しいか
iw dev wlan0 link

# 修正案
# - known_wifi.json のテストAP追加
# - wifi_safety.py のロジック確認（detect_mitm(), detect_evil_twin() など）
```

### 症状: EPD警告表示が出ない

```bash
# 原因調査: EPDスクリプト実行エラー
sudo python3 py/azazel_epd.py --state warning --msg "TEST MESSAGE" --dry-run
# エラーメッセージを確認

# 修正案
# - フォントファイル確認: fonts/icbmss20.ttf 存在確認
# - アイコンファイル確認: icons/epd/warning.png 存在確認
# - controller.py で update_epd() が呼び出されているか確認
```

---

## テスト2: Suricataアラートが検知されない

### 症状: state が CONTAIN へ遷移しない

```bash
# 原因調査1: eve.json が監視されているか
ls -la /var/log/suricata/eve.json

# 原因調査2: first_minute コントローラが eve.json を読んでいるか
journalctl -u azazel-first-minute -f | grep "suricata\|eve"

# 原因調査3: state_machine のシグナル処理が正常か
python3 test_redesign_verification.py
# Suricata cooldown テストが PASS しているか確認

# 修正案
# - eve.json パスが config に正しく設定されているか確認
# - controller.py の _apply_signals() でシグナル処理しているか確認
```

### 症状: CONTAIN遷移は成功するが、すぐに復帰する

```bash
# 原因調査: 最小継続時間が設定されているか
cat configs/first_minute.yaml | grep "contain_min_duration"

# 修正案
# - contain_min_duration_sec >= 20 に設定
# - state_machine.py で最小継続ロジック確認
```

---

## テスト3: suspicion が減衰しない

### 症状: CONTAIN 状態が永続する

```bash
# 原因調査1: decay が実装されているか
cat py/azazel_zero/first_minute/state_machine.py | grep "decay"

# 原因調査2: decay_per_sec パラメータが設定されているか
cat configs/first_minute.yaml | grep "decay_per_sec"

# 修正案
# - decay_per_sec を確認（デフォルト: 3.0）
# - state_machine.py の _decay() メソッドが step() で呼ばれているか確認
```

---

## テスト4: EPD表示が文字化けする

### 症状: フォント未読み込み

```bash
# 原因調査: フォントファイル確認
ls -la fonts/icbmss20.ttf fonts/StardosStencilBold-9mzn.ttf

# 修正案
# - フォントファイルを `fonts/` ディレクトリに配置
# - ファイルパーミッション確認（644）
```

### 症状: アイコンが表示されない

```bash
# 原因調査: アイコンファイル確認
ls -la icons/epd/

# 修正案
# - 必要なPNGファイル: warning.png, danger.png, wifi_*.png
# - ファイルサイズ確認（無圧縮か確認）
```

---

## テスト5: SSH接続がタイムアウトする（CONTAIN中）

### 症状: 管理通信 fast-path が機能していない

```bash
# 原因調査1: nftables ルール確認
sudo nft list chain inet azazel_fmc input | grep "mgmt_ports"

# 原因調査2: stage_contain チェーン確認
sudo nft list chain inet azazel_fmc stage_contain

# 修正案
# - nftables/first_minute.nft で input chain に mgmt_ports set が定義されているか確認
# - stage_contain チェーンに "ip daddr $MGMT_IP tcp dport @mgmt_ports accept" が存在するか確認
# - $MGMT_IP, $MGMT_PORT 変数が正しく展開されているか確認
```

---

## テスト6: リスク統合スコアが不正確

### 症状: スコア値が状態と合致しない

```bash
# 原因調査: スコア計算ロジック確認
cat py/azazel_zero/cli_unified.py | grep -A 50 "def calculate_risk_score"

# 修正案
# - calculate_risk_score() の各要因の配点確認
# - threat_level, suricata_critical, signal_dbm, user_state, dns_blocked の加算式確認
# - min(score, 100) で上限チェックしているか確認
```

---

## 共通トラブルシューティング

### ログが出力されない

```bash
# systemd ログ確認
journalctl -u azazel-first-minute -n 50

# ファイルベースログ確認
cat /var/log/azazel-zero/first_minute.log 2>/dev/null || \
  cat ~/.azazel-zero/run/first_minute.log

# サービス状態確認
systemctl status azazel-first-minute.service
```

### 状態が更新されない

```bash
# 既存プロセスがロックしていないか確認
pgrep -f "azazel-first-minute"

# 既存プロセスをkill（再起動）
sudo systemctl restart azazel-first-minute.service

# Web APIが最新状態を返しているか確認
curl -s http://10.55.0.10:8081/ | jq '.'
```

### EPD が動かない

```bash
# ドライラン（プレビュー生成）
sudo python3 py/azazel_epd.py --state normal --ssid "Test" --ip "192.168.1.1" --dry-run

# プレビュー画像確認
file /tmp/azazel_epd_preview_normal_composite.png

# ハードウェア確認
ls -la /dev/spidev*
```

---

# **テスト完了後のまとめ**

## 結果レポート作成テンプレート

```bash
# テスト結果ファイル作成
cat > PHASE3_TEST_RESULTS.md << 'EOF'
# Phase 3 テスト結果

**実施日**: 2026-01-19  
**実施者**: [実施者名]  
**総実行時間**: [X時間Yy分]  
**判定**: [GO / GO(条件付) / NO-GO(軽度) / NO-GO(中度) / NO-GO(重度)]

## テスト実施結果サマリー

| # | テスト項目 | 期待値 | 実際 | 結果 | 備考 |
|----|----------|--------|------|------|------|
| 1 | 不審AP検知 | user_state遷移 | ✓ SAFE→LIMITED | PASS | 25秒で遷移 |
| 1B | 未検証AP | PROBE実行確認 | ✓ | PASS | - |
| 2A | Suricata→CONTAIN | 15秒以内遷移 | ✓ 3秒 | PASS | 即応性確認 |
| 2B | Cooldown | 重複カウント防止 | ✓ | PASS | 30秒メカニズム動作 |
| 3 | CONTAIN復帰 | 60秒以内復帰 | ✓ 62秒 | PASS | 期待値範囲内 |
| 4 | EPD表示 | DANGER/WARNING正確 | ✓ | PASS | 赤/黄正確に表示 |
| 4B | EPD更新頻度 | Fingerprint比較 | ✓ | PASS | ちらつき抑制 |
| 5 | 管理通信継続 | SSH/API 0% 損失 | ✓ | PASS | レイテンシ +5ms |
| 6 | リスク統合 | スコア範囲正確 | ✓ ±8以内 | PASS | 計算ロジック正常 |

## 詳細結果

### テスト1: 不審AP検知
- **状態遷移**: NORMAL (risk_score: 15) → LIMITED (risk_score: 42)
- **遷移時間**: 25秒
- **ログ記録**: ✓ wifi_tags=["evil_twin", "weak_encryption"]
- **EPD表示**: ✓ WARNING (黄色背景)
- **結果**: ✓ PASS

### テスト2A: Suricata→CONTAIN
- **遷移時間**: 3秒
- **最終suspicion**: 50.0
- **EPD表示**: ✓ DANGER (赤背景)
- **結果**: ✓ PASS

### テスト2B: Cooldown
- **T=5秒時点**: suspicion 変化なし (50.0)
- **T=35秒時点**: suspicion 変化あり (65.0)
- **Cooldown機構**: ✓ 正常動作
- **結果**: ✓ PASS

### テスト3: CONTAIN復帰
- **最小継続時間**: 20秒確認
- **減衰速度**: 3.0/sec 確認
- **総復帰時間**: 62秒
- **最終状態**: NORMAL (suspicion: 0.0)
- **結果**: ✓ PASS

### テスト4: EPD表示
- **NORMAL**: ✓ Wi-Fi icon + SSID + IP
- **WARNING**: ✓ 黄色背景 + "WARNING"
- **DANGER**: ✓ 赤背景 + "ATTACK DETECTED"
- **更新時間**: 2-3秒以内
- **結果**: ✓ PASS

### テスト5: 管理通信継続
- **SSH接続**: ✓ CONTAIN中も接続可能
- **レイテンシ**: 平均 210ms (基準値±5ms)
- **Web API**: ✓ 450ms以内
- **パケット損失**: 0%
- **結果**: ✓ PASS

### テスト6: リスク統合
- **SAFE**: risk_score 12 (期待: <30) ✓
- **LIMITED**: risk_score 45 (期待: 30-50) ✓
- **CONTAINED**: risk_score 78 (期待: ≥70) ✓
- **結果**: ✓ PASS

## 発見事項

1. **良好**: すべてのテストが合格基準を超過
2. **最適化**: Suricata→CONTAIN遷移が期待値(15秒)より大幅に高速(3秒)
3. **安定**: 復帰タイムラインが予測値と一致

## 改善提案

- **テスト4B**: EPD更新頻度制御(30秒)は適切。現在のfingerprint比較で十分。
- **テスト6**: リスクスコア計算は各要因の加算が適切。ML/LLM連携時の参考基準として記録推奨。

## 本番デプロイ判定

✅ **GO判定** - すべてのテスト(1-6)が PASS

### デプロイ手順
```bash
# 1. feature/epd-tui-tuning から main へマージ
git checkout main
git merge feature/epd-tui-tuning

# 2. 本番環境へデプロイ
sudo systemctl restart azazel-first-minute.service
sudo systemctl restart azazel-epd.service

# 3. デプロイ後確認
curl http://10.55.0.10:8081/ | jq '.state'
journalctl -u azazel-first-minute -n 20

# 4. 本番環境で1時間監視
```

EOF
```

## 進捗報告テンプレート

テスト実施中、以下の形式で進捗を記録してください：

```markdown
# Phase 3 テスト進捗

**実施日**: 2026-01-19  
**実施者**: [名前]

## 実施済みテスト
- [x] テスト1A (09:15-10:00) - PASS
- [x] テスト2A (10:00-10:30) - PASS
- [x] テスト3 (10:30-11:00) - PASS
- [ ] テスト4A (11:00-11:30) - 進行中
- [ ] テスト4B (11:00-11:30) - 待機中
- [ ] テスト5 (11:30-12:00) - 待機中
- [ ] テスト6 (12:00-12:30) - 待機中

## 発見事項
- [テスト1A] user_state が 30秒で LIMITED へ遷移 (期待: 30秒以内)
- [テスト2A] CONTAIN 到達時間: 3秒 (期待: 15秒以内)

## 次のアクション
- テスト4A: EPD ドライラン確認
```

---

**テスト計画書版**: 2.0  
**最終更新**: 2026年1月19日  
**ステータス**: 実施待機 → テスト実施開始可
