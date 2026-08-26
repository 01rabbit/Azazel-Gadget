from __future__ import annotations

import unittest

from azazel_gadget.outcome_decision_bridge import (
    LocalExecutionObservation,
    bridge_decision_to_execution,
)
from azazel_gadget.tactics_engine.decision_logger import (
    ChosenAction,
    DecisionRecord,
    InputSnapshot,
    ScoreDelta,
    StateSnapshot,
)


def decision(*, action: str = "contain", action_type: str = "action") -> DecisionRecord:
    state = StateSnapshot(state="NORMAL", user_state="NORMAL", suspicion=0.5, risk_score=50)
    detail = {"action": action} if action_type == "action" else {"target_stage": action}
    return DecisionRecord(
        ts="2026-08-26T00:00:00Z",
        decision_id="decision-1",
        engine={"name": "Tactics Engine", "version": "test"},
        config_hash="sha256:test",
        inputs_snapshot=InputSnapshot(source="suricata", event_digest="sha256:event", event_min={}),
        features={},
        state_before=state,
        score_delta=ScoreDelta(),
        constraints_triggered=[],
        chosen=[ChosenAction(action_type=action_type, detail=detail)],
        state_after=state,
        parse_errors={},
    )


def observation(**overrides) -> LocalExecutionObservation:
    values = dict(
        observed_action="contain",
        status="applied",
        observed_at="2026-08-26T00:00:01Z",
        evidence_refs=("nft:receipt:1",),
        mechanism_kind="isolation",
        mechanism_status="observed",
        mechanism_parameters={"source": "readback"},
        mechanism_evidence_refs=("nft:readback:1",),
    )
    values.update(overrides)
    return LocalExecutionObservation(**values)


class OutcomeDecisionBridgeTests(unittest.TestCase):
    def test_decision_alone_cannot_create_execution_fact(self):
        with self.assertRaisesRegex(ValueError, "decision alone"):
            bridge_decision_to_execution(decision(), None, node_id="gadget-1")

    def test_observed_action_must_match_explicit_decision_action(self):
        with self.assertRaisesRegex(ValueError, "does not match"):
            bridge_decision_to_execution(
                decision(action="contain"),
                observation(observed_action="release"),
                node_id="gadget-1",
            )

    def test_transition_only_decision_cannot_correlate_execution(self):
        with self.assertRaisesRegex(ValueError, "no explicit chosen action"):
            bridge_decision_to_execution(
                decision(action="contain", action_type="transition"),
                observation(observed_action="contain"),
                node_id="gadget-1",
            )

    def test_matching_observation_projects_execution_and_mechanism_without_tactical_effect(self):
        execution, mechanism = bridge_decision_to_execution(
            decision(), observation(), node_id="gadget-1"
        )
        self.assertEqual(execution.decision_ref, "decision-1")
        self.assertEqual(execution.action, "contain")
        self.assertEqual(execution.status, "applied")
        self.assertIsNotNone(mechanism)
        assert mechanism is not None
        self.assertEqual(mechanism.mechanism_kind, "isolation")
        self.assertEqual(mechanism.status, "observed")
        self.assertFalse(hasattr(execution, "effect_class"))
        self.assertFalse(hasattr(mechanism, "tactical_effect"))

    def test_unverified_mechanism_remains_unverified_with_limitation(self):
        _, mechanism = bridge_decision_to_execution(
            decision(),
            observation(mechanism_status="unverified", mechanism_evidence_refs=()),
            node_id="gadget-1",
        )
        self.assertIsNotNone(mechanism)
        assert mechanism is not None
        self.assertEqual(mechanism.status, "unverified")
        self.assertIn("mechanism_not_independently_verified", mechanism.limitations)

    def test_mechanism_parameters_without_kind_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "require mechanism_kind"):
            observation(mechanism_kind=None, mechanism_parameters={"x": 1})


if __name__ == "__main__":
    unittest.main()
