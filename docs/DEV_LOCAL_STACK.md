# Developer Local Stack (macOS / no hardware)

Run Azazel-Gadget (AZ-02) on a developer machine — macOS or plain Linux —
**without** any Raspberry Pi hardware: no `wlan0`/`usb0`, no `nft`/`tc`, no
E-Paper panel, no OpenCanary/Suricata/dnsmasq. This mirrors the Azazel-Edge
dev stack (`bin/azazel-edge-devstack`).

The dev stack runs the **real** first-minute controller and the Flask Web UI —
in a **safe dev mode** (dry-run: it computes decisions but never touches the
firewall, traffic control, or the radio). What the E-Paper panel would show is
viewable in the browser instead.

## Quick start

```bash
# 1. Install the pip-installable deps (a venv is recommended)
pip install -r requirements.txt        # Flask, requests, PyYAML, azazel-common

# 2. Launch the stack (sources tools/dev/env.sh for you)
bin/azazel-gadget-devstack up
```

You'll see:

```
  Dashboard   : http://127.0.0.1:8084/
  EPD preview : http://127.0.0.1:8084/dev/epd
  State API   : http://127.0.0.1:8084/api/state
  EPD API     : http://127.0.0.1:8084/api/epd
```

Other subcommands:

```bash
bin/azazel-gadget-devstack status   # what is running
bin/azazel-gadget-devstack logs     # tail component logs
bin/azazel-gadget-devstack restart
bin/azazel-gadget-devstack down     # stop everything
```

## What "dev mode" does

Dev mode is turned on by `tools/dev/env.sh` (sourced by the launcher). It only
sets environment variables — there are no `if MOCK:` branches in the app, and
appliance behavior is unchanged when these variables are unset.

| Concern | Appliance | Dev (`tools/dev/env.sh`) |
|---|---|---|
| Runtime dir | `/run/azazel-gadget` | `AZAZEL_RUNTIME_DIR=$HOME/.azazel-gadget-dev/run` |
| Control socket | `/run/azazel/control.sock` | `AZAZEL_CONTROL_SOCKET=…/run/control.sock` |
| Suricata events | `/var/log/suricata/eve.json` | `AZAZEL_EVE_PATH=…/suricata/eve.json` |
| Web bind | `0.0.0.0:8084` | `AZAZEL_WEB_HOST=127.0.0.1` (loopback only) |
| Root / `nft`/`tc` | required | `AZAZEL_GADGET_DEV=1` skips the preflight |
| Firewall / TC / EPD / dnsmasq | applied | **dry-run only** (never touched) |

All dev state lives under `~/.azazel-gadget-dev/` — nothing is written to
`/run`, `/etc`, or `/var`. Delete that directory to reset.

## E-Paper (EPD) on the Web

The physical E-Paper panel is not available off-hardware, so the panel content
is served in the browser:

- `GET /api/epd` — the panel content as JSON (mode, `normal|warning|danger`
  state, risk wording, SSID, signal).
- `GET /dev/epd` — a self-contained preview page that renders the 250×122 panel
  and refreshes every 2 seconds.

This is derived from the same live state the panel uses; no Pillow/Waveshare
hardware libraries are required for the browser preview.

**Caveat: the browser preview is a re-derived "digital twin," not a capture of
the panel image.** `/dev/epd` is an independently-coded HTML/CSS approximation
driven by the same input signals (mode, posture, SSID, suspicion) that feed the
real panel — it does **not** run the physical rendering path
(`py/azazel_epd.py`), which is bypassed in dev mode. Pixel parity with the
physical E-Paper panel is therefore not guaranteed; treat `/dev/epd` as a
content/state preview, not a pixel-accurate one. (Azazel-Edge's equivalent
preview additionally serves a `/api/epd/preview.png` rendered by its real PIL
renderer; Gadget's dev stack does not yet have that pixel-accurate path.)

## Notes and limitations

- **Dry-run is enforced.** The controller runs the real decision loop, but
  `nft`/`tc`/`dnsmasq`/EPD/sysctl are never applied (`AZAZEL_GADGET_DEV=1`
  forces `dry_run`). This matches Edge's `AZAZEL_DEFENSE_DRY_RUN=true` posture.
- **No real Wi-Fi.** With no radio, the upstream interface resolves to loopback
  and the dashboard shows Wi-Fi as disconnected — expected on a dev box.
- **No web token in dev.** The UI is open on loopback only (`verify_token()`
  passes when no token file exists). Do not expose the dev port off-loopback.
- **`azazel-common`** provides the shared status view-model; when installed
  (it's in `requirements.txt`), `/api/state` includes a `status_view` field and
  the controller emits `ui_status_view.json`. See
  [`concepts/azazel-common-usage.md`](concepts/azazel-common-usage.md).