"""Tests for the Gadget -> Covenant (azazel_covenant/azazel_common) StatusView adapter.

Skipped when neither azazel_covenant nor azazel_common is installed (it is an
optional, tag-pinned dependency), so this suite stays green in CI environments
that do not install it. Locally, install azazel-covenant (or azazel-common for
the pinned v0.2.0 tag) to exercise the mapping.
"""

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PY_ROOT = REPO_ROOT / "py"
if str(PY_ROOT) not in sys.path:
    sys.path.insert(0, str(PY_ROOT))

from azazel_gadget import common_view


SAMPLE_SNAPSHOT = {
    "now_time": "2026-07-09T00:00:00Z",
    "user_state": "watch",
    "recommendation": "hold; observe canary",
    "reasons": ["suricata critical", "canary target hit"],
    "next_action_hint": "review canary targets",
    "internal": {"state_name": "DECEPTION", "suspicion": 0.8, "decay": 0.0},
    "degrade": {"on": True, "rtt_ms": 120, "rate_mbps": 5},
    "probe": {"tls_ok": 2, "tls_total": 3, "blocked": False},
    "suricata_critical": 1,
    "suricata_warning": 2,
    "evidence": [{"id": "ev-1"}, "ev-2"],
    "attack": {"canary_delay_active": True, "canary_delay_targets": ["10.0.0.9"]},
    "connection": {"captive_state": "open"},
}


@unittest.skipUnless(
    common_view.HAVE_AZAZEL_COMMON,
    "azazel_covenant/azazel_common not installed (optional dependency)",
)
class StatusViewAdapterTest(unittest.TestCase):
    def test_maps_core_fields(self):
        view = common_view.status_view_from_snapshot(SAMPLE_SNAPSHOT, mode_name="SCAPEGOAT")
        self.assertIsNotNone(view)
        self.assertEqual(view.product, "gadget")
        self.assertEqual(view.mode.name, "scapegoat")
        # DECEPTION stage classifies to the shared 'deception' posture.
        self.assertEqual(view.posture, "deception")
        self.assertEqual(view.operator_wording, "hold; observe canary")
        self.assertIn("review canary targets", view.next_actions)
        self.assertEqual(view.evidence_ids, ["ev-1", "ev-2"])

    def test_superset_preserved_in_product_view(self):
        view = common_view.status_view_from_snapshot(SAMPLE_SNAPSHOT, mode_name="SCAPEGOAT")
        raw = view.product_view["gadget_snapshot"]
        # Gadget-only blocks survive untouched.
        self.assertTrue(raw["attack"]["canary_delay_active"])
        self.assertEqual(raw["attack"]["canary_delay_targets"], ["10.0.0.9"])
        self.assertEqual(raw["connection"]["captive_state"], "open")

    def test_health_rows_built(self):
        view = common_view.status_view_from_snapshot(SAMPLE_SNAPSHOT)
        keys = {row.key for row in view.health}
        self.assertIn("link", keys)
        self.assertIn("suricata", keys)

    def test_round_trip_json(self):
        try:  # namespace-agnostic: match whichever the shim resolved
            from azazel_covenant.view import StatusView
        except ImportError:
            from azazel_common.view import StatusView

        view = common_view.status_view_from_snapshot(SAMPLE_SNAPSHOT, mode_name="shield")
        restored = StatusView.model_validate_json(view.model_dump_json())
        self.assertEqual(restored, view)


class AdapterNoCommonTest(unittest.TestCase):
    """These must hold whether or not azazel_covenant/azazel_common is installed."""

    def test_no_common_is_safe_noop(self):
        if common_view.HAVE_AZAZEL_COMMON:
            self.skipTest("azazel_covenant/azazel_common installed; no-op path covered elsewhere")
        self.assertIsNone(common_view.status_view_from_snapshot(SAMPLE_SNAPSHOT))
        # Must not raise even with no paths / no dependency.
        common_view.write_status_view_alongside(SAMPLE_SNAPSHOT, [], mode_name="shield")


if __name__ == "__main__":
    unittest.main()
