# Changelog

This file follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed

- Series-list consolidation (owner decision): product repositories no longer
  carry the full Azazel series table — it lives only in the umbrella
  repository (01rabbit/Azazel). README (EN/JA), docs/INDEX.md,
  SERIES_POSITIONING_AND_TERMS.md, and azazel-system-product-map.md now keep
  a short membership pointer (AZ-02, codename TACMOD) plus Gadget-local
  integration notes only.

### Changed
- Migrated to **Azazel-Fabric v0.3.0**: `requirements.txt` now pins
  `azazel-fabric @ git+https://github.com/01rabbit/Azazel-Fabric.git@v0.3.0`
  (dist name `azazel-fabric`, import namespace `azazel_fabric` — the
  `azazel-common` / `azazel_common` names from the v0.2.0 tag are gone).
  `py/azazel_gadget/common_view.py` drops the `azazel_common` fallback import
  added for this transition and now imports `azazel_fabric` only (still
  guarded — absence remains a safe no-op). Related comments in
  `py/azazel_gadget/control_plane.py`, `azazel_web/app.py`, and
  `py/azazel_gadget/first_minute/controller.py` updated to drop the
  dual-namespace phrasing. `tests/test_common_view.py` and
  `tests/test_status_view_readback.py` updated to match (single-namespace
  skip reasons; `test_round_trip_json` imports `azazel_fabric` directly).
  Docs updated to the new pin/import (`docs/concepts/azazel-common-usage.md`,
  `docs/DEV_LOCAL_STACK.md`, `docs/DEV_LOCAL_STACK_JA.md`,
  `docs/concepts/azazel-system-product-map.md`,
  `docs/SERIES_POSITIONING_AND_TERMS.md`, `docs/INDEX.md`, `README.md`,
  `README_ja.md`); `docs/concepts/azazel-common-adapter.md` is left as
  intentional design-history and still refers to `azazel_common`/`v0.1.0`/
  `v0.2.0` by design.
- Rename follow-up: the upstream `Azazel-CTI` and `Azazel-Common` repositories
  were renamed to `Azazel-Knowledge` (AZ-04, formal name Azazel-Knowledge
  Advisor, repo `01rabbit/Azazel-Knowledge`) and `Azazel-Fabric` (AZ-05, repo
  `01rabbit/Azazel-Fabric`) respectively. Updated all series references in
  `README.md`, `README_ja.md`, `docs/INDEX.md`,
  `docs/SERIES_POSITIONING_AND_TERMS.md`,
  `docs/concepts/azazel-system-product-map.md`,
  `docs/concepts/azazel-common-usage.md`, `docs/DEV_LOCAL_STACK.md`, and
  `docs/DEV_LOCAL_STACK_JA.md` to the new names (each noting "formerly
  Azazel-CTI" / "formerly Azazel-Common" once). `requirements.txt`'s pin now
  points at `git+https://github.com/01rabbit/Azazel-Fabric.git@v0.2.0`; the
  dist name stays `azazel-common` (unchanged by the v0.2.0 tag's pyproject).
  `docs/concepts/azazel-common-adapter.md` and
  `docs/concepts/azazel-common-usage.md` file names are intentionally
  unchanged (linked from CHANGELOG history and the Fabric repo docs).
- Import shim: `py/azazel_gadget/common_view.py` now tries the
  `azazel_fabric` namespace first and falls back to `azazel_common`, so
  Gadget is ready for Fabric's planned v0.3.0 rename of the dist to
  `azazel-fabric` / import to `azazel_fabric` without a code change on
  that day. No behavior change when neither namespace is installed. Related
  comments in `py/azazel_gadget/control_plane.py`, `azazel_web/app.py`, and
  `py/azazel_gadget/first_minute/controller.py` updated to describe the
  shared view as "Fabric (azazel_fabric/azazel_common)". Tests in
  `tests/test_common_view.py` made namespace-agnostic to match.
- Docs: extended the series model beyond AZ-01/AZ-02 in `docs/INDEX.md`,
  `docs/concepts/azazel-system-product-map.md`, and
  `docs/SERIES_POSITIONING_AND_TERMS.md` to name the umbrella Azazel repository
  (doctrine hub), Azazel-CTI (advisory-only knowledge-plane node, working name),
  Azazel-Common (shared contracts library), and Azazel-Boot (AZ-03, reserved) —
  while keeping AZ-01 Azazel-Edge and AZ-02 Azazel-Gadget as the series' two
  device-class peer products.
- Docs: added an "Azazel series" section to `README.md` and `README_ja.md`
  summarizing the same repository roles.
- Docs: `docs/DEV_LOCAL_STACK.md` and `docs/DEV_LOCAL_STACK_JA.md` now clarify
  that the `/dev/epd` browser preview is a re-derived "digital twin" driven by
  the same input signals as the panel, not a capture of the PIL-rendered image,
  and that `py/azazel_epd.py` is bypassed in dev mode — so pixel parity with the
  physical E-Paper panel is not guaranteed.
- Docs: `docs/concepts/azazel-common-adapter.md` now carries a status header
  marking it as the original integration plan, kept for history, superseded by
  `docs/concepts/azazel-common-usage.md` where the two differ.

## [0.2.0] - 2026-07-09

Aligned to **Azazel-Common v0.2.0**: Gadget now depends on the shared
`azazel-common` package and both emits and reads the shared status view-model,
so AZ-02 presents status through the same `StatusView` shape as AZ-01 (Edge) —
as a peer, not a subset. All Gadget-only detail (the `attack{}` canary block,
`connection{}`, the `DECEPTION` stage) is preserved via `StatusView.product_view`.

### Added
- Dependency on `azazel-common @ v0.2.0` (`requirements.txt`), pinned to an exact
  tag. Imported optionally, so Gadget runs identically with or without it.
- `py/azazel_gadget/common_view.py` — maps the Gadget UI snapshot to
  `azazel_common.view.StatusView` via the shared `build_status_view`.
- `controller.write_snapshot` now emits `ui_status_view.json` beside each
  `ui_snapshot.json` (best-effort, never raising into the loop).
- `control_plane.read_status_view_payload()` — reads the shared StatusView back.
- Web UI: `GET /api/state` and the `/api/state/stream` SSE now include a
  `status_view` field (the shared Common view; `null` when not emitted).
- **Developer local stack (no hardware):** `bin/azazel-gadget-devstack` +
  `tools/dev/env.sh` run the real controller (dev mode: dry-run, no root, no
  `nft`/`tc`/EPD) and the Web UI on loopback — mirroring Edge's dev stack.
  Env-gated path/socket/eve overrides (`AZAZEL_RUNTIME_DIR`,
  `AZAZEL_CONTROL_SOCKET`, `AZAZEL_EVE_PATH`) and an `AZAZEL_GADGET_DEV` /
  `--dev` preflight bypass; appliance behavior unchanged when unset.
- **EPD-on-Web:** `GET /api/epd` (panel content as JSON) and `GET /dev/epd`
  (self-contained preview page) make the E-Paper content viewable in a browser
  without the panel.
- Docs: `docs/DEV_LOCAL_STACK.md` (+ `_JA`) and
  `docs/concepts/azazel-common-usage.md` (how Gadget uses Common).
- Series-level documentation baseline:
  - `docs/INDEX.md` (cross-series entry map)
  - `docs/SERIES_POSITIONING_AND_TERMS.md` (AZ-01/AZ-02 terminology and boundaries)
  - `docs/SECURITY_CLAIM_POLICY.md` (documentation claim policy)
  - `docs/RELEASE_NOTES_TEMPLATE.md` (Azazel-Edge style release note template)
  - `docs/concepts/azazel-common-adapter.md` (Common adapter plan / adoption)

### Changed
- `README.md` and `README_ja.md` documentation maps now include series/index/policy/release-template entry points.

### Notes
- Additive and backward-compatible: when `azazel-common` is not installed, the
  shared view is simply absent (`status_view: null`) and every existing output
  is unchanged. Switching the dashboard/TUI/E-Paper to render primarily from
  `status_view` is a follow-up once field parity is confirmed.

## [0.1.0] - 2026-05-16

### Added
- Product-facing README restructuring for AZ-02 positioning:
  - deterministic top-level structure for reviewers/operators
  - explicit security boundary claims/non-claims section
  - architecture overview and operating mode guarantees
- CI unit-test workflow (`.github/workflows/ci-tests.yml`) running:
  - `python -m unittest discover -s tests -v`
  - dependency bootstrap for `PyYAML`
- README guard checks in CI:
  - local relative link/image path validation for `README.md` and `README_ja.md`
  - fenced code-block balance validation
- Release process baseline documentation:
  - `docs/RELEASE_PROCESS.md`
- Pull request quality gate template:
  - `.github/PULL_REQUEST_TEMPLATE.md`
- Japanese README alignment with English top-level structure and claim boundaries.

### Changed
- README top section now includes operational badges:
  - latest release
  - CI tests workflow
  - GitHub Pages workflow
- Documentation map updated to include release/changelog entry points.
- License wording in README clarified to reflect repository reality (no top-level `LICENSE` file currently present).

### Security
- Documentation and review process now explicitly enforce non-overclaiming language and verifiable security claims only.
