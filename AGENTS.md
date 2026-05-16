# AGENTS.md

This file defines repository-specific working rules for coding/documentation agents.

## Scope

- Repository: `01rabbit/Azazel-Gadget`
- Product: `AZ-02 Azazel-Gadget`
- Positioning: peer product in the Azazel system (not a reduced AZ-01 variant)

## Core Product Positioning

When editing documentation, keep this framing:

- AZ-01 Azazel-Edge: Deterministic Edge SOC/NOC Gateway
- AZ-02 Azazel-Gadget: Personal Tactical Defense Gateway / Cyber Scapegoat Gateway
- AZ-02 stands between protected endpoint and untrusted surrounding network.

Avoid describing AZ-02 as:

- VPN replacement
- generic travel router
- endpoint security replacement
- complete attack-prevention system

## Documentation Guardrails

- Do not add claims that cannot be verified from repository implementation.
- Preserve explicit claim vs non-claim boundaries.
- Keep top-level README product-facing, precise, and restrained.
- Keep `README.md` and `README_ja.md` structurally aligned.
- Prefer linking existing files; do not add dead links.

Related policy docs:

- `docs/INDEX.md`
- `docs/SERIES_POSITIONING_AND_TERMS.md`
- `docs/SECURITY_CLAIM_POLICY.md`

## Release and Changelog Rules

- Follow `docs/RELEASE_PROCESS.md`.
- Keep `docs/CHANGELOG.md` updated using Keep a Changelog style.
- Use `docs/RELEASE_NOTES_TEMPLATE.md` for release notes.

## CI Expectations

Before release/documentation-sensitive PR merge:

```bash
python -m unittest discover -s tests -v
```

README guard checks must pass:

- relative links/images valid in `README.md` and `README_ja.md`
- fenced code block balance

## Change Boundaries

For documentation tasks:

- Do not modify runtime behavior, installer behavior, or file naming unless explicitly requested.
- If changing `install.sh`, `installer/`, `systemd/`, include explicit rationale in PR.

## Preferred PR Checklist

- Summary of intent and scope
- Evidence for any security-relevant claim
- Test/validation commands and results
- Updated docs map/changelog when externally visible behavior or claims change
