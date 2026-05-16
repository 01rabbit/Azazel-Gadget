# Security Claim Policy

This policy defines acceptable claim boundaries for Azazel-Gadget documentation and release notes.

## Claim Rules

Any security claim must be:

- implementation-verifiable from this repository
- written in bounded language (what is and is not claimed)
- consistent with current mode semantics and network boundaries

## Allowed Claim Patterns

- deterministic mode switching with visible operator state
- no inbound path from upstream `wlan0` to protected `usb0` clients
- optional isolated deception exposure via OpenCanary in scapegoat mode
- local-first operation without cloud dependency requirements

## Disallowed Claim Patterns

- complete protection against all hostile network attacks
- replacement for endpoint security, VPN, NAC, or enterprise SOC tooling
- autonomous offensive response capability
- invisible/zero-interaction security guarantees

## Evidence Expectations

When adding or modifying security claims, PRs should include:

1. Repository evidence references (service units, scripts, mode manager behavior, API endpoints).
2. Updated claim/non-claim text in `README.md` and `README_ja.md` when relevant.
3. Changelog entry for externally visible claim boundary changes.
