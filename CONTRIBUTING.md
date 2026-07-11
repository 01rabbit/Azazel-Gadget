# Contributing to Azazel-Gadget

## Before you start

Read [AGENTS.md](AGENTS.md) first. AZ-02 is a peer product in the Azazel
system (Personal Tactical Defense Gateway / Cyber Scapegoat Gateway), not a
reduced variant of AZ-01 Azazel-Edge — keep that positioning in any change
you make.

## Branch naming

`<type>/<short-description>`

Examples: `feat/scapegoat-mode-toggle`, `fix/web-token-refresh`, `docs/readme-map`

## Commit message format

`<type>(<scope>): <summary>`

- type: `feat` / `fix` / `refactor` / `test` / `docs` / `chore` / `security`
- scope: `control` / `web` / `epd` / `wifi` / `usb` / `notify` / `installer` / `fabric` / `docs`

## Pull request rules

- 1 PR = 1 purpose. Do not mix unrelated changes.
- Every PR must include:
  - [ ] `python -m unittest discover -s tests` passes (40 baseline — never reduce)
  - [ ] No overclaiming: claims must be verifiable from the implementation
        (the readme-guard CI enforces part of this; `docs/SECURITY_CLAIM_POLICY.md`
        governs the rest)
  - [ ] Optional dependencies follow the guarded-import pattern (absence
        is a safe no-op, not a crash)
  - [ ] Related documentation updated in the same PR
  - [ ] README updates preserve AZ-02's peer positioning (not a subset of Azazel-Edge)

## What not to do (requires human review)

- Do not change `install.sh`, `installer/`, or `systemd/`, or alter runtime
  behavior, without explicit justification in the PR description
- Do not turn the shared-contracts integration (`azazel_fabric`) into a hard
  dependency — it stays optional

## Testing

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m unittest discover -s tests
```

## License

Contributions are accepted under the [MIT License](LICENSE).
