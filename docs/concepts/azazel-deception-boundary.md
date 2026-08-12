# AZ-06 Azazel-Deception Compatibility Boundary

Repository: https://github.com/01rabbit/Azazel-Deception
Tracker: https://github.com/01rabbit/Azazel-Gadget/issues/17
Generic Engage-lite tracker: https://github.com/01rabbit/Azazel-Gadget/issues/16

## Role separation

Azazel-Gadget remains a small personal tactical defense gateway with operator-controlled `portal`, `shield`, and `scapegoat` modes. It does **not** host the full AZ-06 Engagement Environment Plane.

> Gadget exposes only small, pre-approved Engage-lite surfaces. Coherent and dynamic deception-environment orchestration belongs to AZ-06.

## Compatible static subset

After Azazel-Fabric publishes canonical AZ-06 contracts, Gadget may consume only a minimal static subset for fixed `scapegoat` profiles:

- package/profile identity and digest/provenance
- minimal `RuntimeRequirements`
- `ImageManifest`
- a `gadget-lite` or equivalent package-authored `DeploymentTier`
- allowlisted surfaces/ports/protocols
- duration/resource/connection/traffic limits
- outbound denied
- protected-client access denied
- evidence, termination, and reset fields

Fixed decoy images must support `linux/arm64`; optional AMD64 CI may be used for parity.

## Explicit non-goals

Gadget does not implement:

- full AZ-06 control plane
- dynamic narrative generation
- persona/activity scheduling
- multi-step credential-lure chains
- long-running finite-state engagement orchestration
- KVM/GPU/VM requirements
- attacker-tailored runtime planning
- LLM-generated live mutation
- arbitrary service/port expansion

Package compatibility does not permit AZ-06, Fabric, or Knowledge to change the operator-selected Gadget mode.

## Safety

- `usb0` protected clients remain isolated from upstream and decoy namespaces
- decoy egress remains denied
- unsupported architecture, schema, digest, runtime feature, or dynamic field fails closed
- no package tier may expand exposure beyond the active `scapegoat` allowlist
- validation/resource/isolation/stale-state failures terminate exposure and fall back safely

Routing suspicious traffic from Gadget to an external AZ-06 node requires a separate trust/routing design and is outside this compatibility boundary.
