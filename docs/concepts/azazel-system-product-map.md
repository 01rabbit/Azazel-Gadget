# Azazel System Product Map

This document describes how AZ-01 and AZ-02 relate as peer products in the Azazel system,
and where the rest of the Azazel series sits around them.

## AZ-01 Azazel-Edge

- Deterministic Edge SOC/NOC Gateway
- Designed for constrained, temporary, and high-risk local networks
- Emphasizes deterministic NOC/SOC evaluation, bounded action selection, and auditability for broader edge/team operations

Reference repository: [01rabbit/Azazel-Edge](https://github.com/01rabbit/Azazel-Edge)

## AZ-02 Azazel-Gadget

- Personal Tactical Defense Gateway
- Portable Cyber Scapegoat Gateway
- Designed for untrusted Wi-Fi, hostile local segments, and field use
- Emphasizes first-contact surface relocation away from the user's endpoint and deterministic local mode control

Repository: [01rabbit/Azazel-Gadget](https://github.com/01rabbit/Azazel-Gadget)

## Relationship

AZ-02 is not a reduced AZ-01. It is a peer product with a different deployment center:

- AZ-01 centers on deterministic edge SOC/NOC gateway operations.
- AZ-02 centers on portable, personal, hostile-local-network defensive gateway posture.

## Rest of the Azazel Series

AZ-01 and AZ-02 are the series' two device-class products. The wider series adds a
doctrine hub, a reserved future device, and shared infrastructure components — none
of which are peer devices of AZ-01/AZ-02:

- **Azazel (umbrella)** — the doctrine hub repository and project site for the whole
  series ("Cyber Scapegoat Gateway"). Reference: [01rabbit/Azazel](https://github.com/01rabbit/Azazel) ·
  [Project site](https://01rabbit.github.io/Azazel/)
- **AZ-03 Azazel-Boot** — reserved series slot; no repository published yet.
- **AZ-04 Azazel-Knowledge** (formerly Azazel-CTI; formal name Azazel-Knowledge
  Advisor) — an advisory-only, deterministic, on-prem tactical CTI
  knowledge-plane node. It never commands; it pairs with AZ-01 Azazel-Edge,
  which retains final decision authority and keeps working fully without it.
  AZ-02 Azazel-Gadget has no current or planned CTI integration. Reference:
  [01rabbit/Azazel-Knowledge](https://github.com/01rabbit/Azazel-Knowledge)
- **AZ-05 Azazel-Fabric** (formerly Azazel-Common) — the shared contracts library (distributed as `azazel-common`, installed via a pinned git tag; becomes `azazel-fabric` from v0.3.0) that
  AZ-01 and AZ-02 draw on for interoperable schema/view shapes. AZ-02 is its most
  complete consumer today (pinned at v0.2.0); see
  [azazel-common-usage.md](azazel-common-usage.md). Reference:
  [01rabbit/Azazel-Fabric](https://github.com/01rabbit/Azazel-Fabric)
