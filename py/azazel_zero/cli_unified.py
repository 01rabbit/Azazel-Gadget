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
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

DEFAULT_ROOT = Path(__file__).resolve().parent.parent.parent
SNAPSHOT_PATH = Path("/run/azazel-zero/ui_snapshot.json")
CMD_PATH = Path("/run/azazel-zero/ui_command.json")
FALLBACK_RUN = DEFAULT_ROOT / ".azazel-zero" / "run"
FALLBACK_SNAPSHOT = FALLBACK_RUN / "ui_snapshot.json"
FALLBACK_CMD = FALLBACK_RUN / "ui_command.json"
LOG_PATH = Path("/var/log/azazel-zero/first_minute.log")
FALLBACK_LOG = DEFAULT_ROOT / ".azazel-zero" / "log" / "first_minute.log"

STATE_MAP = {
    "CHECKING": ("青", "⟳", "~"),
    "SAFE": ("緑", "✅", "OK"),
    "LIMITED": ("黄", "⚠️", "!"),
    "CONTAINED": ("赤", "⛔", "X"),
    "DECEPTION": ("紫", "👁", "O"),
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
    snapshot_epoch: float = 0.0
    source: str = "SNAPSHOT"
    dns_stats: Dict[str, int] = None  # {"ok": 45, "anomaly": 3, "blocked": 2}
    threat_level: int = 0  # 0-5 scale
    bssid_vendor: str = "-"  # AP vendor info
    battery_pct: int = -1  # -1 = unknown
    channel_congestion: str = "unknown"  # none, low, medium, high, critical
    channel_ap_count: int = 0  # 周囲のAP数
    recommended_channel: int = -1  # 推奨チャンネル
    cpu_percent: float = 0.0  # CPU使用率
    mem_percent: int = 0  # メモリ使用率
    mem_used_mb: int = 0  # 使用メモリ
    mem_total_mb: int = 0  # 総メモリ
    temp_c: float = 0.0  # CPU温度
    download_mbps: float = 0.0  # ダウンロード速度
    upload_mbps: float = 0.0  # アップロード速度
    session_uptime: int = 0  # WiFi接続時間（秒）
    suricata_critical: int = 0  # Suricata重大アラート
    suricata_warning: int = 0  # Suricata警告
    suricata_info: int = 0  # Suricata情報
    packet_loss_percent: float = 0.0  # パケットロス率
    latency_avg_ms: float = 0.0  # 平均レイテンシ
    latency_trend: List[float] = None  # レイテンシ推移
    dns_avg_ms: float = 0.0  # DNS平均応答時間
    dns_cache_hit_rate: int = 0  # DNSキャッシュヒット率
    dns_timeouts: int = 0  # DNSタイムアウト数
    traffic_total_mb: float = 0.0  # 累計トラフィック
    traffic_download_mb: float = 0.0  # 累計ダウンロード
    traffic_upload_mb: float = 0.0  # 累計アップロード
    traffic_packets: int = 0  # 累計パケット数
    state_timeline: str = "-"  # 状態遷移タイムライン
    top_blocked: List[Tuple[str, int]] = None  # ブロックトップ5
    risk_score: int = 0  # リスクスコア 0-100（優先度：低）

    def __post_init__(self):
        if self.dns_stats is None:
            self.dns_stats = {"ok": 0, "anomaly": 0, "blocked": 0}
        if self.latency_trend is None:
            self.latency_trend = []
        if self.top_blocked is None:
            self.top_blocked = []


def detect_unicode(force_ascii: bool, force_unicode: bool) -> bool:
    if force_ascii:
        return False
    if force_unicode:
        return True
    lang = (os.environ.get("LANG", "") + os.environ.get("LC_CTYPE", "")).upper()
    return "UTF-8" in lang or "UTF8" in lang


def build_snapshot(data: Dict[str, object], source: str = "SNAPSHOT") -> Snapshot:
    """Normalize dict -> Snapshot dataclass."""
    age = "00:00:00"
    ts = data.get("snapshot_epoch") or 0
    if ts:
        delta = max(0, int(time.time() - ts))
        age = time.strftime("%H:%M:%S", time.gmtime(delta))
    
    # 脅威レベル計算 (0-5)
    suspicion = data.get("internal", {}).get("suspicion", 0) if isinstance(data.get("internal"), dict) else 0
    threat_level = min(5, max(0, int(suspicion / 20)))  # 0-100 -> 0-5
    
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
        snapshot_epoch=float(ts) if ts else 0.0,
        source=source,
        dns_stats=data.get("dns_stats", {"ok": 0, "anomaly": 0, "blocked": 0}),
        threat_level=threat_level,
        bssid_vendor="-",
        battery_pct=data.get("battery_pct", -1),
        channel_congestion=data.get("channel_congestion", "unknown"),
        channel_ap_count=data.get("channel_ap_count", 0),
        recommended_channel=data.get("recommended_channel", -1),
        cpu_percent=data.get("cpu_percent", 0.0),
        mem_percent=data.get("mem_percent", 0),
        mem_used_mb=data.get("mem_used_mb", 0),
        mem_total_mb=data.get("mem_total_mb", 512),
        temp_c=data.get("temp_c", 0.0),
        download_mbps=data.get("download_mbps", 0.0),
        upload_mbps=data.get("upload_mbps", 0.0),
        session_uptime=data.get("session_uptime", 0),
        suricata_critical=data.get("suricata_critical", 0),
        suricata_warning=data.get("suricata_warning", 0),
        suricata_info=data.get("suricata_info", 0),
        packet_loss_percent=data.get("packet_loss_percent", 0.0),
        latency_avg_ms=data.get("latency_avg_ms", 0.0),
        latency_trend=data.get("latency_trend", []),
        dns_avg_ms=data.get("dns_avg_ms", 0.0),
        dns_cache_hit_rate=data.get("dns_cache_hit_rate", 0),
        dns_timeouts=data.get("dns_timeouts", 0),
        traffic_total_mb=data.get("traffic_total_mb", 0.0),
        traffic_download_mb=data.get("traffic_download_mb", 0.0),
        traffic_upload_mb=data.get("traffic_upload_mb", 0.0),
        traffic_packets=data.get("traffic_packets", 0),
        state_timeline=data.get("state_timeline", "-"),
        top_blocked=data.get("top_blocked", []),
        risk_score=data.get("risk_score", 0),
    )


def _fill_iface_defaults(data: Dict[str, object]) -> None:
    """Ensure interface fields are present even when rebuilt from logs."""
    defaults = {"down_if": "usb0", "down_ip": "10.55.0.10", "up_if": "wlan0"}
    for key, val in defaults.items():
        cur = str(data.get(key, "-"))
        if (not cur) or cur == "-":
            data[key] = val


def _user_state_from_stage_name(stage_name: str) -> str:
    name = stage_name.upper()
    if name in ("PROBE", "INIT"):
        return "CHECKING"
    if name == "NORMAL":
        return "SAFE"
    if name == "DEGRADED":
        return "LIMITED"
    if name == "CONTAIN":
        return "CONTAINED"
    if name == "DECEPTION":
        return "DECEPTION"
    return "CHECKING"


def export_epd_snapshot(snap: Snapshot) -> None:
    """
    EPD表示用にスナップショットをエクスポート
    TUIで計算済みのrisk_scoreやrecommendationをEPDと共有して重複計算を避ける
    """
    try:
        from dataclasses import asdict
        
        # EPDに必要な最小限のフィールドのみをエクスポート
        epd_data = {
            "risk_score": snap.risk_score,
            "recommendation": snap.recommendation,
            "user_state": snap.user_state,
            "threat_level": snap.threat_level,
            "signal_dbm": str(snap.signal_dbm),
            "ssid": snap.ssid,
            "suricata_critical": snap.suricata_critical,
            "suricata_warning": snap.suricata_warning,
            "cpu_percent": snap.cpu_percent,
            "temp_c": snap.temp_c,
            "session_uptime": snap.session_uptime,
            "download_mbps": snap.download_mbps,
            "upload_mbps": snap.upload_mbps,
            "packet_loss_percent": snap.packet_loss_percent,
            "dns_avg_ms": snap.dns_avg_ms,
            "now_time": snap.now_time,
        }
        
        # /tmpに保存（権限問題を回避）
        epd_path = Path("/tmp/epd_snapshot.json")
        epd_path.write_text(json.dumps(epd_data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        # エクスポート失敗してもTUI動作に影響しない
        pass


def _parse_log_ts(line: str) -> float:
    """Parse leading timestamp from a log line into epoch seconds."""
    try:
        parts = line.split(None, 2)
        if len(parts) >= 2:
            ts_part = f"{parts[0]} {parts[1]}"
            for fmt in ("%Y-%m-%d %H:%M:%S,%f", "%Y-%m-%d %H:%M:%S"):
                try:
                    return time.mktime(time.strptime(ts_part, fmt))
                except ValueError:
                    continue
    except Exception:
        return 0.0
    return 0.0


def load_snapshot_from_log() -> Optional[Snapshot]:
    """Fallback: rebuild snapshot from JSON log (first_minute.log)."""
    for path in (LOG_PATH, FALLBACK_LOG):
        if not path.exists():
            continue
        try:
            lines = deque(path.open(encoding="utf-8"), maxlen=200)
        except Exception:
            continue
        for line in reversed(lines):
            idx = line.find("{")
            if idx == -1:
                continue
            try:
                payload = json.loads(line[idx:])
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            
            # ログのタイムスタンプを確認
            snap_ts = _parse_log_ts(line) or time.time()
            age_seconds = time.time() - snap_ts
            
            # 1分以上古いログエントリは無視（常に最新を求める）
            if age_seconds > 60:
                continue
            
            stage = str(payload.get("state", "")).upper()
            link_meta = payload.get("wifi") or {}
            link = link_meta.get("link", {}) if isinstance(link_meta, dict) else {}
            probe_last = payload.get("last_probe") or {}
            tls_mismatch = bool(probe_last.get("tls_mismatch")) if isinstance(probe_last, dict) else False
            probe = {
                "tls_ok": 0 if not probe_last else int(not tls_mismatch),
                "tls_total": 1 if probe_last else 0,
                "blocked": 1 if (probe_last and tls_mismatch) else 0,
            }
            degrade_on = stage in ("PROBE", "DEGRADED")
            data = {
                "now_time": time.strftime("%H:%M:%S", time.localtime(snap_ts)),
                "snapshot_epoch": snap_ts,
                "ssid": link.get("ssid", "-"),
                "bssid": link.get("bssid", "-"),
                "channel": link.get("channel", "-"),
                "signal_dbm": link.get("signal", "-"),
                "gateway_ip": link.get("gateway", "-"),
                "down_if": "-",
                "down_ip": "-",
                "up_if": "-",
                "user_state": _user_state_from_stage_name(stage),
                "recommendation": payload.get("reason", "確認中"),
                "reasons": [payload.get("reason", "確認中")],
                "next_action_hint": "ログから再構成",
                "quic": "blocked" if stage in ("PROBE", "DEGRADED", "CONTAIN") else "allowed",
                "doh": "blocked",
                "dns_mode": "forced via Azazel DNS",
                "degrade": {
                    "on": degrade_on,
                    "rtt_ms": 180 if degrade_on else 0,
                    "rate_mbps": 2.0 if stage == "DEGRADED" else 1.0 if stage == "PROBE" else 0,
                },
                "probe": probe,
                "evidence": [f"state={stage} suspicion={payload.get('suspicion', 0)}"],
                "internal": {
                    "state_name": stage or "UNKNOWN",
                    "suspicion": payload.get("suspicion", 0),
                    "decay": "-",
                },
            }
            _fill_iface_defaults(data)
            return build_snapshot(data, source="LOG")
    return None


# セッション開始時刻（グローバル）
_session_start_time = time.time()

# スループット計算用の前回統計（優先度：低）
_last_net_stats = {}
_last_net_time = time.time()


def calculate_risk_score(snap: Snapshot) -> int:
    """
    リスクスコアを0-100で算出（優先度：低）
    高いほど危険
    """
    score = 0
    
    # 1. Threat Level (0-30点)
    # threat_levelは0-5の整数なので、直接計算
    if isinstance(snap.threat_level, int):
        score += min(snap.threat_level * 6, 30)  # 0-5を0-30にマッピング
    else:
        threat_map = {"low": 0, "medium": 10, "high": 20, "critical": 30}
        score += threat_map.get(str(snap.threat_level).lower(), 0)
    
    # 2. Suricata Alerts (0-25点)
    score += min(snap.suricata_critical * 10, 25)  # critical 1件=10点
    score += min(snap.suricata_warning * 3, 10)  # warning 1件=3点
    
    # 3. WiFi Signal Strength (0-15点)
    if isinstance(snap.signal_dbm, (int, float)):
        if snap.signal_dbm < -80:  # 弱い
            score += 15
        elif snap.signal_dbm < -70:
            score += 10
        elif snap.signal_dbm < -60:
            score += 5
    
    # 4. User State (0-20点)
    state_risk = {
        "SAFE": 0,
        "NORMAL": 5,
        "LIMITED": 10,
        "DEGRADED": 12,
        "DECEPTION": 15,
        "CONTAINED": 20,
    }
    score += state_risk.get(snap.user_state.upper(), 10)
    
    # 5. DNS Blocked (0-10点)
    dns_blocked = snap.dns_stats.get("blocked", 0)
    score += min(dns_blocked * 2, 10)
    
    return min(score, 100)  # 最大100


def generate_recommendation(snap: Snapshot) -> str:
    """
    現在の状態に応じた推奨アクションを生成（優先度：低）
    """
    recommendations = []
    
    # 1. チャンネル混雑度チェック
    if snap.channel_congestion in ["high", "critical"]:
        if snap.recommended_channel > 0:
            recommendations.append(f"📡 Ch{snap.recommended_channel}に変更推奨")
        else:
            recommendations.append("📡 混雑低チャンネルへ変更推奨")
    
    # 2. WiFi信号強度
    if isinstance(snap.signal_dbm, (int, float)) and snap.signal_dbm < -75:
        recommendations.append("📶 APに近づくか再接続")
    
    # 3. リスクスコア
    if snap.risk_score >= 70:
        recommendations.append("⚠️ 危険なネットワーク！切断推奨")
    elif snap.risk_score >= 50:
        recommendations.append("🛡️ Containモードへ移行検討")
    
    # 4. Suricataアラート
    if snap.suricata_critical > 0:
        recommendations.append(f"🚨 {snap.suricata_critical}件の重大脅威検知")
    
    # 5. DNSブロック
    dns_blocked = snap.dns_stats.get("blocked", 0)
    if dns_blocked >= 10:
        recommendations.append(f"🚫 {dns_blocked}件DNSブロック！確認推奨")
    
    # 6. バッテリー
    if 0 <= snap.battery_pct < 20:
        recommendations.append("🔋 バッテリー低下！充電推奨")
    
    # 7. 温度
    if snap.temp_c >= 70:
        recommendations.append("🌡️ 高温警告！冷却推奨")
    
    # 8. 問題なし
    if not recommendations and snap.user_state.upper() == "SAFE":
        recommendations.append("✅ ネットワークは安全です")
    
    return " | ".join(recommendations[:2]) if recommendations else "✅ 問題なし"


def load_snapshot() -> Snapshot:
    path = SNAPSHOT_PATH if SNAPSHOT_PATH.exists() else FALLBACK_SNAPSHOT
    data: Dict[str, object]
    snap_from_log = load_snapshot_from_log()
    if snap_from_log:
        snap = snap_from_log
    elif path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            snap = build_snapshot(data, source="SNAPSHOT")
        except Exception:
            FALLBACK_RUN.mkdir(parents=True, exist_ok=True)
            sample = default_snapshot()
            try:
                path.write_text(json.dumps(sample, ensure_ascii=False), encoding="utf-8")
            except Exception:
                pass
            snap = build_snapshot(sample, source="SAMPLE")
    else:
        FALLBACK_RUN.mkdir(parents=True, exist_ok=True)
        sample = default_snapshot()
        try:
            path.write_text(json.dumps(sample, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
        snap = build_snapshot(sample, source="SAMPLE")
    
    # WiFiチャンネルスキャンを実行（上りインターフェースを使用）
    try:
        # 相対インポートまたは直接インポートを試行
        try:
            from .sensors.wifi_channel_scanner import scan_wifi_channels
        except ImportError:
            import sys
            from pathlib import Path
            sensors_path = Path(__file__).parent / "sensors"
            if str(sensors_path) not in sys.path:
                sys.path.insert(0, str(sensors_path.parent))
            from sensors.wifi_channel_scanner import scan_wifi_channels
        
        scan_result = scan_wifi_channels(snap.up_if)
        if scan_result.get("scan_success"):
            snap.channel_congestion = scan_result.get("congestion_level", "unknown")
            snap.channel_ap_count = scan_result.get("ap_count", 0)
            snap.recommended_channel = scan_result.get("recommended_channel", -1)
            # デバッグ情報をevidenceに追加
            snap.evidence.append(f"🔍 Scan: {snap.channel_ap_count} APs, {snap.channel_congestion}")
        else:
            # スキャン失敗時の情報を追加
            error_msg = scan_result.get("error", "scan failed")
            snap.evidence.append(f"⚠️ Scan failed: {error_msg}")
    except Exception as e:
        # スキャン失敗時はデフォルト値を保持し、エラーをevidenceに記録
        snap.evidence.append(f"⚠️ Scan error: {str(e)}")
    
    # システムメトリクスを収集
    try:
        try:
            from .sensors.system_metrics import collect_all_metrics
        except ImportError:
            import sys
            from pathlib import Path
            sensors_path = Path(__file__).parent / "sensors"
            if str(sensors_path) not in sys.path:
                sys.path.insert(0, str(sensors_path.parent))
            from sensors.system_metrics import collect_all_metrics
        
        metrics = collect_all_metrics(snap.up_if, snap.down_if)
        snap.cpu_percent = metrics.get("cpu_percent", 0.0)
        mem = metrics.get("memory", {})
        snap.mem_percent = mem.get("percent", 0)
        snap.mem_used_mb = mem.get("used_mb", 0)
        snap.mem_total_mb = mem.get("total_mb", 512)
        snap.temp_c = metrics.get("temperature_c", 0.0) or 0.0
        
        # スループット計算（前回値との差分）（優先度：低）
        global _last_net_stats, _last_net_time
        current_time = time.time()
        net_stats = metrics.get("network", {})
        
        if _last_net_stats.get(snap.up_if):
            time_diff = current_time - _last_net_time
            if time_diff > 0:
                last_rx = _last_net_stats[snap.up_if].get("rx_bytes", 0)
                last_tx = _last_net_stats[snap.up_if].get("tx_bytes", 0)
                curr_rx = net_stats.get("rx_bytes", 0)
                curr_tx = net_stats.get("tx_bytes", 0)
                
                rx_diff = max(0, curr_rx - last_rx)
                tx_diff = max(0, curr_tx - last_tx)
                
                # bytes/sec -> Mbps
                snap.download_mbps = (rx_diff / time_diff) * 8 / 1000000
                snap.upload_mbps = (tx_diff / time_diff) * 8 / 1000000
        
        # 次回のために保存
        _last_net_stats[snap.up_if] = net_stats
        _last_net_time = current_time
        
        # Suricataアラート
        alerts = metrics.get("suricata_alerts", {})
        snap.suricata_critical = alerts.get("critical", 0)
        snap.suricata_warning = alerts.get("warning", 0)
        snap.suricata_info = alerts.get("info", 0)
    except Exception:
        pass
    
    # ネットワーク解析（優先度：中）
    try:
        try:
            from .sensors.network_analytics import get_analytics
        except ImportError:
            import sys
            from pathlib import Path
            sensors_path = Path(__file__).parent / "sensors"
            if str(sensors_path) not in sys.path:
                sys.path.insert(0, str(sensors_path.parent))
            from sensors.network_analytics import get_analytics
        
        analytics = get_analytics()
        
        # 状態遷移の記録（前回の状態と比較）
        current_state = snap.user_state
        # グローバル変数で前回の状態を記憶（簡易版）
        if not hasattr(load_snapshot, 'last_state'):
            load_snapshot.last_state = None
        
        if load_snapshot.last_state and load_snapshot.last_state != current_state:
            # 状態が変化したら記録
            if not hasattr(load_snapshot, 'state_start_time'):
                load_snapshot.state_start_time = time.time()
            
            duration = int(time.time() - load_snapshot.state_start_time)
            analytics.add_state_transition(load_snapshot.last_state, current_state, duration)
            load_snapshot.state_start_time = time.time()
        
        load_snapshot.last_state = current_state
        
        # パケットロスとレイテンシ測定（軽量化のためcount=3）
        # ping_result = analytics.measure_packet_loss("8.8.8.8", 3)
        # snap.packet_loss_percent = ping_result.get("loss_percent", 0.0)
        # snap.latency_avg_ms = ping_result.get("avg_rtt_ms", 0.0)
        # snap.latency_trend = analytics.get_ping_trend()
        
        # DNS統計
        dns_stats = analytics.get_dns_stats()
        snap.dns_avg_ms = dns_stats.get("avg_ms", 0.0)
        snap.dns_cache_hit_rate = dns_stats.get("cache_hit_rate", 0)
        snap.dns_timeouts = dns_stats.get("timeouts", 0)
        
        # DNS blockedイベントからドメインを記録
        dns_blocked = snap.dns_stats.get("blocked", 0)
        if dns_blocked > 0:
            # evidenceからブロックされたドメインを抽出（簡易版）
            for ev in snap.evidence[-10:]:
                if "blocked" in ev.lower() and "dns" in ev.lower():
                    # "DNS blocked: example.com" のような形式を想定
                    parts = ev.split(":")
                    if len(parts) >= 2:
                        domain = parts[-1].strip().split()[0]  # 最初の単語を取得
                        analytics.add_blocked_domain(domain)
        
        # 状態遷移タイムライン
        snap.state_timeline = analytics.get_state_timeline()
        
        # ブロックトップ5
        snap.top_blocked = analytics.get_top_blocked(5)
        
        # 累計トラフィック（start_statsはnoneで起動からの累計）
        cumulative = analytics.get_traffic_cumulative(snap.up_if)
        snap.traffic_total_mb = cumulative.get("total_mb", 0.0)
        snap.traffic_download_mb = cumulative.get("download_mb", 0.0)
        snap.traffic_upload_mb = cumulative.get("upload_mb", 0.0)
        snap.traffic_packets = cumulative.get("packets", 0)
    except Exception:
        pass
    
    # セッション稼働時間（優先度：低）
    snap.session_uptime = int(time.time() - _session_start_time)
    
    # リスクスコア計算（優先度：低）
    snap.risk_score = calculate_risk_score(snap)
    
    # 推奨アクション生成（優先度：低）
    auto_recommendation = generate_recommendation(snap)
    # 既存のrecommendationが空またはデフォルトの場合、自動推奨で上書き
    if not snap.recommendation or snap.recommendation == "確認中":
        snap.recommendation = auto_recommendation
    
    # EPD用にスナップショットをエクスポート（計算済みデータを共有）
    export_epd_snapshot(snap)
    
    return snap


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
    color_pair = 3  # cyan
    mapping = STATE_MAP.get(user_state.upper(), STATE_MAP["CHECKING"])
    icon = mapping[1] if unicode_mode else mapping[2]
    if user_state.upper() == "SAFE":
        color_pair = 1  # green
    elif user_state.upper() == "LIMITED":
        color_pair = 4  # yellow
    elif user_state.upper() == "CONTAINED":
        color_pair = 2  # red
    elif user_state.upper() == "DECEPTION":
        color_pair = 5  # magenta
    else:
        color_pair = 3
    return color_pair, icon


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
    colors_on = curses.has_colors()

    def cp(idx: int):
        return curses.color_pair(idx) if colors_on else curses.A_BOLD

    # Status bar with icons, battery, and system metrics
    battery_icon = ""
    if snap.battery_pct >= 0:
        if snap.battery_pct >= 80:
            battery_icon = f"🔋 {snap.battery_pct}%" if unicode_mode else f"Bat:{snap.battery_pct}%"
        elif snap.battery_pct >= 20:
            battery_icon = f"🔋 {snap.battery_pct}%" if unicode_mode else f"Bat:{snap.battery_pct}%"
        else:
            battery_icon = f"🪫 {snap.battery_pct}%" if unicode_mode else f"LOW:{snap.battery_pct}%"
    
    # System metrics
    temp_icon = ""
    if snap.temp_c > 0:
        if snap.temp_c >= 70:
            temp_icon = f"🌡️ {snap.temp_c}°C" if unicode_mode else f"Temp:{snap.temp_c}C"
            temp_color = cp(2)  # red
        elif snap.temp_c >= 60:
            temp_icon = f"🌡️ {snap.temp_c}°C" if unicode_mode else f"Temp:{snap.temp_c}C"
            temp_color = cp(4)  # yellow
        else:
            temp_icon = f"🌡️ {snap.temp_c}°C" if unicode_mode else f"Temp:{snap.temp_c}C"
            temp_color = cp(1)  # green
    
    bar = (
        f"Azazel-Zero | "
        f"{'📶' if unicode_mode else 'WiFi'} SSID: {snap.ssid}  "
        f"{'⬇️' if unicode_mode else 'Down:'} {snap.down_if}  "
        f"{'⬆️' if unicode_mode else 'Up:'} {snap.up_if}  "
        f"{'🕐' if unicode_mode else 'Time:'} {snap.now_time}"
    )
    if battery_icon:
        bar += f"  {battery_icon}"
    stdscr.addnstr(0, 0, bar[: w - 1], w - 1, cp(6) | curses.A_BOLD)
    
    # 1行目の右側：システムメトリクス（温度のみ）
    if temp_icon:
        stdscr.addnstr(0, w - len(temp_icon) - 2, temp_icon, temp_color)

    # View line with age color coding
    live_age = "00:00:00"
    age_color = cp(1)  # green default
    age_icon = "🟢" if unicode_mode else "OK"
    if snap.snapshot_epoch:
        delta = max(0, int(time.time() - snap.snapshot_epoch))
        live_age = time.strftime("%H:%M:%S", time.gmtime(delta))
        if delta > 120:  # 2分以上
            age_color = cp(2)  # red
            age_icon = "🔴" if unicode_mode else "OLD"
        elif delta > 30:  # 30秒〜2分
            age_color = cp(4)  # yellow
            age_icon = "🟡" if unicode_mode else "OLD"
    
    # 2行目：CPU/メモリ + View情報
    color_note = "Color: ON" if colors_on else f"Color: OFF (TERM={os.environ.get('TERM','?')})"
    sys_metrics = f"CPU {snap.cpu_percent}% | Mem {snap.mem_used_mb}/{snap.mem_total_mb}MB ({snap.mem_percent}%)"
    view = f"{sys_metrics}  |  View: {snap.source} (manual)"
    stdscr.addnstr(1, 0, view[: w - 1], w - 1, cp(6))
    
    # 2行目の右側：Age情報
    age_text = f"Age: {age_icon} {live_age}"
    stdscr.addnstr(1, w - len(age_text) - 2, age_text, age_color | curses.A_BOLD)

    # Conclusion card
    card_w = w - 2
    card_h = 7  # リスクスコア追加で1行増
    card_y = 2  # 元々3だったが、ステータスが2行になったので2に
    draw_box(stdscr, card_y, 0, card_h, card_w, not unicode_mode)
    
    # リスクスコア表示（優先度：低）
    risk_color = cp(1)  # default green
    risk_icon = "🟢" if unicode_mode else "LOW"
    if snap.risk_score >= 70:
        risk_color = cp(2) | curses.A_BOLD  # red
        risk_icon = "🔴" if unicode_mode else "CRIT"
    elif snap.risk_score >= 50:
        risk_color = cp(2)  # red
        risk_icon = "🟠" if unicode_mode else "HIGH"
    elif snap.risk_score >= 30:
        risk_color = cp(4)  # yellow
        risk_icon = "🟡" if unicode_mode else "MED"
    
    risk_line = f"Risk Score: {risk_icon} {snap.risk_score}/100"
    stdscr.addnstr(card_y + 1, 2, risk_line, risk_color | curses.A_BOLD)
    
    # State badge（2行目に移動）
    state_color, state_icon = color_for_state(snap.user_state, unicode_mode)
    
    # 状態ラベル（「安全」は常に緑の太字で強調）
    state_labels = {
        "CHECKING": "確認中",
        "SAFE": "安全",
        "LIMITED": "制限中",
        "CONTAINED": "隔離",
        "DECEPTION": "観測誘導",
    }
    state_label = state_labels.get(snap.user_state.upper(), "確認中")
    badge = f" {state_icon} {state_label} "  # 括弧除去、前後にスペース
    
    # 脅威レベルインジケーター (0-5)
    threat_icons = ["🟢", "🟢", "🟡", "🟡", "🔴", "🔴"] if unicode_mode else ["O", "O", "!", "!", "X", "X"]
    threat_bar = "".join([threat_icons[i] if i < snap.threat_level else ("⚪" if unicode_mode else ".") for i in range(5)])
    threat_text = f"脅威度: [{threat_bar}] {['Low', 'Low', 'Med', 'Med', 'High', 'Critical'][min(snap.threat_level, 5)]}"
    
    # 状態バッジを反転表示で強調（SAFE=緑背景、CONTAINED=赤背景など）
    # SAFEの場合は特に緑の太字を強調
    if snap.user_state.upper() == "SAFE":
        badge_attr = cp(1) | curses.A_REVERSE | curses.A_BOLD if colors_on else curses.A_REVERSE | curses.A_BOLD
    else:
        badge_attr = cp(state_color) | curses.A_REVERSE | curses.A_BOLD if colors_on else curses.A_REVERSE
    
    stdscr.addnstr(card_y + 2, 2, badge, min(len(badge), card_w - 4), badge_attr)
    rec_text = f"  推奨：{snap.recommendation}"
    # 推奨文も状態に応じて強調
    rec_attr = cp(state_color) | curses.A_BOLD
    # 絵文字の実際の表示幅を考慮して、固定位置から表示（20文字目から開始）
    rec_start_pos = 20  # 固定位置
    stdscr.addnstr(card_y + 2, rec_start_pos, rec_text[: card_w - rec_start_pos - 2], rec_attr)
    reasons = "理由：" + " / ".join(snap.reasons or ["-"])
    # 理由を状態に応じた色で表示
    stdscr.addnstr(card_y + 3, 2, reasons[: card_w - 4], cp(state_color))
    
    # 脅威レベル表示
    threat_color = cp(1) if snap.threat_level < 2 else cp(4) if snap.threat_level < 4 else cp(2)
    stdscr.addnstr(card_y + 4, 2, threat_text[: card_w - 4], threat_color | curses.A_BOLD)
    
    next_line = "次：" + (snap.next_action_hint or "再評価を待機")
    stdscr.addnstr(card_y + 5, 2, next_line[: card_w - 4], cp(6))

    # Middle panes
    mid_y = card_y + card_h + 1
    pane_h = 10 if not compact else 7  # 高さを増やしてSuricata/Trafficを表示
    pane_w = (w - 3) // 2
    # Left: Connection
    draw_box(stdscr, mid_y, 0, pane_h, pane_w, not unicode_mode)
    stdscr.addnstr(mid_y, 2, "Connection", curses.color_pair(3) | curses.A_BOLD)
    
    # Captive Portal状態を判定
    portal_detected = "portal" in " ".join(snap.reasons).lower()
    portal_status = "⚠ SUSPECTED" if portal_detected else "✓ none" if unicode_mode else "SUSPECTED" if portal_detected else "none"
    portal_color = 2 if portal_detected else 1  # 赤 or 緑
    
    # Gateway IP色分け (プライベートIP=緑、パブリック=黄)
    gw_ip = snap.gateway_ip
    gw_color = 3  # cyan default
    if gw_ip.startswith(("192.168.", "10.", "172.16.", "172.17.", "172.18.", "172.19.", "172.20.")):
        gw_color = 1  # green (private)
        gw_display = f"🏠 {gw_ip}" if unicode_mode else gw_ip
    elif gw_ip != "-" and not gw_ip.startswith(("127.", "169.254.")):
        gw_color = 4  # yellow (public)
        gw_display = f"⚠️ {gw_ip}" if unicode_mode else f"PUB: {gw_ip}"
    else:
        gw_display = gw_ip
    
    # Channel混雑度判定（実際のスキャン結果を使用）
    ch_display = snap.channel
    ch_color = 3
    congestion = snap.channel_congestion
    ap_count = snap.channel_ap_count
    
    # 混雑度に基づく色分けとアイコン
    if congestion == "none":
        ch_icon = "🟢"  # green
        ch_color = 1
        ch_text = "Clear"
    elif congestion == "low":
        ch_icon = "🟢"  # green
        ch_color = 1
        ch_text = "Low"
    elif congestion == "medium":
        ch_icon = "🟡"  # yellow
        ch_color = 4
        ch_text = "Medium"
    elif congestion == "high":
        ch_icon = "🟧"  # orange
        ch_color = 4
        ch_text = "High"
    elif congestion == "critical":
        ch_icon = "🔴"  # red
        ch_color = 2
        ch_text = "Critical"
    else:
        ch_icon = "⚪"  # white
        ch_color = 6
        ch_text = "Unknown"
    
    try:
        ch_num = int(snap.channel)
        # 常にアイコンと混雑度を表示
        if unicode_mode:
            ch_display = f"{ch_icon} Ch{ch_num} - {ch_text} ({ap_count} APs)"
        else:
            ch_display = f"Ch{ch_num} - {ch_text} ({ap_count} APs)"
    except ValueError:
        ch_display = snap.channel
    
    # 推奨チャンネルがある場合、表示を追加
    rec_ch_line = ""
    if snap.recommended_channel > 0 and snap.recommended_channel != int(snap.channel or -1):
        if unicode_mode:
            rec_ch_line = f"→ Ch{snap.recommended_channel} 推奨"
        else:
            rec_ch_line = f"-> Ch{snap.recommended_channel}"
    
    conn_lines = [
        ("BSSID", snap.bssid, 6),
        ("Channel", ch_display, ch_color),
        ("Signal", f"{snap.signal_dbm} dBm", 6),
        ("Gateway", gw_display, gw_color),
    ]
    
    # 推奨チャンネルがあれば追加
    if rec_ch_line:
        conn_lines.append(("", rec_ch_line, 1))  # green
    else:
        conn_lines.append(("Captive Portal", portal_status, portal_color))
    # Signal強度を🟥🟧🟨🟩で視覚的に表現
    try:
        sig = float(snap.signal_dbm)
        if sig >= -50:
            # 非常に良好 (🟩🟩🟩🟩)
            sig_icon = "🟩🟩🟩🟩" if unicode_mode else "████"
            sig_color = 1  # green
        elif sig >= -60:
            # 良好 (🟩🟩🟩)
            sig_icon = "🟩🟩🟩" if unicode_mode else "███"
            sig_color = 1  # green
        elif sig >= -70:
            # 普通 (🟨🟨)
            sig_icon = "🟨🟨" if unicode_mode else "██"
            sig_color = 4  # yellow
        elif sig >= -80:
            # 弱い (🟧)
            sig_icon = "🟧" if unicode_mode else "█"
            sig_color = 4  # yellow/orange
        else:
            # 非常に弱い (🟥)
            sig_icon = "🟥" if unicode_mode else "█"
            sig_color = 2  # red
        conn_lines[2] = ("Signal", f"{sig_icon} {snap.signal_dbm} dBm", sig_color)
    except Exception:
        pass
    
    for i, (label, val, color_idx) in enumerate(conn_lines[: pane_h - 2]):
        line_text = f"{label}: {val}"[: pane_w - 4]
        attr = cp(color_idx) | curses.A_BOLD if i == 4 and portal_detected else cp(color_idx)
        stdscr.addnstr(mid_y + 1 + i, 2, line_text, attr)
    # Right: Control/Safety
    draw_box(stdscr, mid_y, pane_w + 1, pane_h, pane_w, not unicode_mode)
    stdscr.addnstr(mid_y, pane_w + 3, "Control / Safety", cp(3) | curses.A_BOLD)
    degrade = snap.degrade or {}
    probe = snap.probe or {}
    
    # QUIC状態の色分け (blocked=赤、allowed=緑)
    quic_status = snap.quic.lower()
    quic_color = 2 if "block" in quic_status else 1  # red or green
    quic_symbol = "⛔" if "block" in quic_status else "✓" if unicode_mode else "X" if "block" in quic_status else "OK"
    quic_display = f"{quic_symbol} {snap.quic.upper()}"
    
    # DoH状態の色分け
    doh_status = snap.doh.lower()
    doh_color = 2 if "block" in doh_status else 1
    doh_symbol = "⛔" if "block" in doh_status else "✓" if unicode_mode else "X" if "block" in doh_status else "OK"
    doh_display = f"{doh_symbol} {snap.doh.upper()}"
    
    # Degrade状態の色分け (active=黄、off=緑)
    deg_active = degrade.get("on", False)
    deg_color = 4 if deg_active else 1  # yellow or green
    if deg_active:
        deg_txt = f"⚡ ON: RTT +{degrade.get('rtt_ms',0)}ms, Rate {degrade.get('rate_mbps',0)}Mbps" if unicode_mode else f"ON: +{degrade.get('rtt_ms',0)}ms, {degrade.get('rate_mbps',0)}Mbps"
    else:
        deg_txt = "✓ OFF" if unicode_mode else "OFF"
    
    # Probe結果の色分け (blocked>0=赤、all OK=緑、それ以外=黄)
    blocked_count = probe.get('blocked', 0)
    tls_ok = probe.get('tls_ok', 0)
    tls_total = probe.get('tls_total', 0)
    if blocked_count > 0:
        probe_color = 2  # red
        probe_txt = f"⚠ {tls_ok}/{tls_total} OK, {blocked_count} BLOCKED" if unicode_mode else f"{tls_ok}/{tls_total} OK, {blocked_count} BLOCKED"
    elif tls_total > 0 and tls_ok == tls_total:
        probe_color = 1  # green
        probe_txt = f"✓ {tls_ok}/{tls_total} ALL OK" if unicode_mode else f"{tls_ok}/{tls_total} ALL OK"
    else:
        probe_color = 4  # yellow
        probe_txt = f"~ {tls_ok}/{tls_total} OK" if unicode_mode else f"{tls_ok}/{tls_total} OK"
    
    # DNS統計の色分け
    dns_ok = snap.dns_stats.get("ok", 0)
    dns_anomaly = snap.dns_stats.get("anomaly", 0)
    dns_blocked = snap.dns_stats.get("blocked", 0)
    dns_total = dns_ok + dns_anomaly + dns_blocked
    
    if dns_total > 0:
        dns_stat_text = f"DNS: ✅ {dns_ok} ⚠️ {dns_anomaly} 🔴 {dns_blocked}" if unicode_mode else f"DNS: OK:{dns_ok} WARN:{dns_anomaly} BLK:{dns_blocked}"
        if dns_blocked > 0:
            dns_stat_color = 2  # red
        elif dns_anomaly > 0:
            dns_stat_color = 4  # yellow
        else:
            dns_stat_color = 1  # green
    else:
        dns_stat_text = "DNS: (no data)"
        dns_stat_color = 6
    
    # Suricataアラート統計
    suri_total = snap.suricata_critical + snap.suricata_warning + snap.suricata_info
    if suri_total > 0:
        suri_text = f"IDS: 🔴 {snap.suricata_critical} ⚠️ {snap.suricata_warning} 🟢 {snap.suricata_info}" if unicode_mode else f"IDS: C:{snap.suricata_critical} W:{snap.suricata_warning} I:{snap.suricata_info}"
        if snap.suricata_critical > 0:
            suri_color = 2  # red
        elif snap.suricata_warning > 0:
            suri_color = 4  # yellow
        else:
            suri_color = 1  # green
    else:
        suri_text = "IDS: (no alerts)"
        suri_color = 6
    
    # ネットワークスループット
    traffic_text = f"Traffic: ↓ {snap.download_mbps:.1f} Mbps / ↑ {snap.upload_mbps:.1f} Mbps" if unicode_mode else f"Traffic: D:{snap.download_mbps:.1f} U:{snap.upload_mbps:.1f} Mbps"
    traffic_color = 6
    
    # パケットロス統計（優先度：中）
    loss_text = ""
    loss_color = 1  # default green
    if snap.packet_loss_percent > 0 or snap.latency_avg_ms > 0:
        loss_text = f"Loss: {snap.packet_loss_percent:.1f}% | RTT: {snap.latency_avg_ms:.1f}ms"
        if snap.packet_loss_percent >= 10:
            loss_color = 2  # red
        elif snap.packet_loss_percent >= 5:
            loss_color = 4  # yellow
        else:
            loss_color = 1  # green
    
    # DNS応答時間統計（優先度：中）
    dns_perf_text = ""
    dns_perf_color = 1
    if snap.dns_avg_ms > 0:
        cache_info = f" | Cache:{snap.dns_cache_hit_rate}%" if snap.dns_cache_hit_rate > 0 else ""
        timeout_info = f" | TO:{snap.dns_timeouts}" if snap.dns_timeouts > 0 else ""
        dns_perf_text = f"DNS Time: {snap.dns_avg_ms:.1f}ms{cache_info}{timeout_info}"
        if snap.dns_avg_ms >= 100:
            dns_perf_color = 4  # yellow
        elif snap.dns_timeouts > 0:
            dns_perf_color = 2  # red
        else:
            dns_perf_color = 1  # green
    
    # 累計トラフィック（優先度：中）
    traffic_cum_text = ""
    if snap.traffic_total_mb > 0:
        traffic_cum_text = f"Total: {snap.traffic_total_mb:.1f}MB (↓{snap.traffic_download_mb:.1f} ↑{snap.traffic_upload_mb:.1f})"
    
    ctl_items = [
        ("QUIC(UDP/443)", quic_display, quic_color),
        ("DoH(TCP/443)", doh_display, doh_color),
        ("Degrade", deg_txt, deg_color),
        ("Probe", probe_txt, probe_color),
        ("Stats", dns_stat_text, dns_stat_color),
        ("", suri_text, suri_color),  # Suricataアラート
        ("", traffic_text, traffic_color),  # トラフィック
        ("", loss_text, loss_color) if loss_text else ("", "", 6),  # パケットロス
        ("", dns_perf_text, dns_perf_color) if dns_perf_text else ("", "", 6),  # DNS性能
        ("", traffic_cum_text, 6) if traffic_cum_text else ("", "", 6),  # 累計トラフィック
    ]
    
    for i, (label, val, color_idx) in enumerate(ctl_items[: pane_h - 2]):
        line_text = f"{label}: {val}"[: pane_w - 4]
        attr = cp(color_idx) | curses.A_BOLD if colors_on else curses.A_BOLD
        stdscr.addnstr(mid_y + 1 + i, pane_w + 3, line_text, attr)

    # Evidence
    ev_y = mid_y + pane_h + 1
    available = h - ev_y - 3
    if available < 3:
        available = 3
    ev_h = min(max(5, available), h - ev_y - 1)
    draw_box(stdscr, ev_y, 0, ev_h, w, not unicode_mode)
    stdscr.addnstr(ev_y, 2, "Evidence (last 90s)", cp(3) | curses.A_BOLD)
    ev_lines = snap.evidence[-(ev_h - 3) :] if not compact else snap.evidence[-3:]
    
    # キーワードベースの色分け + 重要度マーク
    for i, ev in enumerate(ev_lines):
        ev_lower = ev.lower()
        severity_mark = "⚪" if unicode_mode else "·"  # default
        
        # 異常・エラー系 = 赤
        if any(kw in ev_lower for kw in ["blocked", "fail", "error", "mismatch", "hijack", "contain", "suspected", "anomaly"]):
            color = cp(2) | curses.A_BOLD  # red + bold
            severity_mark = "🔴" if unicode_mode else "X"
        # 警告・注意系 = 黄
        elif any(kw in ev_lower for kw in ["portal", "dns", "probe", "degrade", "warning", "suspect", "limited"]):
            color = cp(4)  # yellow
            severity_mark = "🟡" if unicode_mode else "!"
        # 成功・正常系 = 緑
        elif any(kw in ev_lower for kw in ["ok", "safe", "normal", "pass", "allow", "success"]):
            color = cp(1)  # green
            severity_mark = "🟢" if unicode_mode else "O"
        # アクション系 = シアン
        elif any(kw in ev_lower for kw in ["action", "command", "transition", "stage"]):
            color = cp(3)  # cyan
            severity_mark = "💠" if unicode_mode else ">"
        # その他 = デフォルト
        else:
            color = cp(6)
        
        # タイムスタンプ付き表示（簡易版：先頭に追加）
        ev_display = f"{severity_mark} {ev}"[: w - 4]
        stdscr.addnstr(ev_y + 1 + i, 2, ev_display, color)
    # decision line
    dec = snap.internal or {}
    decision = f"↳ decision: state={dec.get('state_name','-')} suspicion={dec.get('suspicion','-')} decay={dec.get('decay','-')}"
    stdscr.addnstr(ev_y + ev_h - 2, 2, decision[: w - 4], cp(6))

    # 追加パネル：State遷移タイムラインとブロックドメイン（優先度：中）
    extra_y = ev_y + ev_h
    extra_h = h - extra_y - 4
    if extra_h >= 5:
        draw_box(stdscr, extra_y, 0, extra_h, w, not unicode_mode)
        stdscr.addnstr(extra_y, 2, "Analytics (State & Blocked)", cp(5) | curses.A_BOLD)
        
        # セッション稼働時間（優先度：低）
        uptime_str = time.strftime("%H:%M:%S", time.gmtime(snap.session_uptime))
        session_display = f"Session Uptime: ⏱️ {uptime_str}" if unicode_mode else f"Session Uptime: {uptime_str}"
        stdscr.addnstr(extra_y + 1, 2, session_display[: w - 4], cp(3) | curses.A_BOLD)
        
        # State遷移タイムライン
        timeline_display = f"Timeline: {snap.state_timeline}"
        stdscr.addnstr(extra_y + 2, 2, timeline_display[: w - 4], cp(6))
        
        # ブロックトップ5
        if snap.top_blocked:
            blocked_title = "Top Blocked:" if unicode_mode else "Top Blocked:"
            stdscr.addnstr(extra_y + 3, 2, blocked_title, cp(2) | curses.A_BOLD)
            for idx, (domain, count) in enumerate(snap.top_blocked[: extra_h - 5]):
                block_line = f"  {idx+1}. {domain} ({count}x)"
                stdscr.addnstr(extra_y + 4 + idx, 2, block_line[: w - 4], cp(2))
        else:
            no_blocks = "No blocked domains"
            stdscr.addnstr(extra_y + 3, 2, no_blocks[: w - 4], cp(1))

    # Actions + Hint (絵文字なし、シンプル表示)
    actions = "[U] Refresh  [A] Stage-Open  [R] Re-Probe  [C] Contain  [L] Details  [Q] Quit"
    
    # 状態遷移フロー表示
    state_flow = "Flow: PROBE → DEGRADED → NORMAL → ✅ SAFE" if unicode_mode else "Flow: PROBE->DEGRADED->NORMAL->SAFE"
    current_state = snap.internal.get("state_name", "-").upper() if isinstance(snap.internal, dict) else "-"
    if current_state in state_flow:
        # 現在位置を強調表示するため、別々に描画
        stdscr.addnstr(h - 3, 0, state_flow[: w - 1], cp(6))
    else:
        stdscr.addnstr(h - 3, 0, state_flow[: w - 1], cp(6))
    
    stdscr.addnstr(h - 2, 0, actions[: w - 1], cp(6) | curses.A_BOLD)
    hint = "Hint: この画面は自動更新しません。必要時に [U] で更新してください。"
    stdscr.addnstr(h - 1, 0, hint[: w - 1], cp(6))
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
def _parse_log_ts(line: str) -> float:
    """Parse leading timestamp from log line; return epoch or 0."""
    # Expect format like: "2025-01-29 09:29:42,123 INFO {...}"
    try:
        parts = line.split(None, 2)
        if len(parts) >= 2:
            ts_part = f"{parts[0]} {parts[1]}"
            try:
                return time.mktime(time.strptime(ts_part, "%Y-%m-%d %H:%M:%S,%f"))
            except ValueError:
                return time.mktime(time.strptime(ts_part, "%Y-%m-%d %H:%M:%S"))
    except Exception:
        return 0
    return 0
