# Personal Cyber Scapegoat Gateway

Azazel-Gadget (AZ-02) is a personal Cyber Scapegoat Gateway.

Its role is to stand in front of a user's endpoint when the surrounding local network is not trustworthy. Instead of exposing the endpoint directly to first local contact, Azazel-Gadget provides a controlled gateway surface with deterministic behavior.

Key properties:

- The protected endpoint is placed behind the `usb0` side.
- Exposure to upstream local peers is controlled by explicit operating modes.
- Operator-visible status is available through Web UI, TUI, and e-paper.
- Optional notification paths can surface operational events.
- Optional OpenCanary exposure can be enabled in scapegoat posture.

Azazel-Gadget is not:

- a VPN replacement
- a general-purpose travel router
- a standalone generic honeypot

The purpose is to make hostile local-network contact observable, bounded, and optionally deceptive while keeping the protected client side isolated from upstream inbound paths.
