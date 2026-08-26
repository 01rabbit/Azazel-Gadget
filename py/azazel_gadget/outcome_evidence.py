"""Low-cost, non-authoritative Outcome-as-Evidence projection for Gadget.

Gadget contributes execution/mechanism/outcome facts from its local deterministic
controls.  It deliberately does not label DELAY, DIVERT, success, attacker
belief, or global initiative.  Higher-level assessment belongs outside Gadget.
"""

from __future__ import annotations

import hashlib
import json
from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

_ALLOWED_EXECUTION_STATUS = {"applied", "partial", "failed", "rejected", "unverified", "released"}
_ALLOWED_MECHANISMS = {
    "traffic_shaping",
    "redirection",
    "isolation",
    "notification",
    "observation_only",
    "unknown",
}
_ALLOWED_MECHANISM_STATUS = {"observed", "not_observed", "unverified", "released", "stale", "disputed"}
_BANNED_KEYS = {
    "effect_class", "tactical_effect", "success", "successful", "attacker_belief",
    "model_recommendation", "execute", "approve", "override", "select_action",
}
_MAX_MAP_ITEMS = 48
_MAX_LIST_ITEMS = 96
_MAX_STRING = 1024
_MAX_DEPTH = 5


def _validate_bounded(value: Any, *, depth: int = 0) -> None:
    if depth > _MAX_DEPTH:
        raise ValueError("evidence payload exceeds maximum depth")
    if isinstance(value, str):
        if len(value) > _MAX_STRING:
            raise ValueError("evidence payload contains oversized string")
        return
    if value is None or isinstance(value, (bool, int, float)):
        return
    if isinstance(value, Mapping):
        if len(value) > _MAX_MAP_ITEMS:
            raise ValueError("evidence payload map too large")
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValueError("evidence keys must be strings")
            if key.strip().lower() in _BANNED_KEYS:
                raise ValueError(f"forbidden tactical/authority field: {key}")
            _validate_bounded(child, depth=depth + 1)
        return
    if isinstance(value, (list, tuple)):
        if len(value) > _MAX_LIST_ITEMS:
            raise ValueError("evidence payload list too large")
        for child in value:
            _validate_bounded(child, depth=depth + 1)
        return
    raise ValueError(f"unsupported evidence value: {type(value).__name__}")


def _stable_id(prefix: str, *parts: str) -> str:
    raw = "|".join(parts).encode("utf-8")
    return prefix + "-" + hashlib.sha256(raw).hexdigest()[:24]


@dataclass(frozen=True)
class LocalExecutionFact:
    schema_version: str
    producer_product: str
    producer_node: str
    trace_id: str
    decision_ref: str
    execution_ref: str
    action: str
    status: str
    observed_at: str
    evidence_refs: tuple[str, ...] = ()
    release_ref: str | None = None
    authority_class: str = "producer_execution_fact"

    def __post_init__(self) -> None:
        if self.schema_version != "outcome-execution/v0.1":
            raise ValueError("unsupported execution schema")
        if self.status not in _ALLOWED_EXECUTION_STATUS:
            raise ValueError("invalid execution status")
        if self.authority_class != "producer_execution_fact":
            raise ValueError("invalid execution authority class")
        if not all((self.producer_node, self.trace_id, self.decision_ref, self.execution_ref, self.action, self.observed_at)):
            raise ValueError("execution fact requires non-empty identity fields")


@dataclass(frozen=True)
class LocalMechanismFact:
    schema_version: str
    observation_id: str
    producer_product: str
    producer_node: str
    trace_id: str
    decision_ref: str
    execution_ref: str
    mechanism_kind: str
    status: str
    observed_parameters: Mapping[str, Any]
    observed_at: str
    evidence_refs: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    authority_class: str = "producer_mechanism_fact"

    def __post_init__(self) -> None:
        if self.schema_version != "outcome-mechanism/v0.1":
            raise ValueError("unsupported mechanism schema")
        if self.mechanism_kind not in _ALLOWED_MECHANISMS:
            raise ValueError("invalid mechanism kind")
        if self.status not in _ALLOWED_MECHANISM_STATUS:
            raise ValueError("invalid mechanism status")
        if self.authority_class != "producer_mechanism_fact":
            raise ValueError("invalid mechanism authority class")
        _validate_bounded(self.observed_parameters)


@dataclass(frozen=True)
class LocalOutcomeFact:
    schema_version: str
    observation_id: str
    producer_product: str
    producer_node: str
    trace_id: str
    decision_ref: str
    execution_ref: str
    mechanism_observation_ref: str | None
    subject_ref: str | None
    window_start: str
    window_end: str
    phase: str
    observation_class: str
    observation_values: Mapping[str, Any]
    telemetry_coverage: Mapping[str, Any]
    confounders: tuple[str, ...]
    resource_impact: Mapping[str, Any]
    evidence_refs: tuple[str, ...]
    observed_at: str
    authority_class: str = "producer_outcome_fact"

    def __post_init__(self) -> None:
        if self.schema_version != "outcome-observation/v0.1":
            raise ValueError("unsupported outcome schema")
        if self.phase not in {"before", "during", "after"}:
            raise ValueError("invalid observation phase")
        if self.authority_class != "producer_outcome_fact":
            raise ValueError("invalid outcome authority class")
        _validate_bounded(self.observation_values)
        _validate_bounded(self.telemetry_coverage)
        _validate_bounded(self.resource_impact)


def build_execution_fact(
    *,
    node_id: str,
    trace_id: str,
    decision_ref: str,
    action: str,
    status: str,
    observed_at: str,
    evidence_refs: tuple[str, ...] = (),
    release_ref: str | None = None,
) -> LocalExecutionFact:
    execution_ref = _stable_id("gadget-execution", node_id, trace_id, decision_ref, action)
    return LocalExecutionFact(
        schema_version="outcome-execution/v0.1",
        producer_product="azazel-gadget",
        producer_node=node_id,
        trace_id=trace_id,
        decision_ref=decision_ref,
        execution_ref=execution_ref,
        action=action,
        status=status,
        observed_at=observed_at,
        evidence_refs=evidence_refs,
        release_ref=release_ref,
    )


def build_mechanism_fact(
    execution: LocalExecutionFact,
    *,
    mechanism_kind: str,
    status: str,
    observed_at: str,
    observed_parameters: Mapping[str, Any] | None = None,
    evidence_refs: tuple[str, ...] = (),
    limitations: tuple[str, ...] = (),
) -> LocalMechanismFact:
    observation_id = _stable_id("gadget-mechanism", execution.execution_ref, mechanism_kind, observed_at)
    return LocalMechanismFact(
        schema_version="outcome-mechanism/v0.1",
        observation_id=observation_id,
        producer_product=execution.producer_product,
        producer_node=execution.producer_node,
        trace_id=execution.trace_id,
        decision_ref=execution.decision_ref,
        execution_ref=execution.execution_ref,
        mechanism_kind=mechanism_kind,
        status=status,
        observed_parameters=dict(observed_parameters or {}),
        observed_at=observed_at,
        evidence_refs=evidence_refs,
        limitations=limitations,
    )


def build_outcome_fact(
    execution: LocalExecutionFact,
    mechanism: LocalMechanismFact | None,
    *,
    subject_ref: str | None,
    window_start: str,
    window_end: str,
    phase: str,
    observed_at: str,
    before_metrics: Mapping[str, Any] | None,
    after_metrics: Mapping[str, Any] | None,
    evidence_refs: tuple[str, ...] = (),
) -> LocalOutcomeFact:
    """Build a conservative pre/post fact without tactical interpretation."""

    before = dict(before_metrics or {})
    after = dict(after_metrics or {})
    _validate_bounded(before)
    _validate_bounded(after)
    confounders: list[str] = []
    coverage = {
        "before_present": bool(before_metrics),
        "after_present": bool(after_metrics),
    }
    values: dict[str, Any] = {"before": before, "after": after}
    if not before_metrics:
        confounders.append("missing_pre_telemetry")
    if not after_metrics:
        confounders.append("missing_post_telemetry")

    deltas: dict[str, float] = {}
    for key in sorted(set(before) & set(after)):
        left, right = before[key], after[key]
        if isinstance(left, (int, float)) and isinstance(right, (int, float)) and not isinstance(left, bool) and not isinstance(right, bool):
            if right >= left:
                deltas[key] = float(right - left)
            else:
                confounders.append(f"counter_reset:{key}")
    if deltas:
        values["counter_deltas"] = deltas

    if mechanism is not None:
        expected = (execution.trace_id, execution.decision_ref, execution.execution_ref)
        current = (mechanism.trace_id, mechanism.decision_ref, mechanism.execution_ref)
        if current != expected:
            raise ValueError("mechanism does not belong to execution")

    observation_id = _stable_id("gadget-outcome", execution.execution_ref, phase, window_start, window_end)
    return LocalOutcomeFact(
        schema_version="outcome-observation/v0.1",
        observation_id=observation_id,
        producer_product=execution.producer_product,
        producer_node=execution.producer_node,
        trace_id=execution.trace_id,
        decision_ref=execution.decision_ref,
        execution_ref=execution.execution_ref,
        mechanism_observation_ref=mechanism.observation_id if mechanism else None,
        subject_ref=subject_ref,
        window_start=window_start,
        window_end=window_end,
        phase=phase,
        observation_class="gadget_local_metrics",
        observation_values=values,
        telemetry_coverage=coverage,
        confounders=tuple(dict.fromkeys(confounders)),
        resource_impact={},
        evidence_refs=evidence_refs,
        observed_at=observed_at,
    )


def canonical_fact_json(fact: LocalExecutionFact | LocalMechanismFact | LocalOutcomeFact) -> str:
    payload = asdict(fact)
    _validate_bounded(payload)
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@dataclass
class BoundedEvidenceSpool:
    """Non-blocking bounded local spool for disconnected operation."""

    max_entries: int = 256
    _items: deque[str] = field(default_factory=deque, init=False, repr=False)
    dropped: int = 0

    def __post_init__(self) -> None:
        if self.max_entries < 1 or self.max_entries > 4096:
            raise ValueError("max_entries must be between 1 and 4096")

    def enqueue(self, fact: LocalExecutionFact | LocalMechanismFact | LocalOutcomeFact) -> bool:
        encoded = canonical_fact_json(fact)
        if len(self._items) >= self.max_entries:
            self.dropped += 1
            return False
        self._items.append(encoded)
        return True

    def drain(self, limit: int | None = None) -> list[str]:
        if limit is None:
            limit = len(self._items)
        if limit < 0:
            raise ValueError("limit must be non-negative")
        result: list[str] = []
        for _ in range(min(limit, len(self._items))):
            result.append(self._items.popleft())
        return result

    @property
    def depth(self) -> int:
        return len(self._items)
