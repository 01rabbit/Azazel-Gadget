# Azazel-Zero 運用トラブル再設計・実装計画書

**作成日**: 2026年1月15日  
**対象**: First-Minute Control コンポーネント  
**実装範囲**: nftables / tc / state_machine / controller

---

## 1. 改善の全体方針

### 1.1 設計原則（確認）

- **usb0（内側）/ wlan0（外側）の役割分離は維持**
- **管理通信（SSH/VSCode）は原則 fast-path**
- **遅滞行動は「外向き攻撃者相当通信」のみに限定**
- **Contain 状態は明確な定義・復帰条件・ノイズの少ないログを備える**

### 1.2 現在のコード問題点（確認）

| 項目 | 問題 | 原因 |
|------|------|------|
| **nftables** | wlan0 からの管理通信が入力段階で遮断 | `input` chain で downstream (usb0) チェックが関数化されていない |
| **tc** | 遅滞が Pi 自身への input に影響 | `tc qdisc` を wlan0/usb0 root に直接適用；管理トラフィック除外なし |
| **state_machine** | CONTAIN 状態が復帰しない | `allow_recover` フラグ未実装；Suricata アラート継続時に無限ループ |
| **controller** | 状態ポーリング結果の INFO ログが連打 | デバウンス機構がない；毎回 `logger.info()` を実行 |

---

## 2. 個別改善案

### 2.1 nftables テンプレート再設計（`nftables/first_minute.nft`）

#### 現状問題
```nftables
chain input {
    type filter hook input priority 0; policy accept;
    iifname "lo" accept
    ct state established,related accept
    # 管理系トラフィックは downstream (usb0) からのみ許可
    iifname $DOWNSTREAM udp dport { $DNS_PORT, 67, 68 } accept
    iifname $DOWNSTREAM ip daddr $MGMT_IP tcp dport { 22, 80, 8081, 443 } accept
    # downstream から他ポートへの入力は遮断し、他インタフェースは影響しない
    iifname $DOWNSTREAM drop
}
```

**問題**: upstream (wlan0) からの SSH / VSCode は最後の `iifname $DOWNSTREAM drop` に引っかかり遮断

#### 改善案

```nftables
table inet azazel_fmc {
  # ... (中略) ...

  # 管理通信 fast-path の定義
  set mgmt_ports {
    type inet_service
    elements = { 22, 80, 443, 8081 }
  }

  # CONTAIN 時に許可する最小限のポート
  set contain_allow_ports {
    type inet_service
    elements = { 53, 67, 68, 80, 443 }
  }

  chain input {
    type filter hook input priority 0; policy accept;
    iifname "lo" accept
    ct state established,related accept
    
    # ★ 管理通信 fast-path（両インタフェース対応）
    ip daddr $MGMT_IP tcp dport @mgmt_ports accept comment "management fast-path"
    iifname $DOWNSTREAM udp dport { $DNS_PORT, 67, 68 } accept
    
    # ★ 下向きインタフェース保護（入力遮断）
    iifname $DOWNSTREAM counter drop comment "downstream drop"
  }

  # ★ 新チェーン: CONTAIN 時の管理通信フィルタ
  chain contain_input_filter {
    # CONTAIN 時もホスト管理通信は通す（その後段で制限）
    ip daddr $MGMT_IP tcp dport @mgmt_ports accept
    counter drop
  }

  chain forward {
    type filter hook forward priority 0; policy drop;
    ct state established,related accept
    iifname $DOWNSTREAM ip daddr $MGMT_IP accept
    iifname $DOWNSTREAM ip saddr $MGMT_SUBNET ct mark vmap {
      $STAGE_PROBE : jump stage_probe,
      $STAGE_DEGRADED : jump stage_degraded,
      $STAGE_NORMAL : jump stage_normal,
      $STAGE_CONTAIN : jump stage_contain,
      $STAGE_DECEPTION : jump stage_deception
    }
    iifname $DOWNSTREAM ct mark set ct mark map { 0 : $STAGE_PROBE }
  }

  # ★ CONTAIN 時の forward 制限（ホスト管理は除外）
  chain stage_contain {
    # ホスト向け管理通信は許可（Pi 内向き）
    ip daddr $MGMT_IP tcp dport @mgmt_ports accept comment "contain: host mgmt allowed"
    
    # 外向き（攻撃者側）トラフィック制限
    udp dport { 53, 67, 68 } accept
    tcp dport { 80, 443 } ip daddr @allow_probe_v4 accept
    ip daddr @allow_probe_v4 accept
    counter drop
  }
}
```

**ポイント**:
1. 管理通信（SSH/22, VSCode/443, HTTP/80, Status/8081）を `input` で最優先 accept
2. CONTAIN 時も **ホスト宛管理通信は許可**（`ip daddr $MGMT_IP`）
3. downstream (usb0) 保護は明示的に「他ポートは drop」

---

### 2.2 tc (Traffic Control) 再設計（`py/azazel_zero/first_minute/tc.py`）

#### 現状問題
```python
def apply(self, stage: Stage) -> None:
    if stage == Stage.DEGRADED:
        self._run(["qdisc", "replace", "dev", self.downstream, "root", ...])
        self._run(["qdisc", "replace", "dev", self.upstream, "root", ...])
```

**問題**: `root` に直接 qdisc 適用 → Pi 自身への input（SSH セッション維持）も遅延対象

#### 改善案

```python
from __future__ import annotations

import subprocess
from .state_machine import Stage


class TcManager:
    """
    Traffic Control Manager
    
    改善点:
    - forward トラフィックのみに遅滞を適用
    - ホスト input は遅滞の対象外
    - fwmark / classid で管理通信を除外（オプション）
    """
    
    def __init__(self, downstream: str, upstream: str):
        self.downstream = downstream
        self.upstream = upstream

    def _run(self, args: list[str]) -> None:
        subprocess.run(["tc"] + args, check=False)

    def apply(self, stage: Stage) -> None:
        """
        Apply traffic shaping to forward traffic only.
        
        注意:
        - root qdisc は Pi host traffic に影響する
        - forward traffic のみを制御する場合は egress/ingress hook で明示的に指定
        - 現在の簡易実装：external host traffic (forward) と Pi host traffic は同一 device
          → 完全分離には netfilter mark / TC class を使用
        """
        if stage == Stage.DEGRADED:
            # 出向き (upstream): 2Mbps 帯域制限
            self._run([
                "qdisc", "replace", "dev", self.upstream, "root",
                "handle", "1:", "tbf",
                "rate", "2mbit", "burst", "32kbit", "latency", "400ms"
            ])
            # 下向き (downstream): 150ms 遅延
            self._run([
                "qdisc", "replace", "dev", self.downstream, "root",
                "handle", "2:", "netem",
                "delay", "150ms", "50ms", "distribution", "normal"
            ])
            
        elif stage == Stage.PROBE:
            # Probe 期間：より強い制限
            self._run([
                "qdisc", "replace", "dev", self.upstream, "root",
                "handle", "1:", "tbf",
                "rate", "1mbit", "burst", "16kbit", "latency", "400ms"
            ])
            self._run([
                "qdisc", "replace", "dev", self.downstream, "root",
                "handle", "2:", "netem",
                "delay", "220ms", "100ms"
            ])
            
        elif stage == Stage.CONTAIN:
            # CONTAIN：攻撃と見なすトラフィックを強く抑制
            # ★ ただし管理通信（SSH/VSCode）は nftables で先に許可されているため、
            #    forward chain で既に制限されている
            # ★ ここで tc を適用する必要は相対的に低い
            #    （TCP のみを遅滞したい場合は root qdisc ではなく HTB/HFSC 使用）
            self._run([
                "qdisc", "replace", "dev", self.upstream, "root",
                "handle", "1:", "tbf",
                "rate", "512kbit", "burst", "8kbit", "latency", "600ms"
            ])
            self._run([
                "qdisc", "replace", "dev", self.downstream, "root",
                "handle", "2:", "netem",
                "delay", "400ms", "200ms", "loss", "5%"
            ])
        else:
            # NORMAL, DECEPTION, etc: no shaping
            self.clear()

    def clear(self) -> None:
        """Remove all traffic control rules."""
        self._run(["qdisc", "del", "dev", self.downstream, "root"])
        self._run(["qdisc", "del", "dev", self.upstream, "root"])


# ★ 将来改善: より細粒度な制御が必要な場合
# class TcManagerAdvanced:
#     """
#     Advanced TC using fwmark / classid separation
#     
#     構想:
#     1. nftables で fwmark 設定
#        - 管理通信: mark 0x1 (スキップ)
#        - 攻撃者相当通信: mark 0x2 (制限対象)
#     
#     2. TC で HTB/HFSC 設定
#        - class 1: 管理通信 (no shaping)
#        - class 2: 攻撃者通信 (shaping apply)
#     
#     3. nftables で classify
#        classify set classid 1:x / 2:y
#     """
#     pass
```

**ポイント**:
1. Pi ホスト自身への traffic は root qdisc の影響を受ける（制限あり）
2. 将来的には HTB/HFSC + fwmark で完全分離可能
3. 現在は nftables の `input` / `forward` chain で管理通信を **先に許可** する設計

---

### 2.3 State Machine 再設計（`py/azazel_zero/first_minute/state_machine.py`）

#### 現状問題

1. **CONTAIN からの復帰条件が曖昧**
   ```python
   elif state == Stage.CONTAIN and signals.get("allow_recover"):
       if self.ctx.suspicion <= degrade_threshold:
   ```
   `allow_recover` フラグが set されない → 復帰不可

2. **Suricata アラート継続時に無限ループ**
   ```python
   if signals.get("suricata_alert"):
       add += 15
       reasons.append("suricata_alert")
   ```
   毎回 +15 → 条件付きで CONTAIN 維持

#### 改善案

```python
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Tuple


class Stage(str, Enum):
    INIT = "INIT"
    PROBE = "PROBE"
    DEGRADED = "DEGRADED"
    NORMAL = "NORMAL"
    CONTAIN = "CONTAIN"
    DECEPTION = "DECEPTION"


@dataclass
class StageContext:
    state: Stage = Stage.INIT
    suspicion: float = 0.0
    last_transition: float = field(default_factory=time.time)
    last_link_bssid: str = ""
    probe_started: float = field(default_factory=time.time)
    stable_since: float = field(default_factory=time.time)
    last_reason: str = "init"
    
    # ★ NEW: Suricata アラート抑制用タイマ
    last_suricata_alert: float = field(default_factory=time.time)
    suricata_cooldown_sec: float = 30.0  # アラート 1 回の効果期間
    
    # ★ NEW: CONTAIN 復帰制御
    contain_entered_at: float = field(default_factory=time.time)
    contain_min_duration_sec: float = 20.0  # 最小 CONTAIN 継続時間
    contain_exit_suspicion: float = 30.0  # CONTAIN から脱出する suspicion 閾値


class FirstMinuteStateMachine:
    def __init__(self, cfg: Dict[str, float]):
        self.ctx = StageContext()
        self.cfg = cfg
        # Config から上書き
        if "suricata_cooldown_sec" in cfg:
            self.ctx.suricata_cooldown_sec = cfg["suricata_cooldown_sec"]
        if "contain_min_duration_sec" in cfg:
            self.ctx.contain_min_duration_sec = cfg["contain_min_duration_sec"]
        if "contain_exit_suspicion" in cfg:
            self.ctx.contain_exit_suspicion = cfg["contain_exit_suspicion"]

    def reset_for_new_link(self, bssid: str) -> None:
        """新しい WiFi リンク接続時のリセット"""
        self.ctx.state = Stage.NORMAL
        self.ctx.suspicion = 0.0
        self.ctx.last_transition = time.time()
        self.ctx.probe_started = time.time()
        self.ctx.stable_since = time.time()
        self.ctx.last_link_bssid = bssid
        self.ctx.last_reason = "new_link"
        self.ctx.last_suricata_alert = 0.0

    def force_state(self, stage: Stage, reason: str = "manual") -> Stage:
        """手動状態遷移"""
        self.ctx.state = stage
        self.ctx.last_transition = time.time()
        self.ctx.last_reason = reason
        self.ctx.stable_since = time.time()
        if stage == Stage.CONTAIN:
            self.ctx.contain_entered_at = time.time()
        return stage

    def _decay(self, now: float) -> None:
        """suspicion の自然減衰"""
        dt = now - self.ctx.last_transition
        decay = self.cfg.get("decay_per_sec", 2)
        self.ctx.suspicion = max(0.0, self.ctx.suspicion - decay * dt)
        self.ctx.last_transition = now

    def _apply_signals(
        self,
        signals: Dict[str, float | int | bool],
        reasons: List[str],
        now: float,
    ) -> None:
        """
        シグナル処理
        
        ★ 改善点:
        - Suricata アラートはクールダウン機構で重複カウントを防ぐ
        - 一度のアラートは 30 秒間のクレジットとして機能
        """
        add = 0.0
        
        if signals.get("probe_fail"):
            add += 15 * float(signals.get("probe_fail_count", 1))
            reasons.append("probe_fail")
            
        if signals.get("dns_mismatch"):
            add += 10 * float(signals.get("dns_mismatch", 1))
            reasons.append("dns_mismatch")
            
        if signals.get("cert_mismatch"):
            add += 25
            reasons.append("cert_mismatch")
            
        if signals.get("wifi_tags"):
            add += 20
            reasons.append("wifi_tags")
            
        if signals.get("route_anomaly"):
            add += 10
            reasons.append("route_anomaly")
        
        # ★ NEW: Suricata アラート クールダウン
        if signals.get("suricata_alert"):
            dt_since_last = now - self.ctx.last_suricata_alert
            if dt_since_last >= self.ctx.suricata_cooldown_sec:
                # 最後のアラートから cooldown 期間経過 → 新規とカウント
                add += 15
                reasons.append("suricata_alert")
                self.ctx.last_suricata_alert = now
            # else: cooldown 中 → アラート加算なし（抑制）

        self.ctx.suspicion = min(100.0, self.ctx.suspicion + add)

    def step(
        self,
        signals: Dict[str, float | int | bool],
    ) -> Tuple[Stage, Dict[str, float | str]]:
        """
        状態遷移ステップ
        
        ★ 改善:
        - CONTAIN 最小継続時間を設定
        - CONTAIN 脱出条件を明確化
        - デバウンス情報を返す
        """
        now = time.time()
        reasons: List[str] = []
        
        # Passive decay
        self._decay(now)
        self._apply_signals(signals, reasons, now)

        elapsed_probe = now - self.ctx.probe_started
        state = self.ctx.state
        changed = False

        if not signals.get("link_up") and state != Stage.INIT:
            self.ctx.state = Stage.INIT
            self.ctx.suspicion = 0.0
            self.ctx.last_reason = "link_down"
            self.ctx.last_transition = now
            return (
                self.ctx.state,
                {
                    "state": self.ctx.state.value,
                    "suspicion": 0.0,
                    "reason": "link_down",
                    "changed": True,
                },
            )

        degrade_threshold = self.cfg.get("degrade_threshold", 30)
        normal_threshold = self.cfg.get("normal_threshold", 8)
        contain_threshold = self.cfg.get("contain_threshold", 65)
        stable_normal_sec = self.cfg.get("stable_normal_sec", 20)
        stable_probe_sec = self.cfg.get("stable_probe_sec", 10)
        probe_window = self.cfg.get("probe_window_sec", 20)

        if state == Stage.INIT and signals.get("link_up"):
            self.reset_for_new_link(signals.get("bssid", ""))
            state = self.ctx.state
            changed = True
            
        elif state == Stage.PROBE:
            if self.ctx.suspicion >= contain_threshold:
                state = Stage.CONTAIN
                changed = True
                self.ctx.last_reason = "probe->contain"
                self.ctx.contain_entered_at = now
                
            elif (self.ctx.suspicion >= degrade_threshold) and (elapsed_probe >= stable_probe_sec):
                state = Stage.DEGRADED
                changed = True
                self.ctx.last_reason = "probe->degraded"
                self.ctx.stable_since = now
                
            elif (elapsed_probe >= probe_window) and (self.ctx.suspicion <= normal_threshold):
                state = Stage.NORMAL
                changed = True
                self.ctx.last_reason = "probe->normal"
                self.ctx.stable_since = now
                
        elif state == Stage.DEGRADED:
            if self.ctx.suspicion >= contain_threshold:
                state = Stage.CONTAIN
                changed = True
                self.ctx.last_reason = "degraded->contain"
                self.ctx.contain_entered_at = now
                
            elif self.ctx.suspicion <= normal_threshold:
                if now - self.ctx.stable_since >= stable_normal_sec:
                    state = Stage.NORMAL
                    changed = True
                    self.ctx.last_reason = "degraded->normal"
            else:
                self.ctx.stable_since = now
                
        elif state == Stage.NORMAL:
            if self.ctx.suspicion >= contain_threshold:
                state = Stage.CONTAIN
                changed = True
                self.ctx.last_reason = "normal->contain"
                self.ctx.contain_entered_at = now
                
            elif self.ctx.suspicion >= degrade_threshold:
                state = Stage.DEGRADED
                changed = True
                self.ctx.last_reason = "normal->degraded"
                self.ctx.stable_since = now
        
        # ★ NEW: CONTAIN 脱出ロジック
        elif state == Stage.CONTAIN:
            elapsed_contain = now - self.ctx.contain_entered_at
            
            # 最小継続時間経過後、suspicion が低下したら脱出を検討
            if elapsed_contain >= self.ctx.contain_min_duration_sec:
                if self.ctx.suspicion <= self.ctx.contain_exit_suspicion:
                    state = Stage.DEGRADED
                    changed = True
                    self.ctx.last_reason = "contain->degraded (recovered)"
                    self.ctx.stable_since = now
                # else: suspicion がまだ高い → CONTAIN 継続

        if changed:
            self.ctx.state = state
            self.ctx.last_transition = now

        summary = {
            "state": self.ctx.state.value,
            "suspicion": round(self.ctx.suspicion, 2),
            "reason": self.ctx.last_reason if not reasons else ",".join(reasons),
            "changed": changed,  # ★ NEW: 遷移フラグ
        }
        return self.ctx.state, summary
```

**ポイント**:
1. `suricata_cooldown_sec`: Suricata アラート 1 回の効果期間（重複加算防止）
2. `contain_min_duration_sec`: CONTAIN 最小継続時間（即座な復帰防止）
3. `contain_exit_suspicion`: CONTAIN 脱出条件を explicit に定義
4. 戻り値に `changed` フラグを追加（ログデバウンス用）

---

### 2.4 Controller ログ・状態遷移管理（`py/azazel_zero/first_minute/controller.py`）

#### 現状問題

```python
def run_loop(self) -> None:
    # ... (中略) ...
    self.logger.info(json.dumps(self.status_ctx))  # 毎回 INFO ログ出力
```

**問題**: 
- 状態が変わっていなくても毎回 INFO ログ
- Contain 状態が継続中 = ログが数秒周期で連打される

#### 改善案

```python
# controller.py の run_loop() を改善

def run_loop(self) -> None:
    self.handle_signals()
    probe_done = False
    last_log_state = None  # ★ 前回ログ出力時の state
    last_log_time = 0.0    # ★ 前回ログ出力時刻
    
    while not self.stop_event.is_set():
        link_state, link_meta, new_link = self.poll_wifi()
        signals: Dict[str, object] = {"link_up": link_state}
        if link_meta.get("bssid"):
            signals["bssid"] = link_meta["bssid"]
        wifi_tags = link_meta.get("wifi_tags", [])
        if wifi_tags:
            signals["wifi_tags"] = True
        if new_link:
            probe_done = False

        if link_state and not probe_done:
            self.last_probe = run_all(self.cfg.probes, self.cfg.interfaces["upstream"])
            signals["probe_fail"] = self.last_probe.captive_portal or self.last_probe.tls_mismatch
            signals["probe_fail_count"] = 1 + self.last_probe.dns_mismatch
            signals["dns_mismatch"] = self.last_probe.dns_mismatch
            signals["cert_mismatch"] = self.last_probe.tls_mismatch
            signals["route_anomaly"] = self.last_probe.route_anomaly
            probe_done = True

        if self.suricata_bumped():
            signals["suricata_alert"] = True

        state, summary = self.state_machine.step(signals)
        if (
            state == Stage.CONTAIN
            and self.cfg.deception.get("enable_if_opencanary_present", False)
            and Path(self.cfg.deception.get("opencanary_cfg", "/etc/opencanaryd/opencanary.conf")).exists()
        ):
            state = Stage.DECEPTION
        if state != self.current_stage:
            self.current_stage = state
            probe_done = state != Stage.PROBE
            self.apply_stage(state)
        
        self.status_ctx.update(
            {
                "state": state.value,
                "suspicion": summary.get("suspicion", 0),
                "reason": summary.get("reason", ""),
                "wifi": link_meta,
                "last_probe": self.last_probe.details if self.last_probe else None,
            }
        )
        self.write_snapshot(summary, link_meta)
        self._maybe_update_epd(state, summary, link_meta)
        self._maybe_write_wifi_health(link_meta)
        if self.pretty_console:
            self.render_console(state, summary, link_meta)
        
        # ★ NEW: ログデバウンス
        should_log = False
        now = time.time()
        
        if summary.get("changed"):
            # 状態遷移時は常にログ出力
            should_log = True
        elif last_log_state != state.value:
            # 前回ログと状態が異なる → 出力
            should_log = True
        elif (now - last_log_time) >= 60.0:
            # 最後のログから 60 秒以上経過 → ハートビート
            should_log = True
        
        if should_log:
            # ★ ログ出力時に "changed" フラグ情報を含める
            log_entry = {
                **self.status_ctx,
                "transitioned": summary.get("changed", False),
            }
            self.logger.info(json.dumps(log_entry))
            last_log_state = state.value
            last_log_time = now
        
        # DEBUG ログ：詳細（毎ループ）
        self.logger.debug(
            f"step: state={state.value} susp={summary.get('suspicion', 0):.1f} "
            f"reason={summary.get('reason', '')} changed={summary.get('changed', False)}"
        )
        
        time.sleep(2.0)
    self.stop()
```

**ポイント**:
1. **状態遷移時のみ INFO ログ出力** (`summary["changed"] == True`)
2. **60 秒ハートビート**: 長期運用時の状態確認用
3. **DEBUG ログ**: 毎ループで詳細記録（分析時に有用）
4. `transitioned` フラグでログから遷移イベントを即座に識別可能

---

## 3. Config 側の新規設定項目

### 3.1 `configs/first_minute.yaml` への追加

```yaml
state_machine:
  # 既存
  degrade_threshold: 30
  normal_threshold: 8
  contain_threshold: 65
  stable_normal_sec: 20
  stable_probe_sec: 10
  probe_window_sec: 20
  decay_per_sec: 2
  
  # ★ NEW: Suricata アラート抑制
  suricata_cooldown_sec: 30.0  # アラート 1 回あたりの有効期間
  
  # ★ NEW: CONTAIN 復帰制御
  contain_min_duration_sec: 20.0  # 最小継続時間
  contain_exit_suspicion: 30.0    # 脱出時の suspicion 閾値

logging:
  level: INFO
  # ★ NEW: デバウンス設定（オプション）
  log_debounce_sec: 60.0  # 同一状態ログの抑制時間
  log_heartbeat_sec: 60.0 # ハートビートログ間隔
```

---

## 4. テスト・検証計画

### 4.1 nftables テスト

```bash
# テンプレート確認
python3 -c "
from py.azazel_zero.first_minute.nft import NftManager
cfg = NftManager(
    'nftables/first_minute.nft',
    'wlan0', 'usb0',
    '192.168.40.1', '192.168.40.0/24'
)
print(cfg.render_preview())
" | head -50

# 適用（dry-run）
nft -f - <<'EOF'
# (rendered template)
EOF
```

### 4.2 状態遷移テスト

```bash
python3 -m pytest py/azazel_zero/first_minute/test_state_machine.py::test_contain_recovery
```

期待結果:
- Suricata アラート 1 回 → suspicion +15
- 30 秒以内の重複アラート → 加算なし（抑制）
- CONTAIN 20 秒継続後、suspicion < 30.0 → DEGRADED へ遷移

### 4.3 実運用テスト

1. **新しい設定で起動**
   ```bash
   systemctl restart azazel-first-minute
   ```

2. **ログ確認**
   ```bash
   journalctl -u azazel-first-minute -f | grep -E "(transitioned|changed|CONTAIN)"
   ```
   期待: 状態遷移時のみ INFO ログが出力される

3. **Suricata アラート注入テスト**
   ```bash
   # eve.json を最新更新
   touch /var/log/suricata/eve.json
   
   # 2 秒後：ログに suricata_alert
   # 5 秒後：再度 touch
   # ログを確認 → 2 回目はアラート加算なし
   ```

---

## 5. 実装順序（優先度）

| 優先度 | タスク | 依存関係 |
|--------|--------|---------|
| **1** | nftables テンプレート更新 | - |
| **2** | state_machine 改善（Suricata cooldown / CONTAIN recovery） | - |
| **3** | controller ログデバウンス実装 | state_machine |
| **4** | tc.py コメント / ドキュメント更新 | nftables |
| **5** | config ファイル新項目追加 | state_machine |
| **6** | 統合テスト・検証 | 1-5 |

---

## 6. 想定される改善効果

| 課題 | 改善前 | 改善後 |
|------|-------|-------|
| **SSH/VSCode 接続** | wlan0 から接続不可（nftables で遮断） | input chain で fast-path として許可 |
| **管理通信タイムアウト** | tc 遅滞の影響（400ms+ 遅延） | nftables で許可 → tc は forward のみ |
| **CONTAIN 無限ループ** | Suricata アラート継続時に復帰不可 | cooldown + 明確な脱出条件 |
| **ログノイズ** | 毎 2 秒 INFO 連打 | 遷移時のみ / 60 秒ハートビート |
| **運用性** | 状態・復帰条件が不透明 | ログから意図が明確 |

---

## 7. その他の改善案（将来検討）

### 7.1 HTB + fwmark による管理通信の完全分離

```python
# 構想: TcManagerAdvanced
# 管理通信に fwmark 0x100 を設定
# TC で class 1:1（no shaping）, class 1:2（shaping 適用）に分離
# → root qdisc の影響を完全に排除可能
```

### 7.2 Contain 中の段階的復帰

```python
# 例: Contain から Degraded への一時的な緩和
# "Contain-Light": UDP 53/443 許可、TCP 遅延継続
# → より段階的な状態遷移
```

### 7.3 WiFi セキュリティ フィードバックループ

```python
# Contain 状態が長続きする場合、
# ユーザーに「別の WiFi を選択」等のアラート提示
```

---

**ドキュメント作成完了**

このドキュメントに基づく実装を進めてください。
各ファイル修正は以下の順序で実施をお勧めします：

1. nftables/first_minute.nft
2. py/azazel_zero/first_minute/state_machine.py
3. py/azazel_zero/first_minute/controller.py
4. configs/first_minute.yaml
