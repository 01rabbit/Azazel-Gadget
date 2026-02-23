import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PY_ROOT = REPO_ROOT / "py"
if str(PY_ROOT) not in sys.path:
    sys.path.insert(0, str(PY_ROOT))

from azazel_control.mode_manager import ModeManager, extract_opencanary_ports, render_nft_rules


class OpenCanaryPortParseTests(unittest.TestCase):
    def test_extract_enabled_ports(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = Path(td) / "opencanary.conf"
            cfg.write_text(
                json.dumps(
                    {
                        "ssh.enabled": True,
                        "ssh.port": 22,
                        "http.enabled": True,
                        "http.port": 80,
                        "ftp.enabled": False,
                        "ftp.port": 21,
                    }
                ),
                encoding="utf-8",
            )
            ports = extract_opencanary_ports(cfg)
        self.assertEqual(ports, [22, 80])

    def test_extract_fallback_ports_when_empty(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = Path(td) / "opencanary.conf"
            cfg.write_text(json.dumps({"ssh.enabled": False, "ssh.port": 22}), encoding="utf-8")
            ports = extract_opencanary_ports(cfg)
        self.assertEqual(ports, [22, 80])


class NftRenderTests(unittest.TestCase):
    def test_render_is_deterministic(self):
        first = render_nft_rules(
            mode="shield",
            usb_if="usb0",
            upstream_if="wlan0",
            mgmt_subnet="10.55.0.0/24",
            canary_ports=[80, 22],
        )
        second = render_nft_rules(
            mode="shield",
            usb_if="usb0",
            upstream_if="wlan0",
            mgmt_subnet="10.55.0.0/24",
            canary_ports=[22, 80],
        )
        self.assertEqual(first, second)

    def test_scapegoat_includes_allowlist_redirect(self):
        rendered = render_nft_rules(
            mode="scapegoat",
            usb_if="usb0",
            upstream_if="wlan0",
            mgmt_subnet="10.55.0.0/24",
            canary_ports=[22, 80],
        )
        self.assertIn('iifname "wlan0" tcp dport { 22, 80 } dnat ip to 169.254.240.2', rendered)
        self.assertIn('iifname "vcanary_host" oifname "usb0" drop', rendered)


class ConfigHashTests(unittest.TestCase):
    def test_effective_hash_is_stable(self):
        mgr = ModeManager()
        payload = {
            "mode": "shield",
            "usb_if": "usb0",
            "upstream_if": "wlan0",
            "mgmt_subnet": "10.55.0.0/24",
            "mgmt_ip": "10.55.0.10",
            "fw_backend": "nft",
            "canary_ports": [22, 80],
        }
        h1 = mgr._hash_effective_config(payload)
        h2 = mgr._hash_effective_config(dict(payload))
        self.assertEqual(h1, h2)


if __name__ == "__main__":
    unittest.main()
