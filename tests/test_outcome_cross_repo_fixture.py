from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / "py"
if str(PY) not in sys.path:
    sys.path.insert(0, str(PY))

from azazel_gadget.outcome_evidence import build_execution_fact, canonical_fact_json  # noqa: E402


FIXTURE = ROOT / "tests" / "fixtures" / "outcome" / "gadget_execution_v0.json"


class CrossRepoFixtureTests(unittest.TestCase):
    def test_gadget_producer_matches_shared_execution_fixture(self):
        expected = json.loads(FIXTURE.read_text(encoding="utf-8"))
        fact = build_execution_fact(
            node_id="gadget-1",
            trace_id="trace-golden-1",
            decision_ref="local-decision-golden-1",
            action="isolate",
            status="applied",
            observed_at="2026-08-26T00:00:00Z",
            evidence_refs=("gadget:decision:golden-1",),
        )
        actual = json.loads(canonical_fact_json(fact))
        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
