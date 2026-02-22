# Azazel-Gadget (Azazel-Zero) — Cyber Scapegoat Gateway

Azazel-Gadget (formerly Azazel-Zero) is a portable defensive gateway for untrusted Wi-Fi environments on Raspberry Pi Zero 2 W / Pi 4-class devices.

This README is implementation-first: it describes features that are currently present in this repository and how they are connected.

## Implemented capabilities (repo-verified)

### 1) First-minute control plane
- Main controller tracks upstream health, captive portal status, and risk transitions (`NORMAL`/`DEGRADED`/`CONTAIN`).
- Writes UI snapshot JSON consumed by Web UI and TUI.
- Exposes local Status API (`:8082`) with action endpoints (`/action/*`) and details endpoint (`/details`).
- Includes tactics decision logging (`decision_explanations.jsonl`) and ntfy notifier hooks.
- In `DECEPTION`, applies `tc` delay only to Suricata-confirmed OpenCanary attack flows (targeted Delay-to-Win).

Reference: `py/azazel_gadget/first_minute/controller.py`

### 2) Action/control daemon (Unix socket)
- Dedicated daemon at `/run/azazel/control.sock`.
- Executes action scripts, Wi-Fi scan/connect handlers, and portal-viewer startup workflow.
- Supports control-plane snapshot streaming (`watch_snapshot`) for clients.
- Includes path-schema actions (`path_schema_status`, `migrate_path_schema`).

Reference: `py/azazel_control/daemon.py`, `systemd/azazel-control-daemon.service`

### 3) Web UI backend (Flask)
- Dashboard + state API + SSE state stream.
- Action API (new and legacy format), Wi-Fi scan/connect API, portal-viewer APIs.
- ntfy event bridge SSE endpoint.
- CA certificate metadata/download endpoints for local HTTPS onboarding.
- Token auth via header or query (if token file exists).

Reference: `azazel_web/app.py`, `systemd/azazel-web.service`

### 4) Portal viewer (noVNC)
- Browser-assisted captive-portal workflow (Chromium + Xvfb + x11vnc + noVNC).
- Web UI can start and open it on demand (`/api/portal-viewer/open`).
- Runtime start URL override is supported.

Reference: `scripts/azazel-portal-viewer.sh`, `systemd/azazel-portal-viewer.service`

### 5) E-paper integration
- Boot/shutdown splash service.
- Periodic captive-portal detection display updates.
- Suricata-linked e-paper alert updates.

Reference: `systemd/azazel-epd.service`, `systemd/azazel-epd-shutdown.service`, `systemd/azazel-epd-portal.service`, `systemd/azazel-epd-portal.timer`, `systemd/suri-epaper.service`

### 6) Optional local monitoring/deception
- OpenCanary systemd unit and startup wrapper.
- Suricata integration and monitoring-state reflection in UI.
- Optional local ntfy server (`--with-ntfy`) and `/api/events/stream` bridge.

Reference: `systemd/opencanary.service`, `azazel_web/app.py`, `scripts/install_ntfy.sh`

## Runtime dependency map

1. `azazel-first-minute.service`
- Produces state snapshot and Status API (`:8082`).
2. `azazel-control-daemon.service`
- Bridges action requests over `/run/azazel/control.sock`.
3. `azazel-web.service`
- Flask backend (`127.0.0.1:8084` by default), reads snapshot and calls control daemon/Status API.
4. Optional `caddy.service` (installer `--with-webui`)
- TLS reverse proxy (`https://<MGMT_IP>:443`) to Flask backend.
5. Optional `azazel-portal-viewer.service`
- noVNC endpoint (default `10.55.0.10:6080`), started on demand by API.

## Systemd units in this repo

| Unit | Purpose |
|---|---|
| `azazel-first-minute.service` | Main control-plane process |
| `azazel-control-daemon.service` | Unix socket action daemon |
| `azazel-web.service` | Flask backend API/UI |
| `azazel-portal-viewer.service` | Captive-portal viewer (noVNC) |
| `usb0-static.service` | Forces static IPv4 on `usb0` |
| `azazel-nat.service` | iptables-based forwarding/NAT helper |
| `azazel-epd.service` | E-paper startup status |
| `azazel-epd-shutdown.service` | E-paper shutdown clear/splash |
| `azazel-epd-portal.service` + `.timer` | E-paper captive-portal checks |
| `suri-epaper.service` | Suricata-driven E-paper updates |
| `opencanary.service` | Optional deception service |

## Installer feature switches

Main entrypoint: `install.sh`

| Option | Effect |
|---|---|
| `--with-webui` | Installs Flask venv + Caddy HTTPS reverse proxy |
| `--with-canary` | Installs/enables OpenCanary |
| `--with-ntfy` | Installs local ntfy server (`:8081`) |
| `--with-portal-viewer` | Installs noVNC/Chromium stack |
| `--with-epd` | Enables Waveshare E-Paper dependencies (default ON) |
| `--all` | Enables all optional features above |
| `--resume` | Resume after reboot-required network stage |

Typical:

```bash
sudo ./install.sh --all
# if prompted for reboot:
sudo ./install.sh --resume
```

## Web API surface (current)

| Endpoint | Notes |
|---|---|
| `GET /` | Dashboard HTML |
| `GET /api/state` | Snapshot + monitoring + portal-viewer state |
| `GET /api/state/stream` | SSE state stream |
| `GET /api/events/stream` | SSE ntfy bridge events |
| `GET /api/portal-viewer` | noVNC state/URL |
| `POST /api/portal-viewer/open` | Start/open portal viewer |
| `POST /api/action` | New action format |
| `POST /api/action/<action>` | Legacy action format |
| `GET /api/wifi/scan` | Wi-Fi scan (currently no token required) |
| `POST /api/wifi/connect` | Wi-Fi connect |
| `GET /api/certs/azazel-webui-local-ca/meta` | Local CA metadata |
| `GET /api/certs/azazel-webui-local-ca.crt` | Local CA download |
| `GET /health` | Web backend health |

Allowed actions (API): `refresh`, `reprobe`, `contain`, `release`, `details`, `stage_open`, `disconnect`, `wifi_scan`, `wifi_connect`, `portal_viewer_open`, `shutdown`, `reboot`

Token auth:
- Header: `X-AZAZEL-TOKEN` or `X-Auth-Token`
- Query: `?token=...`

Reference: `azazel_web/app.py`

## Operator interfaces

- Web UI: `azazel_web/`
- Unified TUI monitor/menu: `py/azazel_gadget/cli_unified.py`
- Menu compatibility launcher: `py/azazel_menu.py`
- Terminal status panel: `py/azazel_status.py`
- E-paper renderer/controller: `py/azazel_epd.py`, `py/boot_splash_epd.py`

## Tests included

- Unit tests: `tests/`
- Regression scripts: `scripts/tests/regression/`
- UI stack smoke test: `scripts/tests/e2e/run_ui_stack_smoke.sh`

## Path schema and naming compatibility

Both naming schemas are supported:
- Current: `azazel-gadget` (`/etc/azazel-gadget`, `/run/azazel-gadget`, `~/.azazel-gadget`)
- Legacy: `azazel-zero` (`/etc/azazel-zero`, `/run/azazel-zero`, `~/.azazel-zero`)

Schema helpers and migration are in `py/azazel_gadget/path_schema.py`.
Current deprecation marker for legacy compatibility paths is `2026-12-31`.

## Repository structure (main)

| Path | Meaning |
|---|---|
| `py/azazel_gadget/` | Controller, sensors, tactics engine, path schema |
| `py/azazel_control/` | Control daemon + Wi-Fi handlers + action scripts |
| `azazel_web/` | Flask backend + static dashboard |
| `systemd/` | Service and timer units |
| `installer/` | Staged installer |
| `configs/` | Default runtime configs |
| `scripts/` | Runtime helpers + tests |
| `docs/` | Development/archive notes |

## License

See `LICENSE` if present in this repository.
