# Security Policy

Azazel-Gadget (AZ-02, "Cyber Scapegoat Gateway") is a portable personal
defense gateway meant to be carried and operated on untrusted networks by
design — hostile Wi-Fi, hotel/airport LANs, and similar surroundings are the
expected operating environment, not an edge case.

## Reporting a vulnerability

Report privately via GitHub Security Advisories:
<https://github.com/01rabbit/Azazel-Gadget/security/advisories/new>

Do **not** open a public issue for a suspected vulnerability.

Include: affected version/commit, hardware/OS (e.g. Raspberry Pi model, OS
image/version), repro steps or a minimal PoC, and observed impact.

No bounty program. Reporters are credited unless anonymity is requested.

## Response targets

- Acknowledgement: within 7 days
- Initial assessment (severity, affected versions): within 14 days
- Fix and disclosure are coordinated with the reporter.

## Scope

**In scope**: token-auth bypass on the web UI/API (`azazel_web`); privilege
escalation from the USB-gadget or Wi-Fi control plane to the host;
captive/consent-flow bypass; secrets or credentials leaking into logs or
snapshots; nftables policy bypass that exposes the protected endpoint;
integrity issues in the installer.

**Out of scope**: attacker interaction with deception/delay surfaces (that
is the product working as intended); documented fail-open behaviors that
are explicit configuration choices (`docs/SECURITY_CLAIM_POLICY.md` governs
what the project claims); findings requiring physical access to an unlocked
device.

This document covers vulnerability reporting; `docs/SECURITY_CLAIM_POLICY.md`
governs what the project claims. See that file for claim boundaries.

## Supported versions

The latest tagged release and `main` are supported.
