# Phase 3 テスト計画書（完成版 / 実装準拠）

**作成日**: 2026年1月19日  
**対象バージョン**: feature/epd-tui-tuning ブランチ  
**フェーズ**: Phase 3 - 脅威検知・応答テスト（実機環境）  
**ステータス**: 計画書（実施予定）  
**参照**: PHASE2_COMPLETION_REPORT.md / EPD_CONTAIN_DISPLAY_REVIEW.md / REDESIGN_IMPLEMENTATION_PLAN.md

---

## 0. この完成版での重要方針（矛盾排除）

本フェーズは「実装されている挙動」を正とします。よって、閾値・減衰・クールダウン等の数値を計画書に固定せず、**テスト開始時点の実装パラメータを必ずスナップショット取得**し、その値に従って期待値を組み立てます。  
（この手順を省略すると、テストは"気分"で判定され、実機が静かに反乱を起こします。）

---

## 📋 目次

1. 概要  
2. テスト目的と範囲  
3. テスト環境構成  
4. テスト前の必須スナップショット（実装パラメータ・状態）  
5. テストツール・依存関係  
6. テスト項目詳細（Test 1〜6）  
7. 合格基準（全体 / 個別）  
8. トラブルシューティング  
9. 証跡・成果物の保存  
10. テスト完了後のまとめ（結果レポート）

---

# 1. 概要

## 1.1 Phase 3 の位置付け

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
├─ [本書] 脅威検知・応答テスト（実機）
├─ Wi-Fi安全性判定の実検証
├─ Suricataシグナル→CONTAIN遷移と復帰
├─ CONTAIN中の管理通信fast-path確認
└─ 結果: 本番環境デプロイ可否判断

## 1.2 テスト実施期間

- **計画期間**: 2026年1月19日～23日（3〜4日で完了可能）
- **実施者**: Raspberry Pi Zero 2 W + Waveshare EPD環境
- **総推定時間**: 10〜12時間（Test 1〜6）

---

# 2. テスト目的と範囲

## 2.1 主目的

1. **脅威検知の実効性確認**  
   不審APや未検証AP接続時に、Wi-Fi安全性判定→ログ→ユーザー状態が一貫して更新されること。

2. **攻撃応答の動作確認**  
   Suricataアラートをトリガとして、所定時間内に CONTAIN 遷移し、遮断が有効化され、同時に管理通信が継続すること。

3. **状態復帰の正確性確認**  
   CONTAIN の最小継続時間と suspicion 減衰が実装通りに動作し、想定通りに自動復帰すること。

4. **ユーザー通知の有効性確認（EPD/TUI/Web）**  
   通知が崩れず、必要な情報が欠落せず、運用者が次アクションを誤らないこと。

## 2.2 テスト範囲

### ✅ 対象（実機で検証）
- \`py/azazel_zero/sensors/wifi_safety.py\`（Wi-Fi安全性）
- \`py/azazel_zero/app/threat_judge.py\`（脅威スコアリング）
- \`py/azazel_zero/first_minute/state_machine.py\`（遷移・復帰）
- \`py/azazel_zero/first_minute/controller.py\`（信号取り込み・EPD更新トリガ）
- \`py/azazel_epd.py\`（EPD描画：normal/warning/danger）
- \`nftables/first_minute.nft\`（CONTAIN中fast-path）

### ❌ 対象外（Phase 2で検証済みとして扱う）
- 基本ネットワーク疎通（SSH/HTTP）
- systemd/journalctl の基礎ログ出力
- nftables 構文チェック
- tc（Traffic Control）の動作

---

# 3. テスト環境構成

## 3.1 ハードウェア要件

| 機器 | 仕様 | 用途 |
|-----|------|------|
| Raspberry Pi Zero 2 W | BCM2710 + 1GB RAM | ゲートウェイ本体 |
| Waveshare EPD 2.13" | 250x122px, 3色 | ユーザー通知 |
| USB Wi-Fi Adapter | 802.11ac以上 | upstream接続 |
| USB Ethernet/HUB | Fast Ethernet | downstream管理 |
| Test PC | Mac/Linux/Windows | 操作・監視 |

## 3.2 ネットワーク構成（論理）

Test PC
↓ [SSH: 192.168.40.184]
Raspberry Pi Zero 2 W (azazel)
├─ wlan0 (upstream): テストAP / 実AP
└─ usb0 (downstream): Test PC → 管理用
├─ 10.55.0.10:8081 (Web Status API)
└─ 22/tcp (SSH)

---

# 4. テスト前の必須スナップショット（実装パラメータ・状態）

Phase 3 の期待値は **このスナップショット** を元に決定します。必ず保存してください。

## 4.1 実装パラメータ（first_minute.yaml 等）の取得

\`\`\`bash
cd /home/azazel/Azazel-Zero

# 設定ファイルの候補（実装に合わせて存在する方を採用）
ls -la configs/first_minute.yaml 2>/dev/null || true
ls -la configs/first_minute.yml  2>/dev/null || true

# 閾値・時間・減衰など（存在するキーをそのまま記録）
grep -nE "contain_|decay_|cooldown|threshold|interval" configs/first_minute.yaml 2>/dev/null || true

# 設定全文を証跡として保存（推奨）
mkdir -p /tmp/phase3_artifacts
cp -a configs/first_minute.yaml /tmp/phase3_artifacts/first_minute.yaml 2>/dev/null || true
\`\`\`

記録すべき代表パラメータ（存在するもののみ）:
- \`contain_min_duration_sec\`（最小継続）
- \`decay_per_sec\`（suspicion減衰）
- \`contain_threshold\`（CONTAIN遷移閾値）
- \`contain_exit_threshold\`（復帰閾値）
- \`suricata_cooldown_sec\`（Suricata加算のクールダウン）
- \`epd_update_min_interval_sec\`（EPD更新間隔。設計により例外あり）

## 4.2 実行中の状態とバージョン（証跡）

\`\`\`bash
git rev-parse --abbrev-ref HEAD
git rev-parse HEAD > /tmp/phase3_artifacts/git_commit.txt

systemctl is-active azazel-first-minute.service
curl -s http://10.55.0.10:8081/ | jq '.' > /tmp/phase3_artifacts/api_baseline.json
journalctl -u azazel-first-minute -n 80 > /tmp/phase3_artifacts/journal_baseline.log
\`\`\`

---

# 5. テストツール・依存関係

## 5.1 依存関係確認（既にインストール済み想定）

\`\`\`bash
python3 --version
pip3 show pillow
pip3 show waveshare-epd
journalctl --version
nft --version
jq --version
\`\`\`

## 5.2 よく使う確認コマンド

\`\`\`bash
# Wi-Fi
iw dev wlan0 link
sudo iw dev wlan0 scan | grep -E "SSID|signal"

# API
curl -s http://10.55.0.10:8081/ | jq '.state, .user_state, .risk_score, .suspicion'

# ログ
journalctl -u azazel-first-minute -f
journalctl -u azazel-first-minute | grep -E "CONTAIN|PROBE|NORMAL|suspicion|wifi_tags|transition"

# nftables
sudo nft list table inet azazel_fmc
sudo nft list chain inet azazel_fmc input
sudo nft list chain inet azazel_fmc stage_contain
\`\`\`

---

# 6. テスト項目詳細

以降、以下の用語を区別します。混同すると判定が破綻します。
- \`state\`: 内部状態（例: NORMAL / PROBE / CONTAIN）
- \`user_state\`: ユーザー向け状態（例: SAFE / NORMAL / LIMITED / DEGRADED / CONTAINED）
- \`suspicion\`: 内部スコア（遷移・減衰対象）
- \`risk_score\`: 統合リスク（0〜100）

---

## Test 1: 不審AP / 未検証AP 検知（Wi-Fi安全性）

### 目的

Wi-Fi安全性判定がログと API に反映され、user_state が適切に遷移することを確認。

### 前提
- azazel-first-minute.service 稼働
- Web API 応答あり
- Wi-Fi接続切り替え可能（nmcli/iwctl）

### Test 1A: 既知悪質AP接続（known_wifi.json）

\`\`\`bash
# 事前: known_wifi.json の読み取り確認
cat configs/known_wifi.json | jq '.' | head -n 40

# 初期確認
curl -s http://10.55.0.10:8081/ | jq '.user_state, .risk_score, .wifi_tags?'

# 接続切替（例）
sudo nmcli dev wifi connect "Known-Evil-SSID" password "test123" || true

# 監視
journalctl -u azazel-first-minute -f | grep -E "wifi_tags|user_state|risk_score|reason"
\`\`\`

期待（実装準拠で表現）:
- ログに wifi_tags（例: evil_twin 等）が出現
- APIの user_state が SAFE/NORMAL から LIMITED/DEGRADED 側へ遷移
- risk_score が上昇し、その理由（reason/recommendation）が欠落しない

### Test 1B: 未検証AP接続（新規SSID）

\`\`\`bash
sudo nmcli dev wifi connect "New-Unknown-SSID" password "test123" || true
journalctl -u azazel-first-minute -f | grep -E "probe|CHECKING|wifi|user_state|probe_results"
\`\`\`

期待:
- 未検証→検証（CHECKING/PROBE 相当）がログに残る
- プローブ結果がログに記録される（キー名は実装に従う）

### Test 1C: 良性AP + 弱電界（誤検知抑制）

目的:
- 「弱い電界」だけで危険側に落ち過ぎないこと（設計通りであること）を確認。

期待:
- user_state が LIMITED/CONTAINED に直行しない（ただし実装仕様がそうでない場合は仕様確認事項として記録）

---

## Test 2: Suricataアラート → CONTAIN 遷移

### 目的

Suricataシグナルが suspicion に加算され、閾値を超えると CONTAIN に遷移することを確認。

### 前提
- \`/var/log/suricata/eve.json\` が存在し、監視対象として動作している
- azazel-first-minute.service 稼働

### 準備（安全に初期化）

\`\`\`bash
sudo mkdir -p /var/log/suricata
sudo touch /var/log/suricata/eve.json
sudo chmod 666 /var/log/suricata/eve.json
sudo truncate -s 0 /var/log/suricata/eve.json
\`\`\`

### Test 2A: アラート偽装注入（最小構成）

\`\`\`bash
# 監視
journalctl -u azazel-first-minute -f | grep -E "suricata|eve|suspicion|transition|CONTAIN|PROBE" &
MON_PID=$!

# 注入（1行JSONを推奨）
echo '{"timestamp":"2026-01-19T12:00:00+00:00","alert":{"severity":1,"signature":"Simulated Critical Attack","gid":1,"sid":1000001}}' \
  | tee -a /var/log/suricata/eve.json > /dev/null

# 状態確認（最大15秒を目安。閾値は 4章のスナップショット値に従う）
for i in {1..15}; do
  echo "=== ${i}s ==="
  curl -s http://10.55.0.10:8081/ | jq '.state, .user_state, .suspicion'
  sleep 1
done

kill $MON_PID 2>/dev/null || true
\`\`\`

期待:
- ログに「Suricata入力の受理」と「suspicion加算」が記録される
- suspicion >= contain_threshold で state=CONTAIN へ遷移（contain_threshold はスナップショットで確認）
- user_state も CONTAINED 相当へ遷移（実装のマッピングに従う）

### Test 2B: Cooldown 検証（重複加算防止）

\`\`\`bash
# 1回目（Test 2Aと同様に注入）
echo '{"timestamp":"2026-01-19T12:00:00+00:00","alert":{"severity":1,"signature":"First"}}' \
  | tee -a /var/log/suricata/eve.json > /dev/null

# 短時間で2回目（cooldown内）
sleep 5
echo '{"timestamp":"2026-01-19T12:00:05+00:00","alert":{"severity":1,"signature":"Second"}}' \
  | tee -a /var/log/suricata/eve.json > /dev/null

curl -s http://10.55.0.10:8081/ | jq '.suspicion'

# cooldown経過後に3回目
sleep 30
echo '{"timestamp":"2026-01-19T12:00:35+00:00","alert":{"severity":1,"signature":"Third"}}' \
  | tee -a /var/log/suricata/eve.json > /dev/null

curl -s http://10.55.0.10:8081/ | jq '.suspicion'
\`\`\`

期待:
- cooldown 内は加算が抑制される
- cooldown 経過後は再度加算される
（クールダウン秒数は suricata_cooldown_sec のスナップショット値に従う）

### Test 2C: 異常入力耐性（任意・推奨）

目的:
- 壊れたJSONや不完全行が eve.json に混入しても、プロセスが死なない/状態が暴走しないこと。

---

## Test 3: CONTAIN 最小継続と自動復帰（減衰）

### 目的

CONTAIN が contain_min_duration_sec 以上継続し、その後 decay_per_sec により suspicion が減衰して復帰することを確認。

### 計測（5秒刻み推奨）

\`\`\`bash
mkdir -p /tmp/phase3_artifacts
START=$(date +%s)
for i in {0..120..5}; do
  TS=$(date '+%Y-%m-%d %H:%M:%S')
  curl -s http://10.55.0.10:8081/ | jq -c --arg ts "$TS" '{ts:$ts,state:.state,user_state:.user_state,suspicion:.suspicion,risk_score:.risk_score}' \
    | tee -a /tmp/phase3_artifacts/contain_recovery_timeline.jsonl > /dev/null
  sleep 5
done
\`\`\`

期待:
- state=CONTAIN が contain_min_duration_sec 未満で解除されない
- decay_per_sec に相当する速度で suspicion が減少する
- suspicion <= contain_exit_threshold 付近で state が CONTAIN から復帰側へ遷移する
（exit閾値は実装のキーに従い、スナップショット値を参照）

---

## Test 4: EPD表示（normal/warning/danger）と崩れ検知

### 目的

表示が崩れず、状態に応じた内容が出ること。
マスター確認済み事項として、--state danger --msg "ATTACK DETECTED" --dry-run のプレビューが崩れていない点は本テストで再現性として証跡化します。

### Test 4A: dry-run プレビュー生成（必須）

\`\`\`bash
sudo python3 py/azazel_epd.py --state normal  --ssid "TestNet" --ip "10.55.0.10" --signal -55 --dry-run
sudo python3 py/azazel_epd.py --state warning --msg "SUSPICIOUS AP" --dry-run
sudo python3 py/azazel_epd.py --state danger  --msg "ATTACK DETECTED" --dry-run

ls -la /tmp/azazel_epd_preview_*png | tee /tmp/phase3_artifacts/epd_preview_files.txt
\`\`\`

期待:
- composite画像が生成される
- 文字欠け・はみ出し・アイコン欠落がない（目視確認）
- danger は赤背景 + 白文字、warning は注意表現、normal はSSID/IP/signalが欠落しない（実装仕様に従う）

### Test 4B: 実機更新の頻度（fingerprint/抑制）

EPDの更新抑制（fingerprint比較、最小更新間隔）を実装している場合、以下を確認します。
- 同一内容の連続更新が抑制される
- ただし CONTAIN遷移（危険通知）は即時性が最優先 であり、抑制が危険通知を遅延させるなら不具合として扱う

確認例:

\`\`\`bash
# EPD呼び出しの痕跡（環境依存。straceが重い場合は省略可）
strace -f -e execve -o /tmp/phase3_artifacts/strace_epd.log sudo python3 py/azazel_zero/cli_unified.py --enable-epd
\`\`\`

---

## Test 5: CONTAIN中の管理通信（SSH/Web API）継続

### 目的

遮断中でも管理fast-pathが保たれ、運用者が制御不能に陥らないことを確認。

\`\`\`bash
# 事前基準
time ssh azazel@192.168.40.184 'echo OK'

# CONTAIN中に複数回
for i in {1..5}; do
  echo "=== Try $i ==="
  time ssh azazel@192.168.40.184 'curl -s http://10.55.0.10:8081/ | jq -r .state'
  sleep 2
done
\`\`\`

追加確認（推奨）:
- nftables の counter が stage_contain で増加する（管理許可ルールが使われている証跡）

\`\`\`bash
sudo nft list chain inet azazel_fmc stage_contain | tee /tmp/phase3_artifacts/nft_stage_contain.txt
\`\`\`

---

## Test 6: リスクスコア統合（0〜100）の妥当性

### 目的

risk_score が状態・信号・検知要因により一貫して変化することを確認。
（数値レンジは実装に依存するため、ここも固定値ではなく"傾向"と"上限/下限処理"を重視します。）

\`\`\`bash
for i in {1..10}; do
  curl -s http://10.55.0.10:8081/ | jq '.user_state, .risk_score, .suspicion, .signal_dbm?'
  sleep 3
done
\`\`\`

期待:
- risk_score が 0〜100 の範囲外に出ない
- 危険側（CONTAINED相当）で明確に高くなる
- 同一条件で乱高下しない（大きな跳躍が頻発する場合は要調査）

---

# 7. 合格基準

## 7.1 全体合格基準（GO/NO-GO）

| テスト | 合格 | 注記 |
|--------|------|------|
| Test 1 | 必須 | Wi-Fi判定の実効性 |
| Test 2A/2B | 必須 | 検知→遷移、cooldown |
| Test 3 | 必須 | 最小継続と復帰 |
| Test 4 | 必須 | 表示の信頼性 |
| Test 5 | 必須 | 運用継続性 |
| Test 6 | 推奨 | ただし異常値はNO-GO要因 |

## 7.2 個別合格基準（実装準拠）

Test 2/3 は必ず「4章のスナップショット値」に基づき判定します。
- Test 2A: suspicion が加算され、contain_threshold 到達で state=CONTAIN へ遷移する
- Test 2B: suricata_cooldown_sec 内の重複加算が抑制される
- Test 3: contain_min_duration_sec 未満で CONTAIN が解除されない。decay_per_sec 相当で減衰し、contain_exit_threshold 付近で復帰する
- Test 4: プレビュー/実機ともに「崩れ」がない。危険通知は遅延しない（抑制が危険通知を遅らせる場合はFAIL）
- Test 5: CONTAIN 中も SSH と Web API が継続する（遮断はFAIL）

---

# 8. トラブルシューティング（要点のみ）

## 8.1 Wi-Fi判定が動かない

\`\`\`bash
journalctl -u azazel-first-minute | grep -E "wifi|evaluate|probe|known_wifi|tags"
iw dev wlan0 link
cat configs/known_wifi.json | jq '.'
\`\`\`

## 8.2 Suricataが拾われない

\`\`\`bash
ls -la /var/log/suricata/eve.json
journalctl -u azazel-first-minute | grep -E "suricata|eve|alert|parse"
\`\`\`

## 8.3 CONTAINが即解除される

\`\`\`bash
grep -nE "contain_min_duration|contain_exit_threshold" configs/first_minute.yaml
journalctl -u azazel-first-minute | grep -E "CONTAIN|exit|min_duration"
\`\`\`

## 8.4 EPDが更新されない

\`\`\`bash
sudo python3 py/azazel_epd.py --state danger --msg "ATTACK DETECTED" --dry-run
ls -la /tmp/azazel_epd_preview_*png
ls -la /dev/spidev*
\`\`\`

## 8.5 CONTAIN中にSSHが落ちる（最優先で対処）

\`\`\`bash
sudo nft list chain inet azazel_fmc input | grep -nE "mgmt|22|8081"
sudo nft list chain inet azazel_fmc stage_contain
\`\`\`

---

# 9. 証跡・成果物の保存（必須）

最低限、以下を \`/tmp/phase3_artifacts/\` に保存します。
- git_commit.txt
- first_minute.yaml（存在すればコピー）
- api_baseline.json
- journal_baseline.log
- contain_recovery_timeline.jsonl
- nft_stage_contain.txt
- epd_preview_files.txt
- EPDプレビュー画像（/tmp/azazel_epd_preview_*.png をコピー推奨）

\`\`\`bash
cp -a /tmp/azazel_epd_preview_*.png /tmp/phase3_artifacts/ 2>/dev/null || true
tar -czf /tmp/phase3_artifacts_$(date +%Y%m%d_%H%M).tar.gz /tmp/phase3_artifacts
\`\`\`

---

# 10. テスト完了後のまとめ（結果レポート）

## 10.1 結果レポート作成テンプレート

\`\`\`bash
cat > PHASE3_TEST_RESULTS.md << 'EOF'
# Phase 3 テスト結果

**実施日**: 2026-01-__  
**実施者**: ______  
**対象ブランチ**: feature/epd-tui-tuning  
**コミット**: ______  
**判定**: [GO / GO(条件付) / NO-GO]

## 実装パラメータ（スナップショット）
- contain_threshold: __
- contain_exit_threshold: __
- contain_min_duration_sec: __
- decay_per_sec: __
- suricata_cooldown_sec: __
- epd_update_min_interval_sec: __

## テスト結果サマリー

| # | テスト | 結果 | 根拠（ログ/証跡） |
|---|--------|------|-------------------|
| 1A | 既知悪質AP | PASS/FAIL | wifi_tags / user_state |
| 1B | 未検証AP | PASS/FAIL | probe / results |
| 2A | Suricata→CONTAIN | PASS/FAIL | state遷移 / suspicion |
| 2B | Cooldown | PASS/FAIL | 加算抑制ログ |
| 3 | CONTAIN復帰 | PASS/FAIL | timeline.jsonl |
| 4 | EPD表示 | PASS/FAIL | preview画像 / 実機 |
| 5 | 管理通信 | PASS/FAIL | SSH/Web継続 |
| 6 | risk_score | PASS/FAIL | API推移 |

## 重大事項（NO-GO条件）
- CONTAIN中に管理通信が落ちる
- 危険通知（EPD）が遅延/欠落する
- state machine が想定外に暴走する（復帰しない等）

## 改善アクション
- [ ] Issue 1: ______
- [ ] Issue 2: ______

EOF
\`\`\`

---

**テスト計画書版**: 3.0（実装準拠・パラメータスナップショット方式）  
**最終更新**: 2026年1月19日  
**ステータス**: 実施開始可
