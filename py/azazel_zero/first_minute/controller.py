from __future__ import annotations

import json
import logging
import os
import re
import signal
import socket
from urllib.parse import urlparse
import subprocess
import threading
import time
import shutil
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, Optional

from azazel_zero.sensors.wifi_safety import evaluate_wifi_safety
from azazel_zero.tactics_engine import ConfigHash, DecisionLogger
from azazel_zero.tactics_engine.decision_logger import (
    StateSnapshot, InputSnapshot, ScoreDelta, ChosenAction, DecisionRecord,
)

from .config import FirstMinuteConfig
from .dns_observer import DNSObserver, seed_probe_ips
from .nft import NftManager
from .notifier import NtfyNotifier  # ★ ntfy 通知統合
from .probes import ProbeOutcome, run_all
from .state_machine import FirstMinuteStateMachine, Stage
from .tc import TcManager
from .web_api import add_history_event


class StatusHandler(BaseHTTPRequestHandler):
    def __init__(self, ctx: Dict[str, object], *args, **kwargs):
        self.ctx = ctx
        super().__init__(*args, **kwargs)

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(self.ctx, default=str).encode("utf-8"))

    def do_POST(self):
        """Handle POST requests for action endpoints.
        
        Supported endpoints:
        - /action/reprobe: Force re-run safety probes
        - /action/refresh: Force refresh EPD display and state
        """
        if self.path == "/action/reprobe":
            # Signal controller to re-run probes
            self.ctx["force_reprobe"] = True
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "action": "reprobe"}).encode("utf-8"))
        elif self.path == "/action/refresh":
            # Signal controller to force EPD update
            self.ctx["force_epd_update"] = True
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "action": "refresh"}).encode("utf-8"))
        else:
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "unknown endpoint"}).encode("utf-8"))

    def log_message(self, fmt, *args):  # pragma: no cover - avoid noisy logs
        return


def make_status_server(host: str, port: int, ctx: Dict[str, object]) -> ThreadingHTTPServer:
    def handler(*args, **kwargs):
        return StatusHandler(ctx, *args, **kwargs)

    return ThreadingHTTPServer((host, port), handler)


class FirstMinuteController:
    def __init__(self, cfg: FirstMinuteConfig, dry_run: bool = False, no_dns_start: bool = False, pretty_console: bool = False):
        self.cfg = cfg
        self.dry_run = dry_run
        self.no_dns_start = no_dns_start
        self.pretty_console = pretty_console
        self.logger = logging.getLogger("first_minute")
        self.stop_event = threading.Event()
        self.state_machine = FirstMinuteStateMachine(cfg.state_machine)
        self.current_stage: Stage = Stage.INIT
        self.last_probe: Optional[ProbeOutcome] = None
        self.nft = NftManager(
            cfg.nft_template_path,
            cfg.interfaces["upstream"],
            cfg.interfaces["downstream"],
            cfg.interfaces["mgmt_ip"],
            cfg.interfaces["mgmt_subnet"],
            int(cfg.policy.get("probe_allow_ttl", 120)),
            int(cfg.policy.get("dynamic_allow_ttl", 300)),
        )
        self.tc = TcManager(cfg.interfaces["downstream"], cfg.interfaces["upstream"])
        self.dns_thread: Optional[DNSObserver] = None
        
        # ★ ntfy 通知クライアントを初期化
        self.notifier: Optional[NtfyNotifier] = None
        if cfg.notify.get("enabled", False):
            self._init_notifier()
        
        # Tactics Engine: config_hash を計算して status_ctx に追加
        self.config_hash = ConfigHash.compute(config_file=Path(cfg.yaml_path) if cfg.yaml_path else None)
        self.last_decision_id: Optional[str] = None
        self.decision_logger = DecisionLogger(output_dir=Path("/opt/azazel/logs/tactics_engine"))
        
        # Web UI 用：起動時刻を記録
        self._start_time = time.time()
        
        self.status_ctx: Dict[str, object] = {
            "state": "INIT",
            "suspicion": 0,
            "last_probe": None,
            "config_hash": self.config_hash,
            "last_decision_id": self.last_decision_id,
            "start_time": self._start_time,
        }
        self.status_server: Optional[ThreadingHTTPServer] = None
        self.web_server: Optional[object] = None
        self.processes: Dict[str, subprocess.Popen] = {}
        self.last_console = 0.0
        self.snapshot_path = cfg.runtime_dir / "ui_snapshot.json"
        self.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        # Keep Wi-Fi connection state in memory to preserve across snapshots
        self.persistent_connection_state: Dict[str, object] = {}
        self.epd_last_update = 0.0
        self.epd_last_fp: Optional[tuple] = None
        # Track signal strength separately to skip updates when only signal changes
        self.epd_last_signal_bucket: Optional[str] = None
        self._eve_offset = 0
        self._eve_inode: Optional[int] = None
        self._eve_partial = ""
        self._eve_initialized = False
        self._eve_parse_errors = {"json_decode_fail": 0, "skipped_lines": 0}
        try:
            # デフォルト30秒：電子ペーパーの刷新頻度を抑制、不要な更新を削減
            self.epd_min_interval = float(os.environ.get("AZAZEL_EPD_MIN_INTERVAL", "30"))
        except ValueError:
            self.epd_min_interval = 8.0
        self.epd_enabled = os.environ.get("AZAZEL_EPD", "1").strip().lower() not in ("0", "false", "no", "off")
        self.health_last_update = 0.0
        self.health_last_fp: Optional[tuple] = None
        try:
            self.health_min_interval = float(os.environ.get("AZAZEL_HEALTH_INTERVAL", "20"))
        except ValueError:
            self.health_min_interval = 20.0
        # Suricata alert context
        self._last_suricata_severity: int = 0

    def preflight(self) -> None:
        if os.geteuid() != 0:
            raise SystemExit("First-Minute Control requires root.")
        for bin_name in ("nft", "tc", "ip"):
            if not shutil.which(bin_name):  # type: ignore[name-defined]
                raise SystemExit(f"{bin_name} not found in PATH")

    def apply_sysctl(self) -> None:
        cmds = [
            ["sysctl", "-w", "net.ipv4.ip_forward=1"],
            ["sysctl", "-w", "net.ipv4.conf.all.rp_filter=1"],
            ["sysctl", "-w", "net.ipv4.conf.default.rp_filter=1"],
        ]
        for cmd in cmds:
            subprocess.run(cmd, check=False)

    def start_dnsmasq(self) -> None:
        if self.no_dns_start or not self.cfg.dnsmasq.get("enable", True):
            return
        cmd = ["dnsmasq", f"--conf-file={self.cfg.dnsmasq_conf_path}"]
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.processes["dnsmasq"] = proc

    def stop_dnsmasq(self) -> None:
        proc = self.processes.get("dnsmasq")
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()

    def start_dns_observer(self) -> None:
        self.dns_thread = DNSObserver(self.cfg.dns_log_path, self.nft, self.stop_event)
        self.dns_thread.start()

    def start_status_api(self) -> None:
        host = self.cfg.status_api.get("host", "127.0.0.1")
        port = int(self.cfg.status_api.get("port", 8082))
        # ステータス API（JSON）
        self.status_server = make_status_server(host, port, self.status_ctx)
        thread = threading.Thread(target=self.status_server.serve_forever, daemon=True)
        thread.start()
        self.logger.info(f"Status API started on {host}:{port}")

    def write_snapshot(self, summary: Dict[str, object], link_meta: Dict[str, object]) -> None:
        """Write a UI snapshot JSON for the TUI to consume."""
        # Step 1: Update persistent connection state from any available file
        # This ensures we capture any updates from wifi_connect.py
        self._sync_connection_state()
        self.logger.info("snapshot: write_snapshot() called with new persistent state logic")
        
        link = link_meta.get("link", {}) if link_meta else {}
        
        # Gather system metrics
        cpu_temp = self._get_cpu_temp()
        cpu_usage = self._get_cpu_usage()
        mem_usage = self._get_memory_usage()
        
        snap = {
            "now_time": time.strftime("%H:%M:%S"),
            "snapshot_epoch": time.time(),
            "ssid": (link or {}).get("ssid", "-"),
            "bssid": (link or {}).get("bssid", "-"),
            "channel": (link or {}).get("channel", "-"),
            "signal_dbm": (link or {}).get("signal", "-"),
            "gateway_ip": (link or {}).get("gateway") or self.cfg.interfaces.get("gateway_ip", "-"),
            "down_if": self.cfg.interfaces.get("downstream", "usb0"),
            "down_ip": self.cfg.interfaces.get("mgmt_ip", "-"),
            "up_if": self.cfg.interfaces.get("upstream", "wlan0"),
            "user_state": self._user_state_from_stage(self.current_stage),
            "recommendation": summary.get("reason", "確認中"),
            "reasons": [summary.get("reason", "")] if summary.get("reason") else [],
            "next_action_hint": "再評価を待機",
            "quic": "blocked" if self.current_stage in (Stage.PROBE, Stage.DEGRADED, Stage.CONTAIN) else "allowed",
            "doh": "blocked",
            "dns_mode": "forced via Azazel DNS",
            "degrade": {
                "on": self.current_stage in (Stage.PROBE, Stage.DEGRADED),
                "rtt_ms": 180 if self.current_stage in (Stage.PROBE, Stage.DEGRADED) else 0,
                "rate_mbps": 2.0 if self.current_stage == Stage.DEGRADED else 1.0 if self.current_stage == Stage.PROBE else 0,
            },
            "probe": {
                "tls_ok": (self.last_probe.tls_mismatch is False) if self.last_probe else 0,
                "tls_total": 1 if self.last_probe else 0,
                "blocked": 1 if (self.last_probe and self.last_probe.tls_mismatch) else 0,
            },
            "evidence": self._evidence_lines(link_meta),
            "internal": {
                "state_name": self.state_machine.ctx.state.value,
                "suspicion": summary.get("suspicion", 0),
                "decay": self.state_machine.ctx.last_transition,
            },
            # System metrics (shared with Web UI)
            "cpu_percent": cpu_usage,
            "mem_percent": mem_usage,
            "temp_c": cpu_temp,
            # Default connection section (will be overwritten with persisted state below)
            "connection": {
                "wifi_state": "DISCONNECTED",
                "usb_nat": "OFF",
                "internet_check": "UNKNOWN",
                "captive_portal": "UNKNOWN"
            }
        }
        try:
            self.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Preserve Wi-Fi connection state from previous snapshot
            # This allows wifi_connect.py to update connection info without being overwritten
            # Check both primary and fallback paths to ensure we don't lose data
            existing_connection = None
            fallback_snapshot_path = Path.home() / ".azazel-zero/run/ui_snapshot.json"
            
            try:
                if self.snapshot_path.exists():
                    existing = json.loads(self.snapshot_path.read_text(encoding="utf-8"))
                    existing_connection = existing.get("connection")
                    if existing_connection:
                        self.logger.debug(f"snapshot: preserving connection state from primary path: {existing_connection}")
            except Exception as e:
                self.logger.debug(f"snapshot: failed to read primary path: {e}")
            
            # If primary has no connection, try fallback path
            if not existing_connection:
                try:
                    if fallback_snapshot_path.exists():
                        existing = json.loads(fallback_snapshot_path.read_text(encoding="utf-8"))
                        existing_connection = existing.get("connection")
                        if existing_connection:
                            self.logger.debug(f"snapshot: preserving connection state from fallback path: {existing_connection}")
                except Exception as e:
                    self.logger.debug(f"snapshot: failed to read fallback path: {e}")
            
            # Merge persistent connection state (from memory or file)
            # This ensures Wi-Fi connection data is never lost across snapshot writes
            if self.persistent_connection_state:
                snap["connection"] = self.persistent_connection_state.copy()
                self.logger.debug(f"snapshot: using persistent connection state (from memory): {self.persistent_connection_state}")
            elif existing_connection:
                snap["connection"] = existing_connection.copy()
                # Also update memory for next iteration
                self.persistent_connection_state = existing_connection.copy()
                self.logger.debug(f"snapshot: loaded connection state from file: {existing_connection}")
            else:
                self.logger.debug("snapshot: no connection state available")
            
            # Write snapshot to BOTH paths to ensure synchronization
            # Primary path: /run/azazel-zero/ui_snapshot.json
            try:
                self.snapshot_path.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
            except Exception as e:
                self.logger.debug(f"snapshot: failed to write primary path: {e}")
            
            # Fallback path: ~/.azazel-zero/run/ui_snapshot.json
            fallback_snapshot_path = Path.home() / ".azazel-zero/run/ui_snapshot.json"
            try:
                fallback_snapshot_path.parent.mkdir(parents=True, exist_ok=True)
                fallback_snapshot_path.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
            except Exception as e:
                self.logger.debug(f"snapshot: failed to write fallback path: {e}")
        except Exception as e:
            self.logger.warning(f"snapshot: failed overall: {e}")

    def _sync_connection_state(self) -> None:
        """Sync persistent connection state from files.
        
        This reads from both the primary and fallback snapshot paths to detect
        when wifi_connect.py has written new connection data. This is essential
        because write_snapshot() executes every 2 seconds and would otherwise
        overwrite the connection section that wifi_connect.py just wrote.
        """
        # Check primary and fallback paths for any updates
        state_path = Path("/run/azazel-zero/ui_snapshot.json")
        fallback_path = Path.home() / ".azazel-zero/run/ui_snapshot.json"
        
        self.logger.debug(f"sync: checking for connection state updates (current: {self.persistent_connection_state})")
        
        # Check BOTH paths - either one might have the latest connection data
        for path in [state_path, fallback_path]:
            try:
                if path.exists():
                    data = json.loads(path.read_text(encoding="utf-8"))
                    conn = data.get("connection")
                    self.logger.debug(f"sync: read from {path}: {conn}")
                    
                    # If we find new/different connection data, use it
                    if conn:
                        # Convert to tuple for comparison (dicts are unhashable)
                        current_tuple = tuple(sorted(self.persistent_connection_state.items())) if self.persistent_connection_state else ()
                        incoming_tuple = tuple(sorted(conn.items()))
                        
                        if current_tuple != incoming_tuple:
                            self.persistent_connection_state = conn.copy()
                            self.logger.info(f"sync: UPDATED persistent state from {path}: {conn}")
                            return  # Found and updated, exit
                        else:
                            self.logger.debug(f"sync: connection unchanged from {path}")
                    else:
                        self.logger.debug(f"sync: no connection section in {path}")
            except Exception as e:
                self.logger.debug(f"sync: failed to read {path}: {e}")

    def _get_interface_ip(self, iface: str) -> str:
        if not iface:
            return "-"
        try:
            out = subprocess.check_output(["ip", "-4", "addr", "show", iface], text=True, timeout=1.5)
        except Exception:
            return "-"
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("inet "):
                return line.split()[1].split("/")[0]
        return "-"

    def _parse_signal_dbm(self, signal: object) -> Optional[int]:
        if signal is None:
            return None
        try:
            val = int(float(str(signal).strip()))
        except Exception:
            return None
        if 0 <= val <= 100:
            return int(val * 0.6 - 90)
        return val

    def _epd_signal_bucket(self, signal_dbm: Optional[int]) -> str:
        if signal_dbm is None:
            return "none"
        if signal_dbm >= -60:
            return "strong"
        if signal_dbm >= -70:
            return "medium"
        if signal_dbm >= -80:
            return "weak"
        return "none"

    def _epd_fingerprint(
        self,
        mode: str,
        ssid: str,
        up_ip: str,
        signal_bucket: str,
        msg: str,
    ) -> tuple:
        # For NORMAL state: only SSID and IP matter; signal strength changes don't warrant refresh
        if mode == "normal":
            return (mode, ssid, up_ip)
        # For other states: include message
        return (mode, msg)

    def _maybe_update_epd(self, stage: Stage, summary: Dict[str, object], link_meta: Dict[str, object], force: bool = False) -> None:
        if self.dry_run or not self.epd_enabled:
            return
        now = time.time()
        if not force and (now - self.epd_last_update) < self.epd_min_interval:
            return

        link = link_meta.get("link", {}) if link_meta else {}
        up_ip = self._get_interface_ip(self.cfg.interfaces.get("upstream", "wlan0"))
        reason = str(summary.get("reason", "") or "")

        epd_script = Path(__file__).resolve().parents[2] / "azazel_epd.py"
        if not epd_script.exists():
            return

        # SSIDを取得：実際に接続されているSSIDを優先
        # link_meta は実際のシステム接続状態を反映している
        ssid = str(link.get("ssid") or "No SSID")
        
        signal_dbm = self._parse_signal_dbm(link.get("signal"))
        signal_bucket = self._epd_signal_bucket(signal_dbm)
        
        # EPD表示用に簡潔なメッセージを作成（文字数制限考慮）
        if stage == Stage.DEGRADED:
            # DEGRADEDの場合、reasonから簡潔な表示を作成
            if "contain" in reason.lower() and "degraded" in reason.lower():
                msg = "RECOVERED"  # CONTAIN→DEGRADED の場合
            elif "degraded" in reason.lower():
                msg = "CAUTION"    # その他のDEGRADED
            else:
                msg = (reason or "LIMITED")[:12]  # 12文字制限
        else:
            msg = (reason or stage.value)[:12]  # その他のステートも12文字制限

        epd_ip = up_ip if up_ip and up_ip != "-" else "No IP"
        if stage in (Stage.INIT, Stage.PROBE, Stage.NORMAL):
            mode = "normal"
            # フィンガープリント：信号強度を除外（信号のみの変化で更新をスキップ）
            fp = self._epd_fingerprint(mode, ssid, epd_ip, "", "")
            
            self.logger.debug(f"EPD: fingerprint check - current={fp}, last={self.epd_last_fp}, match={fp == self.epd_last_fp}")
            self.logger.debug(f"EPD: signal_bucket - current={signal_bucket}, last={self.epd_last_signal_bucket}")
            
            # 主要な状態が変わったかチェック
            if not force and fp == self.epd_last_fp:
                # 主要な状態（SSID/IP/stage）は変わっていない
                if signal_bucket == self.epd_last_signal_bucket:
                    # 信号強度のアイコンも変わっていない → 更新スキップ
                    self.logger.debug(f"EPD: Skipping update - no meaningful changes")
                    return
                else:
                    # 信号強度のアイコンが変わった（例：strong→medium）
                    self.logger.info(f"EPD: Updating display - signal icon changed ({self.epd_last_signal_bucket}→{signal_bucket})")
                    # ここで更新処理に進む（下記のcmd実行へ）
            cmd = ["python3", str(epd_script), "--state", mode, "--ssid", ssid, "--ip", epd_ip]
            if signal_dbm is not None:
                cmd += ["--signal", str(signal_dbm)]
        elif stage == Stage.DEGRADED:
            mode = "warning"
            fp = self._epd_fingerprint(mode, "", "", "", msg)
            self.logger.debug(f"EPD: fingerprint check - current={fp}, last={self.epd_last_fp}, match={fp == self.epd_last_fp}")
            if not force and fp == self.epd_last_fp:
                self.logger.debug(f"EPD: Skipping update - fingerprint unchanged")
                return
            cmd = ["python3", str(epd_script), "--state", mode, "--msg", msg]
        elif stage == Stage.CONTAIN:
            mode = "danger"
            # ★ Phase 2: CONTAIN状態で統一メッセージを表示
            contain_msg = "ATTACK DETECTED"
            fp = self._epd_fingerprint(mode, "", "", "", contain_msg)
            self.logger.debug(f"EPD: fingerprint check - current={fp}, last={self.epd_last_fp}, match={fp == self.epd_last_fp}")
            if not force and fp == self.epd_last_fp:
                self.logger.debug(f"EPD: Skipping update - fingerprint unchanged")
                return
            cmd = ["python3", str(epd_script), "--state", mode, "--msg", contain_msg]
        else:
            self.logger.debug(f"EPD: Unknown stage {stage}, skipping update")
            return

        # Execute EPD update command
        self.logger.info(f"EPD: Updating display - mode={mode}, stage={stage.value}, forced={force}")
        try:
            subprocess.run(cmd, timeout=30, check=False)
            self.epd_last_update = now
            self.epd_last_fp = fp
            # 信号強度も更新 (NORMAL状態時)
            if stage in (Stage.INIT, Stage.PROBE, Stage.NORMAL):
                self.epd_last_signal_bucket = signal_bucket
            self.logger.info(f"EPD: Update successful")
        except Exception as e:
            self.logger.warning(f"EPD: Update failed: {e}")
            return

    def _maybe_write_wifi_health(self, link_meta: Dict[str, object]) -> None:
        now = time.time()
        link = link_meta.get("link", {}) if link_meta else {}
        tags = link_meta.get("wifi_tags", []) if link_meta else []

        try:
            from azazel_zero.core.mock_llm_core import MockLLMCore
            from azazel_zero.sensors.wifi_health_monitor import health_paths
        except Exception:
            return

        core = MockLLMCore(profile="zero")
        verdict = core.evaluate("wifi_health", features={"tags": tags, "service": "wifi"})
        risk = int(verdict.risk)
        status = "ok" if risk <= 2 else "warn"
        summary = {
            "ts": now,
            "iface": self.cfg.interfaces.get("upstream", "wlan0"),
            "link": link,
            "tags": tags,
            "risk": risk,
            "category": verdict.category,
            "reason": verdict.reason,
            "status": status,
        }

        fp = (
            str(link.get("ssid", "")),
            str(link.get("bssid", "")),
            tuple(tags),
            risk,
            verdict.category,
            verdict.reason[:60],
            status,
        )
        if self.health_last_fp == fp and (now - self.health_last_update) < self.health_min_interval:
            return

        out_path, _ = health_paths()
        try:
            out_path.write_text(json.dumps(summary, ensure_ascii=False))
            self.health_last_fp = fp
            self.health_last_update = now
        except Exception:
            pass

    def _evidence_lines(self, link_meta: Dict[str, object]) -> List[str]:
        lines: List[str] = []
        tags = link_meta.get("wifi_tags") or []
        if tags:
            lines.append("• wifi tags: " + ",".join(tags))
        if self.last_probe:
            lines.append(f"• captive portal: {'yes' if self.last_probe.captive_portal else 'no'}")
            lines.append(f"• tls mismatch: {'yes' if self.last_probe.tls_mismatch else 'no'}")
            lines.append(f"• dns mismatch: {self.last_probe.dns_mismatch}")
        if not lines:
            lines.append("• no recent evidence")
        lines.append(
            f"↳ decision: state={self.state_machine.ctx.state.value} suspicion={round(self.state_machine.ctx.suspicion,2)}"
        )
        return lines

    def _user_state_from_stage(self, stage: Stage) -> str:
        if stage == Stage.PROBE or stage == Stage.INIT:
            return "CHECKING"
        if stage == Stage.NORMAL:
            return "SAFE"
        if stage == Stage.DEGRADED:
            return "LIMITED"
        if stage == Stage.CONTAIN:
            return "CONTAINED"
        if stage == Stage.DECEPTION:
            return "DECEPTION"
        return "CHECKING"

    def _get_cpu_temp(self) -> float:
        """Get CPU temperature in Celsius"""
        try:
            with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
                temp_millidegrees = int(f.read().strip())
                return round(temp_millidegrees / 1000, 1)
        except Exception:
            return 0.0

    def _get_cpu_usage(self) -> float:
        """Get CPU usage percentage"""
        try:
            result = subprocess.run(
                ['top', '-bn1'],
                capture_output=True,
                text=True,
                timeout=2
            )
            match = re.search(r'%Cpu\(s\):\s+([\d.]+)\s+us', result.stdout)
            if match:
                return round(float(match.group(1)), 1)
        except Exception:
            pass
        return 0.0

    def _get_memory_usage(self) -> float:
        """Get memory usage percentage"""
        try:
            result = subprocess.run(
                ['free', '-b'],
                capture_output=True,
                text=True,
                timeout=2
            )
            lines = result.stdout.split('\n')
            if len(lines) > 1:
                mem_line = lines[1].split()
                if len(mem_line) >= 3:
                    total = int(mem_line[1])
                    used = int(mem_line[2])
                    percentage = round((used / total) * 100, 1)
                    return percentage
        except Exception:
            pass
        return 0.0

    def apply_stage(self, stage: Stage) -> None:
        if self.dry_run:
            self.logger.info("dry-run stage change -> %s", stage.value)
            return
        self.nft.set_stage(stage)
        self.tc.apply(stage)

    def seed_probe_destinations(self) -> None:
        hosts = []
        captive = self.cfg.probes.get("captive_portal", {}) or {}
        tls_list = self.cfg.probes.get("tls", []) or []
        for entry in tls_list:
            host = entry.get("host")
            if host:
                hosts.append(host)
        if captive.get("url"):
            parsed = urlparse(captive.get("url"))
            if parsed.hostname:
                hosts.append(parsed.hostname)
        ips = []
        for host in hosts:
            try:
                info = socket.getaddrinfo(host, None)
                ips.extend([i[4][0] for i in info if i[4]])
            except socket.gaierror:
                continue
        seed_probe_ips(self.nft, ips)

    def start(self) -> None:
        self.cfg.ensure_dirs()
        self.preflight()
        if not self.dry_run:
            self.apply_sysctl()
            self.nft.apply_base()
            # まずは開放状態 (NORMAL) から開始し、脅威を検知した場合のみ縮退させる
            self.apply_stage(Stage.NORMAL)
            self.start_dnsmasq()
            self.start_dns_observer()
            self.start_status_api()
            self.seed_probe_destinations()
        self.run_loop()

    def stop(self) -> None:
        self.stop_event.set()
        self.stop_dnsmasq()
        if self.status_server:
            self.status_server.shutdown()
        if self.web_server:
            self.web_server.shutdown()
        if not self.dry_run:
            self.tc.clear()
            self.nft.clear()

    def handle_signals(self) -> None:
        signal.signal(signal.SIGTERM, lambda *_: self.stop_event.set())
        signal.signal(signal.SIGINT, lambda *_: self.stop_event.set())

    def _parse_eve_timestamp(self, ts: object) -> Optional[float]:
        if not isinstance(ts, str) or not ts:
            return None
        norm = ts
        if norm.endswith("Z"):
            norm = norm[:-1] + "+00:00"
        if len(norm) >= 5 and norm[-5] in ("+", "-") and norm[-3] != ":":
            norm = f"{norm[:-2]}:{norm[-2:]}"
        try:
            return datetime.fromisoformat(norm).timestamp()
        except ValueError:
            pass
        for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
            try:
                return datetime.strptime(norm, fmt).timestamp()
            except ValueError:
                continue
        return None

    def _read_new_eve_events(self, eve: Path) -> list[Dict[str, object]]:
        try:
            stat = eve.stat()
        except OSError:
            return []
        if not self._eve_initialized:
            self._eve_inode = stat.st_ino
            self._eve_offset = 0  # Start from beginning to catch alerts added during initialization
            self._eve_partial = ""
            self._eve_initialized = True
            # Read once on initialization to catch any events already present
            try:
                with eve.open("r", encoding="utf-8", errors="ignore") as handle:
                    data = handle.read()
                    self._eve_offset = handle.tell()
                    lines = data.splitlines()
                    if data and not data.endswith("\n"):
                        self._eve_partial = lines.pop() if lines else data
                    else:
                        self._eve_partial = ""
                    events = []
                    for line in lines:
                        try:
                            obj = json.loads(line)
                            if isinstance(obj, dict):
                                events.append(obj)
                        except (json.JSONDecodeError, Exception):
                            continue
                    return events
            except Exception:
                return []
        if self._eve_inode is None or stat.st_ino != self._eve_inode:
            self._eve_inode = stat.st_ino
            self._eve_offset = 0
            self._eve_partial = ""
        elif stat.st_size < self._eve_offset:
            self._eve_offset = 0
            self._eve_partial = ""
        try:
            with eve.open("r", encoding="utf-8", errors="ignore") as handle:
                handle.seek(self._eve_offset)
                data = handle.read()
                self._eve_offset = handle.tell()
        except Exception:
            return []
        if not data:
            return []
        data = self._eve_partial + data
        lines = data.splitlines()
        if data and not data.endswith("\n"):
            self._eve_partial = lines.pop() if lines else data
        else:
            self._eve_partial = ""
        events: list[Dict[str, object]] = []
        for line in lines:
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                self._eve_parse_errors["json_decode_fail"] += 1
                continue
            except Exception:
                self._eve_parse_errors["skipped_lines"] += 1
                continue
            if isinstance(obj, dict):
                events.append(obj)
        return events

    def suricata_bumped(self) -> bool:
        eve = Path(self.cfg.suricata.get("eve_path", "/var/log/suricata/eve.json"))
        if not self.cfg.suricata.get("enabled", False) or not eve.exists():
            return False
        events = self._read_new_eve_events(eve)
        if not events:
            return False
        now = time.time()
        found_alert = False
        for event in events:
            if event.get("event_type") != "alert" and "alert" not in event:
                continue
            try:
                sev = int((event.get("alert") or {}).get("severity", 3))
            except Exception:
                sev = 3
            self._last_suricata_severity = max(1, min(3, sev))
            ts = self._parse_eve_timestamp(event.get("timestamp"))
            if ts is not None:
                dt = now - ts
                self.logger.debug(f"[suricata] alert: ts={ts:.0f} sev={sev} dt={dt:.1f}s")
                if dt < 30:
                    found_alert = True
                    return True
        if not found_alert and events:
            self.logger.debug(f"[suricata] {len(events)} alerts found but all outside 30s window")
        return False

    def run_loop(self) -> None:
        self.handle_signals()
        probe_done = False
        while not self.stop_event.is_set():
            # Check for force flags from Status API
            force_reprobe = self.status_ctx.pop("force_reprobe", False)
            force_epd_update = self.status_ctx.pop("force_epd_update", False)
            
            if force_reprobe:
                self.logger.info("ACTION: Force re-probe requested via API")
                probe_done = False  # Force probe re-run
            
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
                
                # ★ DNS 不一致を通知（閾値超過時）
                dns_mismatch_alert_threshold = int(
                    self.cfg.notify.get("thresholds", {}).get("dns_mismatch_alert", 3)
                )
                if self.last_probe.dns_mismatch >= dns_mismatch_alert_threshold:
                    self._notify_signal_alert(
                        signal_type="dns_mismatch",
                        reason=f"DNS mismatch detected: {self.last_probe.dns_mismatch} mismatches",
                        tags=["dns", "warning"],
                    )
                
                probe_done = True

            if self.suricata_bumped():
                signals["suricata_alert"] = True
                signals["suricata_severity"] = max(1, min(3, int(self._last_suricata_severity or 3)))
                
                # ★ Suricata アラートを通知
                severity_name = {1: "Low", 2: "Medium", 3: "High"}.get(
                    int(self._last_suricata_severity or 3), "Unknown"
                )
                self._notify_signal_alert(
                    signal_type="suricata_alert",
                    reason=f"Suricata detected suspicious activity (severity: {severity_name})",
                    tags=["suricata", "ids", severity_name.lower()],
                )

            state, summary = self.state_machine.step(signals)
            if (
                state == Stage.CONTAIN
                and self.cfg.deception.get("enable_if_opencanary_present", False)
                and Path(self.cfg.deception.get("opencanary_cfg", "/etc/opencanaryd/opencanary.conf")).exists()
            ):
                state = Stage.DECEPTION
            if state != self.current_stage:
                # ★ 状態遷移を通知
                self._notify_state_transition(self.current_stage, state)
                
                # Web UI 履歴に記録
                add_history_event(
                    from_stage=self.current_stage.value,
                    to_stage=state.value,
                    suspicion=summary.get("suspicion", 0),
                    reason=summary.get("reason", "")
                )
                self.current_stage = state
                probe_done = state != Stage.PROBE
                self.apply_stage(state)
            
            # Tactics Engine: DecisionRecord を作成・ログ（状態遷移時のみ）
            if state != self.current_stage or "suricata_alert" in signals:
                try:
                    # 簡略版：suricata_alert のみを記録
                    if "suricata_alert" in signals:
                        source = "suricata"
                        event_digest = "sha256:pending"  # 本実装ではeve.json全体のハッシュを想定
                        event_min = None
                    else:
                        source = "internal"
                        event_digest = "sha256:internal"
                        event_min = None

                    state_before = StateSnapshot(
                        state=self.current_stage.value,
                        user_state=str(summary.get("reason", "")),
                        suspicion=float(summary.get("suspicion", 0)),
                        risk_score=0,
                    )
                    state_after = StateSnapshot(
                        state=state.value,
                        user_state=str(summary.get("reason", "")),
                        suspicion=float(summary.get("suspicion", 0)),
                        risk_score=0,
                    )
                    score_delta = ScoreDelta(
                        suspicion_add=max(0.0, float(summary.get("suspicion", 0))),
                        suspicion_decay=0.0,
                    )
                    constraints_triggered = summary.get("constraints", []) if isinstance(summary.get("constraints", []), list) else []

                    chosen = [
                        ChosenAction(
                            action_type="transition",
                            detail={"from": self.current_stage.value, "to": state.value}
                        )
                    ]

                    record = DecisionLogger.create_record(
                        engine_version="0.1.0",
                        config_hash=self.config_hash,
                        inputs_source=source,
                        event_digest=event_digest,
                        event_min=event_min,
                        features={
                            "suricata_alert": "suricata_alert" in signals,
                            "suricata_severity": int(signals.get("suricata_severity", 0)),
                        },
                        state_before=state_before,
                        score_delta=score_delta,
                        constraints_triggered=constraints_triggered,
                        chosen=chosen,
                        state_after=state_after,
                        parse_errors=self._eve_parse_errors.copy(),
                    )
                    self.decision_logger.log_decision(record)
                    self.last_decision_id = record.decision_id
                except Exception as e:
                    self.logger.warning(f"Failed to log decision: {e}")
            
            # Tactics Engine: status_ctx を更新（config_hash は常に含める）
            link = link_meta.get("link", {}) if link_meta else {}
            self.status_ctx.update(
                {
                    "stage": state.value,
                    "suspicion": summary.get("suspicion", 0),
                    "reason": summary.get("reason", ""),
                    "wifi": link_meta,
                    "last_probe": self.last_probe.details if self.last_probe else None,
                    "config_hash": self.config_hash,
                    "last_decision_id": self.last_decision_id,
                    # Web UI 用の追加データ
                    "start_time": getattr(self, "_start_time", time.time()),
                    "upstream_if": self.cfg.interfaces.get("upstream", "wlan0"),
                    "downstream_if": self.cfg.interfaces.get("downstream", "usb0"),
                    "mgmt_ip": self.cfg.interfaces.get("mgmt_ip", "10.55.0.10"),
                    "ssid": (link or {}).get("ssid", "-"),
                    "bssid": (link or {}).get("bssid", "-"),
                    "signal_dbm": (link or {}).get("signal", "-"),
                    "rtt_ms": 180 if state in (Stage.PROBE, Stage.DEGRADED) else 0,
                    "rate_mbps": 2.0 if state == Stage.DEGRADED else 1.0 if state == Stage.PROBE else 0,
                    "last_signals": signals,
                    "degrade_threshold": self.cfg.state_machine.get("degrade_threshold", 20),
                    "normal_threshold": self.cfg.state_machine.get("normal_threshold", 8),
                    "contain_threshold": self.cfg.state_machine.get("contain_threshold", 50),
                    "decay_per_sec": self.cfg.state_machine.get("decay_per_sec", 3),
                    "suricata_cooldown_sec": self.cfg.state_machine.get("suricata_cooldown_sec", 30),
                }
            )
            self.write_snapshot(summary, link_meta)
            self._maybe_update_epd(state, summary, link_meta, force=force_epd_update)
            self._maybe_write_wifi_health(link_meta)
            if self.pretty_console:
                self.render_console(state, summary, link_meta)
            
            # ★ NEW: ログデバウンス
            # 状態遷移時のみ INFO ログ出力；その他は DEBUG
            if summary.get("changed", False):
                # 状態遷移時は常にログ出力
                log_entry = {
                    **self.status_ctx,
                    "transitioned": True,
                }
                self.logger.info(json.dumps(log_entry))
            
            # DEBUG ログ：詳細（毎ループ）
            self.logger.debug(
                f"step: state={state.value} susp={summary.get('suspicion', 0):.1f} "
                f"reason={summary.get('reason', '')} changed={summary.get('changed', False)}"
            )
            
            time.sleep(2.0)
        self.stop()

    def poll_wifi(self) -> tuple[bool, Dict[str, object], bool]:
        tags, meta = evaluate_wifi_safety(
            self.cfg.interfaces["upstream"],
            self.cfg.paths.get("known_db", ""),
            self.cfg.interfaces.get("gateway_ip"),
        )
        link = meta.get("link", {})
        connected = link.get("connected") == "1"
        bssid = link.get("bssid", "")
        new_link = False
        if connected and bssid and bssid != self.state_machine.ctx.last_link_bssid:
            self.state_machine.reset_for_new_link(bssid)
            self.current_stage = Stage.NORMAL
            new_link = True
        meta["wifi_tags"] = tags
        return connected, meta, new_link

    def render_console(self, state: Stage, summary: Dict[str, object], link_meta: Dict[str, object]) -> None:
        # Simple text dashboard; keeps JSON logs intact.
        now = time.time()
        if now - self.last_console < 1:
            return
        self.last_console = now
        link = link_meta.get("link", {}) if link_meta else {}
        ssid = link.get("ssid", "")
        bssid = link.get("bssid", "")
        bar_len = min(20, int(float(summary.get("suspicion", 0)) / 5))
        bar = "#" * bar_len + "." * (20 - bar_len)
        probe = self.last_probe
        probe_lines = []
        if probe:
            probe_lines.append(f"Captive: {'YES' if probe.captive_portal else 'no'}")
            probe_lines.append(f"TLS mismatch: {'YES' if probe.tls_mismatch else 'no'}")
            probe_lines.append(f"DNS mismatch: {probe.dns_mismatch}")
        tags = link_meta.get("wifi_tags", []) if link_meta else []
        out = []
        out.append("\033[2J\033[H")  # clear screen
        out.append("Azazel-Zero First-Minute Control")
        out.append(f"State: {state.value:8}  Suspicion: {summary.get('suspicion', 0):5} [{bar}]")
        out.append(f"Reason: {summary.get('reason','')}")
        out.append(f"Wi-Fi: ssid={ssid} bssid={bssid}")
        if tags:
            out.append(f"Wi-Fi tags: {','.join(tags)}")
        if probe_lines:
            out.append("Probe: " + " | ".join(probe_lines))
        out.append("Ctrl+Cで停止 / JSONログ: first_minute.log")
        sys.stdout.write("\n".join(out) + "\n")
        sys.stdout.flush()
    def _init_notifier(self) -> None:
        """★ ntfy 通知クライアントを初期化（トークンファイルから読込）"""
        try:
            ntfy_cfg = self.cfg.notify.get("ntfy", {})
            token_file = Path(ntfy_cfg.get("token_file", "/etc/azazel/ntfy.token"))
            
            if not token_file.exists():
                self.logger.warning(f"ntfy token file not found: {token_file}, notifications disabled")
                return
            
            token = token_file.read_text().strip()
            if not token:
                self.logger.warning(f"ntfy token file is empty: {token_file}, notifications disabled")
                return
            
            self.notifier = NtfyNotifier(
                base_url=ntfy_cfg.get("base_url", "http://10.55.0.10:8081"),
                token=token,
                topic_alert=ntfy_cfg.get("topic_alert", "azg-alert-critical"),
                topic_info=ntfy_cfg.get("topic_info", "azg-info-status"),
                cooldown_sec=int(ntfy_cfg.get("cooldown_sec", 30)),
            )
            self.logger.info("ntfy notifier initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize ntfy notifier: {e}")
            self.notifier = None
    
    def _notify_state_transition(self, from_stage: Stage, to_stage: Stage) -> None:
        """★ 状態遷移を通知"""
        if not self.notifier:
            return
        
        # 危険側（DEGRADED/CONTAIN）のみアラート通知、それ以外は情報通知
        is_danger = to_stage in (Stage.DEGRADED, Stage.CONTAIN)
        title = f"State: {from_stage.value} → {to_stage.value}"
        event_key = f"state_change:{from_stage.value}->{to_stage.value}"
        
        if is_danger:
            self.notifier.notify_alert(
                title=title,
                body=f"Azazel-Gadget transitioned to {to_stage.value}",
                tags=["state-change", to_stage.value.lower()],
                priority=4,
                event_key=event_key,
            )
        else:
            self.notifier.notify_info(
                title=title,
                body=f"Azazel-Gadget transitioned to {to_stage.value}",
                tags=["state-change", to_stage.value.lower()],
                priority=2,
                event_key=event_key,
            )
    
    def _notify_signal_alert(self, signal_type: str, reason: str, tags: Optional[list] = None) -> None:
        """★ シグナルアラートを通知（suricata, dns_mismatch など）"""
        if not self.notifier:
            return
        
        event_key = f"signal:{signal_type}"
        tag_list = tags or [signal_type.lower()]
        
        self.notifier.notify_alert(
            title=f"Signal Alert: {signal_type}",
            body=reason,
            tags=tag_list,
            priority=5,
            event_key=event_key,
        )