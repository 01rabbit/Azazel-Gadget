# First-Contact Surface Relocation

## Definition

First-contact surface means the network-facing surface that receives initial local discovery, probing, and opportunistic attack attempts.

For personal devices on hostile local segments, placing this surface directly on the endpoint increases risk concentration at the endpoint itself.

Azazel-Gadget moves the first-contact surface away from the user's endpoint.

## Why hostile local segments matter

On untrusted Wi-Fi or contested local networks, local peers can perform:

- service and port discovery
- opportunistic probing
- repeated low-cost reconnaissance

Even when internet traffic is tunneled, local L2/L3 contact behavior still matters.

## Difference from VPNs

VPNs protect traffic paths and remote routing, but they do not by themselves remove the endpoint's local first-contact surface.

## Difference from endpoint firewalls

Endpoint firewalls are important but operate on the endpoint itself. Azazel-Gadget introduces a separate gateway boundary in front of the endpoint.

## Difference from travel routers

Travel routers mainly focus on connectivity and convenience. Azazel-Gadget is designed as a defensive, operator-visible, deterministic mode gateway with optional deception posture.

## Difference from standalone honeypots

Standalone honeypots collect observations from exposed services. Azazel-Gadget combines gateway isolation, deterministic mode control, and optional isolated decoy exposure as part of a personal defensive workflow.

## Why relocation is useful

By relocating first contact to a controlled gateway:

- exposure policy becomes explicit (`portal`, `shield`, `scapegoat`)
- protected client side remains separated from upstream inbound paths
- operator can observe and adjust posture during field use
