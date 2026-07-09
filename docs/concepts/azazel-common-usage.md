# Using Azazel-Common in Azazel-Gadget

[`azazel-common`](https://github.com/01rabbit/Azazel-Common) is the shared
contract package for the Azazel series. Gadget (AZ-02) uses it so that it
speaks the same "language" as Edge (AZ-01) — the same status shape, the same
schemas — while keeping its own decision logic, hardware control, and
renderers local. Gadget is a **peer** of Edge, not a subset.

This page documents what Gadget uses from Common today and how it flows through
the system. For the full call-site plan see
[`azazel-common-adapter.md`](azazel-common-adapter.md).

## What Gadget uses today (v0.2.0)

Gadget depends on `azazel-common @ v0.2.0` (pinned in `requirements.txt`) and
uses **`azazel_common.view`** — the shared **status view-model**:

- `StatusView` — the normalized data a status surface shows (mode, posture,
  headline, reasons, current action, health, evidence).
- `build_status_view` — the single shared builder Gadget and Edge both call, so
  posture/headline are derived identically across products.

The import is **optional and guarded**: if `azazel-common` is not installed,
every integration point below becomes a no-op and Gadget runs exactly as
before. This matches the guarded-import pattern Gadget already uses for
`requests` and `PyYAML`.

## The flow: emit → read back → surface

```
first-minute controller
  │  write_snapshot()  (every ~2s)
  ├─►  ui_snapshot.json                     (unchanged, existing renderers)
  └─►  ui_status_view.json                  (NEW: shared StatusView)
            via py/azazel_gadget/common_view.py → azazel_common.view.build_status_view
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
  (`null` when Common is not installed).

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
Gadget-specific rides through untouched, so aligning to Common never narrows
AZ-02 to "Edge minus features."

## Enabling it

`azazel-common` is installed with the pip requirements:

```bash
pip install -r requirements.txt   # includes azazel-common @ v0.2.0
```

On a developer machine, `bin/azazel-gadget-devstack up` runs the controller and
web with Common installed, so you can see `status_view` in `/api/state` and the
EPD content at `/dev/epd`. See [`../DEV_LOCAL_STACK.md`](../DEV_LOCAL_STACK.md).

## Roadmap

- **Renderer migration (next):** switch the dashboard / TUI / E-Paper to render
  *primarily* from `status_view`, once field parity is confirmed in the UI.
  Today they read the existing snapshot and `status_view` is exposed alongside.
- **Future Common modules:** `azazel_common.paths` (Gadget's existing
  `path_schema` is the reference input), `azazel_common.audit`, and
  `azazel_common.notify` are later Common phases Gadget can adopt where they
  remove real duplication.