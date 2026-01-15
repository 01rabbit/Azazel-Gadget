# 改善実装一覧（クイック参照）

## 修正ファイル一覧

### 1. nftables/first_minute.nft
**目的**: 管理通信（SSH/VSCode）を wlan0 からでも接続可能にする

**変更点**:
- ✅ `set mgmt_ports` を追加（22, 80, 443, 8081）
- ✅ `input` chain で管理通信を「両インタフェース対応」に変更
- ✅ `stage_contain` で CONTAIN 中もホスト宛管理通信を許可

**確認コマンド**:
```bash
nft -f nftables/first_minute.nft --check  # 構文確認
```

---

### 2. py/azazel_zero/first_minute/state_machine.py
**目的**: CONTAIN 無限ループを解決、Suricata 重複アラートを抑制

**変更点**:
- ✅ `suricata_cooldown_sec` パラメータ追加（30 秒デフォルト）
- ✅ `contain_min_duration_sec` パラメータ追加（20 秒デフォルト）
- ✅ `contain_exit_suspicion` パラメータ追加（30.0 デフォルト）
- ✅ `_apply_signals()` で Suricata クールダウン機構を実装
- ✅ `step()` で CONTAIN 脱出ロジック（最小継続時間 + suspicion 閾値）を実装
- ✅ 戻り値に `changed` フラグを追加

**テスト**:
```bash
python3 test_redesign_verification.py
```

---

### 3. py/azazel_zero/first_minute/controller.py
**目的**: ログノイズを削減、状態遷移イベントを明確化

**変更点**:
- ✅ `run_loop()` で状態遷移時のみ INFO ログ出力
- ✅ 毎ループ DEBUG ログを追加
- ✅ ログに `transitioned` フラグを付与

**ログ確認**:
```bash
# 状態遷移（NORMAL → CONTAIN など）を検出
journalctl -u azazel-first-minute | grep "transitioned"

# 詳細ログ（DEBUG）を確認
journalctl -u azazel-first-minute --output=json | jq '.MESSAGE'
```

---

### 4. py/azazel_zero/first_minute/tc.py
**目的**: 遅滞行動の設計思想をドキュメント化

**変更点**:
- ✅ クラスドキュメント（docstring）を大幅強化
- ✅ nftables との協調設計を明記
- ✅ 将来改善案（HTB + fwmark）を記録

---

### 5. configs/first_minute.yaml
**目的**: 新規パラメータのデフォルト値を設定

**変更点**:
- ✅ `state_machine:` セクションに以下を追加:
  - `suricata_cooldown_sec: 30.0`
  - `contain_min_duration_sec: 20.0`
  - `contain_exit_suspicion: 30.0`

**注**: 既存の config を使用する場合は、これらのパラメータがなくてもデフォルト値が適用されます。

---

## 🧪 テスト実行方法

### テストスクリプト実行

```bash
cd /home/azazel/Azazel-Zero
python3 test_redesign_verification.py
```

**期待される出力**:
```
============================================================
Azazel-Zero Redesign Verification Tests
============================================================

[TEST 1] Suricata Cooldown Mechanism
============================================================
1回目アラート: suspicion=15.0 (expected: 15.0)
2回目アラート（5秒後）: suspicion=15.0 (expected: 15.0, no increment)
3回目アラート（35秒後）: suspicion=30.0 (expected: 30.0)
✓ PASS: Suricata cooldown working correctly

...

============================================================
✓ ALL TESTS PASSED
============================================================
```

### 実運用テスト

#### 1. SSH 接続テスト（wlan0 経由）

```bash
# 修正前: 接続不可 (Timeout)
# 修正後: 接続可能
ssh -vvv pi@192.168.4.1  # wlan0 IP

# VSCode Remote-SSH でも接続可能に
```

#### 2. Suricata アラート抑制テスト

```bash
# eve.json を最新更新（アラート発火）
touch /var/log/suricata/eve.json

# ログ確認（最初のみ suricata_alert 加算）
journalctl -u azazel-first-minute -f --output=json | \
  jq 'select(.MESSAGE | contains("suricata_alert")) | .MESSAGE'
```

期待: 1 回のアラート検知で suspicion +15、30 秒以内の重複では加算なし

#### 3. CONTAIN 自動復帰テスト

```bash
# 高い suspicion を生じさせる
# → CONTAIN 状態へ

# 20 秒経過 + suspicion が低下すると自動復帰
journalctl -u azazel-first-minute -f | grep "degraded (recovered)"
```

期待: `contain->degraded (recovered)` ログが出力される

#### 4. ログデバウンステスト

```bash
# 状態が変わらない時間帯のログを確認
journalctl -u azazel-first-minute --since="10 minutes ago" | wc -l

# 修正前: ~300 行（毎 2 秒 INFO）
# 修正後: ~10 行（遷移時のみ INFO + DEBUG）
```

---

## 📊 改善効果の確認方法

### ダッシュボード/ログの見方

**修正前** (ログノイズが多い):
```json
{"state": "CONTAIN", "suspicion": 100.0, "reason": "suricata_alert"}
{"state": "CONTAIN", "suspicion": 100.0, "reason": "suricata_alert"}  # 重複
{"state": "CONTAIN", "suspicion": 100.0, "reason": "suricata_alert"}  # 重複
{"state": "CONTAIN", "suspicion": 100.0, "reason": "suricata_alert"}  # 重複
```

**修正後** (遷移時のみ):
```json
{"state": "NORMAL", "suspicion": 0.0, "reason": "new_link"}
{"state": "NORMAL", "suspicion": 20.0, "reason": "suricata_alert", "transitioned": false}
{"state": "CONTAIN", "suspicion": 65.0, "reason": "normal->contain", "transitioned": true}
... (20 秒後) ...
{"state": "DEGRADED", "suspicion": 25.0, "reason": "contain->degraded (recovered)", "transitioned": true}
```

---

## ⚠️ トラブルシューティング

### Q: SSH が接続不可

**確認事項**:
1. nftables が正しく適用されているか
   ```bash
   sudo nft list table inet azazel_fmc | grep -A 5 "chain input"
   ```
   → `ip daddr $MGMT_IP tcp dport @mgmt_ports accept` が存在するか確認

2. wlan0 の IP アドレスが正しいか
   ```bash
   ip addr show wlan0
   ```

### Q: CONTAIN から脱出しない

**確認事項**:
1. `contain_min_duration_sec` が経過しているか
2. `suspicion` が `contain_exit_suspicion` より低下しているか
   ```bash
   journalctl -u azazel-first-minute | grep "suspicion"
   ```

3. Suricata アラートが継続発火していないか
   ```bash
   sudo ls -la /var/log/suricata/eve.json
   ```

### Q: ログが出力されない

**確認事項**:
1. ログレベルが INFO 以上か
   ```bash
   journalctl -u azazel-first-minute --priority=info
   ```

2. systemd サービスが起動しているか
   ```bash
   systemctl status azazel-first-minute
   ```

---

## 📞 サポート情報

このドキュメントと併読してください：
- [REDESIGN_IMPLEMENTATION_PLAN.md](REDESIGN_IMPLEMENTATION_PLAN.md) - 詳細設計書
- [IMPLEMENTATION_REPORT.md](IMPLEMENTATION_REPORT.md) - 実装レポート
- [README.md](README.md) - プロジェクト概要

---

**最終更新**: 2026年1月15日
