from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


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
        # デフォルトは開放 (NORMAL) とし、検知時にのみ縮退させる
        self.ctx.state = Stage.NORMAL
        self.ctx.suspicion = 0.0
        self.ctx.last_transition = time.time()
        self.ctx.probe_started = time.time()
        self.ctx.stable_since = time.time()
        self.ctx.last_link_bssid = bssid
        self.ctx.last_reason = "new_link"
        self.ctx.last_suricata_alert = 0.0

    def force_state(self, stage: Stage, reason: str = "manual") -> Stage:
        self.ctx.state = stage
        self.ctx.last_transition = time.time()
        self.ctx.last_reason = reason
        self.ctx.stable_since = time.time()
        if stage == Stage.CONTAIN:
            self.ctx.contain_entered_at = time.time()
        return stage

    def _decay(self, now: float) -> None:
        # ★ BUG FIX: decay should NOT update last_transition
        # last_transition is set only on state changes, not on every step
        if self.ctx.state == Stage.INIT:
            return  # INIT では decay しない
        
        # Calculate elapsed time since last_transition (state change)
        dt = now - self.ctx.last_transition
        decay_rate = self.cfg.get("decay_per_sec", 2)
        
        # Apply decay
        self.ctx.suspicion = max(0.0, self.ctx.suspicion - decay_rate * dt)
        
        # ★ FIX: Do NOT update last_transition here
        # This stays tied to the state change timestamp, not the current step

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

    def step(self, signals: Dict[str, float | int | bool], now: Optional[float] = None) -> Tuple[Stage, Dict[str, float | str]]:
        """
        状態遷移ステップ
        
        ★ 改善:
        - CONTAIN 最小継続時間を設定
        - CONTAIN 脱出条件を明確化
        - デバウンス情報を返す
        
        Args:
            signals: 入力シグナル辞書
            now: テスト用の現在時刻（デフォルト: time.time()）
        """
        if now is None:
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
            return self.ctx.state, {"state": self.ctx.state.value, "suspicion": 0.0, "reason": "link_down", "changed": True}

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
                    # ★ FIX: Reset Suricata cooldown on exit so new alerts can trigger
                    self.ctx.last_suricata_alert = 0.0
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
