"""Conservative bridge from Tactics Engine decisions to Outcome-as-Evidence facts.

A DecisionRecord is intent/audit evidence only.  It is never sufficient to
create an execution fact.  Callers must provide a separate observation from
the component that actually attempted/applied the local mechanism.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Any

from azazel_gadget.outcome_evidence import (
    LocalExecutionFact,
    LocalMechanismFact,
    build_execution_fact,
    build_mechanism_fact,
)
from azazel_gadget.tactics_engine.decision_logger import DecisionRecord


_ALLOWED_STATUS = {"applied", "partial", "failed", "rejected", "unverified", "released"}
_ALLOWED_MECHANISMS = {
    "traffic_shaping", "redirection", "isolation", "notification",
    "observation_only", "unknown",
}


@dataclass(frozen=True)
class LocalExecutionObservation:
    """Independent local observation made after a decision.

    ``observed_action`` is the action the execution layer reports it actually
    attempted.  It must match one of the decision's chosen action details;
    absence/mismatch fails closed rather than guessing from state_after.
    """

    observed_action: str
    status: str
    observed_at: str
    evidence_refs: tuple[str, ...]
    mechanism_kind: str | None = None
    mechanism_status: str = "unverified"
    mechanism_parameters: Mapping[str, Any] | None = None
    mechanism_evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.observed_action.strip():
            raise ValueError("observed_action is required")
        if self.status not in _ALLOWED_STATUS:
            raise ValueError("invalid execution status")
        if not self.observed_at.strip():
            raise ValueError("observed_at is required")
        if not self.evidence_refs:
            raise ValueError("execution observation requires evidence refs")
        if self.mechanism_kind is not None and self.mechanism_kind not in _ALLOWED_MECHANISMS:
            raise ValueError("invalid mechanism kind")
        if self.mechanism_kind is None and self.mechanism_parameters:
            raise ValueError("mechanism parameters require mechanism_kind")


def _decision_actions(record: DecisionRecord) -> set[str]:
    actions: set[str] = set()
    for chosen in record.chosen:
        detail = chosen.detail if isinstance(chosen.detail, dict) else {}
        for key in ("action", "stage", "target_stage", "name"):
            value = detail.get(key)
            if isinstance(value, str) and value.strip():
                actions.add(value.strip().lower())
        # Existing records sometimes carry the action in the action_type itself.
        if chosen.action_type not in {"transition", "action", "constraint"}:
            actions.add(str(chosen.action_type).strip().lower())
    return actions


def bridge_decision_to_execution(
    record: DecisionRecord,
    observation: LocalExecutionObservation | None,
    *,
    node_id: str,
) -> tuple[LocalExecutionFact, LocalMechanismFact | None]:
    """Project independently observed execution after a deterministic decision.

    Decision-only input is deliberately rejected.  The bridge does not infer an
    execution from ``state_after`` and never emits DELAY/DIVERT/tactical success.
    """

    if observation is None:
        raise ValueError("decision alone cannot create execution evidence")
    if not node_id.strip():
        raise ValueError("node_id is required")

    decision_actions = _decision_actions(record)
    observed_action = observation.observed_action.strip().lower()
    if not decision_actions:
        raise ValueError("decision contains no explicit chosen action to correlate")
    if observed_action not in decision_actions:
        raise ValueError("observed execution action does not match decision")

    execution = build_execution_fact(
        node_id=node_id,
        trace_id=record.decision_id,
        decision_ref=record.decision_id,
        action=observed_action,
        status=observation.status,
        observed_at=observation.observed_at,
        evidence_refs=observation.evidence_refs,
    )

    mechanism: LocalMechanismFact | None = None
    if observation.mechanism_kind is not None:
        mechanism = build_mechanism_fact(
            execution,
            mechanism_kind=observation.mechanism_kind,
            status=observation.mechanism_status,
            observed_at=observation.observed_at,
            observed_parameters=dict(observation.mechanism_parameters or {}),
            evidence_refs=observation.mechanism_evidence_refs,
            limitations=() if observation.mechanism_status == "observed" else ("mechanism_not_independently_verified",),
        )
    return execution, mechanism
