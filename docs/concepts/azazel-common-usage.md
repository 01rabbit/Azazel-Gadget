# Using Azazel-Fabric in Azazel-Gadget

[`azazel-fabric`](https://github.com/01rabbit/Azazel-Fabric) — **Azazel-Fabric**
(AZ-05, formerly Azazel-Common) — is the shared contract package for the
Azazel series. Gadget (AZ-02) uses it so that it speaks the same "language"
as Edge (AZ-01) — the same status shape, the same schemas — while keeping its
own decision logic, hardware control, and renderers local. Gadget is a
**peer** of Edge, not a subset.

This page documents what Gadget uses from Fabric today and how it flows through
the system. For the full call-site plan see
[`azazel-common-adapter.md`](azazel-common-adapter.md).

## What Gadget uses today (v0.4.0)

Gadget depends on `azazel-fabric @ v0.4.0` (pinned in `requirements.txt` to
a tag on the `01rabbit/Azazel-Fabric` repository) and uses
**`azazel_fabric.view`** — the shared **status view-model**:

- `StatusView` — the normalized data a status surface shows (mode, posture,
  headline, reasons, current action, health, evidence).
- `build_status_view` — the single shared builder Gadget and Edge both call, so
  posture/headline are derived identically across products.

The import is **optional and guarded** (see [Enabling it](#enabling-it)
below). If it is not installed, every integration point below becomes a
no-op and Gadget runs exactly as before. This matches the guarded-import
pattern Gadget already uses for `requests` and `PyYAML`.

## The flow: emit → read back → surface

```
first-minute controller
  │  write_snapshot()  (every ~2s)
  ├─►  ui_snapshot.json                     (unchanged, existing renderers)
  └─►  ui_status_view.json                  (NEW: shared StatusView)
            via py/azazel_gadget/common_view.py → azazel_fabric.view.build_status_view
                                   │
web UI (azazel_web/app.py)         │  read back
  ├─  GET /api/state  → adds "status_view"  ◄── control_plane.read_status_view_payload()
  ├─  /api/state/stream (SSE) → adds "status_view"
  └─  GET /api/epd / /dev/epd → EPD panel content (derived from the same state)
```

- **Emit:** `controller.write_snapshot` writes `ui_status_view.json` beside
  `ui_snapshot.json`, best-effort (never raises into the control loop).
- **Read back:** `control_plane.read_status_view_payload()` reads it.
- **Surface:** `/api/state` and the SSE stream include a `status_view` field
  (`null` when Fabric is not installed).

## Snapshot → StatusView mapping (peer, not subset)

`py/azazel_gadget/common_view.py` maps the Gadget UI snapshot into the shared
shape:

| StatusView field | Source in the Gadget snapshot |
|---|---|
| `product` | `"gadget"` |
| `mode` | current mode (`portal`/`shield`/`scapegoat`) |
| `posture` | derived from the FSM stage (`DECEPTION`→`deception`, `CONTAIN`→`contain`, `DEGRADED`→`degraded`, …) via the shared `build_status_view` |
| `reasons` / `operator_wording` | `reasons[]` / `recommendation` |
| `next_actions` | `next_action_hint` |
| `health[]` | `degrade`, `probe`, Suricata counts |
| `evidence_ids` | `evidence[]` |
| `product_view` | **the entire raw snapshot** — so Gadget-only detail (`attack{}` canary block, `connection{}`, the `DECEPTION` stage) is never lost |

The `product_view` field is the "peer, not subset" guarantee: everything
Gadget-specific rides through untouched, so aligning to Fabric never narrows
AZ-02 to "Edge minus features."

## Enabling it

`azazel-fabric` is installed with the pip requirements:

```bash
pip install -r requirements.txt   # includes azazel-fabric @ v0.4.0 (from 01rabbit/Azazel-Fabric)
```

On a developer machine, `bin/azazel-gadget-devstack up` runs the controller and
web with Fabric installed, so you can see `status_view` in `/api/state` and the
EPD content at `/dev/epd`. See [`../DEV_LOCAL_STACK.md`](../DEV_LOCAL_STACK.md).

## v0.4.0 module evaluation

Fabric v0.4.0 adds `azazel_fabric.paths`, `.audit`, `.api`, `.notify`, and
`.testing`. Each was evaluated against Gadget's existing code for a genuine,
zero-behavior-change adoption:

- **`azazel_fabric.testing`** (factories + invariant assertions): evaluated
  against `tests/test_common_view.py` and `tests/test_status_view_readback.py`,
  the two suites that touch Fabric shapes. Neither hand-builds a Fabric model
  that the factories would simplify — `test_common_view.py` exercises
  `common_view.status_view_from_snapshot()` against a Gadget-native snapshot
  dict (not a Fabric model) and only *parses* a `StatusView` back
  (`model_validate_json`) for its round-trip check; `test_status_view_readback.py`
  deliberately uses a bare, partial JSON dict so the suite stays
  `azazel_fabric`-free and runs unconditionally in CI. Adopting the factories
  there would force a hard `azazel_fabric` install onto a suite whose stated
  purpose is to run without it. No change made.
- **`azazel_fabric.notify`** (`to_ntfy_payload`/`to_mattermost_payload`):
  Gadget's `py/azazel_gadget/first_minute/notifier.py` (`NtfyNotifier`) posts
  to ntfy's plain-text publish endpoint with the title/priority/tags carried
  as HTTP *headers* and the body as the raw POST payload. Fabric's
  `to_ntfy_payload` returns a `{title, message, priority, tags}` **JSON body**
  shape for ntfy's JSON publish API — not byte-equivalent to what Gadget
  sends today. Gadget has no Mattermost integration. Not a drop-in — skipped.
- **`azazel_fabric.api` token helpers** (`extract_token`/`token_matches`):
  Gadget's `verify_token()` in `azazel_web/app.py` fail-*opens* when no token
  file is configured, also accepts a `?token=` query-string fallback, and
  compares with `==`. Fabric's `token_matches` is fail-closed (denies when no
  expected token), header-only, and constant-time. Different semantics by
  design — not a drop-in — skipped, matching the expectation set for this
  module.
- **`azazel_fabric.paths` / `.audit`**: no current Gadget call site exercises
  candidate-dir hinting or chain-free audit JSONL formatting; left for a
  future pass rather than force-fit here.

## Roadmap

- **Renderer migration (next):** switch the dashboard / TUI / E-Paper to render
  *primarily* from `status_view`, once field parity is confirmed in the UI.
  Today they read the existing snapshot and `status_view` is exposed alongside.
- **Future Fabric modules:** `azazel_fabric.paths` (Gadget's existing
  `path_schema` is the reference input) and `azazel_fabric.audit` are later
  Fabric phases Gadget can adopt where they remove real duplication.
  `azazel_fabric.notify` and the `azazel_fabric.api` token helpers were
  evaluated at v0.4.0 and are not drop-ins for Gadget's current
  ntfy/token-auth code (see above); revisit only as part of a deliberate
  behavior change, not a pin bump.