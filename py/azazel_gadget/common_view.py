"""Adapter: Gadget UI snapshot -> shared `azazel_common` StatusView.

This is the emit-alongside step of `docs/concepts/azazel-common-adapter.md`:
Gadget builds the shared status view-model *next to* its existing snapshot,
without changing what any renderer currently reads. The Web UI / TUI / E-Paper
renderers are switched to consume this view only after parity is confirmed.

`azazel_common` is imported optionally. If it is not installed (it is pinned in
`requirements.txt` to a tagged release), every function here becomes a safe
no-op, so Gadget runs identically with or without the shared package — matching
the guarded-import pattern already used for `requests`/`yaml`.

Gadget is a peer of Edge, not a subset: the whole raw snapshot is carried in
`StatusView.product_view`, so Gadget-only fields (the `attack{}` canary block,
`connection{}`, `DECEPTION` stage) are never lost.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Iterable, List, Optional

try:  # optional dependency — pinned in requirements.txt, absent is fine
    from azazel_common.schema.mode import ModeState
    from azazel_common.view import HealthDimension, StatusView, build_status_view

    HAVE_AZAZEL_COMMON = True
except Exception:  # pragma: no cover - exercised only when the dep is absent
    HAVE_AZAZEL_COMMON = False


def _evidence_ids(snap: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    for item in snap.get("evidence") or []:
        if isinstance(item, dict):
            ident = item.get("id") or item.get("evidence_id")
            if ident:
                out.append(str(ident))
        elif item:
            out.append(str(item))
    return out


def _health(snap: Dict[str, Any]) -> list:
    """Map a few Gadget signals into render-agnostic health rows."""
    rows = []
    degrade = snap.get("degrade") or {}
    if degrade:
        on = bool(degrade.get("on"))
        rows.append(
            HealthDimension(
                key="link",
                label="degraded" if on else "nominal",
                status="warn" if on else "ok",
                detail=f"rtt_ms={degrade.get('rtt_ms')} rate_mbps={degrade.get('rate_mbps')}",
            )
        )
    probe = snap.get("probe") or {}
    if probe:
        blocked = bool(probe.get("blocked"))
        rows.append(
            HealthDimension(
                key="probe",
                label=f"{probe.get('tls_ok')}/{probe.get('tls_total')}",
                status="critical" if blocked else "ok",
            )
        )
    crit = snap.get("suricata_critical")
    if crit is not None:
        rows.append(
            HealthDimension(
                key="suricata",
                label=f"crit={crit} warn={snap.get('suricata_warning')}",
                status="critical" if crit else "ok",
            )
        )
    return rows


def status_view_from_snapshot(
    snap: Dict[str, Any], mode_name: Optional[str] = None
) -> "Optional[StatusView]":
    """Build a shared `StatusView` from a Gadget UI snapshot dict.

    Returns ``None`` if `azazel_common` is not installed. Never raises for
    ordinary shape variation — missing keys degrade to defaults.
    """
    if not HAVE_AZAZEL_COMMON:
        return None

    internal = snap.get("internal") or {}
    state_word = internal.get("state_name")
    resolved_mode = str(mode_name or snap.get("mode") or "shield").lower()
    since = str(snap.get("now_time") or snap.get("snapshot_epoch") or "")

    next_hint = snap.get("next_action_hint")
    next_actions: Iterable[str] = [str(next_hint)] if next_hint else []

    return build_status_view(
        product="gadget",
        mode=ModeState(name=resolved_mode, since=since),
        generated_at=since,
        state_word=state_word,
        reasons=[str(r) for r in (snap.get("reasons") or [])],
        operator_wording=(str(snap["recommendation"]) if snap.get("recommendation") else None),
        next_actions=next_actions,
        health=_health(snap),
        evidence_ids=_evidence_ids(snap),
        # Superset: carry the whole raw snapshot so no Gadget-only field is lost.
        product_view={"gadget_snapshot": snap},
    )


def write_status_view_alongside(
    snap: Dict[str, Any],
    snapshot_paths: Iterable[Any],
    mode_name: Optional[str] = None,
    logger: Any = None,
) -> None:
    """Write a StatusView JSON next to each snapshot path. Best-effort no-op.

    For a snapshot at ``<dir>/ui_snapshot.json`` the view is written to
    ``<dir>/ui_status_view.json``. This never raises into the caller and does
    nothing when `azazel_common` is absent.
    """
    if not HAVE_AZAZEL_COMMON:
        return
    try:
        view = status_view_from_snapshot(snap, mode_name=mode_name)
        if view is None:
            return
        payload = view.model_dump_json()
    except Exception as exc:  # pragma: no cover - defensive
        if logger is not None:
            logger.debug(f"status_view: build failed: {exc}")
        return

    for snap_path in snapshot_paths:
        try:
            view_path = snap_path.with_name("ui_status_view.json")
            view_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = view_path.with_suffix(view_path.suffix + ".tmp")
            tmp_path.write_text(payload, encoding="utf-8")
            os.replace(tmp_path, view_path)
        except Exception as exc:  # pragma: no cover - defensive
            if logger is not None:
                logger.debug(f"status_view: failed to write beside {snap_path}: {exc}")
