import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
PY_ROOT = REPO_ROOT / "py"
if str(PY_ROOT) not in sys.path:
    sys.path.insert(0, str(PY_ROOT))

from azazel_gadget.first_minute.controller import FirstMinuteController
from azazel_gadget.first_minute.state_machine import Stage
from azazel_gadget.first_minute.tc import TcManager


class CanaryTargetExtractionTests(unittest.TestCase):
    def _mk_controller(self):
        ctrl = object.__new__(FirstMinuteController)
        ctrl.cfg = SimpleNamespace(
            interfaces={"upstream": "wlan0"},
            deception={"delay_on_canary_attack": True, "opencanary_cfg": "/nonexistent"},
            suricata={"enabled": True, "eve_path": "/tmp/none"},
        )
        ctrl.logger = SimpleNamespace(debug=lambda *args, **kwargs: None)
        ctrl._canary_delay_enabled = True
        ctrl._opencanary_ports = set()
        ctrl._opencanary_cfg_mtime_ns = None
        ctrl._canary_delay_targets = {}
        ctrl._canary_delay_window_sec = 45.0
        ctrl._canary_delay_ms = 650
        ctrl._canary_delay_jitter_ms = 120
        ctrl._canary_delay_loss_percent = 0.0
        ctrl._last_suricata_severity = 0
        ctrl._get_interface_ip = lambda iface: "192.0.2.10"
        return ctrl

    def test_extract_canary_target_from_destination_tuple(self):
        ctrl = self._mk_controller()
        event = {
            "event_type": "alert",
            "src_ip": "198.51.100.7",
            "src_port": 53000,
            "dest_ip": "192.0.2.10",
            "dest_port": 22,
        }
        target = FirstMinuteController._extract_canary_target_from_event(ctrl, event)
        self.assertEqual(target, ("198.51.100.7", 22))

    def test_extract_canary_target_returns_none_for_non_canary_port(self):
        ctrl = self._mk_controller()
        event = {
            "event_type": "alert",
            "src_ip": "198.51.100.7",
            "dest_ip": "192.0.2.10",
            "dest_port": 443,
        }
        target = FirstMinuteController._extract_canary_target_from_event(ctrl, event)
        self.assertIsNone(target)


class SuricataSummaryTests(unittest.TestCase):
    def _mk_controller(self, eve_path: Path):
        ctrl = object.__new__(FirstMinuteController)
        ctrl.cfg = SimpleNamespace(
            interfaces={"upstream": "wlan0"},
            deception={"delay_on_canary_attack": True, "opencanary_cfg": "/nonexistent"},
            suricata={"enabled": True, "eve_path": str(eve_path)},
        )
        ctrl.logger = SimpleNamespace(debug=lambda *args, **kwargs: None)
        ctrl._canary_delay_enabled = True
        ctrl._opencanary_ports = set()
        ctrl._opencanary_cfg_mtime_ns = None
        ctrl._canary_delay_targets = {}
        ctrl._canary_delay_window_sec = 45.0
        ctrl._canary_delay_ms = 650
        ctrl._canary_delay_jitter_ms = 120
        ctrl._canary_delay_loss_percent = 0.0
        ctrl._last_suricata_severity = 0
        ctrl._get_interface_ip = lambda iface: "192.0.2.10"
        return ctrl

    def test_suricata_bumped_returns_canary_targets(self):
        with tempfile.TemporaryDirectory() as td:
            eve = Path(td) / "eve.json"
            eve.write_text("{}\n", encoding="utf-8")

            ctrl = self._mk_controller(eve)
            ctrl._read_new_eve_events = lambda path: [
                {
                    "event_type": "alert",
                    "timestamp": "2026-02-22T10:00:00.000000+0000",
                    "src_ip": "198.51.100.30",
                    "src_port": 42000,
                    "dest_ip": "192.0.2.10",
                    "dest_port": 80,
                    "alert": {"severity": 1},
                }
            ]
            ctrl._parse_eve_timestamp = lambda ts: time.time() - 1

            summary = FirstMinuteController.suricata_bumped(ctrl)
            self.assertTrue(summary.get("alert"))
            self.assertEqual(summary.get("severity"), 1)
            self.assertIn(("198.51.100.30", 80), summary.get("canary_targets", []))


class DeceptionDelaySyncTests(unittest.TestCase):
    def _mk_controller(self):
        ctrl = object.__new__(FirstMinuteController)
        ctrl.dry_run = False
        ctrl._canary_delay_enabled = True
        ctrl._canary_delay_ms = 650
        ctrl._canary_delay_jitter_ms = 120
        ctrl._canary_delay_loss_percent = 0.0
        ctrl._canary_delay_targets = {("198.51.100.40", 22): time.time() + 30}

        class DummyTc:
            def __init__(self):
                self.applied = 0
                self.cleared = 0

            def apply_deception_delay(self, targets, delay_ms, jitter_ms, loss_percent):
                self.applied += 1

            def clear_deception_delay(self):
                self.cleared += 1

        ctrl.tc = DummyTc()
        return ctrl

    def test_sync_applies_only_for_deception_stage(self):
        ctrl = self._mk_controller()
        FirstMinuteController._sync_deception_delay_tc(ctrl, Stage.NORMAL, time.time())
        self.assertEqual(ctrl.tc.applied, 0)
        self.assertEqual(ctrl.tc.cleared, 1)

        FirstMinuteController._sync_deception_delay_tc(ctrl, Stage.DECEPTION, time.time())
        self.assertEqual(ctrl.tc.applied, 1)


class TcManagerDeceptionTests(unittest.TestCase):
    @patch("azazel_gadget.first_minute.tc.subprocess.run")
    def test_apply_deception_delay_is_idempotent_for_same_signature(self, run_mock):
        tc = TcManager("usb0", "wlan0")
        tc.apply_deception_delay([("198.51.100.9", 22)], delay_ms=600, jitter_ms=100)
        first_call_count = run_mock.call_count
        tc.apply_deception_delay([("198.51.100.9", 22)], delay_ms=600, jitter_ms=100)
        self.assertEqual(run_mock.call_count, first_call_count)


if __name__ == "__main__":
    unittest.main()
