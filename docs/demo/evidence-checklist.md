# Demo Evidence Checklist

Use this checklist to verify that the demo reflects implemented behavior.

## Core runtime and services

- Confirm key services are active:

```bash
sudo systemctl status azazel-mode azazel-first-minute azazel-control-daemon azazel-web --no-pager
```

- Confirm current mode state:

```bash
sudo azctl mode status
```

## Operator surfaces

- Web UI is reachable on configured local management path.
- Unified TUI starts from repository tooling.
- E-paper state file exists (or fallback/no-hardware behavior is documented):

```bash
ls -l /run/azazel/epd_state.json
```

## Network behavior checks

- Protected `usb0` client can use intended outbound path.
- In `shield`, upstream inbound does not reach protected client side.
- In `scapegoat`, decoy exposure appears only on allowlisted OpenCanary ports when enabled.

## Logging and audit visibility

- Mode/audit records update during mode changes:

```bash
sudo tail -n 20 /var/log/azazel/mode_changes.jsonl
```

- Runtime snapshot/state files update during demo actions.

## Optional monitoring evidence

- Suricata/OpenCanary/ntfy indicators are visible where those components are installed.
- If optional components are not installed, note this explicitly in demo narration.
