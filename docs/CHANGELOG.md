# Changelog

This file follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

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
