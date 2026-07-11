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

The full series map (umbrella hub, AZ-03 Azazel-Boot reserved slot,
AZ-04 Azazel-Knowledge Advisor, AZ-05 Azazel-Fabric Contract) is maintained in
the umbrella repository: [01rabbit/Azazel](https://github.com/01rabbit/Azazel).
This document intentionally covers only the AZ-01/AZ-02 device relationship.
