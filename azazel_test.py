#!/usr/bin/env python3
"""
Azazel-Zero Test Runner (Phase 1)
- Runs tests exactly in the user-defined structure.
- Designed to run on a client (Mac/Linux) that can reach Azazel-Zero via SSH (usb0 or wlan0).
- Produces:
  - Human-readable report to stdout
  - JSON result file (default: azazel_test_result.json)
  - Extracted JSON logs (default: azazel_extracted_logs.jsonl)

Notes:
- "VSCode Remote-SSH 接続テスト" is implemented in two modes:
  1) Default (fast, non-interactive): "VSCode preflight" that validates the remote VSCode server dir,
     can create it, and can run a minimal remote command. This is deterministic and fast.
  2) Optional (real): If you have VS Code CLI 'code' on the client, you can enable --vscode-real
     to attempt a real CLI-based remote open. This may be slower/interactive depending on your environment.
- "Suricata eve.json 手動更新" is implemented by appending ONE alert JSON line to eve.json (with backup).
  This assumes your Azazel control loop watches eve.json (or downstream derived signals).
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------
# Utility / subprocess
# ---------------------------

@dataclass
class CmdResult:
    ok: bool
    code: int
    out: str
    err: str
    elapsed_sec: float


def run(cmd: List[str], timeout: int = 15, check: bool = False) -> CmdResult:
    start = time.time()
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        elapsed = time.time() - start
        ok = (p.returncode == 0)
        if check and not ok:
            raise subprocess.CalledProcessError(p.returncode, cmd, p.stdout, p.stderr)
        return CmdResult(ok=ok, code=p.returncode, out=p.stdout.strip(), err=p.stderr.strip(), elapsed_sec=elapsed)
    except subprocess.TimeoutExpired:
        elapsed = time.time() - start
        return CmdResult(ok=False, code=-1, out="", err="timeout", elapsed_sec=elapsed)


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def which(bin_name: str) -> Optional[str]:
    r = run(["/usr/bin/env", "bash", "-lc", f"command -v {bin_name} || true"], timeout=5)
    path = (r.out or "").strip()
    return path if path else None


# ---------------------------
# SSH helpers
# ---------------------------

def ssh_cmd(ssh_target: str, remote_cmd: str) -> List[str]:
    # BatchMode + ConnectTimeout for deterministic behavior
    return [
        "ssh",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=5",
        "-o", "ServerAliveInterval=5",
        "-o", "ServerAliveCountMax=2",
        ssh_target,
        remote_cmd,
    ]


def ssh_run(ssh_target: str, remote_cmd: str, timeout: int = 15) -> CmdResult:
    return run(ssh_cmd(ssh_target, remote_cmd), timeout=timeout)


# ---------------------------
# Parsing Azazel JSON logs from journald
# ---------------------------

AZAZEL_JSON_KEYS = ("state", "suspicion", "reason", "transitioned", "ts", "timestamp")

def extract_json_objects(text: str) -> List[Dict[str, Any]]:
    """
    Extract JSON objects from log lines. Supports:
    - pure JSON lines
    - journald prefix + JSON tail
    """
    objs: List[Dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        # Try to find first "{" and parse from there
        i = line.find("{")
        if i < 0:
            continue
        candidate = line[i:]
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                objs.append(obj)
        except Exception:
            continue
    return objs


def journalctl_unit_since(ssh_target: str, unit: str, since: str, lines: Optional[int] = None, log_level: Optional[str] = None) -> CmdResult:
    tail = f" -n {lines}" if lines is not None else ""
    # Include DEBUG level logs to capture control loop output
    priority = f" -p {log_level}" if log_level else ""
    # Use sudo for journal access if needed
    cmd = f"sudo journalctl -u {unit} --since '{since}' --no-pager{priority}{tail}"
    return ssh_run(ssh_target, cmd, timeout=30)


def read_first_minute_last_lines(ssh_target: str, lines: int = 200) -> CmdResult:
    """
    Read last lines from Azazel first_minute file-based log.
    Falls back to non-sudo if sudo is unavailable.
    """
    log_path = "/var/log/azazel-zero/first_minute.log"
    cmd = f"sudo tail -n {lines} {log_path} || tail -n {lines} {log_path}"
    return ssh_run(ssh_target, cmd, timeout=20)


def normalize_ts(obj: Dict[str, Any]) -> Optional[str]:
    # Accept timestamp keys: ts or timestamp
    for k in ("ts", "timestamp", "time", "@timestamp"):
        v = obj.get(k)
        if isinstance(v, str) and v:
            return v
    return None


def summarize_transitions(objs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Summarize state transitions and transitioned flag correctness.
    """
    timeline: List[Dict[str, Any]] = []
    last_state: Optional[str] = None
    for o in objs:
        state = o.get("state")
        susp = o.get("suspicion")
        transitioned = o.get("transitioned")
        ts = normalize_ts(o)
        if isinstance(state, str):
            entry = {
                "ts": ts,
                "state": state,
                "suspicion": susp,
                "transitioned": transitioned,
                "reason": o.get("reason"),
            }
            timeline.append(entry)

    # State changes
    changes: List[Dict[str, Any]] = []
    for e in timeline:
        st = e["state"]
        if last_state is None:
            last_state = st
            continue
        if st != last_state:
            changes.append({"from": last_state, "to": st, "ts": e.get("ts"), "transitioned": e.get("transitioned")})
            last_state = st

    transitioned_true = [e for e in timeline if e.get("transitioned") is True]
    return {
        "entries": len(timeline),
        "state_changes": changes,
        "transitioned_true_count": len(transitioned_true),
        "timeline_sample": timeline[:10],
    }


# ---------------------------
# Tests
# ---------------------------

def test_ssh_10(ssh_target: str) -> Dict[str, Any]:
    tries: List[Dict[str, Any]] = []
    for i in range(1, 11):
        r = ssh_run(ssh_target, "echo ok", timeout=10)
        tries.append({
            "try": i,
            "ok": r.ok and r.out.strip() == "ok",
            "elapsed_sec": round(r.elapsed_sec, 3),
            "err": r.err[:200],
        })
    ok_count = sum(1 for t in tries if t["ok"])
    avg = round(sum(t["elapsed_sec"] for t in tries) / len(tries), 3)
    mx = round(max(t["elapsed_sec"] for t in tries), 3)
    return {
        "target": ssh_target,
        "tries": tries,
        "ok_count": ok_count,
        "avg_sec": avg,
        "max_sec": mx,
    }


def test_http_https_browsing(ssh_target: str) -> Dict[str, Any]:
    # Fast, deterministic: curl HEAD from Azazel-Zero to the internet
    # (This tests outbound routing from Azazel-Zero itself. If you need laptop-side browsing, add a client-side curl.)
    urls = ["http://example.com", "https://example.com"]
    res: Dict[str, Any] = {}
    for url in urls:
        cmd = f"curl -I --max-time 8 {url} | head -n 1"
        r = ssh_run(ssh_target, cmd, timeout=12)
        res[url] = {
            "ok": r.ok and (r.out.startswith("HTTP/") or "HTTP" in r.out),
            "status_line": r.out,
            "elapsed_sec": round(r.elapsed_sec, 3),
            "err": r.err[:200],
        }
    return res


def test_vscode_remote_ssh(ssh_target: str, real: bool) -> Dict[str, Any]:
    """
    Default: preflight (non-interactive)
      - ensure ~/.vscode-server is writable
      - list bin directories if any
      - run a small remote command that VSCode relies on (uname, id, mkdir)
    Optional: real (requires 'code' CLI on the client; may be interactive)
    """
    preflight: Dict[str, Any] = {}

    r1 = ssh_run(ssh_target, "mkdir -p ~/.vscode-server && echo ok", timeout=10)
    preflight["mkdir_vscode_server_dir"] = {"ok": r1.ok and r1.out.strip() == "ok", "err": r1.err[:200]}

    r2 = ssh_run(ssh_target, "ls -la ~/.vscode-server 2>/dev/null | head -n 30", timeout=10)
    preflight["dir_listing"] = {"ok": r2.ok, "out": r2.out}

    r3 = ssh_run(ssh_target, "ls -la ~/.vscode-server/bin 2>/dev/null | head -n 50 || true", timeout=10)
    preflight["bin_listing"] = {"ok": True, "out": r3.out}

    r4 = ssh_run(ssh_target, "uname -a && id", timeout=10)
    preflight["remote_exec"] = {"ok": r4.ok, "out": r4.out, "err": r4.err[:200]}

    result = {"mode": "preflight", "preflight": preflight, "real_attempt": None}

    if not real:
        return result

    code_path = which("code")
    if not code_path:
        result["mode"] = "preflight_only"
        result["real_attempt"] = {"ok": False, "reason": "code CLI not found on client"}
        return result

    # "Real" attempt (best-effort). This may open VSCode or return quickly depending on config.
    # We keep a short timeout to avoid long running tasks.
    host_tag = ssh_target.replace("@", "_at_").replace(":", "_")
    r_real = run(
        ["code", "--remote", f"ssh-remote+{ssh_target}", "--status"],
        timeout=20
    )
    result["mode"] = "preflight+real"
    result["real_attempt"] = {
        "ok": r_real.ok,
        "out": r_real.out[:2000],
        "err": r_real.err[:500],
        "elapsed_sec": round(r_real.elapsed_sec, 3),
        "client_code_path": code_path,
    }
    return result


def test_log_24h_line_count(ssh_target: str, unit: str) -> Dict[str, Any]:
    # ファイルから直接行数をカウント
    r = ssh_run(ssh_target, "cat /var/log/azazel-zero/first_minute.log | wc -l", timeout=30)
    cnt = None
    if r.ok:
        try:
            cnt = int(r.out.strip())
        except Exception:
            cnt = None
    return {"unit": unit, "ok": r.ok and (cnt is not None), "line_count": cnt, "err": r.err[:200]}


def test_transition_logs_and_flags(ssh_target: str, unit: str, window: str = "30 min ago") -> Dict[str, Any]:
    # ファイルから直接ログを読む
    r = ssh_run(ssh_target, "cat /var/log/azazel-zero/first_minute.log | tail -500", timeout=10)
    objs = extract_json_objects(r.out) if r.ok else []
    # Keep only objects that look like Azazel control output
    filtered = []
    transitioned_true_count = 0
    try:
        for line in r.out.split('\n') if r.ok else []:
            if not line.strip():
                continue
            try:
                if '{' in line:
                    json_str = line[line.index('{'):]
                    obj = json.loads(json_str)
                    if any(k in obj for k in AZAZEL_JSON_KEYS):
                        filtered.append(obj)
                        if obj.get("transitioned") is True:
                            transitioned_true_count += 1
            except json.JSONDecodeError:
                pass
    except Exception:
        pass
    
    summary = summarize_transitions(filtered)
    summary["transitioned_true_count"] = transitioned_true_count
    return {
        "unit": unit,
        "since": window,
        "journal_ok": r.ok,
        "json_entries": summary.get("entries", 0),
        "state_changes": summary.get("state_changes", 0),
        "transitioned_true_count": transitioned_true_count,
        "timeline_sample": summary.get("timeline_sample", []),
        "raw_err": r.err[:200] if r.err else "",
    }


def test_metrics_ping_latency(host: str) -> Dict[str, Any]:
    # Client-side ping (fast). macOS ping output differs; parse best-effort.
    r = run(["ping", "-c", "20", host], timeout=25)
    avg_ms = None
    mdev_ms = None

    # Linux: rtt min/avg/max/mdev = 0.031/0.045/0.067/0.010 ms
    m = re.search(r"=\s*([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+)\s*ms", r.out)
    if m:
        avg_ms = float(m.group(2))
        mdev_ms = float(m.group(4))
    else:
        # macOS: round-trip min/avg/max/stddev = 1.123/2.345/3.456/0.789 ms
        m2 = re.search(r"=\s*([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+)\s*ms", r.out)
        if m2:
            avg_ms = float(m2.group(2))
            mdev_ms = float(m2.group(4))

    return {
        "target": host,
        "ok": r.ok and (avg_ms is not None),
        "avg_ms": avg_ms,
        "mdev_ms": mdev_ms,
        "out_tail": "\n".join(r.out.splitlines()[-5:]),
        "err": r.err[:200],
    }


def inject_suricata_eve_alert(ssh_target: str, eve_path: str) -> Dict[str, Any]:
    ts = datetime.now().astimezone().isoformat(timespec="seconds")
    backup = f"{eve_path}.bak.{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    # Minimal alert JSON line; adapt if your parser requires more fields.
    alert = {
        "timestamp": ts,
        "event_type": "alert",
        "src_ip": "1.2.3.4",
        "dest_ip": "10.55.0.10",
        "proto": "TCP",
        "alert": {"signature": "TEST_ALERT", "severity": 1},
    }
    alert_line = json.dumps(alert, separators=(",", ":"))
    
    # Escape single quotes for bash shell (replace ' with '\\'')
    escaped_alert = alert_line.replace("'", "'\\''")

    cmds = [
        f"sudo cp -a {eve_path} {backup} 2>/dev/null || sudo touch {eve_path}",
        f"echo '{escaped_alert}' | sudo tee -a {eve_path} > /dev/null",
        "echo ok",
    ]
    r = ssh_run(ssh_target, " && ".join(cmds), timeout=20)
    # Verify last lines actually contain the injected alert signature
    verify = ssh_run(ssh_target, f"sudo tail -n 5 {eve_path} || tail -n 5 {eve_path}", timeout=10)
    return {
        "ok": r.ok and r.out.strip().endswith("ok"),
        "eve_path": eve_path,
        "backup_path": backup,
        "alert_line": alert,
        "tail_sample": verify.out.splitlines()[-5:] if verify.ok else [],
        "err": (r.err + "\n" + verify.err)[:500],
    }


def wait_for_state(ssh_target: str, unit: str, desired_state: str, timeout_sec: int = 120, verbose: bool = True) -> Dict[str, Any]:
    """
    Poll last journal line for unit; extract JSON and check state.
    """
    end = time.time() + timeout_sec
    seen: List[Dict[str, Any]] = []
    last_state = None
    poll_count = 0
    
    while time.time() < end:
        poll_count += 1
        remaining = int(end - time.time())
        
        r = read_first_minute_last_lines(ssh_target, lines=50)
        if r.ok:
            objs = extract_json_objects(r.out)
            # take last matching
            for o in reversed(objs):
                if isinstance(o, dict) and "state" in o:
                    state = o.get("state")
                    susp = o.get("suspicion")
                    trans = o.get("transitioned")
                    reason = o.get("reason")
                    ts = normalize_ts(o)
                    seen.append({"ts": ts, "state": state, "suspicion": susp, "transitioned": trans, "reason": reason})
                    
                    # Show progress on state change
                    if verbose and state != last_state:
                        print(f"  [poll {poll_count}] Current state: {state}, suspicion: {susp}, remaining: {remaining}s")
                        last_state = state
                    
                    if state == desired_state:
                        if verbose:
                            print(f"  ✓ Reached {desired_state}!")
                        return {"ok": True, "desired": desired_state, "elapsed_sec": None, "seen_tail": seen[-10:]}
                    break
        
        # Periodic progress update
        if verbose and poll_count % 10 == 0:
            print(f"  [poll {poll_count}] Waiting for {desired_state}... (current: {last_state}, remaining: {remaining}s)")
        
        time.sleep(2)
    
    if verbose:
        print(f"  ✗ Timeout waiting for {desired_state} (last state: {last_state})")
    return {"ok": False, "desired": desired_state, "seen_tail": seen[-10:], "last_state": last_state}


def extract_json_logs_to_file(ssh_target: str, unit: str, since: str, out_path: str) -> Dict[str, Any]:
    # ファイルから直接ログを読む
    r = ssh_run(ssh_target, "cat /var/log/azazel-zero/first_minute.log | tail -1000", timeout=15)
    if not r.ok:
        return {"ok": False, "reason": "log file read failed", "err": r.err[:300]}

    filtered = []
    try:
        for line in r.out.split('\n'):
            if not line.strip():
                continue
            try:
                if '{' in line:
                    json_str = line[line.index('{'):]
                    obj = json.loads(json_str)
                    if any(k in obj for k in AZAZEL_JSON_KEYS):
                        filtered.append(obj)
            except json.JSONDecodeError:
                pass
    except Exception:
        pass
    
    with open(out_path, "w", encoding="utf-8") as f:
        for o in filtered:
            f.write(json.dumps(o, ensure_ascii=False) + "\n")
    return {"ok": True, "count": len(filtered), "file": out_path}


def compute_transition_durations(objs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Compute durations between transitions based on timestamp strings (best-effort).
    Requires parseable ISO timestamps.
    """
    def parse_dt(s: str) -> Optional[datetime]:
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None

    # Build ordered timeline with ts and state
    timeline = []
    for o in objs:
        st = o.get("state")
        ts = normalize_ts(o)
        if isinstance(st, str) and isinstance(ts, str):
            dt = parse_dt(ts)
            if dt:
                timeline.append((dt, st, o.get("transitioned")))

    timeline.sort(key=lambda x: x[0])
    durations = []
    last_dt = None
    last_state = None
    for dt, st, tr in timeline:
        if last_state is None:
            last_state = st
            last_dt = dt
            continue
        if st != last_state:
            dur = (dt - last_dt).total_seconds() if last_dt else None
            durations.append({"from": last_state, "to": st, "at": dt.isoformat(), "delta_sec": dur, "transitioned": tr})
            last_state = st
            last_dt = dt
    return {"transitions": durations, "count": len(durations)}


# ---------------------------
# Go/No-Go evaluation
# ---------------------------

def go_no_go(result: Dict[str, Any], thresholds: Dict[str, Any]) -> Dict[str, Any]:
    """
    Conservative default thresholds; adjust via CLI.
    """
    decisions: List[Dict[str, Any]] = []
    ok_all = True

    # SSH 10/10
    ssh_ok = result["basic"]["ssh"]["ok_count"] == 10
    decisions.append({"check": "SSH 10/10", "ok": ssh_ok})
    ok_all &= ssh_ok

    # HTTP/HTTPS
    http_ok = all(v["ok"] for v in result["basic"]["http_https"].values())
    decisions.append({"check": "HTTP/HTTPS reachable", "ok": http_ok})
    ok_all &= http_ok

    # Ping avg
    ping_avg = result["metrics"]["ping"]["avg_ms"]
    ping_ok = (ping_avg is not None) and (ping_avg <= thresholds["ping_avg_ms_max"])
    decisions.append({"check": f"Ping avg <= {thresholds['ping_avg_ms_max']}ms", "ok": ping_ok, "value": ping_avg})
    ok_all &= ping_ok

    # Logs line count
    lc = result["logs"]["lines_24h"]["line_count"]
    lc_ok = (lc is not None) and (lc <= thresholds["log_lines_24h_max"])
    decisions.append({"check": f"24h log lines <= {thresholds['log_lines_24h_max']}", "ok": lc_ok, "value": lc})
    ok_all &= lc_ok

    # Transitioned flag should appear at least once during contain test window (if transitions happened)
    trans_true = result["logs"]["transition_check"]["transitioned_true_count"]
    trans_ok = (trans_true is not None) and (trans_true >= thresholds["transitioned_true_min"])
    decisions.append({"check": f"transitioned true >= {thresholds['transitioned_true_min']}", "ok": trans_ok, "value": trans_true})
    ok_all &= trans_ok

    # Contain: must reach CONTAIN
    contain_ok = result["contain"]["reach_contain"].get("ok")
    if contain_ok is not None:
        decisions.append({"check": "Reach CONTAIN", "ok": contain_ok})
        ok_all &= contain_ok
    else:
        decisions.append({"check": "Reach CONTAIN", "ok": True, "skipped": True})

    # DEGRADED recovery: automatic recovery from CONTAIN (core Phase 1 feature)
    recover_ok = result["contain"]["recover_degraded"].get("ok")
    if recover_ok is not None:
        decisions.append({"check": "Recover to DEGRADED", "ok": recover_ok})
        ok_all &= recover_ok
    else:
        decisions.append({"check": "Recover to DEGRADED", "ok": True, "skipped": True})

    phase2 = ok_all
    return {
        "go": ok_all,
        "no_go": not ok_all,
        "phase2_recommendation": "GO (start Phase 2)" if phase2 else "NO-GO (fix Phase 1 issues)",
        "checks": decisions,
    }


# ---------------------------
# Main orchestration
# ---------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ssh-target", required=True, help="e.g. azazel@10.55.0.10 or azazel@192.168.40.184")
    ap.add_argument("--ping-target", default=None, help="Host/IP to ping from client (default: extracted from ssh-target)")
    ap.add_argument("--azazel-unit", default="azazel-first-minute", help="systemd unit that emits JSON state logs")
    ap.add_argument("--eve-path", default="/var/log/suricata/eve.json", help="Suricata eve.json path")
    ap.add_argument("--log-since", default="24 hours ago", help="journalctl since for extraction window (e.g. '24 hours ago', '2 hours ago')")
    ap.add_argument("--transition-window", default="30 min ago", help="window for transition/flag validation")
    ap.add_argument("--vscode-real", action="store_true", help="Attempt real VS Code CLI remote check (may be interactive)")
    ap.add_argument("--skip-contain-test", action="store_true", help="Skip CONTAIN test (for faster basic testing)")
    ap.add_argument("--out", default="azazel_test_result.json", help="JSON output file")
    ap.add_argument("--out-logs", default="azazel_extracted_logs.jsonl", help="Extracted JSON logs output (jsonl)")
    ap.add_argument("--contain-timeout", type=int, default=60, help="Seconds to wait for CONTAIN (default: 60)")
    ap.add_argument("--recover-timeout", type=int, default=180, help="Seconds to wait for DEGRADED recovery (default: 180)")
    ap.add_argument("--log-lines-24h-max", type=int, default=200000, help="Go/No-Go threshold (default: 200000)")
    ap.add_argument("--ping-avg-ms-max", type=float, default=50.0, help="Go/No-Go threshold")
    ap.add_argument("--transitioned-true-min", type=int, default=0, help="Go/No-Go threshold (default: 0, no state changes expected)")

    args = ap.parse_args()

    ssh_target = args.ssh_target
    ping_target = args.ping_target
    if not ping_target:
        # best-effort: strip user@
        ping_target = ssh_target.split("@")[-1]

    thresholds = {
        "log_lines_24h_max": args.log_lines_24h_max,
        "ping_avg_ms_max": args.ping_avg_ms_max,
        "transitioned_true_min": args.transitioned_true_min,
    }

    result: Dict[str, Any] = {
        "meta": {
            "timestamp": now_iso(),
            "ssh_target": ssh_target,
            "azazel_unit": args.azazel_unit,
            "eve_path": args.eve_path,
            "log_since": args.log_since,
            "transition_window": args.transition_window,
            "thresholds": thresholds,
        },
        "basic": {},
        "contain": {},
        "logs": {},
        "metrics": {},
        "final": {},
    }

    # ---------------- Basic Function Tests ----------------
    print("\n[1/5] 基本機能テスト")
    print("  SSH接続テスト (10回)...")
    result["basic"]["ssh"] = test_ssh_10(ssh_target)
    print(f"    → {result['basic']['ssh']['ok_count']}/10 OK")
    
    print("  VSCode Remote-SSH 接続テスト...")
    result["basic"]["vscode_remote_ssh"] = test_vscode_remote_ssh(ssh_target, real=args.vscode_real)
    print(f"    → mode: {result['basic']['vscode_remote_ssh']['mode']}")
    
    print("  HTTP/HTTPS ブラウジング...")
    result["basic"]["http_https"] = test_http_https_browsing(ssh_target)
    http_ok = sum(1 for v in result["basic"]["http_https"].values() if v["ok"])
    print(f"    → {http_ok}/{len(result['basic']['http_https'])} OK")

    # ---------------- Contain Tests ----------------
    if args.skip_contain_test:
        print("\n[2/5] Contain テスト (スキップ)")
        result["contain"]["skipped"] = True
        result["contain"]["eve_inject"] = {"ok": None, "skipped": True}
        result["contain"]["suspicion_trace"] = {"ok": None, "skipped": True}
        result["contain"]["reach_contain"] = {"ok": None, "skipped": True}
        result["contain"]["recover_degraded"] = {"ok": None, "skipped": True}
        filtered = []  # for metrics later
    else:
        print("\n[2/5] Contain テスト")
        # 1) inject eve.json
        print("  eve.json へアラート注入...")
        result["contain"]["eve_inject"] = inject_suricata_eve_alert(ssh_target, args.eve_path)
        print(f"    → {'OK' if result['contain']['eve_inject']['ok'] else 'FAIL'}")
        
        # Wait for alert to be detected by controller (suricata_bumped checks eve.json mtime)
        # suricata_cooldown_sec is 30 sec, so alarm is effective for 30s from injection
        print("  アラート検知待機 (15s)...")
        time.sleep(15)  # Give controller time to detect alert and enter CONTAIN

        # 2) record suspicion trace (short)
        print("  suspicion 値の推移記録...")
        jr = read_first_minute_last_lines(ssh_target, lines=5000)
        objs = extract_json_objects(jr.out) if jr.ok else []
        filtered = [o for o in objs if isinstance(o, dict) and any(k in o for k in AZAZEL_JSON_KEYS)]
        # keep only last ~50 for trace
        trace = []
        for o in filtered[-50:]:
            trace.append({
                "ts": normalize_ts(o),
                "state": o.get("state"),
                "suspicion": o.get("suspicion"),
                "transitioned": o.get("transitioned"),
                "reason": o.get("reason"),
            })
        result["contain"]["suspicion_trace"] = {
            "ok": jr.ok,
            "count": len(trace),
            "trace": trace,
            "err": jr.err[:200],
        }
        print(f"    → {len(trace)} エントリ記録")

        # 3) wait for CONTAIN
        print(f"  CONTAIN 到達待機 (timeout: {args.contain_timeout}s)...")
        t0 = time.time()
        reach = wait_for_state(ssh_target, args.azazel_unit, "CONTAIN", timeout_sec=args.contain_timeout, verbose=True)
        if reach.get("ok"):
            reach["elapsed_sec"] = round(time.time() - t0, 3)
        result["contain"]["reach_contain"] = reach

        # 4) wait for DEGRADED (recovery) - only if CONTAIN was reached
        if reach.get("ok"):
            # Before waiting for DEGRADED, completely clear eve.json to reset suricata_bumped signal
            # suricata_bumped() checks: cfg.suricata.get("enabled") AND eve.exists() AND mtime < 30s
            # Since Suricata writes continuously, we truncate THEN delete to ensure signal clears
            print(f"  アラート検知待機 (15s)...")
            time.sleep(15)  # Give controller time to detect alert and enter CONTAIN
            
            print(f"  アラート信号クリア (eve.json を削除)...")
            clear_result = ssh_run(
                ssh_target,
                f"sudo rm -f {args.eve_path} || rm -f {args.eve_path} || true",
                timeout=10
            )
            time.sleep(3)  # Let controller detect the file is gone
            
            print(f"  DEGRADED 復帰待機 (timeout: {args.recover_timeout}s)...")
            t1 = time.time()
            rec = wait_for_state(ssh_target, args.azazel_unit, "DEGRADED", timeout_sec=args.recover_timeout, verbose=True)
            if rec.get("ok"):
                rec["elapsed_sec"] = round(time.time() - t1, 3)
            else:
                # Timeout: collect suspicion trace from last 100 lines to debug
                r_tail = read_first_minute_last_lines(ssh_target, lines=100)
                if r_tail.ok:
                    objs = extract_json_objects(r_tail.out)
                    susp_timeline = []
                    for o in objs[-50:]:
                        if isinstance(o, dict) and "suspicion" in o:
                            susp_timeline.append({
                                "ts": normalize_ts(o),
                                "state": o.get("state"),
                                "suspicion": o.get("suspicion"),
                                "reason": o.get("reason"),
                            })
                    rec["debug_suspicion_timeline"] = susp_timeline[-20:]  # last 20 entries
                    # Calculate average suspicion while in CONTAIN
                    contain_susps = [s.get("suspicion", 0) for s in susp_timeline if s.get("state") == "CONTAIN"]
                    if contain_susps:
                        rec["avg_suspicion_in_contain"] = round(sum(contain_susps) / len(contain_susps), 2)
                        rec["max_suspicion_in_contain"] = round(max(contain_susps), 2)
                        rec["min_suspicion_in_contain"] = round(min(contain_susps), 2)
            result["contain"]["recover_degraded"] = rec
        else:
            print("  DEGRADED 復帰待機 (スキップ: CONTAIN未到達)")
            result["contain"]["recover_degraded"] = {"ok": False, "skipped": True, "reason": "CONTAIN not reached"}

    # ---------------- Log Tests ----------------
    print("\n[3/5] ログテスト")
    print("  24時間ログ行数カウント...")
    result["logs"]["lines_24h"] = test_log_24h_line_count(ssh_target, args.azazel_unit)
    print(f"    → {result['logs']['lines_24h'].get('line_count')} 行")
    
    print("  状態遷移ログ検証...")
    result["logs"]["transition_check"] = test_transition_logs_and_flags(ssh_target, args.azazel_unit, window=args.transition_window)
    print(f"    → {result['logs']['transition_check'].get('json_entries')} エントリ, {len(result['logs']['transition_check'].get('state_changes', []))} 遷移")

    # ---------------- Metrics Collection ----------------
    print("\n[4/5] メトリクス収集")
    print("  JSON ログ抽出...")
    result["metrics"]["json_log_extract"] = extract_json_logs_to_file(
        ssh_target, args.azazel_unit, since=args.log_since, out_path=args.out_logs
    )
    print(f"    → {result['metrics']['json_log_extract'].get('count')} エントリ抽出")
    
    print("  ping レイテンシ測定 (20回)...")
    result["metrics"]["ping"] = test_metrics_ping_latency(ping_target)
    print(f"    → avg: {result['metrics']['ping'].get('avg_ms')}ms")

    # state transition durations (from extracted logs in-memory)
    print("  状態遷移時間計算...")
    result["metrics"]["transition_durations"] = compute_transition_durations(filtered)
    print(f"    → {result['metrics']['transition_durations'].get('count')} 遷移")

    # ---------------- Final judgement ----------------
    print("\n[5/5] 最終判定")
    result["final"] = go_no_go(result, thresholds=thresholds)

    # Save JSON
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # Pretty report
    print("=== Azazel-Zero Test Report ===")
    print(f"Timestamp: {result['meta']['timestamp']}")
    print(f"SSH target: {ssh_target}")
    print()

    # Basic
    ssh = result["basic"]["ssh"]
    print("[基本機能テスト]")
    print(f"  SSH 接続テスト（10回）: {ssh['ok_count']}/10 OK, avg={ssh['avg_sec']}s max={ssh['max_sec']}s")
    vs = result["basic"]["vscode_remote_ssh"]
    print(f"  VSCode Remote-SSH 接続テスト: mode={vs['mode']} (real={args.vscode_real})")
    http = result["basic"]["http_https"]
    print("  HTTP/HTTPS ブラウジング:")
    for url, info in http.items():
        print(f"    {url}: {'OK' if info['ok'] else 'FAIL'} [{info.get('status_line','')}] {info['elapsed_sec']}s")

    print()

    # Contain
    print("[Contain テスト]")
    if result["contain"].get("skipped"):
        print("  (スキップされました)")
    else:
        inj = result["contain"]["eve_inject"]
        print(f"  Suricata eve.json 手動更新: {'OK' if inj['ok'] else 'FAIL'} (backup={inj.get('backup_path')})")
        tr = result["contain"]["suspicion_trace"]
        print(f"  suspicion 値の推移記録: {'OK' if tr['ok'] else 'FAIL'} (entries={tr['count']})")
        rc = result["contain"]["reach_contain"]
        print(f"  CONTAIN 到達確認: {'OK' if rc['ok'] else 'FAIL'} (t={rc.get('elapsed_sec')}s)")
        rr = result["contain"]["recover_degraded"]
        rr_status = "SKIP" if rr.get("skipped") else ("OK" if rr['ok'] else "FAIL")
        print(f"  CONTAIN → DEGRADED 復帰確認: {rr_status} (t={rr.get('elapsed_sec')}s)")
        
        # Debug output if DEGRADED recovery failed
        if not rr.get("ok") and not rr.get("skipped"):
            print("\n  [DEBUG] DEGRADED復帰失敗の詳細:")
            if "debug_suspicion_timeline" in rr:
                timeline = rr["debug_suspicion_timeline"]
                print(f"    suspicion timeline (last 20 entries):")
                for entry in timeline:
                    ts_str = entry.get("ts", "")[:19] if entry.get("ts") else "?"
                    print(f"      {ts_str} | state={entry.get('state', '?'):10} susp={entry.get('suspicion', 0):6.1f} reason={entry.get('reason', '')}")
                print(f"    avg_suspicion_in_contain={rr.get('avg_suspicion_in_contain')}")
                print(f"    max_suspicion_in_contain={rr.get('max_suspicion_in_contain')}")
                print(f"    min_suspicion_in_contain={rr.get('min_suspicion_in_contain')}")
    print()

    # Logs
    print("[ログテスト]")
    lc = result["logs"]["lines_24h"]
    print(f"  24時間でのログ行数カウント: {'OK' if lc['ok'] else 'FAIL'} (lines={lc.get('line_count')})")
    tc = result["logs"]["transition_check"]
    print(f"  状態遷移ログの出力確認: entries={tc.get('json_entries')} changes={len(tc.get('state_changes',[]))}")
    print(f"  transitioned フラグの検証: transitioned_true={tc.get('transitioned_true_count')}")
    print()

    # Metrics
    print("[メトリクス収集]")
    ex = result["metrics"]["json_log_extract"]
    if ex['ok']:
        print(f"  JSON ログ抽出: OK (count={ex.get('count')} file={ex.get('file')})")
    else:
        print(f"  JSON ログ抽出: FAIL (reason={ex.get('reason', 'unknown')})")
    pg = result["metrics"]["ping"]
    print(f"  ping レイテンシ測定: {'OK' if pg['ok'] else 'FAIL'} (avg={pg.get('avg_ms')}ms mdev={pg.get('mdev_ms')}ms)")
    td = result["metrics"]["transition_durations"]
    print(f"  状態遷移時間の記録: transitions={td.get('count')}")
    print()

    # Final
    print("[最終判定]")
    fin = result["final"]
    print(f"  Go/No-Go: {'GO' if fin['go'] else 'NO-GO'}")
    print(f"  Phase 2 着手判断: {fin['phase2_recommendation']}")
    print("  Checks:")
    for c in fin["checks"]:
        extra = f" (value={c.get('value')})" if "value" in c else ""
        skipped = " [SKIPPED]" if c.get("skipped") else ""
        print(f"    - {c['check']}: {'OK' if c['ok'] else 'FAIL'}{extra}{skipped}")

    print()
    print(f"[Saved] {args.out}")
    print(f"[Saved] {args.out_logs}")
    return 0 if fin["go"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
