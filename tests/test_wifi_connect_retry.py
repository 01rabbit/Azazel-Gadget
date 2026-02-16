import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
PY_ROOT = REPO_ROOT / "py"
if str(PY_ROOT) not in sys.path:
    sys.path.insert(0, str(PY_ROOT))

from azazel_control import wifi_connect


class CaptiveRetryTests(unittest.TestCase):
    def test_schedule_default(self):
        with patch.dict(os.environ, {}, clear=False):
            if "AZAZEL_CAPTIVE_RETRY_SCHEDULE_SEC" in os.environ:
                del os.environ["AZAZEL_CAPTIVE_RETRY_SCHEDULE_SEC"]
            schedule = wifi_connect.get_captive_retry_schedule()
        self.assertEqual(schedule, [0, 3, 10])

    def test_schedule_inserts_zero_when_missing(self):
        with patch.dict(os.environ, {"AZAZEL_CAPTIVE_RETRY_SCHEDULE_SEC": "2,5"}):
            schedule = wifi_connect.get_captive_retry_schedule()
        self.assertEqual(schedule, [0, 2, 5])

    def test_no_ip_returns_na(self):
        out = wifi_connect.evaluate_captive_portal_with_retries("wlan0", has_ip=False)
        self.assertEqual(out["status"], "NA")
        self.assertEqual(out["reason"], "NO_IP")
        self.assertEqual(out["attempts"][0]["reason"], "NO_IP")

    def test_retry_stops_on_yes(self):
        checks_204 = {"http_code": "204", "body_len": 0, "curl_error": ""}
        checks_302 = {"http_code": "302", "body_len": 0, "curl_error": ""}
        with patch("azazel_control.wifi_connect.get_captive_retry_schedule", return_value=[0, 1, 2]):
            with patch("azazel_control.wifi_connect.check_connectivity", side_effect=[checks_204, checks_302]):
                with patch("time.sleep", return_value=None):
                    out = wifi_connect.evaluate_captive_portal_with_retries("wlan0", has_ip=True)
        self.assertEqual(out["status"], "YES")
        self.assertEqual(out["reason"], "HTTP_30X")
        self.assertEqual(len(out["attempts"]), 2)

    def test_no_retries_complete_when_always_no(self):
        checks_204 = {"http_code": "204", "body_len": 0, "curl_error": ""}
        with patch("azazel_control.wifi_connect.get_captive_retry_schedule", return_value=[0, 1]):
            with patch("azazel_control.wifi_connect.check_connectivity", side_effect=[checks_204, checks_204]):
                with patch("time.sleep", return_value=None):
                    out = wifi_connect.evaluate_captive_portal_with_retries("wlan0", has_ip=True)
        self.assertEqual(out["status"], "NO")
        self.assertEqual(out["reason"], "HTTP_204")
        self.assertEqual(len(out["attempts"]), 2)


if __name__ == "__main__":
    unittest.main()
