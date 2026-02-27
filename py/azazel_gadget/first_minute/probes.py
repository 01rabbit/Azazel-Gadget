from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import ssl
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from shutil import which
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse


SAFE_TOKEN_RE = re.compile(r"^[a-zA-Z0-9_.:-]+$")
APPLE_CAPTIVE_HOST = "captive.apple.com"


@dataclass
class ProbeOutcome:
    captive_portal: bool
    captive_status: str
    captive_reason: str
    captive_checked_at: str
    captive_iface: str
    tls_mismatch: bool
    dns_mismatch: int
    route_anomaly: bool
    details: Dict[str, object]


def _now_iso8601() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_location(headers: str) -> str:
    for line in headers.splitlines():
        if line.lower().startswith("location:"):
            return line.split(":", 1)[1].strip()
    return ""


def _iface_ready_for_probe(iface: str) -> Tuple[bool, str, Dict[str, object]]:
    detail: Dict[str, object] = {"iface": iface}
    if not SAFE_TOKEN_RE.match(iface):
        return False, "INVALID_IFACE", detail
    try:
        link_raw = subprocess.check_output(
            ["ip", "-j", "link", "show", "dev", iface],
            text=True,
            timeout=2,
        )
        link_data = json.loads(link_raw) or []
        if not link_data:
            return False, "NOT_FOUND", detail
        operstate = str(link_data[0].get("operstate", "")).upper()
        detail["operstate"] = operstate
        if operstate != "UP":
            return False, "LINK_DOWN", detail
    except Exception:
        return False, "NOT_FOUND", detail

    try:
        addr_raw = subprocess.check_output(
            ["ip", "-j", "-4", "addr", "show", "dev", iface],
            text=True,
            timeout=2,
        )
        addr_data = json.loads(addr_raw) or []
    except Exception:
        return False, "NO_IP", detail

    ipv4 = ""
    for entry in addr_data:
        for info in entry.get("addr_info", []) or []:
            if info.get("family") != "inet":
                continue
            if info.get("scope") == "host":
                continue
            local = str(info.get("local") or "")
            if local:
                ipv4 = local
                break
        if ipv4:
            break
    detail["ipv4"] = ipv4
    if not ipv4:
        return False, "NO_IP", detail
    return True, "READY", detail


def probe_captive_portal(
    iface: Optional[str],
    url: str,
    timeout: int,
    retries: int,
) -> Tuple[str, str, Dict[str, object]]:
    checked_at = _now_iso8601()
    detail: Dict[str, object] = {
        "url": url,
        "iface": iface or "",
        "checked_at": checked_at,
    }

    if not iface:
        return "NA", "NOT_FOUND", detail
    if not SAFE_TOKEN_RE.match(iface):
        return "NA", "INVALID_IFACE", detail

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return "SUSPECTED", "INVALID_URL", detail

    ready, not_ready_reason, iface_detail = _iface_ready_for_probe(iface)
    detail.update(iface_detail)
    if not ready:
        return "NA", not_ready_reason, detail

    tries = max(1, retries + 1)
    last_status = "NA"
    last_reason = "CURL_ERR"
    for _ in range(tries):
        body_path = ""
        hdr_path = ""
        try:
            tmp_dir = "/run/azazel" if os.path.isdir("/run/azazel") else "/tmp"
            with tempfile.NamedTemporaryFile(prefix="azazel_cap_body_", delete=False, dir=tmp_dir) as body_fp:
                body_path = body_fp.name
            with tempfile.NamedTemporaryFile(prefix="azazel_cap_hdr_", delete=False, dir=tmp_dir) as hdr_fp:
                hdr_path = hdr_fp.name

            cmd = [
                "curl",
                "--interface",
                iface,
                "-sS",
                "--max-time",
                str(timeout),
                "-o",
                body_path,
                "-D",
                hdr_path,
                "-w",
                "%{http_code} %{url_effective}",
                url,
            ]
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=max(2, timeout + 2),
            )

            stdout = (proc.stdout or "").strip()
            http_code = "000"
            effective_url = ""
            if stdout:
                parts = stdout.split(maxsplit=1)
                http_code = parts[0]
                if len(parts) > 1:
                    effective_url = parts[1]

            headers = ""
            try:
                with open(hdr_path, "r", encoding="utf-8", errors="ignore") as fh:
                    headers = fh.read()
            except Exception:
                headers = ""

            location = _parse_location(headers)
            body_len = 0
            body_preview = ""
            try:
                body_len = os.path.getsize(body_path)
            except OSError:
                body_len = 0
            if body_len > 0 and body_len <= 8192:
                try:
                    with open(body_path, "r", encoding="utf-8", errors="ignore") as bf:
                        body_preview = bf.read(2048)
                except Exception:
                    body_preview = ""

            detail.update(
                {
                    "http_code": http_code,
                    "effective_url": effective_url,
                    "location": location,
                    "body_len": body_len,
                }
            )

            if proc.returncode != 0:
                if proc.returncode == 28:
                    last_reason = "TIMEOUT"
                elif proc.returncode == 6:
                    last_reason = "DNS_FAIL"
                elif proc.returncode in (35, 51, 58, 60):
                    last_reason = "CERT_FAIL"
                else:
                    last_reason = f"CURL_ERR_{proc.returncode}"
                detail["curl_rc"] = proc.returncode
                detail["stderr"] = (proc.stderr or "").strip()
                last_status = "NA"
                time.sleep(0.25)
                continue

            if http_code == "204":
                return "NO", "HTTP_204", detail
            if (
                parsed.hostname == APPLE_CAPTIVE_HOST
                and http_code == "200"
                and body_preview
                and "success" in body_preview.lower()
            ):
                return "NO", "HTTP_200_APPLE_SUCCESS", detail
            if http_code.startswith("30"):
                return "YES", "HTTP_30X", detail
            if http_code == "200" and body_len > 0:
                return "SUSPECTED", "HTTP_200_BODY", detail
            return "NA", f"HTTP_{http_code or '000'}", detail
        except subprocess.TimeoutExpired:
            detail["error"] = "subprocess timeout"
            last_status = "NA"
            last_reason = "TIMEOUT"
        except Exception as exc:  # pragma: no cover - network dependent
            detail["error"] = str(exc)
            last_status = "NA"
            last_reason = "CURL_ERR"
        finally:
            for p in (body_path, hdr_path):
                if p:
                    try:
                        os.unlink(p)
                    except OSError:
                        pass
        time.sleep(0.25)
    return last_status, last_reason, detail


def probe_tls_endpoint(host: str, port: int, fingerprint: str, timeout: int) -> Tuple[bool, Dict[str, object]]:
    mismatch = False
    detail: Dict[str, object] = {"host": host, "port": port}
    ctx = ssl.create_default_context()
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as tls_sock:
                der = tls_sock.getpeercert(binary_form=True)
                fp = hashlib.sha256(der).hexdigest()
                detail["fingerprint"] = fp
                if fingerprint:
                    mismatch = fp.lower() != fingerprint.lower()
                detail["sni"] = tls_sock.server_hostname
                detail["subject"] = tls_sock.getpeercert().get("subject")
    except Exception as exc:  # pragma: no cover - network dependent
        detail["error"] = str(exc)
        mismatch = True
    return mismatch, detail


def probe_dns_compare(sample_names: List[str], reference: str, timeout: int, max_mismatch: int) -> Tuple[int, Dict[str, object]]:
    mismatches = 0
    detail: Dict[str, object] = {"reference": reference, "results": []}
    has_dig = which("dig") is not None

    for name in sample_names:
        default_ips = set()
        ref_ips = set()
        try:
            info = socket.getaddrinfo(name, None, proto=socket.IPPROTO_TCP)
            default_ips = {item[4][0] for item in info if item[4]}
        except Exception as exc:  # pragma: no cover - network dependent
            detail["results"].append({"name": name, "error": str(exc)})
            mismatches += 1
            continue

        if has_dig:
            try:
                cmd = ["dig", f"@{reference}", name, "+short", "+time=" + str(timeout), "+tries=1"]
                out = subprocess.check_output(cmd, timeout=timeout, text=True, stderr=subprocess.DEVNULL)
                ref_ips = {line.strip() for line in out.splitlines() if line.strip() and line[0].isdigit()}
            except subprocess.SubprocessError as exc:
                detail["results"].append({"name": name, "error": str(exc)})
        else:
            ref_ips = default_ips

        if default_ips != ref_ips:
            mismatches += 1
        detail["results"].append({"name": name, "default": sorted(default_ips), "ref": sorted(ref_ips)})
    detail["mismatches"] = mismatches
    detail["threshold"] = max_mismatch
    return mismatches, detail


def probe_route(upstream: str) -> Tuple[bool, Dict[str, object]]:
    detail: Dict[str, object] = {"upstream": upstream}
    if not upstream:
        detail["error"] = "missing upstream interface"
        return True, detail
    try:
        out = subprocess.check_output(["ip", "route", "show", "default"], text=True, timeout=2)
    except subprocess.SubprocessError as exc:
        detail["error"] = str(exc)
        return True, detail
    lines = [ln for ln in out.splitlines() if ln.strip()]
    detail["routes"] = lines
    anomaly = True
    for ln in lines:
        if f"dev {upstream}" in ln:
            anomaly = False
    return anomaly, detail


def run_all(cfg: Dict[str, object], upstream: str, captive_iface: Optional[str] = None) -> ProbeOutcome:
    captive_cfg = cfg.get("captive_portal", {}) or {}
    tls_cfg = cfg.get("tls", []) or []
    dns_cfg = cfg.get("dns_compare", {}) or {}

    captive_status, captive_reason, captive_detail = probe_captive_portal(
        captive_iface,
        str(captive_cfg.get("url", "http://connectivitycheck.gstatic.com/generate_204")),
        int(captive_cfg.get("timeout", 4)),
        int(captive_cfg.get("retries", 1)),
    )
    captive_bool = captive_status in ("YES", "SUSPECTED")

    tls_mismatch = False
    tls_details: List[object] = []
    for entry in tls_cfg:
        mismatch, detail = probe_tls_endpoint(
            entry.get("host", "example.com"),
            int(entry.get("port", 443)),
            entry.get("fingerprint_sha256", ""),
            int(entry.get("timeout", 4)),
        )
        tls_mismatch = tls_mismatch or mismatch
        tls_details.append(detail)

    dns_mismatch_count = 0
    dns_detail: Dict[str, object] = {}
    if dns_cfg.get("enabled", False):
        dns_mismatch_count, dns_detail = probe_dns_compare(
            dns_cfg.get("sample_names", ["example.com"]),
            dns_cfg.get("reference_resolver", "9.9.9.9"),
            int(dns_cfg.get("timeout", 3)),
            int(dns_cfg.get("max_mismatch", 2)),
        )

    route_anomaly, route_detail = probe_route(upstream)

    details = {
        "captive": captive_detail,
        "tls": tls_details,
        "dns": dns_detail,
        "route": route_detail,
    }
    return ProbeOutcome(
        captive_portal=captive_bool,
        captive_status=captive_status,
        captive_reason=captive_reason,
        captive_checked_at=str(captive_detail.get("checked_at") or _now_iso8601()),
        captive_iface=str(captive_iface or ""),
        tls_mismatch=tls_mismatch,
        dns_mismatch=dns_mismatch_count,
        route_anomaly=route_anomaly,
        details=details,
    )
