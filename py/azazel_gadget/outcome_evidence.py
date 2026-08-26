"""Low-cost, non-authoritative Outcome-as-Evidence projection for Gadget.

Gadget contributes execution/mechanism/outcome facts from its local deterministic
controls. It deliberately does not label DELAY, DIVERT, success, attacker
belief, or global initiative. Higher-level assessment belongs outside Gadget.
"""

from __future__ import annotations

import hashlib
import json
from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

_ALLOWED_EXECUTION_STATUS = {"applied", "partial", "failed", "rejected", "unverified", "released"}
_ALLOWED_MECHANISMS = {
    "traffic_shaping", "redirection", "isolation", "notification",
    "observation_only", "unknown",
}
_ALLOWED_MECHANISM_STATUS = {"observed", "not_observed", "unverified", "released", "stale", "disputed"}
_BANNED_KEYS = {
    "effect_class", "tactical_effect", "success", "successful", "attacker_belief",
    "model_recommendation", "execute", "execution_command", "provider_command",
    "command", "commands", "approve", "approval", "override", "arbiter_override",
    "auto_execute", "select_action", "selected_action",
}
_MAX_MAP_ITEMS = 48
_MAX_LIST_ITEMS = 96
_MAX_STRING = 1024
_MAX_DEPTH = 5


def _normalized_key(raw: str) -> str:
    normalized = "".join(ch.lower() if ch.isalnum() else "_" for ch in raw.strip())
    while "__" in normalized:
        normalized = normalized.replace("__", "_")
    return normalized.strip("_")


def _is_forbidden_key(raw: str) -> bool:
    key = _normalized_key(raw)
    return (
        key in _BANNED_KEYS
        or "provider_command" in key
        or key.endswith("_command")
        or key.startswith("command_")
        or key.startswith("success_")
        or key.endswith("_success")
        or "attacker_belief" in key
        or "model_recommendation" in key
        or "effect_class" in key
        or "tactical_effect" in key
    )


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
            if _is_forbidden_key(key):
                raise ValueError(f"forbidden tactical/authority field: {key}")
            if len(key) > 128:
                raise ValueError("evidence payload contains oversized key")
            _validate_bounded(child, depth=depth + 1)
        return
    if isinstance(value, (list, tuple)):
        if len(value) > _MAX_LIST_ITEMS:
            raise ValueError("evidence payload list too large")
        for child in value:
            _validate_bounded(child, depth=depth + 1)
        return
    raise ValueError(f"unsupported evidence value: {type(value).__name__}")


def _require_text(label: str, value: Any, *, optional: bool = False) -> None:
    if optional and value is None:
        return
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    if len(value) > _MAX_STRING:
        raise ValueError(f"{label} is oversized")


def _require_refs(label: str, value: tuple[str, ...]) -> None:
    if not isinstance(value, tuple) or len(value) > _MAX_LIST_ITEMS:
        raise ValueError(f"{label} must be a bounded tuple")
    for item in value:
        _require_text(label, item)


def _require_chain_fields(
    *,
    producer_product: str,
    producer_node: str,
    trace_id: str,
    decision_ref: str,
    execution_ref: str,
    observed_at: str,
) -> None:
    for label, value in (
        ("producer_product", producer_product),
        ("producer_node", producer_node),
        ("trace_id", trace_id),
        ("decision_ref", decision_ref),
        ("execution_ref", execution_ref),
        ("observed_at", observed_at),
    ):
        _require_text(label, value)


def _stable_id(prefix: str, *parts: str) -> str:
    for index, part in enumerate(parts):
        _require_text(f"id_part_{index}", part)
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
        _require_chain_fields(
            producer_product=self.producer_product,
            producer_node=self.producer_node,
            trace_id=self.trace_id,
            decision_ref=self.decision_ref,
            execution_ref=self.execution_ref,
            observed_at=self.observed_at,
        )
        _require_text("action", self.action)
        _require_text("release_ref", self.release_ref, optional=True)
        _require_refs("evidence_refs", self.evidence_refs)


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
        _require_chain_fields(
            producer_product=self.producer_product,
            producer_node=self.producer_node,
            trace_id=self.trace_id,
            decision_ref=self.decision_ref,
            execution_ref=self.execution_ref,
            observed_at=self.observed_at,
        )
        _require_text("observation_id", self.observation_id)
        _require_refs("evidence_refs", self.evidence_refs)
        _require_refs("limitations", self.limitations)
        if not isinstance(self.observed_parameters, Mapping):
            raise ValueError("observed_parameters must be a mapping")
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
        _require_chain_fields(
            producer_product=self.producer_product,
            producer_node=self.producer_node,
            trace_id=self.trace_id,
            decision_ref=self.decision_ref,
            execution_ref=self.execution_ref,
            observed_at=self.observed_at,
        )
        _require_text("observation_id", self.observation_id)
        _require_text("mechanism_observation_ref", self.mechanism_observation_ref, optional=True)
        _require_text("subject_ref", self.subject_ref, optional=True)
        _require_text("window_start", self.window_start)
        _require_text("window_end", self.window_end)
        _require_text("observation_class", self.observation_class)
        _require_refs("confounders", self.confounders)
        _require_refs("evidence_refs", self.evidence_refs)
        for label, value in (
            ("observation_values", self.observation_values),
            ("telemetry_coverage", self.telemetry_coverage),
            ("resource_impact", self.resource_impact),
        ):
            if not isinstance(value, Mapping):
                raise ValueError(f"{label} must be a mapping")
            _validate_bounded(value)


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

    if before_metrics is not None and not isinstance(before_metrics, Mapping):
        raise ValueError("before_metrics must be a mapping or None")
    if after_metrics is not None and not isinstance(after_metrics, Mapping):
        raise ValueError("after_metrics must be a mapping or None")
    before = dict(before_metrics or {})
    after = dict(after_metrics or {})
    _validate_bounded(before)
    _validate_bounded(after)
    confounders: list[str] = []
    coverage = {
        "before_present": before_metrics is not None,
        "after_present": after_metrics is not None,
    }
    values: dict[str, Any] = {"before": before, "after": after}
    if before_metrics is None:
        confounders.append("missing_pre_telemetry")
    if after_metrics is None:
        confounders.append("missing_post_telemetry")

    deltas: dict[str, float] = {}
    for key in sorted(set(before) & set(after)):
        left, right = before[key], after[key]
        if (
            isinstance(left, (int, float))
            and isinstance(right, (int, float))
            and not isinstance(left, bool)
            and not isinstance(right, bool)
        ):
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
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0:
            raise ValueError("limit must be a non-negative integer")
        result: list[str] = []
        for _ in range(min(limit, len(self._items))):
            result.append(self._items.popleft())
        return result

    @property
    def depth(self) -> int:
        return len(self._items)
