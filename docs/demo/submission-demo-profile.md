# Submission Demo Profile (Azazel-Gadget)

## Status

This document is a submission-preparation demo profile. Azazel-Gadget has not been accepted to Black Hat USA Arsenal.

## Demo objective

Show that Azazel-Gadget moves the first-contact surface away from the user's endpoint and provides deterministic, operator-visible exposure control in hostile local-network conditions.

## Core message

Azazel-Gadget moves the first-contact surface away from the user's endpoint.

## 3-minute demo

- Connect a protected endpoint through Azazel-Gadget (`usb0`).
- Join an untrusted upstream segment (`wlan0`).
- Show baseline in `shield` mode and confirm inbound exposure is blocked.

Audience takeaway: endpoint is no longer the immediate local contact surface.

## 7-minute demo

- Start in `shield` and show operator-visible state in Web UI/TUI/e-paper.
- Switch to `scapegoat`.
- Demonstrate that only allowlisted decoy ports are exposed when OpenCanary is enabled.

Audience takeaway: mode-controlled exposure changes are deterministic and visible.

## 15-minute demo

- Attacker-peer view: discovery/probe attempts against upstream side.
- Protected-endpoint view: outbound usability retained, upstream inbound isolation preserved in `shield`.
- Gadget-operator view: mode state, monitoring signals, and audit/state updates.
- Optional: ntfy event stream and OpenCanary visibility in scapegoat posture.

Audience takeaway: practical tactical workflow across attacker, protected client, and operator perspectives.

## Required hardware

- Azazel-Gadget device (Raspberry Pi Zero 2 W or Pi 4 class)
- Protected endpoint connected via USB gadget path (`usb0`)
- Upstream Wi-Fi/local segment for hostile-peer simulation
- Optional e-paper module

## Network layout

- Attacker peer -> Azazel-Gadget upstream side (`wlan0`)
- Protected endpoint -> Azazel-Gadget protected side (`usb0`)

## Attacker actions

- local discovery
- service probing against upstream-facing surface

## Expected Gadget state changes

- `shield`: upstream inbound blocked to protected client side
- `scapegoat`: only allowlisted decoy services exposed (when OpenCanary enabled)
- operator state reflected via Web UI, TUI, and e-paper

## What the audience should understand

- this is not a VPN/travel-router pitch
- this is a portable first-contact relocation and controlled-surface defensive gateway model
- exposure is deterministic, bounded, and operator-visible
