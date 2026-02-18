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
- `PORTAL_NOVNC_BIND` (default: `0.0.0.0`)
- `PORTAL_NOVNC_PORT` (default: `6080`)
- `PORTAL_VNC_PASSWORD` (set/change before operation)
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
