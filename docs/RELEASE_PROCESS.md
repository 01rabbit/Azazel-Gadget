# Release Process

This document defines the standard release flow for Azazel-Gadget, aligned with Azazel-Edge operational style.

## Versioning and tags

- Tag format: `vMAJOR.MINOR.PATCH` (example: `v0.1.0`)
- Release title format: `Azazel-Gadget vX.Y.Z`
- Default release type: non-draft, non-prerelease unless explicitly required

## Required pre-release checks

Before creating a tag/release:

```bash
python -m unittest discover -s tests -v
```

CI expectations:

- `CI Tests` workflow is green on target commit
- README guard checks are green:
  - local link/image path validity in `README.md` and `README_ja.md`
  - fenced code block balance

## Release note style

Use the same structure style as Azazel-Edge release notes:

1. `Theme`
2. `Highlights`
3. `Scope boundaries`
4. `Validation checklist (release candidate)`

Claims in release notes must be:

- repository-verifiable
- bounded (no autonomous/complete protection claims)
- explicit about what changed vs what did not

## Release sequence

1. Confirm working tree is clean.
2. Confirm tests/CI pass.
3. Update docs as needed:
   - `docs/CHANGELOG.md`
   - release notes document (for example `docs/RELEASE_NOTES_vX.Y.Z.md`)
4. Create and push tag:

```bash
git tag vX.Y.Z
git push origin vX.Y.Z
```

5. Create GitHub release:

```bash
gh release create vX.Y.Z \
  --title "Azazel-Gadget vX.Y.Z" \
  --notes-file docs/RELEASE_NOTES_vX.Y.Z.md
```

## Post-release checks

- Verify release URL and artifact visibility on GitHub.
- Verify README badges reflect new release tag.
- Ensure changelog and release notes remain consistent.
