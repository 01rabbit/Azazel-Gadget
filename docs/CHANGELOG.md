# Changelog

This file follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Series-level documentation baseline:
  - `docs/INDEX.md` (cross-series entry map)
  - `docs/SERIES_POSITIONING_AND_TERMS.md` (AZ-01/AZ-02 terminology and boundaries)
  - `docs/SECURITY_CLAIM_POLICY.md` (documentation claim policy)
  - `docs/RELEASE_NOTES_TEMPLATE.md` (Azazel-Edge style release note template)

### Changed
- `README.md` and `README_ja.md` documentation maps now include series/index/policy/release-template entry points.

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
