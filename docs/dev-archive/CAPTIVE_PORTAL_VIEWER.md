# Captive Portal Viewer (noVNC)

## Overview

Azazel-Zero can expose a browser running on Raspberry Pi as a noVNC screen.
This lets a downstream laptop/smartphone operate upstream captive portal pages.

- Browser on Pi: Chromium (virtual X display)
- Remote UI: noVNC (`websockify`)
- Service: `azazel-portal-viewer.service`

## Install

```bash
cd /home/azazel/Azazel-Zero
sudo ./install.sh --with-portal-viewer
```

With Web UI together:

```bash
sudo ./install.sh --with-webui --with-portal-viewer
```

## Access

Default URL:

```text
http://10.55.0.10:6080/vnc.html?autoconnect=true&resize=scale
```

## Config

Environment file:

`/etc/azazel-zero/portal-viewer.env`

Main keys:

- `PORTAL_START_URL` (default: `http://neverssl.com`)
- `PORTAL_NOVNC_BIND` (default: `10.55.0.10`)
- `PORTAL_NOVNC_PORT` (default: `6080`)
- `PORTAL_VNC_PASSWORD` (optional; empty means no VNC password)
- `PORTAL_BROWSER_CMD` (`auto`, `chromium`, `chromium-browser`)

Apply changes:

```bash
sudo systemctl restart azazel-portal-viewer.service
```

## Operations

```bash
sudo systemctl status azazel-portal-viewer.service
sudo journalctl -u azazel-portal-viewer.service -f
```

Runtime logs:

- `/run/azazel-portal-viewer/xvfb.log`
- `/run/azazel-portal-viewer/browser.log`
- `/run/azazel-portal-viewer/x11vnc.log`
- `/run/azazel-portal-viewer/websockify.log`

## Captive Probe Verification (Operational Checklist)

Use this checklist when captive portal behavior looks suspicious after deployment.

### Pre-check

```bash
sudo systemctl daemon-reload
sudo systemctl restart azazel-first-minute.service
sudo systemctl restart azazel-epd-portal.timer
sudo systemctl status azazel-epd-portal.service azazel-epd-portal.timer --no-pager
```

Expected:
- `azazel-epd-portal.service` is `active (exited)`
- no `203/EXEC` in journal

### Expected outcomes by scenario

- WLAN normal AP:
  - `connection.captive_probe_iface` resolves to wireless interface
  - probe to `generate_204` returns `HTTP_204`
  - `connection.captive_portal=NO`
- WLAN captive AP:
  - HTTP `30x` => `YES` (`HTTP_30X`)
  - HTTP `200` with body / other non-204 => `SUSPECTED`
- ETH only (`captive_probe_policy: wifi_prefer`):
  - no wireless candidate -> fallback to wired interface
  - reason contains `fallback_to_<iface>`
- No usable interface:
  - `connection.captive_portal=NA`
  - reason `NO_IP` or `LINK_DOWN` or `NOT_FOUND`

### Timer/Service periodic execution

```bash
sudo systemctl list-timers azazel-epd-portal.timer --no-pager
journalctl -u azazel-epd-portal.service -n 100 --no-pager
```

Expected log examples:

```text
captive_probe_iface resolved: wlan0 (policy=wifi_prefer, src=auto)
skip captive probe: reason=NO_IP
Portal status=YES reason=HTTP_30X iface=wlan0
```
