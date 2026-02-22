from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

try:
    import yaml  # type: ignore
except ImportError as exc:  # pragma: no cover - dependency notice
    raise SystemExit("PyYAML is required: sudo apt-get install -y python3-yaml") from exc

from azazel_gadget.path_schema import (
    config_dir_candidates,
    log_dir_candidates,
    runtime_dir_candidates,
    warn_if_legacy_path,
)


@dataclass
class FirstMinuteConfig:
    interfaces: Dict[str, str]
    paths: Dict[str, str]
    dnsmasq: Dict[str, Any]
    state_machine: Dict[str, Any]
    probes: Dict[str, Any]
    policy: Dict[str, Any]
    status_api: Dict[str, Any]
    suricata: Dict[str, Any]
    deception: Dict[str, Any]
    captive_probe_policy: str = "wifi_prefer"
    suppress_auto_wifi: bool = True
    notify: Dict[str, Any] = field(default_factory=dict)  # ★ ntfy 通知設定
    yaml_path: str | Path = ""  # Track the config file path for reproducibility

    @staticmethod
    def load(path: str | Path) -> "FirstMinuteConfig":
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Config not found: {p}")
        data = yaml.safe_load(p.read_text()) or {}
        # Provide minimal defaults for keys that may be missing to avoid KeyErrors
        defaults = {
            "interfaces": {
                "upstream": "auto",
                "captive_probe": "auto",
                "downstream": "usb0",
                "mgmt_ip": "192.168.7.1",
                "mgmt_subnet": "192.168.7.0/24",
            },
            "paths": {},
            "dnsmasq": {"enable": True},
            "state_machine": {},
            "probes": {},
            "policy": {},
            "captive_probe_policy": "wifi_prefer",
            "suppress_auto_wifi": True,
            "status_api": {
                "host": "127.0.0.1",
                "port": 8082
            },
            "suricata": {"enabled": False},
            "deception": {
                "enable_if_opencanary_present": True,
                "opencanary_cfg": "/etc/opencanaryd/opencanary.conf",
                "delay_on_canary_attack": True,
                "canary_delay_window_sec": 45.0,
                "canary_delay_ms": 650,
                "canary_delay_jitter_ms": 120,
                "canary_delay_loss_percent": 0.0,
            },
            "notify": {  # ★ ntfy デフォルト設定
                "enabled": False,
                "ntfy": {
                    "base_url": "http://10.55.0.10:8081",
                    "token_file": "/etc/azazel/ntfy.token",
                    "topic_alert": "azg-alert-critical",
                    "topic_info": "azg-info-status",
                    "cooldown_sec": 30,
                },
                "thresholds": {
                    "temp_c_alert": 75,
                    "dns_mismatch_alert": 3,
                },
            },
        }
        for key, val in defaults.items():
            if isinstance(val, dict):
                existing = data.get(key)
                if not isinstance(existing, dict):
                    data[key] = val.copy()
                    continue
                merged = val.copy()
                merged.update(existing)
                data[key] = merged
            else:
                data.setdefault(key, val)
        cfg = FirstMinuteConfig(**data)
        cfg.yaml_path = p  # Set the path after construction
        return cfg

    @property
    def runtime_dir(self) -> Path:
        default = runtime_dir_candidates()[0]
        path = Path(self.paths.get("runtime_dir", str(default)))
        warn_if_legacy_path(path, logger=None)
        return path

    @property
    def log_dir(self) -> Path:
        default = log_dir_candidates()[0]
        path = Path(self.paths.get("log_dir", str(default)))
        warn_if_legacy_path(path, logger=None)
        return path

    @property
    def pid_file(self) -> Path:
        default = runtime_dir_candidates()[0] / "first_minute.pid"
        path = Path(self.paths.get("pid_file", str(default)))
        warn_if_legacy_path(path, logger=None)
        return path

    @property
    def dns_log_path(self) -> Path:
        return Path(self.paths.get("dns_log", "/var/log/azazel-dnsmasq.log"))

    @property
    def nft_template_path(self) -> Path:
        default = config_dir_candidates()[0] / "nftables" / "first_minute.nft"
        path = Path(self.paths.get("nft_template", str(default)))
        warn_if_legacy_path(path, logger=None)
        return path

    @property
    def dnsmasq_conf_path(self) -> Path:
        default = config_dir_candidates()[0] / "dnsmasq-first_minute.conf"
        path = Path(self.paths.get("dnsmasq_conf", str(default)))
        warn_if_legacy_path(path, logger=None)
        return path

    def ensure_dirs(self) -> None:
        # Try desired locations; if not writable (e.g., non-root), fall back to repo-local .azazel-gadget
        try_dirs = [self.runtime_dir, self.log_dir]
        try:
            for d in try_dirs:
                d.mkdir(parents=True, exist_ok=True)
            return
        except PermissionError:
            pass

        fallback_base = Path(__file__).resolve().parents[3] / ".azazel-gadget"
        fallback_runtime = fallback_base / "run"
        fallback_log = fallback_base / "log"
        fallback_base.mkdir(parents=True, exist_ok=True)
        fallback_runtime.mkdir(parents=True, exist_ok=True)
        fallback_log.mkdir(parents=True, exist_ok=True)
        self.paths["runtime_dir"] = str(fallback_runtime)
        self.paths["log_dir"] = str(fallback_log)
        self.paths["pid_file"] = str(fallback_runtime / "first_minute.pid")
        self.paths["dns_log"] = str(fallback_log / "azazel-dnsmasq.log")
        for d in [fallback_runtime, fallback_log]:
            d.mkdir(parents=True, exist_ok=True)

    def env(self) -> Dict[str, str]:
        env = os.environ.copy()
        env.setdefault("UPSTREAM_IFACE", self.interfaces["upstream"])
        env.setdefault("DOWNSTREAM_IFACE", self.interfaces["downstream"])
        return env
