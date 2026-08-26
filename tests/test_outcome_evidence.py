from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / "py"
if str(PY) not in sys.path:
    sys.path.insert(0, str(PY))

from azazel_gadget.outcome_evidence import (  # noqa: E402
    BoundedEvidenceSpool,
    LocalMechanismFact,
    build_execution_fact,
    build_mechanism_fact,
    build_outcome_fact,
    canonical_fact_json,
)


class OutcomeEvidenceTests(unittest.TestCase):
    def execution(self, **overrides):
        data = {
            "node_id": "gadget-1",
            "trace_id": "trace-1",
            "decision_ref": "local-decision-1",
            "action": "contain",
            "status": "applied",
            "observed_at": "2026-08-26T00:00:00Z",
            "evidence_refs": ("decision-log:1",),
        }
        data.update(overrides)
        return build_execution_fact(**data)

    def mechanism(self, execution=None, **overrides):
        data = {
            "mechanism_kind": "isolation",
            "status": "observed",
            "observed_at": "2026-08-26T00:00:01Z",
            "observed_parameters": {"client_scope": "client-1"},
            "evidence_refs": ("nft-readback:1",),
        }
        data.update(overrides)
        return build_mechanism_fact(execution or self.execution(), **data)

    def test_execution_and_mechanism_never_emit_tactical_effect(self):
        execution = self.execution()
        mechanism = self.mechanism(execution)
        for encoded in (canonical_fact_json(execution), canonical_fact_json(mechanism)):
            payload = json.loads(encoded)
            self.assertNotIn("effect_class", payload)
            self.assertNotIn("tactical_effect", payload)
            self.assertNotIn("success", payload)
            self.assertNotIn("delay", encoded.lower())
            self.assertNotIn("divert", encoded.lower())

    def test_unknown_mechanism_is_allowed_without_upgrade(self):
        mechanism = self.mechanism(mechanism_kind="unknown", status="unverified")
        self.assertEqual(mechanism.mechanism_kind, "unknown")
        self.assertEqual(mechanism.status, "unverified")

    def test_tactical_effect_name_is_rejected_as_mechanism_kind(self):
        with self.assertRaises(ValueError):
            self.mechanism(mechanism_kind="delay")
        with self.assertRaises(ValueError):
            self.mechanism(mechanism_kind="divert")

    def test_nested_success_or_authority_field_is_rejected(self):
        with self.assertRaises(ValueError):
            self.mechanism(observed_parameters={"nested": {"success": True}})
        with self.assertRaises(ValueError):
            self.mechanism(observed_parameters={"nested": {"select_action": "isolate"}})

    def test_missing_telemetry_becomes_confounder_not_success(self):
        execution = self.execution()
        outcome = build_outcome_fact(
            execution,
            self.mechanism(execution),
            subject_ref="src-ip:198.51.100.8",
            window_start="2026-08-26T00:00:00Z",
            window_end="2026-08-26T00:00:10Z",
            phase="after",
            observed_at="2026-08-26T00:00:10Z",
            before_metrics=None,
            after_metrics={"rx_packets": 20},
        )
        self.assertIn("missing_pre_telemetry", outcome.confounders)
        payload = json.loads(canonical_fact_json(outcome))
        self.assertNotIn("success", payload)
        self.assertNotIn("tactical_effect", payload)

    def test_counter_decrease_is_counter_reset_not_negative_improvement(self):
        execution = self.execution()
        outcome = build_outcome_fact(
            execution,
            self.mechanism(execution),
            subject_ref=None,
            window_start="a",
            window_end="b",
            phase="after",
            observed_at="b",
            before_metrics={"rx_packets": 100},
            after_metrics={"rx_packets": 4},
        )
        self.assertIn("counter_reset:rx_packets", outcome.confounders)
        self.assertNotIn("rx_packets", outcome.observation_values.get("counter_deltas", {}))

    def test_cross_trace_mechanism_is_rejected(self):
        execution = self.execution()
        other = self.execution(trace_id="other", decision_ref="other-decision")
        mechanism = self.mechanism(other)
        with self.assertRaises(ValueError):
            build_outcome_fact(
                execution,
                mechanism,
                subject_ref=None,
                window_start="a",
                window_end="b",
                phase="after",
                observed_at="b",
                before_metrics={"x": 1},
                after_metrics={"x": 2},
            )

    def test_bounded_spool_drops_without_blocking_or_reinterpreting(self):
        spool = BoundedEvidenceSpool(max_entries=1)
        first = self.execution(observed_at="original-ts")
        second = self.execution(decision_ref="local-decision-2", observed_at="second-ts")
        self.assertTrue(spool.enqueue(first))
        self.assertFalse(spool.enqueue(second))
        self.assertEqual(spool.dropped, 1)
        drained = spool.drain()
        self.assertEqual(len(drained), 1)
        self.assertEqual(json.loads(drained[0])["observed_at"], "original-ts")
        self.assertEqual(spool.depth, 0)

    def test_bounded_spool_capacity_is_bounded(self):
        with self.assertRaises(ValueError):
            BoundedEvidenceSpool(max_entries=0)
        with self.assertRaises(ValueError):
            BoundedEvidenceSpool(max_entries=4097)

    def test_direct_construction_rejects_bad_mechanism_status(self):
        with self.assertRaises(ValueError):
            LocalMechanismFact(
                schema_version="outcome-mechanism/v0.1",
                observation_id="x",
                producer_product="azazel-gadget",
                producer_node="g",
                trace_id="t",
                decision_ref="d",
                execution_ref="e",
                mechanism_kind="unknown",
                status="applied",  # execution status, not mechanism observation status
                observed_parameters={},
                observed_at="now",
            )


if __name__ == "__main__":
    unittest.main()
