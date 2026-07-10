# Azazel-Fabric (formerly Azazel-Common) Gadget Adapter Plan

> **Document status:** This was the *original* integration plan (Issue 6
> deliverable) written before adoption landed, when the shared-contracts
> repository was still named `Azazel-Common` (now renamed to
> `01rabbit/Azazel-Fabric`, AZ-05). It is kept for historical record and its
> body intentionally still uses the names and paths current at the time it was
> written. What actually shipped is documented in
> [`azazel-common-usage.md`](azazel-common-usage.md), which **supersedes this
> note wherever the two differ** (notably: Gadget ended up pinned to
> `azazel-common v0.2.0`, not the `v0.1.0` referenced below, and the
> dependency-manifest question in §2 was resolved via `requirements.txt`).
> Treat this file as design-history context, not as the current contract.

Status: **Design note / proposal only.** No adapter code is written by this
document, and no existing Gadget behavior is changed. This is the deliverable
for Issue 6 in `Azazel-Common/docs/issue-breakdown.md`, implementing the
planning step of `Azazel-Common/docs/migration-plan.md` Phase 4.

This note identifies the *exact* call sites in Gadget (AZ-02) that would
serialize through `azazel_common` schemas, states explicitly which code is
**not** touched, treats Gadget as a **peer of Edge (not a subset)**, records how
Gadget's existing path schema feeds a later issue, confirms zero behavior
change to the demo paths, and defines a per-adapter rollback point. Whether the
adapters themselves are implemented next is gated on review of this note.

**CTI is not in scope.** Gadget has no CTI integration, and `migration-plan.md`
Phase 4 (Gadget) is intentionally CTI-free — it covers only `StateSnapshot`,
`ModeState`, `ActionIntent`, `AuditEvent`, and notification payloads. Any future
Gadget↔CTI connection is a next-fiscal-year-onward (FY2027+) concern and is out
of scope here.

## 1. Gadget is a sibling of Edge, not a reduced Edge

Per `docs/SERIES_POSITIONING_AND_TERMS.md` and `docs/INDEX.md`, AZ-02 is a peer
product, not a reduced variant of AZ-01. This adapter work must therefore map
Gadget onto the shared schema **without** assuming Edge's field set is the
baseline. Concretely, these Gadget-only shapes must survive round-tripping and
are carried in open enums / the loosely-typed `summary`/`payload` fields, never
dropped to fit an Edge-shaped model (`Azazel-Common/docs/design-principles.md`
§4.4):

- **`Stage.DECEPTION`** — the 6-state first-minute FSM
  (`INIT/PROBE/DEGRADED/NORMAL/CONTAIN/DECEPTION`,
  `py/azazel_gadget/first_minute/state_machine.py:9-15`) includes a
  Suricata+OpenCanary-driven deception stage Edge does not have.
- **`scapegoat` mode + decoy namespace** — the `scapegoat` gateway posture with
  its isolated network namespace (`ns` in the EPD/mode state).
- **`attack{canary_delay_*}` telemetry** — the canary-delay attack block in the
  UI snapshot (`controller.py:1023-1046`): `canary_delay_active`,
  `canary_delay_target_count`, `canary_delay_targets[]`, etc.

## 2. Prerequisite and dependency pinning — an open decision

Depends on `azazel-common` `v0.1.0` (schema-only), already tagged/released on
`01rabbit/Azazel-Common`. Pinned tag form
(`Azazel-Common/docs/design-principles.md` §6):

```
azazel-common @ git+https://github.com/01rabbit/Azazel-Common.git@v0.1.0
```

**Gap to resolve first:** Gadget has **no dependency manifest at all** — no
`pyproject.toml`, `setup.py`, or `requirements*.txt`. `py/` is placed on
`sys.path` directly, and third-party deps are declared imperatively in
`installer/stages/10_dependencies.sh` (apt: `python3-requests`, `python3-yaml`,
Flask pinned in a venv, etc.). So pinning `azazel-common` requires a **choice**,
which review should settle before any adapter lands:

- (a) add an install line to `installer/stages/10_dependencies.sh` (~`:32`), or
- (b) introduce a real `requirements.txt` / `pyproject.toml` at repo root.

This is a bigger prerequisite than on the Edge side (Edge already has
`requirements/runtime.txt`). Recommendation: (b), a minimal `requirements.txt`
so the pin is declarative and reviewable, with the installer sourcing it — but
this is explicitly deferred to review.

## 3. Boundary map — serialization vs. decision/execution logic

Gadget's loop (`first_minute/controller.py`) ingests signals → the FSM
(`state_machine.py`) sets a `Stage` → enforcement is delegated to `nft`/`tc` →
state/mode/notification are written out → decisions are audited. Only the
**write-out / audit** surfaces are serialization boundaries. The FSM scoring,
the arbiter-equivalent stage selection, and all `nft`/`tc`/radio/USB execution
are decision/execution logic and out of scope (§7). Gadget only standardizes
how state/mode/decisions are *written down*, not how they are *decided* or
*enforced*.

## 4. Adapter sites (existing code that would wrap Common schemas)

Each row is an independent, **emit-alongside** adapter: it adds a Common-shaped
serialization *next to* the existing write and does not replace or alter the
existing output until contract tests prove parity (Issue 4). Each is its own
commit and rollback point.

### 4.1 State → `azazel_common.schema.StateSnapshot`

- **Primary site (UI snapshot):** `py/azazel_gadget/first_minute/controller.py`
  — dict built at `controller.py:1050-1098`, written at `controller.py:1135-1141`
  (`json.dumps(snap, ...)` → atomic `os.replace` into the runtime snapshot
  paths).
- **FSM verdict source:** `first_minute/state_machine.py:238-244` `step()`
  returns `{state, suspicion, reason, changed}`.
- **Other serialization surfaces that would consume the same projection:** the
  status API `StatusHandler` (`controller.py:57-77`), the legacy Web API
  `web_api.py:56-81`, and the Flask `GET /api/state` / SSE stream
  (`azazel_web/app.py:1049-1100`).
- **Mapping:** `StateSnapshot(product="gadget", schema_version, mode=<§4.2>,
  generated_at=snap ts, trace_id=<synthesized — see §8>, summary={...})`. The
  large Gadget-specific payload (`attack{}`, `connection{}`, `probe{}`,
  `degrade{}`, sensor metrics) rides in `StateSnapshot.summary` (the loosely
  typed field exists precisely for product-specific state that does not warrant
  a shared shape yet). No Gadget field is lost.
- **Rollback point:** revert the single commit that adds the Common projection
  next to `write_snapshot`; the existing snapshot write is untouched.

### 4.2 Mode → `azazel_common.schema.ModeState`

- **Site:** `py/azazel_control/mode_manager.py` — `ModeManager.status()`
  (`:73-99`) and the persisted `mode.json` written by `_write_mode_state()`
  (`:684`), record shape `{current_mode, last_change, requested_by,
  config_hash}` (`:146-151`).
- **Mode set:** `MODE_CHOICES = ("portal", "shield", "scapegoat")`
  (`mode_manager.py:32`), default `shield`. All three are already in
  `azazel_common`'s `KNOWN_MODE_NAMES` — **clean mapping, no new enum values
  needed**, and `ModeState.name` is an open `str` enum so this stays
  non-breaking.
- **Mapping:** `ModeState(name=current_mode, since=last_change,
  reason=requested_by/last audit reason)`. The EPD-only "switching"/"failed"
  render states (`epd_mode_refresh.py:98-124`) and the "warning display state"
  are **not** modes (per `SERIES_POSITIONING_AND_TERMS.md`) and are deliberately
  not modeled as `ModeState` — consistent with Common leaving display state out.
- **Rollback point:** projection emit in `status()`/`_write_mode_state` is
  additive; revert one commit.

### 4.3 Action intent → `azazel_common.schema.ActionIntent`

- **Site (serialized intent):** `tactics_engine/decision_logger.py:41`
  `ChosenAction{action_type, detail}` (`action_type ∈
  {"transition","action","constraint"}`), constructed at
  `controller.py:2371-2376`.
- **Vocabulary mismatch to flag (Issue 3):** Gadget's `action_type`
  (`transition`/`action`/`constraint`) is **not** the `ActionKind` vocabulary
  (`observe/notify/throttle/redirect/isolate/decoy/release`). The natural
  bridge is the FSM `Stage`: `NORMAL→observe`, `DEGRADED→throttle`,
  `CONTAIN→isolate`, `DECEPTION→decoy`, notification→`notify`. `decoy` and
  `release` in Common cover Gadget's deception/release semantics — a point in
  favor of Common already being a superset, not an Edge-only set.
- **Not an executor:** the actual enforcement (`first_minute/nft.py:60`
  `set_stage`, `first_minute/tc.py:33` `apply` / `:63` `apply_deception_delay`)
  is execution logic and is **out of scope** — the adapter serializes the
  intent, it never wraps the nft/tc calls.
- **Rollback point:** additive projection; revert one commit.

### 4.4 Audit → `azazel_common.schema.AuditEvent`

Gadget has **two** audit writers; both map to `AuditEvent` via `event_type`,
each as its own emit-alongside adapter:

- **Rich decision log:** `tactics_engine/decision_logger.py` `DecisionRecord`
  (`:48-88`), writer `log_decision()` (`:115-134`), path
  `/opt/azazel/logs/tactics_engine/decision_explanations.jsonl` (`:105`); write
  site `controller.py:2378-2397`.
- **Mode-change log:** `mode_manager.py:1011` `_log_mode_change(...)`, record
  `{ts, from, to, by, result, reason}`, path
  `/var/log/azazel/mode_changes.jsonl` (`mode_manager.py:37`).
- **Structural gap to flag (Issue 3):** neither writer carries `trace_id`,
  `hmac`, or a hash chain. `DecisionRecord` has `decision_id` (UUID4) +
  `config_hash` only. So mapping to `AuditEvent`:
  - `AuditEvent.event_id` ← `decision_id` (decision log) / synthesized (mode
    log); `event_type` ← the writer/kind; `config_hash` ← the record's
    `config_hash` (already `"sha256:..."`, matching Edge's convention);
    `hmac` ← left `None` (Gadget has no HMAC today); the rest rides in
    `payload`.
  - `trace_id` is **required by `AuditEvent`** but Gadget has no trace_id
    convention at all (§8, item 1) — a synthesized value is needed.
- **Rollback point:** each writer's projection is additive to a separate
  stream; revert its commit.

### 4.5 Notification → shared notification model (Common Phase 5)

- **Site:** `first_minute/notifier.py:21` `NtfyNotifier` — `notify_alert`
  (`:56-92`), `notify_info` (`:94-130`), low-level `_send` (`:132-186`); send
  call sites `controller.py:2555-2596`.
- **Payload today:** `{title, body, tags[], priority (1–5), event_key}`. **This
  is ntfy-only; there is no Mattermost and no SSE-as-notifier in Gadget.**
- **Mapping to the shared model** (`azazel_common.notify`, a Phase-5 module not
  in `v0.1.0` yet — so this row is the *plan*, adopted when that module ships):
  `severity` ← derived from `priority` (e.g. ≥4 → `critical`/`warning`, else
  `info`); `title`/`body` direct; `trace_id`/`created_at` — **absent in Gadget**
  (§8), synthesized or left optional. `event_key` (dedupe) has no home in the
  Common model yet and would ride in an extension/`tags` until modeled.
- **Note:** Common's `notify` model includes a Mattermost helper; Gadget simply
  does not use it — a helper being available is not a mandate to adopt it
  (`migration-plan.md` Phase 5).
- **Rollback point:** additive; revert one commit (and gated on the Common
  `notify` module existing).

## 5. Path schema — input to Issue 7, not replaced here

Gadget already has a mature path-schema / legacy-migration implementation. Per
`migration-plan.md` Phase 4, it is reviewed as **input** to
`azazel_common.paths` (Issue 7 / Phase 5), **not replaced** in this phase.

- **Module:** `py/azazel_gadget/path_schema.py` (+ thin CLI
  `py/azazel-path-schema.py`).
- **Legacy name mapping (`_order_for`, `path_schema.py:33-37`):** the legacy
  pair is **`azazel-zero` ↔ `azazel-gadget`** — v2 prefers `azazel-gadget`
  (legacy `azazel-zero`), v1 the reverse. There is **no** `azazel-pi`→
  `azazel-edge` mapping in this repo; that pairing is an Edge-side concern.
  This matches `Azazel-Common/docs/contracts.md` §5 (`azazel-zero` →
  `azazel-gadget`).
- **Conventions (already `/run|/etc|/var/log/azazel-<name>`):**
  `runtime_dir_candidates` (`:80`), `config_dir_candidates` (`:90`),
  `log_dir_candidates` (`:85`) — the exact `/run|/etc|/var/log/azazel-<product>`
  shape `azazel_common.paths` is proposed to generalize.
- **Dry-run migration:** `migrate_schema(target_schema, dry_run=False)`
  (`:212-310`) records `actions[]`/`rollback_hints` without executing when
  `dry_run` — the "never silently move/delete" property Common's helper must
  preserve. Legacy-deprecation date `2026-12-31` (`:12`).
- **Take-away for Issue 7:** generalize Gadget's design, do **not** copy it
  wholesale — Gadget-specific assumptions (the `azazel-zero` legacy name, the
  fixed `/run/azazel/...` control-plane paths) must not leak into the shared
  version (`migration-plan.md` Phase 5).

## 6. (No CTI adapter)

Unlike the Edge plan, there is no CTI section: Gadget has no CTI client and
Phase 4 does not introduce one. Recorded here only so the omission is explicit,
not an oversight.

## 7. Explicitly NOT touched (decision / execution / hardware — out of scope)

| Component | Path | Why out of scope |
|---|---|---|
| Wi-Fi connection control | `py/azazel_control/wifi_connect.py`, `wifi_scan.py`; `py/azazel_gadget/sensors/wifi_*.py` | Associates/scans the radio via `nmcli`/`iw`. Hardware control; the adapter only *reads* their output via the snapshot `connection{}` block. |
| USB gadget / `usb0` bring-up | `scripts/usb0-static.sh`, `systemd/usb0-static.service`, `scripts/azazel-nat.sh` | Brings up and NATs the protected `usb0` side. Hardware/topology. |
| Captive portal **viewer** | `scripts/azazel-portal-viewer.sh`; Flask `azazel_web/app.py:1103-1111` | Renders the captive portal (Xvfb/chromium/noVNC). This is the viewer, distinct from the `portal` **mode** (§4.2) and from portal **detection** (`bin/portal_detect.sh`, which only feeds snapshot `connection.captive_*`). |
| FSM scoring / stage selection | `first_minute/state_machine.py` (scoring), `nft.py`, `tc.py` | Deterministic decision + enforcement. The arbiter-equivalent decides; Common only serializes the result. |

The adapter reads the *outputs* of these (the snapshot dict, the mode state, the
decision record) to build Common schemas; it never calls into or modifies them.

## 8. Zero behavior change & rollback posture

- Every adapter in §4 is **emit-alongside**: it writes a Common-shaped copy to a
  *separate* stream and leaves the existing snapshot / mode.json / audit JSONL
  writes byte-for-byte unchanged until contract tests (Issue 4) prove parity.
- The producing paths (`controller.py` main loop `:2308-2397`, `mode_manager`
  `set_mode`) run exactly as today; the adapter only reads the dict/record they
  already produce. The `set_mode` **dry-run** path (`mode_manager.py:128-138`)
  is untouched.
- Verification before any adapter merge: run the project's demo/verify checks
  and `pytest` (the existing `tests/` suite must stay green unmodified).
- Rollback points, in dependency order:
  1. Resolve the dependency-manifest decision (§2) and add the `azazel-common`
     pin (import-only).
  2. State projection in `first_minute/controller.py`.
  3. Mode projection in `azazel_control/mode_manager.py`.
  4. Action-intent projection alongside the decision log.
  5. Audit projections (two writers, separate streams).
  6. Notification projection (gated on the Common `notify` module shipping in a
     later release).

## 9. Open questions for review (feed Issue 3 / Issue 7)

1. **`trace_id` is absent across Gadget** — decision log, mode log, snapshot,
   and notifications carry no `trace_id`, but several `azazel_common` models
   require it. Decide: synthesize a `trace_id` at the adapter boundary (e.g.
   from `decision_id` / `snapshot_epoch`), or introduce a real trace_id thread
   in Gadget. This is the single biggest gap and should be settled first.
2. **Action vocabulary** — confirm the FSM-`Stage`→`ActionKind` bridge in §4.3
   (`NORMAL/DEGRADED/CONTAIN/DECEPTION` → `observe/throttle/isolate/decoy`)
   rather than trying to map the internal `action_type`
   (`transition/action/constraint`).
3. **Two audit writers** — confirm both `DecisionRecord` and the mode-change log
   project to `AuditEvent` (differentiated by `event_type`), and how the missing
   `hmac`/chain and required `event_id`/`trace_id` are populated.
4. **Sibling extensions** — confirm `Stage.DECEPTION`, `scapegoat`+namespace, and
   the `attack{canary_delay_*}` block are preserved via `summary`/open enums, so
   Gadget is not silently narrowed to an Edge-shaped subset.
5. **Dependency manifest** — settle §2 (installer line vs. new
   `requirements.txt`/`pyproject.toml`) before any adapter lands.
6. **Path schema (Issue 7)** — Gadget's `azazel-zero`↔`azazel-gadget` mapping and
   dry-run migrator are the reference input; confirm they inform, not dictate,
   `azazel_common.paths`.
