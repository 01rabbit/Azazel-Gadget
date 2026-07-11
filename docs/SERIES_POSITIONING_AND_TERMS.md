# Azazel Series Positioning and Terms

This document standardizes cross-repository wording for Azazel series documentation.

## Product Relationship

- AZ-01 Azazel-Edge  
  Deterministic Edge SOC/NOC Gateway for constrained, temporary, and high-risk local networks.
- AZ-02 Azazel-Gadget  
  Personal Tactical Defense Gateway for untrusted Wi-Fi, hostile local segments, and field use.

Both are peer products in the same Azazel system, and both are device-class
appliances. The wider series (umbrella doctrine hub, the reserved AZ-03
Azazel-Boot slot, AZ-04 Azazel-Knowledge Advisor, AZ-05 Azazel-Fabric
Contract) is enumerated in one place only — the umbrella repository:
[01rabbit/Azazel](https://github.com/01rabbit/Azazel).
## Canonical Terms

- `Deterministic mode`: explicit mode behavior selected by operator or deterministic policy logic.
- `Cyber Scapegoat Gateway`: gateway posture that receives first contact and exposes controlled surfaces to buy operator decision time.
- `Protected side`: AZ-02 `usb0` client-facing segment.
- `Upstream side`: AZ-02 `wlan0` network-facing segment.
- `Operating modes`: `portal`, `shield`, `scapegoat` (plus warning display state, which is not a mode).

## Required Positioning Language for AZ-02

Documentation should describe AZ-02 as:

- portable personal tactical defense gateway
- cyber scapegoat gateway
- standing between endpoint and surrounding untrusted network
- deterministic, operator-visible control surface

Documentation must avoid describing AZ-02 as:

- generic travel router
- VPN replacement
- endpoint security replacement
- autonomous offensive security platform

## Cross-Repository Linking Guidance

- When mentioning AZ-01 design lineage, link to Azazel-Edge repository root or the specific public document.
- Keep AZ-02 claims bounded to this repository implementation.
