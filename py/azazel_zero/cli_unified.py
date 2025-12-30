#!/usr/bin/env python3
"""
Azazel-Zero full-screen TUI (manual refresh, dark theme, fixed layout).
 - Snapshot JSON is fetched on demand (no auto-refresh).
 - IPC is file-based by default: /run/azazel-zero/ui_snapshot.json and ui_command.json
 - Actions send commands via the command file; controller側で処理することを想定。
 - Unicode が不安定なら ASCII 枠＋アイコンに自動フォールバック (--ascii/--unicodeで強制可)。
"""
from __future__ import annotations

import argparse
import curses
import json
import locale
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

DEFAULT_ROOT = Path(__file__).resolve().parent.parent.parent
SNAPSHOT_PATH = Path("/run/azazel-zero/ui_snapshot.json")
CMD_PATH = Path("/run/azazel-zero/ui_command.json")
FALLBACK_RUN = DEFAULT_ROOT / ".azazel-zero" / "run"
FALLBACK_SNAPSHOT = FALLBACK_RUN / "ui_snapshot.json"
FALLBACK_CMD = FALLBACK_RUN / "ui_command.json"

STATE_MAP = {
    "CHECKING": ("青", "⟳", "~"),
    "SAFE": ("緑", "✓", "OK"),
    "LIMITED": ("黄", "!", "!"),
    "CONTAINED": ("赤", "⛔", "X"),
    "DECEPTION": ("紫", "◉", "O"),
}


@dataclass
class Snapshot:
    now_time: str
    ssid: str
    bssid: str
    channel: str
    signal_dbm: str
    gateway_ip: str
    down_if: str
    down_ip: str
    up_if: str
    user_state: str
    recommendation: str
    reasons: List[str]
    next_action_hint: str
    quic: str
    doh: str
    dns_mode: str
    degrade: Dict[str, object]
    probe: Dict[str, object]
    evidence: List[str]
    internal: Dict[str, object]
    age: str = "00:00:00"


def detect_unicode(force_ascii: bool, force_unicode: bool) -> bool:
    if force_ascii:
        return False
    if force_unicode:
        return True
    lang = (os.environ.get("LANG", "") + os.environ.get("LC_CTYPE", "")).upper()
    return "UTF-8" in lang or "UTF8" in lang


def load_snapshot() -> Snapshot:
    path = SNAPSHOT_PATH if SNAPSHOT_PATH.exists() else FALLBACK_SNAPSHOT
    if not path.exists():
        FALLBACK_RUN.mkdir(parents=True, exist_ok=True)
        sample = default_snapshot()
        path.write_text(json.dumps(sample, ensure_ascii=False), encoding="utf-8")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = default_snapshot()
    # compute age
    age = "00:00:00"
    ts = data.get("snapshot_epoch") or 0
    if ts:
        delta = max(0, int(time.time() - ts))
        age = time.strftime("%H:%M:%S", time.gmtime(delta))
    return Snapshot(
        now_time=data.get("now_time", time.strftime("%H:%M:%S")),
        ssid=data.get("ssid", "-"),
        bssid=data.get("bssid", "-"),
        channel=str(data.get("channel", "-")),
        signal_dbm=str(data.get("signal_dbm", "-")),
        gateway_ip=data.get("gateway_ip", "-"),
        down_if=data.get("down_if", "-"),
        down_ip=data.get("down_ip", "-"),
        up_if=data.get("up_if", "-"),
        user_state=data.get("user_state", "CHECKING"),
        recommendation=data.get("recommendation", "確認中"),
        reasons=data.get("reasons", [])[:3],
        next_action_hint=data.get("next_action_hint", ""),
        quic=data.get("quic", "unknown"),
        doh=data.get("doh", "unknown"),
        dns_mode=data.get("dns_mode", "unknown"),
        degrade=data.get("degrade", {"on": False, "rtt_ms": 0, "rate_mbps": 0}),
        probe=data.get("probe", {"tls_ok": 0, "tls_total": 0, "blocked": 0}),
        evidence=data.get("evidence", [])[-6:],  # oldest→newest想定
        internal=data.get("internal", {}),
        age=age,
    )


def default_snapshot() -> Dict[str, object]:
    return {
        "now_time": time.strftime("%H:%M:%S"),
        "ssid": "unknown",
        "bssid": "-",
        "channel": "-",
        "signal_dbm": "-",
        "gateway_ip": "-",
        "down_if": "usb0",
        "down_ip": "-",
        "up_if": "wlan0",
        "user_state": "CHECKING",
        "recommendation": "確認中",
        "reasons": ["情報収集中"],
        "next_action_hint": "再評価を待機",
        "quic": "blocked",
        "doh": "blocked",
        "dns_mode": "forced via Azazel DNS",
        "degrade": {"on": True, "rtt_ms": 180, "rate_mbps": 2.0},
        "probe": {"tls_ok": 2, "tls_total": 3, "blocked": 1},
        "evidence": ["waiting for snapshot"],
        "internal": {"state_name": "PROBE", "suspicion": 0, "decay": 0},
        "snapshot_epoch": time.time(),
    }


def send_command(action: str) -> None:
    path = CMD_PATH if CMD_PATH.exists() or CMD_PATH.parent.exists() else FALLBACK_CMD
    path.parent.mkdir(parents=True, exist_ok=True)
    cmd = {"ts": time.time(), "action": action}
    try:
        path.write_text(json.dumps(cmd), encoding="utf-8")
    except Exception:
        pass


def color_for_state(user_state: str, unicode_mode: bool) -> Tuple[int, str]:
    icon = "~"
    ascii_icon = "~"
    color = curses.COLOR_CYAN
    mapping = STATE_MAP.get(user_state.upper(), STATE_MAP["CHECKING"])
    icon = mapping[1] if unicode_mode else mapping[2]
    if user_state.upper() == "SAFE":
        color = curses.COLOR_GREEN
    elif user_state.upper() == "LIMITED":
        color = curses.COLOR_YELLOW
    elif user_state.upper() == "CONTAINED":
        color = curses.COLOR_RED
    elif user_state.upper() == "DECEPTION":
        color = curses.COLOR_MAGENTA
    else:
        color = curses.COLOR_CYAN
    return color, icon


def draw_box(win, y, x, h, w, ascii_mode: bool):
    if ascii_mode:
        tl, tr, bl, br, hz, vt = "+", "+", "+", "+", "-", "|"
    else:
        tl, tr, bl, br, hz, vt = "┌", "┐", "└", "┘", "─", "│"
    win.addstr(y, x, tl + hz * (w - 2) + tr)
    for i in range(1, h - 1):
        win.addstr(y + i, x, vt + " " * (w - 2) + vt)
    win.addstr(y + h - 1, x, bl + hz * (w - 2) + br)


def wrap_text(text: str, width: int) -> List[str]:
    words = text.split()
    lines: List[str] = []
    cur = ""
    for w in words:
        if len(cur) + len(w) + 1 > width:
            lines.append(cur.rstrip())
            cur = w + " "
        else:
            cur += w + " "
    if cur:
        lines.append(cur.rstrip())
    return lines or [""]


def render(stdscr, snap: Snapshot, unicode_mode: bool):
    stdscr.erase()
    h, w = stdscr.getmaxyx()
    min_w, min_h = 100, 30
    compact = w < min_w or h < min_h

    if h < 20 or w < 80:
        msg = "Terminal too small (min 80x20). Resize and press U to refresh."
        stdscr.addnstr(0, 0, msg[: w - 1], w - 1, curses.color_pair(2))
        stdscr.refresh()
        return

    # Colors
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_GREEN, -1)
    curses.init_pair(2, curses.COLOR_RED, -1)
    curses.init_pair(3, curses.COLOR_CYAN, -1)
    curses.init_pair(4, curses.COLOR_YELLOW, -1)
    curses.init_pair(5, curses.COLOR_MAGENTA, -1)
    curses.init_pair(6, curses.COLOR_WHITE, -1)
    curses.init_pair(7, curses.COLOR_BLACK, -1)

    # Status bar
    bar = (
        f"Azazel-Zero  "
        f"{'⌁' if unicode_mode else 'WiFi'} SSID: {snap.ssid}  "
        f"{'⇄' if unicode_mode else 'Down:'} Down: {snap.down_if}({snap.down_ip})  "
        f"{'⎈' if unicode_mode else 'Up:'} Up: {snap.up_if}  "
        f"Time: {snap.now_time}"
    )
    stdscr.addnstr(0, 0, bar[: w - 1], w - 1, curses.color_pair(6))

    # View line
    view = f"View: SNAPSHOT (manual refresh)  Last Refresh: {snap.now_time}  Age: {snap.age}   Theme: Dark"
    stdscr.addnstr(1, 0, view[: w - 1], w - 1, curses.color_pair(6))

    # Conclusion card
    card_w = w - 2
    card_h = 5
    card_y = 3
    draw_box(stdscr, card_y, 0, card_h, card_w, not unicode_mode)
    state_color, state_icon = color_for_state(snap.user_state, unicode_mode)
    badge = f"[ {state_icon} " + {
        "CHECKING": "確認中",
        "SAFE": "安全",
        "LIMITED": "制限中",
        "CONTAINED": "隔離",
        "DECEPTION": "観測誘導",
    }.get(snap.user_state.upper(), "確認中") + " ]"
    stdscr.addnstr(card_y + 1, 2, f"{badge}  推奨：{snap.recommendation}"[: card_w - 4], curses.color_pair(state_color))
    reasons = "理由：" + " / ".join(snap.reasons or ["-"])
    stdscr.addnstr(card_y + 2, 2, reasons[: card_w - 4], curses.color_pair(6))
    next_line = "次：" + (snap.next_action_hint or "再評価を待機")
    stdscr.addnstr(card_y + 3, 2, next_line[: card_w - 4], curses.color_pair(6))

    # Middle panes
    mid_y = card_y + card_h + 1
    pane_h = 8 if not compact else 5
    pane_w = (w - 3) // 2
    # Left: Connection
    draw_box(stdscr, mid_y, 0, pane_h, pane_w, not unicode_mode)
    stdscr.addnstr(mid_y, 2, "Connection", curses.color_pair(3))
    conn_lines = [
        f"BSSID: {snap.bssid}",
        f"Channel: {snap.channel}   Signal: {snap.signal_dbm} dBm",
        f"Gateway: {snap.gateway_ip}",
        f"Captive Portal: {'suspected' if 'portal' in ' '.join(snap.reasons).lower() else 'none'}",
    ]
    for i, ln in enumerate(conn_lines[: pane_h - 2]):
        stdscr.addnstr(mid_y + 1 + i, 2, ln[: pane_w - 4], curses.color_pair(6))
    # Right: Control/Safety
    draw_box(stdscr, mid_y, pane_w + 1, pane_h, pane_w, not unicode_mode)
    stdscr.addnstr(mid_y, pane_w + 3, "Control / Safety", curses.color_pair(3))
    degrade = snap.degrade or {}
    probe = snap.probe or {}
    deg_txt = "off"
    if degrade.get("on"):
        deg_txt = f"RTT +{degrade.get('rtt_ms',0)}ms, Rate {degrade.get('rate_mbps',0)}Mbps"
    ctl_lines = [
        f"QUIC(UDP/443): {snap.quic}",
        f"DoH: {snap.doh}",
        f"DNS: {snap.dns_mode}",
        f"Degrade: {deg_txt}",
        f"Probe: TLS {probe.get('tls_ok',0)}/{probe.get('tls_total',0)} OK, {probe.get('blocked',0)} blocked",
    ]
    for i, ln in enumerate(ctl_lines[: pane_h - 2]):
        stdscr.addnstr(mid_y + 1 + i, pane_w + 3, ln[: pane_w - 4], curses.color_pair(6))

    # Evidence
    ev_y = mid_y + pane_h + 1
    available = h - ev_y - 3
    if available < 3:
        available = 3
    ev_h = min(max(5, available), h - ev_y - 1)
    draw_box(stdscr, ev_y, 0, ev_h, w, not unicode_mode)
    stdscr.addnstr(ev_y, 2, "Evidence (last 90s)", curses.color_pair(3))
    ev_lines = snap.evidence[-(ev_h - 3) :] if not compact else snap.evidence[-3:]
    for i, ev in enumerate(ev_lines):
        color = curses.color_pair(4 if "portal" in ev.lower() or "dns" in ev.lower() else 6)
        stdscr.addnstr(ev_y + 1 + i, 2, ev[: w - 4], color)
    # decision line
    dec = snap.internal or {}
    decision = f"↳ decision: state={dec.get('state_name','-')} suspicion={dec.get('suspicion','-')} decay={dec.get('decay','-')}"
    stdscr.addnstr(ev_y + ev_h - 2, 2, decision[: w - 4], curses.color_pair(6))

    # Actions + Hint
    actions = "[U] Refresh  [A] Stage-Open  [R] Re-Probe  [C] Contain  [L] Details  [Q] Quit"
    hint = "Hint: この画面は自動更新しません。必要時に [U] で更新してください。"
    stdscr.addnstr(h - 2, 0, actions[: w - 1], curses.color_pair(6))
    stdscr.addnstr(h - 1, 0, hint[: w - 1], curses.color_pair(6))
    stdscr.refresh()


def details_view(stdscr, snap: Snapshot, unicode_mode: bool):
    stdscr.erase()
    h, w = stdscr.getmaxyx()
    stdscr.addnstr(0, 0, "Details (B=Back)", w - 1, curses.A_BOLD)
    # logs
    logs = snap.evidence[-30:]
    for i, ln in enumerate(logs[: h - 6]):
        stdscr.addnstr(1 + i, 0, ln[: w - 1], curses.color_pair(6))
    cur = snap.internal or {}
    info = [
        f"State: {cur.get('state_name','-')}",
        f"Suspicion: {cur.get('suspicion','-')}",
        f"Decay: {cur.get('decay','-')}",
        f"Rules: QUIC={snap.quic} DoH={snap.doh} DNS={snap.dns_mode}",
    ]
    base_y = h - 4
    for i, ln in enumerate(info):
        stdscr.addnstr(base_y + i, 0, ln[: w - 1], curses.color_pair(6))
    stdscr.refresh()
    while True:
        ch = stdscr.getch()
        if ch in (ord("b"), ord("B")):
            break


def main():
    locale.setlocale(locale.LC_ALL, "")
    parser = argparse.ArgumentParser(description="Azazel-Zero manual-refresh TUI")
    parser.add_argument("--ascii", action="store_true", help="Force ASCII fallback")
    parser.add_argument("--unicode", action="store_true", help="Force Unicode box/icons")
    args = parser.parse_args()

    unicode_mode = detect_unicode(args.ascii, args.unicode)
    snap = load_snapshot()

    def _loop(stdscr):
        nonlocal snap
        while True:
            render(stdscr, snap, unicode_mode)
            ch = stdscr.getch()
            if ch in (ord("q"), ord("Q")):
                break
            elif ch in (ord("u"), ord("U")):
                snap = load_snapshot()
            elif ch in (ord("a"), ord("A")):
                send_command("stage_open")
                snap.evidence.append("• action: stage-open command sent")
            elif ch in (ord("r"), ord("R")):
                send_command("reprobe")
                snap.evidence.append("• action: reprobe command sent")
            elif ch in (ord("c"), ord("C")):
                send_command("contain")
                snap.evidence.append("• action: contain command sent")
            elif ch in (ord("l"), ord("L")):
                details_view(stdscr, snap, unicode_mode)
            snap = snap  # no-op to keep reference

    curses.wrapper(_loop)


if __name__ == "__main__":
    main()
