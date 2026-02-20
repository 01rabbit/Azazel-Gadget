import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
PY_ROOT = REPO_ROOT / "py"
if str(PY_ROOT) not in sys.path:
    sys.path.insert(0, str(PY_ROOT))

from azazel_zero.first_minute.controller import FirstMinuteController
from azazel_zero.first_minute.probes import probe_captive_portal


class ResolveCaptiveProbeIfaceTests(unittest.TestCase):
    def _mk_controller(self, inventory, policy="wifi_prefer", upstream="auto", captive_probe="auto"):
        ctrl = object.__new__(FirstMinuteController)
        ctrl.cfg = SimpleNamespace(
            interfaces={
                "upstream": upstream,
                "downstream": "usb0",
                "captive_probe": captive_probe,
            },
            captive_probe_policy=policy,
        )
        ctrl._collect_iface_inventory = lambda exclude=None: inventory
        return ctrl

    def test_wifi_prefer_prefers_wireless(self):
        inv = {
            "wlan0": {
                "is_up": True,
                "has_ipv4": True,
                "has_default_route": False,
                "default_metric": 200,
                "is_wireless": True,
            },
            "eth0": {
                "is_up": True,
                "has_ipv4": True,
                "has_default_route": True,
                "default_metric": 100,
                "is_wireless": False,
            },
        }
        ctrl = self._mk_controller(inv)
        resolved = FirstMinuteController.resolve_captive_probe_iface(ctrl)
        self.assertEqual(resolved["iface"], "wlan0")
        self.assertEqual(resolved["policy"], "wifi_prefer")

    def test_wifi_prefer_falls_back_to_wired(self):
        inv = {
            "wlan0": {
                "is_up": False,
                "has_ipv4": False,
                "has_default_route": False,
                "default_metric": 200,
                "is_wireless": True,
            },
            "eth0": {
                "is_up": True,
                "has_ipv4": True,
                "has_default_route": True,
                "default_metric": 100,
                "is_wireless": False,
            },
        }
        ctrl = self._mk_controller(inv)
        resolved = FirstMinuteController.resolve_captive_probe_iface(ctrl)
        self.assertEqual(resolved["iface"], "eth0")
        self.assertTrue(resolved["reason"].startswith("fallback_to_"))

    def test_wifi_prefer_returns_na_when_no_ip(self):
        inv = {
            "wlan0": {
                "is_up": True,
                "has_ipv4": False,
                "has_default_route": False,
                "default_metric": 200,
                "is_wireless": True,
            },
            "eth0": {
                "is_up": True,
                "has_ipv4": False,
                "has_default_route": False,
                "default_metric": 100,
                "is_wireless": False,
            },
        }
        ctrl = self._mk_controller(inv)
        resolved = FirstMinuteController.resolve_captive_probe_iface(ctrl)
        self.assertEqual(resolved["iface"], "")
        self.assertEqual(resolved["reason"], "NO_IP")


class ProbeCaptivePortalDecisionTests(unittest.TestCase):
    def _fake_curl_result(self, rc, code, headers="", body=b""):
        def _run(cmd, capture_output, text, timeout):
            body_path = cmd[cmd.index("-o") + 1]
            hdr_path = cmd[cmd.index("-D") + 1]
            Path(body_path).write_bytes(body)
            Path(hdr_path).write_text(headers, encoding="utf-8")
            return SimpleNamespace(returncode=rc, stdout=f"{code} http://example.test/", stderr="")

        return _run

    def test_http_204_means_no(self):
        with patch("azazel_zero.first_minute.probes._iface_ready_for_probe", return_value=(True, "READY", {})):
            with patch("subprocess.run", side_effect=self._fake_curl_result(0, "204", "HTTP/1.1 204 No Content\r\n", b"")):
                status, reason, _ = probe_captive_portal("wlan0", "http://connectivitycheck.gstatic.com/generate_204", 3, 0)
        self.assertEqual(status, "NO")
        self.assertEqual(reason, "HTTP_204")

    def test_http_302_means_yes(self):
        headers = "HTTP/1.1 302 Found\r\nLocation: http://login.local/\r\n"
        with patch("azazel_zero.first_minute.probes._iface_ready_for_probe", return_value=(True, "READY", {})):
            with patch("subprocess.run", side_effect=self._fake_curl_result(0, "302", headers, b"")):
                status, reason, detail = probe_captive_portal("wlan0", "http://connectivitycheck.gstatic.com/generate_204", 3, 0)
        self.assertEqual(status, "YES")
        self.assertEqual(reason, "HTTP_30X")
        self.assertEqual(detail.get("location"), "http://login.local/")

    def test_http_200_body_means_suspected(self):
        with patch("azazel_zero.first_minute.probes._iface_ready_for_probe", return_value=(True, "READY", {})):
            with patch("subprocess.run", side_effect=self._fake_curl_result(0, "200", "HTTP/1.1 200 OK\r\n", b"portal-page")):
                status, reason, _ = probe_captive_portal("wlan0", "http://connectivitycheck.gstatic.com/generate_204", 3, 0)
        self.assertEqual(status, "SUSPECTED")
        self.assertEqual(reason, "HTTP_200_BODY")

    def test_apple_success_means_no(self):
        with patch("azazel_zero.first_minute.probes._iface_ready_for_probe", return_value=(True, "READY", {})):
            with patch("subprocess.run", side_effect=self._fake_curl_result(0, "200", "HTTP/1.1 200 OK\r\n", b"Success")):
                status, reason, _ = probe_captive_portal("wlan0", "http://captive.apple.com/hotspot-detect.html", 3, 0)
        self.assertEqual(status, "NO")
        self.assertEqual(reason, "HTTP_200_APPLE_SUCCESS")

    def test_curl_timeout_means_na(self):
        with patch("azazel_zero.first_minute.probes._iface_ready_for_probe", return_value=(True, "READY", {})):
            with patch("subprocess.run", side_effect=self._fake_curl_result(28, "000", "", b"")):
                status, reason, _ = probe_captive_portal("wlan0", "http://connectivitycheck.gstatic.com/generate_204", 3, 0)
        self.assertEqual(status, "NA")
        self.assertEqual(reason, "TIMEOUT")


if __name__ == "__main__":
    unittest.main()
