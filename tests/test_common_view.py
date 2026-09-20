"""Tests for the Gadget -> Fabric (azazel_fabric) StatusView adapter.

Skipped when azazel_fabric is not installed, because it is an optional,
tag-pinned dependency and a contributor without it must still get a green
run. `pip install -r requirements.txt` installs it.

**That skip used to apply to this repository's own CI**, which installed
PyYAML alone. The four cases below are the only ones that exercise the
adapter, so nothing here ran on any commit: the pinned Fabric tag could have
been changed to a broken one, or to a release that renamed `StatusView`, and
CI would have stayed green while reporting the same test count.

CI now installs the manifest, and `CiInstallsFabricTest` below fails if it
ever stops -- a skip that is correct on a laptop is not correct on the
machine whose green run is the evidence.
"""

import os
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
    "azazel_fabric not installed (optional dependency)",
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
        from azazel_fabric.view import StatusView

        view = common_view.status_view_from_snapshot(SAMPLE_SNAPSHOT, mode_name="shield")
        restored = StatusView.model_validate_json(view.model_dump_json())
        self.assertEqual(restored, view)


class AdapterNoCommonTest(unittest.TestCase):
    """These must hold whether or not azazel_fabric is installed."""

    def test_no_common_is_safe_noop(self):
        if common_view.HAVE_AZAZEL_COMMON:
            self.skipTest("azazel_fabric installed; no-op path covered elsewhere")
        self.assertIsNone(common_view.status_view_from_snapshot(SAMPLE_SNAPSHOT))
        # Must not raise even with no paths / no dependency.
        common_view.write_status_view_alongside(SAMPLE_SNAPSHOT, [], mode_name="shield")


class CiInstallsFabricTest(unittest.TestCase):
    """The adapter suite above must not be skipped on CI.

    Every other test here is guarded by `skipUnless(HAVE_AZAZEL_COMMON)`, and
    a skipped test reports success. So "the adapter is covered" is a claim
    about the CI environment, not about this file, and nothing was checking
    it -- CI installed PyYAML only, and all four cases silently skipped on
    every commit.

    This is the check. Outside CI it skips, because a contributor without the
    optional dependency should still get a green run; on CI it fails, naming
    the manifest as the fix. `CI` is set to "true" by GitHub Actions on every
    step of every run.
    """

    def test_the_adapter_suite_is_not_skipped_on_ci(self):
        if os.environ.get("CI", "").lower() != "true":
            self.skipTest("not running on CI; azazel_fabric is optional locally")
        self.assertTrue(
            common_view.HAVE_AZAZEL_COMMON,
            "azazel_fabric is not installed on CI, so every StatusView adapter "
            "test above is skipping and the pinned Fabric tag is unverified. "
            "Install the manifest in .github/workflows/ci-tests.yml "
            "(`pip install -r requirements.txt`).",
        )


if __name__ == "__main__":
    unittest.main()
