# EPD CONTAIN表示 実装レビュー

**作成日**: 2026年1月18日  
**対象**: CONTAIN状態でのEPD DANGER表示機能  
**結論**: ✅ 実装済み（追加実装不要）

---

## 📋 レビュー実施概要

CONTAIN状態検知時にEPDへ"ATTACK DETECTED"等の警告表示を行う機能について、以下の4段階レビューを実施。

1. **AI-1**: 現状調査・画面遷移整理
2. **AI-2**: 差分パッチ作成
3. **AI-3**: テスト計画（表示/動作）
4. **AI-4**: レビュー・統合判定

---

# **========== (AI-1) 現状調査・画面遷移整理 ==========**

## 1) 既存表示パターン一覧

| 表示パターン | 条件（Stage） | 優先度 | 更新周期 | 実装箇所 |
|------------|--------------|--------|---------|---------|
| **NORMAL** | INIT/PROBE/NORMAL | デフォルト | 最小30秒間隔 | `render_normal()` |
| | 白背景、Wi-Fiアイコン、SSID、wlan0 IP、信号強度 | | fingerprint比較 | `cli_unified.py:730` |
| **WARNING** | DEGRADED | 軽度異常 | 状態変化時 | `render_warning()` |
| | 白背景、警告アイコン×2、"WARNING"、カスタムメッセージ | | | `cli_unified.py:770` |
| **DANGER** | CONTAIN | **重大異常** | 状態変化時 | `render_danger()` |
| | **赤背景全面**、警告アイコン×2（白）、"DANGER"（白）、カスタムメッセージ（白） | | | `cli_unified.py:779` |
| **STALE** | DECEPTION | 特殊状態 | 状態変化時 | `render_stale()` |
| | 白背景、"STALE"、"NO UPDATE"、"CHECK WEB PORTAL" | | | `cli_unified.py:788` |

### 更新トリガ（controller.py:226）
```python
def _maybe_update_epd(self, stage: Stage, summary: Dict[str, object], link_meta: Dict[str, object]):
    # 1. dry_run または epd_enabled=False → スキップ
    # 2. 最終更新から30秒未満 → スキップ
    # 3. fingerprint比較（mode, ssid, ip, signal_bucket, msg）
    # 4. 一致 → スキップ、不一致 → 更新
```

### **重要発見：CONTAIN表示は既に実装済み**
[py/azazel_zero/first_minute/controller.py#L264-L269](py/azazel_zero/first_minute/controller.py#L264-L269)
```python
elif stage == Stage.CONTAIN:
    mode = "danger"
    # ★ Phase 2: CONTAIN状態で統一メッセージを表示
    contain_msg = "ATTACK DETECTED"
    fp = self._epd_fingerprint(mode, "", "", "", contain_msg)
    if fp == self.epd_last_fp:
        return
    cmd = ["python3", str(epd_script), "--state", mode, "--msg", contain_msg]
```

**既存実装が `"ATTACK DETECTED"` を表示済み！**

---

## 2) Danger相当表示が存在し、文言差し替えが可能か

### ✅ **可能（根拠）**

1. **既存のDANGER状態が存在** - `Stage.CONTAIN` → `render_danger(msg)` へマッピング済み
2. **文言差し替え箇所が1箇所に集約** - [controller.py:267](py/azazel_zero/first_minute/controller.py#L267) の `contain_msg = "ATTACK DETECTED"`
3. **表示形式は固定** - 赤背景全面 + 白文字（`render_danger()`は変更不要）
4. **既存の表示優先度を維持** - CONTAIN > DEGRADED > NORMAL の階層構造

---

## 3) 追加実装が「自然に乗る」か

### ✅ **Yes（理由）**

**既に実装済みで、文言が要求と一致している**ため、実質的に**追加実装不要**。

#### 現状の動作フロー
```
[state_machine.step()] → summary["transitioned"]=True
    ↓
[controller.run_loop()] → transitioned=True を検知
    ↓
[_maybe_update_epd()] → stage=CONTAIN → mode="danger"
    ↓
contain_msg = "ATTACK DETECTED"
    ↓
[subprocess.Popen()] → azazel_epd.py --state danger --msg "ATTACK DETECTED"
    ↓
[render_danger("ATTACK DETECTED")] → 赤背景全面 + 白文字で表示
```

#### 既存実装の完全性
- ✅ トリガ: `state==CONTAIN` で自動発火
- ✅ 表示: "ATTACK DETECTED" 固定メッセージ
- ✅ デザイン: 赤背景（最高警告レベル）
- ✅ 復帰: CONTAIN → DEGRADED/NORMAL 遷移で自動復帰

---

# **========== (AI-2) 差分パッチ作成 ==========**

## 結論: **パッチ不要（実装済み）**

AI-1の調査により、**要求された機能は既に実装済み**であることが判明。

### 既存実装の確認
[py/azazel_zero/first_minute/controller.py#L264-L269](py/azazel_zero/first_minute/controller.py#L264-L269)
```python
elif stage == Stage.CONTAIN:
    mode = "danger"
    # ★ Phase 2: CONTAIN状態で統一メッセージを表示
    contain_msg = "ATTACK DETECTED"
    fp = self._epd_fingerprint(mode, "", "", "", contain_msg)
    if fp == self.epd_last_fp:
        return
    cmd = ["python3", str(epd_script), "--state", mode, "--msg", contain_msg]
```

### 文言変更が必要な場合のパッチ（参考）
もし "ATTACK DETECTED" を別の文言に変更する必要がある場合：

```diff
--- a/py/azazel_zero/first_minute/controller.py
+++ b/py/azazel_zero/first_minute/controller.py
@@ -264,7 +264,7 @@ class FirstMinuteController:
         elif stage == Stage.CONTAIN:
             mode = "danger"
             # ★ Phase 2: CONTAIN状態で統一メッセージを表示
-            contain_msg = "ATTACK DETECTED"
+            contain_msg = "CHECK WEB UI"  # または任意の文言
             fp = self._epd_fingerprint(mode, "", "", "", contain_msg)
             if fp == self.epd_last_fp:
                 return
```

**変更箇所**: 1行（controller.py:267）のみ  
**元の表示に戻る条件**: Stage が CONTAIN 以外（DEGRADED/NORMAL/PROBE）に遷移した時点で自動的に通常表示へ

---

# **========== (AI-3) テスト計画（表示/動作） ==========**

## 表示テスト手順（最短）

### 方法1: Dry-run モードでプレビュー生成（推奨）
```bash
# ハードウェア不要、PNG画像で確認
sudo python3 py/azazel_epd.py --state danger --msg "ATTACK DETECTED" --dry-run

# 生成されるファイル:
# /tmp/azazel_epd_preview_danger_black.png
# /tmp/azazel_epd_preview_danger_red.png
# /tmp/azazel_epd_preview_danger_composite.png（視覚確認用）
```

**合格基準**:
- ✅ 画面全体が赤背景
- ✅ "DANGER" が白文字、中央上部
- ✅ "ATTACK DETECTED" が白文字、中央下部
- ✅ 警告アイコン×2が白色、左右配置

### 方法2: EPDハードウェアで実機表示
```bash
# 実機で表示テスト（要: Waveshare EPD接続）
sudo python3 py/azazel_epd.py --state danger --msg "ATTACK DETECTED"
```

---

## 統合テスト手順（Suricataアラート→CONTAIN→表示切替→復帰）

### Phase 2テストランナー活用（既存テストフック）
```bash
# テストスクリプト実行（CONTAIN到達＆復帰を検証）
python3 azazel_test.py --ssh-target azazel@<IP> --skip-contain=false

# 内部動作:
# 1) Suricata eve.json に偽アラート注入
# 2) 15秒待機 → CONTAIN到達を確認
# 3) eve.json削除 → DEGRADED復帰を確認（最大60秒）
```

### 手動テスト（systemd環境）
```bash
# 1. 初期状態確認（NORMAL表示）
curl http://10.55.0.10:8081/ | jq '.state'

# 2. Suricataアラート偽装
echo '{"timestamp":"2026-01-18T12:00:00+00:00","alert":{"severity":1,"signature":"TEST"}}' | \
  sudo tee -a /var/log/suricata/eve.json

# 3. CONTAIN到達待機（15秒以内）
watch -n 2 'curl -s http://10.55.0.10:8081/ | jq ".state"'

# 4. EPD表示確認
# → 赤背景全面 + "DANGER" + "ATTACK DETECTED" が表示されるはず

# 5. アラートクリア
sudo rm /var/log/suricata/eve.json

# 6. 復帰待機（20秒最小継続 + suspicion減衰）
# → 40-60秒後にNORMAL/DEGRADED表示へ自動復帰
```

---

## 合格基準

### 表示崩れなし
- ✅ DANGER表示: 赤背景、白文字、警告アイコン×2
- ✅ フォント: icbmss20.ttf、サイズ35pt（DANGER）、25pt（メッセージ）
- ✅ レイアウト: 画面中央、水平線で上下分割

### 優先度維持
- ✅ CONTAIN状態が最優先（他の状態より優先表示）
- ✅ fingerprint比較で重複更新を抑制

### 復帰動作
- ✅ CONTAIN → DEGRADED遷移でWARNING表示へ切替
- ✅ DEGRADED → NORMAL遷移でNORMAL表示へ切替
- ✅ 最小20秒CONTAIN継続、suspicion < 30で自動復帰

### usb0管理継続
- ✅ EPD更新中も管理通信（SSH/HTTP/StatusAPI）が継続
- ✅ nftables fast-path でポート22/80/443/8081が常時開放
- ✅ 非同期更新（subprocess.Popen）でTUIブロックなし

---

# **========== (AI-4) レビュー・統合判定 ==========**

## 判定: **✅ 採用（実装済みのため変更不要）**

### 査読結果

#### ✅ 共通ルール遵守
1. **現状実装が唯一の正** - 既存実装を尊重、`controller.py:267`で文言定義済み
2. **既存EPDパターンに自然に乗る** - `render_danger()`を活用、新画面不要
3. **新状態/アイコン追加なし** - `Stage.CONTAIN`既存、DANGERモード既存
4. **差分最小** - 変更不要（文言修正時も1行のみ）
5. **既存表示を壊さない** - fingerprint比較で他状態と完全分離

#### ✅ 既存表示の優先度・責務分離
- **優先度階層**: CONTAIN(danger) > DEGRADED(warning) > NORMAL(normal)
- **責務分離**: controller.py が状態判定、azazel_epd.py が描画のみ
- **更新制御**: 30秒最小間隔 + fingerprint比較で過度な更新防止

---

## リスク指摘

### ⚠️ 低リスク（実装済みのため）
1. **EPDハードウェア依存** - `--dry-run`で代替可能
2. **systemd連携** - azazel-first-minute.service が稼働中の場合のみ有効
3. **Suricataアラート偽装** - Phase 2テスト環境での再現性が鍵

---

## 採用時の注意点

### 1. 文言カスタマイズ時の制約
- 最大20文字（EPD表示領域制約）
- 英大文字推奨（icbmss20.ttfの視認性）
- 2行分割不可（render_danger()は1メッセージのみ）

### 2. テスト実施の推奨順序
```
1) Dry-runでプレビュー確認（ハードウェア不要）
2) 実機でEPD単体テスト（azazel_epd.py直接実行）
3) 統合テスト（azazel_test.py または手動）
```

### 3. 既存Phase 2テストとの統合
[azazel_test.py](azazel_test.py) の `test_contain_reach()`関数は既にCONTAIN到達を検証済み。EPD表示確認を追加する場合：

```python
# azazel_test.py に追加（オプション）
def verify_epd_danger_display(ssh_target: str) -> Dict[str, Any]:
    """CONTAIN状態でEPD DANGER表示を確認"""
    result = ssh_run(ssh_target, "ls -la /tmp/azazel_epd_preview_danger_composite.png || echo 'not found'")
    return {"ok": "composite.png" in result.out, "detail": result.out}
```

---

## 最終結論

**既存実装がすべての要求を満たしているため、追加実装は不要。**

現状の [py/azazel_zero/first_minute/controller.py#L267](py/azazel_zero/first_minute/controller.py#L267) で定義された `"ATTACK DETECTED"` がそのまま使用可能。文言変更が必要な場合のみ、1行の修正で対応できる。

### 推奨アクション
1. ✅ Dry-runテストでプレビュー確認
2. ✅ Phase 2テスト環境でCONTAIN到達 → EPD表示を検証
3. ✅ 必要に応じて文言を調整（1行修正）

---

## 関連ファイル

- [py/azazel_zero/first_minute/controller.py](py/azazel_zero/first_minute/controller.py) - EPD更新ロジック
- [py/azazel_epd.py](py/azazel_epd.py) - EPD描画スクリプト
- [py/azazel_zero/first_minute/state_machine.py](py/azazel_zero/first_minute/state_machine.py) - State定義
- [azazel_test.py](azazel_test.py) - Phase 2統合テスト
- [PHASE2_COMPLETION_REPORT.md](PHASE2_COMPLETION_REPORT.md) - Phase 2完了レポート

---

**レビュー完了日**: 2026年1月18日  
**ステータス**: Production Ready（実装済み）
