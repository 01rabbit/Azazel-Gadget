#!/usr/bin/env python3
"""
Textual implementation for Azazel-Zero unified TUI.

This app is intentionally thin and reuses existing backend callbacks from
cli_unified.py for snapshot loading, command dispatch, and optional EPD updates.
"""
from __future__ import annotations

import asyncio
import sys
import time
from typing import Any, Callable, Optional, Tuple

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Header, Static


SnapshotLoader = Callable[[], Any]
ActionSender = Callable[[str], None]
EpdUpdater = Callable[[Any, bool], None]
EpdFingerprint = Callable[[Any], Tuple[str, str, str, Optional[int], str]]


class AzazelTextualApp(App):
    """Manual-refresh monitor app with key bindings compatible with curses UI."""

    TITLE = "Azazel-Zero Textual Monitor"
    SUB_TITLE = "Manual refresh mode"

    CSS = """
    Screen {
        layout: vertical;
    }

    #status-line {
        height: 1;
        color: black;
        background: $accent;
        content-align: left middle;
        padding: 0 1;
    }

    #summary {
        height: 8;
        border: round $accent;
        padding: 0 1;
    }

    #middle {
        height: 12;
    }

    #connection {
        width: 1fr;
        border: round green;
        padding: 0 1;
    }

    #control {
        width: 1fr;
        border: round cyan;
        padding: 0 1;
    }

    #evidence {
        height: 1fr;
        border: round yellow;
        padding: 0 1;
    }

    #flow {
        height: 1;
        background: $panel;
        color: $text;
        content-align: left middle;
        padding: 0 1;
    }

    #actions {
        height: 1;
        background: $boost;
        color: $text;
        content-align: left middle;
        padding: 0 1;
    }

    #details {
        height: 8;
        border: round magenta;
        padding: 0 1;
        display: none;
    }
    """

    BINDINGS = [
        Binding("u", "refresh", "Refresh"),
        Binding("a", "stage_open", "Stage-Open"),
        Binding("r", "reprobe", "Re-Probe"),
        Binding("c", "contain", "Contain"),
        Binding("l", "details", "Details"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(
        self,
        load_snapshot_fn: SnapshotLoader,
        send_command_fn: ActionSender,
        update_epd_fn: EpdUpdater,
        epd_fingerprint_fn: EpdFingerprint,
        unicode_mode: bool,
        enable_epd: bool,
    ) -> None:
        super().__init__()
        self._load_snapshot_fn = load_snapshot_fn
        self._send_command_fn = send_command_fn
        self._update_epd_fn = update_epd_fn
        self._epd_fingerprint_fn = epd_fingerprint_fn
        self._unicode_mode = unicode_mode
        self._enable_epd = enable_epd

        self._snapshot: Any = None
        self._is_loading = False
        self._details_open = False
        self._last_epd_fp: Optional[Tuple[str, str, str, Optional[int], str]] = None
        self._status_message = "Ready"

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("Status: booting...", id="status-line", markup=False)
        yield Static("Loading snapshot...", id="summary", markup=False)
        with Horizontal(id="middle"):
            yield Static("Loading connection...", id="connection", markup=False)
            yield Static("Loading control...", id="control", markup=False)
        yield Static("Loading evidence...", id="evidence", markup=False)
        yield Static("Flow: PROBE -> DEGRADED -> NORMAL -> SAFE", id="flow", markup=False)
        yield Static("[U] Refresh  [A] Stage-Open  [R] Re-Probe  [C] Contain  [L] Details  [Q] Quit", id="actions", markup=False)
        yield Static("Details hidden. Press [L] to toggle.", id="details", markup=False)

    async def on_mount(self) -> None:
        self.set_interval(1.0, self._tick_age_only)
        await self._refresh_snapshot(initial=True)

    def _tick_age_only(self) -> None:
        if self._snapshot is not None:
            self._render_status_line()

    def _safe_get(self, obj: Any, name: str, default: Any) -> Any:
        try:
            return getattr(obj, name, default)
        except Exception:
            return default

    def _live_age(self) -> str:
        ts = self._safe_get(self._snapshot, "snapshot_epoch", 0.0) or 0.0
        if not ts:
            return "00:00:00"
        delta = max(0, int(time.time() - float(ts)))
        return time.strftime("%H:%M:%S", time.gmtime(delta))

    def _render_status_line(self) -> None:
        if self._snapshot is None:
            self.query_one("#status-line", Static).update(Text(f"Status: {self._status_message}"))
            return

        ssid = self._safe_get(self._snapshot, "ssid", "-")
        state = self._safe_get(self._snapshot, "user_state", "CHECKING")
        source = self._safe_get(self._snapshot, "source", "SNAPSHOT")
        risk = self._safe_get(self._snapshot, "risk_score", 0)
        line = (
            f"State={state}  SSID={ssid}  Risk={risk}/100  "
            f"Age={self._live_age()}  View={source}  Status={self._status_message}"
        )
        self.query_one("#status-line", Static).update(Text(line))

    def _state_label(self, state: str) -> str:
        labels = {
            "CHECKING": "CHECKING",
            "SAFE": "SAFE",
            "LIMITED": "LIMITED",
            "CONTAINED": "CONTAINED",
            "DECEPTION": "DECEPTION",
        }
        return labels.get(str(state).upper(), "CHECKING")

    def _state_icon(self, state: str) -> str:
        state = str(state).upper()
        if not self._unicode_mode:
            return {"SAFE": "OK", "LIMITED": "!", "CONTAINED": "X", "DECEPTION": "D"}.get(state, "~")
        return {
            "SAFE": "✅",
            "LIMITED": "⚠️",
            "CONTAINED": "⛔",
            "DECEPTION": "👁",
        }.get(state, "⟳")

    def _threat_bar(self, level: int) -> str:
        level = max(0, min(int(level), 5))
        if self._unicode_mode:
            return "".join("🔴" if i < level else "⚪" for i in range(5))
        return "".join("X" if i < level else "." for i in range(5))

    def _severity_prefix(self, line: str) -> str:
        lowered = line.lower()
        if any(x in lowered for x in ("blocked", "error", "fail", "contain", "anomaly", "hijack")):
            return "🔴" if self._unicode_mode else "X"
        if any(x in lowered for x in ("warning", "suspect", "portal", "dns", "degrade", "limited")):
            return "🟡" if self._unicode_mode else "!"
        if any(x in lowered for x in ("ok", "safe", "normal", "success")):
            return "🟢" if self._unicode_mode else "O"
        return "•"

    def _render_panels(self) -> None:
        if self._snapshot is None:
            return

        snap = self._snapshot
        connection = self._safe_get(snap, "connection", {}) or {}
        monitoring = self._safe_get(snap, "monitoring", {}) or {}
        degrade = self._safe_get(snap, "degrade", {}) or {}
        probe = self._safe_get(snap, "probe", {}) or {}
        dns_stats = self._safe_get(snap, "dns_stats", {}) or {}
        top_blocked = self._safe_get(snap, "top_blocked", []) or []
        evidence = self._safe_get(snap, "evidence", []) or []

        state = self._safe_get(snap, "user_state", "CHECKING")
        state_icon = self._state_icon(state)
        state_label = self._state_label(state)
        threat_level = self._safe_get(snap, "threat_level", 0)
        threat_bar = self._threat_bar(threat_level)
        reasons = " / ".join(self._safe_get(snap, "reasons", []) or ["-"])
        summary = (
            f"{state_icon} {state_label}   Recommendation: {self._safe_get(snap, 'recommendation', '-')}\n"
            f"Reason: {reasons}\n"
            f"Threat: [{threat_bar}] level={threat_level}   "
            f"Risk Score: {self._safe_get(snap, 'risk_score', 0)}/100\n"
            f"Next: {self._safe_get(snap, 'next_action_hint', '-')}\n"
            f"CPU: {self._safe_get(snap, 'cpu_percent', 0.0)}%  "
            f"Mem: {self._safe_get(snap, 'mem_used_mb', 0)}/{self._safe_get(snap, 'mem_total_mb', 0)}MB "
            f"({self._safe_get(snap, 'mem_percent', 0)}%)  Temp: {self._safe_get(snap, 'temp_c', 0.0)}C\n"
            f"Monitoring: Suricata={monitoring.get('suricata', 'UNKNOWN')}  "
            f"OpenCanary={monitoring.get('opencanary', 'UNKNOWN')}  ntfy={monitoring.get('ntfy', 'UNKNOWN')}"
        )
        self.query_one("#summary", Static).update(Text(summary))

        connection_text = (
            "Connection\n"
            f"SSID: {self._safe_get(snap, 'ssid', '-')}\n"
            f"BSSID: {self._safe_get(snap, 'bssid', '-')}\n"
            f"Signal: {self._safe_get(snap, 'signal_dbm', '-')} dBm\n"
            f"Channel: {self._safe_get(snap, 'channel', '-')} "
            f"(congestion={self._safe_get(snap, 'channel_congestion', 'unknown')}, "
            f"APs={self._safe_get(snap, 'channel_ap_count', 0)})\n"
            f"Gateway: {self._safe_get(snap, 'gateway_ip', '-')}\n"
            f"Up/Down IF: {self._safe_get(snap, 'up_if', '-')}/{self._safe_get(snap, 'down_if', '-')}\n"
            f"WiFi: {connection.get('wifi_state', 'UNKNOWN')}  "
            f"NAT: {connection.get('usb_nat', 'UNKNOWN')}  "
            f"Internet: {connection.get('internet_check', 'UNKNOWN')}"
        )
        self.query_one("#connection", Static).update(Text(connection_text))

        control_text = (
            "Control / Safety\n"
            f"QUIC: {self._safe_get(snap, 'quic', 'unknown')}  "
            f"DoH: {self._safe_get(snap, 'doh', 'unknown')}  "
            f"DNS mode: {self._safe_get(snap, 'dns_mode', 'unknown')}\n"
            f"Degrade: on={degrade.get('on', False)} "
            f"rtt={degrade.get('rtt_ms', 0)}ms rate={degrade.get('rate_mbps', 0)}Mbps\n"
            f"Probe: ok={probe.get('tls_ok', 0)}/{probe.get('tls_total', 0)} "
            f"blocked={probe.get('blocked', 0)}\n"
            f"DNS stats: ok={dns_stats.get('ok', 0)} warn={dns_stats.get('anomaly', 0)} "
            f"blocked={dns_stats.get('blocked', 0)} avg={self._safe_get(snap, 'dns_avg_ms', 0.0)}ms\n"
            f"Traffic: down={self._safe_get(snap, 'download_mbps', 0.0):.1f} "
            f"up={self._safe_get(snap, 'upload_mbps', 0.0):.1f} Mbps\n"
            f"Monitoring: IDS={monitoring.get('suricata', 'UNKNOWN')} "
            f"Canary={monitoring.get('opencanary', 'UNKNOWN')} ntfy={monitoring.get('ntfy', 'UNKNOWN')}"
        )
        self.query_one("#control", Static).update(Text(control_text))

        ev_lines = evidence[-12:] if len(evidence) > 12 else evidence
        evidence_text = "Evidence (last entries)\n" + "\n".join(f"{self._severity_prefix(line)} {line}" for line in ev_lines)
        if not ev_lines:
            evidence_text += "\n- (no evidence)"
        self.query_one("#evidence", Static).update(Text(evidence_text))

        flow_text = (
            f"Flow: PROBE -> DEGRADED -> NORMAL -> SAFE"
            f" | state_timeline: {self._safe_get(snap, 'state_timeline', '-')}"
        )
        self.query_one("#flow", Static).update(Text(flow_text))

        if self._details_open:
            blocked_text = ", ".join(f"{d}({c})" for d, c in top_blocked[:5]) if top_blocked else "-"
            details_text = (
                f"Details / Internal\n"
                f"state_name={self._safe_get(snap, 'internal', {}).get('state_name', '-')}\n"
                f"suspicion={self._safe_get(snap, 'internal', {}).get('suspicion', '-')}\n"
                f"decay={self._safe_get(snap, 'internal', {}).get('decay', '-')}\n"
                f"state_timeline={self._safe_get(snap, 'state_timeline', '-')}\n"
                f"top_blocked={blocked_text}\n"
                f"session_uptime={self._safe_get(snap, 'session_uptime', 0)}s\n"
                f"traffic_total={self._safe_get(snap, 'traffic_total_mb', 0.0)}MB "
                f"(down={self._safe_get(snap, 'traffic_download_mb', 0.0)}MB "
                f"up={self._safe_get(snap, 'traffic_upload_mb', 0.0)}MB)"
            )
            self.query_one("#details", Static).update(Text(details_text))

        self._render_status_line()

    async def _refresh_snapshot(self, initial: bool = False) -> None:
        if self._is_loading:
            return
        self._is_loading = True
        self._status_message = "Refreshing..."
        self._render_status_line()
        try:
            snap = await asyncio.to_thread(self._load_snapshot_fn)
        except Exception as exc:
            self._status_message = f"Refresh failed: {exc}"
        else:
            self._snapshot = snap
            self._status_message = "Refresh complete"
            if self._enable_epd:
                try:
                    fp = self._epd_fingerprint_fn(snap)
                    if initial or fp != self._last_epd_fp:
                        await asyncio.to_thread(self._update_epd_fn, snap, self._enable_epd)
                        self._last_epd_fp = fp
                except Exception:
                    self._status_message = "Refresh complete (EPD update skipped)"
        finally:
            self._is_loading = False
            self._render_panels()

    def _append_local_evidence(self, message: str) -> None:
        if self._snapshot is None:
            return
        evidence = self._safe_get(self._snapshot, "evidence", None)
        if isinstance(evidence, list):
            evidence.append(message)
            del evidence[:-30]

    async def _send_action(self, action: str, log_line: str) -> None:
        try:
            await asyncio.to_thread(self._send_command_fn, action)
            self._status_message = f"Action sent: {action}"
            self._append_local_evidence(log_line)
        except Exception as exc:
            self._status_message = f"Action failed: {exc}"
        finally:
            self._render_panels()

    async def action_refresh(self) -> None:
        await self._refresh_snapshot()

    async def action_stage_open(self) -> None:
        await self._send_action("stage_open", "• action: stage-open command sent")

    async def action_reprobe(self) -> None:
        await self._send_action("reprobe", "• action: reprobe command sent")

    async def action_contain(self) -> None:
        await self._send_action("contain", "• action: contain command sent")

    def action_details(self) -> None:
        self._details_open = not self._details_open
        details = self.query_one("#details", Static)
        details.styles.display = "block" if self._details_open else "none"
        self._status_message = "Details shown" if self._details_open else "Details hidden"
        self._render_panels()


def run_textual(
    load_snapshot_fn: SnapshotLoader,
    send_command_fn: ActionSender,
    update_epd_fn: EpdUpdater,
    epd_fingerprint_fn: EpdFingerprint,
    unicode_mode: bool,
    enable_epd: bool,
) -> None:
    app = AzazelTextualApp(
        load_snapshot_fn=load_snapshot_fn,
        send_command_fn=send_command_fn,
        update_epd_fn=update_epd_fn,
        epd_fingerprint_fn=epd_fingerprint_fn,
        unicode_mode=unicode_mode,
        enable_epd=enable_epd,
    )
    app.run()


if __name__ == "__main__":
    print(
        "This module is a backend for cli_unified.\n"
        "Run: python3 py/azazel_zero/cli_unified.py --textual",
        file=sys.stderr,
    )
    sys.exit(2)
