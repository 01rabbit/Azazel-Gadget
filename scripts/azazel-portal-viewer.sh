#!/bin/bash
# Launch a browser-backed captive portal viewer and expose it via noVNC.

set -euo pipefail

log() {
    echo "[portal-viewer] $*" >&2
}

require_cmd() {
    local cmd="$1"
    if ! command -v "$cmd" >/dev/null 2>&1; then
        log "ERROR: required command not found: $cmd"
        exit 1
    fi
}

resolve_browser() {
    local configured="${PORTAL_BROWSER_CMD:-auto}"
    if [[ "$configured" != "auto" ]]; then
        if command -v "$configured" >/dev/null 2>&1; then
            echo "$configured"
            return 0
        fi
        log "ERROR: PORTAL_BROWSER_CMD is set but command is missing: $configured"
        exit 1
    fi

    if command -v chromium >/dev/null 2>&1; then
        echo "chromium"
        return 0
    fi
    if command -v chromium-browser >/dev/null 2>&1; then
        echo "chromium-browser"
        return 0
    fi

    log "ERROR: chromium/chromium-browser not found"
    exit 1
}

PORTAL_RUNTIME_DIR="${PORTAL_RUNTIME_DIR:-/run/azazel-portal-viewer}"
PORTAL_DISPLAY="${PORTAL_DISPLAY:-:99}"
PORTAL_SCREEN="${PORTAL_SCREEN:-1366x768x24}"
PORTAL_START_URL="${PORTAL_START_URL:-http://neverssl.com}"
PORTAL_START_URL_FILE="${PORTAL_START_URL_FILE:-/run/azazel/portal-viewer-start-url}"
PORTAL_VNC_PORT="${PORTAL_VNC_PORT:-5900}"
# Default to the usb0 management IP so noVNC is not exposed on uplink networks.
PORTAL_NOVNC_BIND="${PORTAL_NOVNC_BIND:-10.55.0.10}"
PORTAL_NOVNC_PORT="${PORTAL_NOVNC_PORT:-6080}"
PORTAL_BROWSER_PROFILE="${PORTAL_BROWSER_PROFILE:-$HOME/.config/azazel-portal-browser}"
PORTAL_BROWSER_ARGS="${PORTAL_BROWSER_ARGS:---new-window --no-first-run --no-default-browser-check --start-maximized}"
PORTAL_NOVNC_WEB="${PORTAL_NOVNC_WEB:-/usr/share/novnc}"

require_cmd Xvfb
require_cmd openbox
require_cmd x11vnc
require_cmd websockify

BROWSER_BIN="$(resolve_browser)"

is_http_url() {
    local url="$1"
    [[ "$url" =~ ^https?://[^[:space:]]+$ ]]
}

if [[ ! -d "$PORTAL_NOVNC_WEB" ]]; then
    log "ERROR: noVNC web root not found: $PORTAL_NOVNC_WEB"
    exit 1
fi

mkdir -p "$PORTAL_RUNTIME_DIR"
chmod 0700 "$PORTAL_RUNTIME_DIR" || true
mkdir -p "$PORTAL_BROWSER_PROFILE"
chmod 0700 "$PORTAL_BROWSER_PROFILE" || true

if [[ -f "$PORTAL_START_URL_FILE" ]]; then
    runtime_start_url="$(head -n 1 "$PORTAL_START_URL_FILE" | tr -d '\r')"
    if is_http_url "$runtime_start_url"; then
        PORTAL_START_URL="$runtime_start_url"
        log "Using runtime portal start URL: $PORTAL_START_URL"
    else
        log "Ignoring invalid runtime portal start URL in $PORTAL_START_URL_FILE"
    fi
    rm -f "$PORTAL_START_URL_FILE" || true
fi

XVFB_PID=""
OPENBOX_PID=""
BROWSER_PID=""
X11VNC_PID=""
WEBSOCKIFY_PID=""

cleanup() {
    local pids=("$WEBSOCKIFY_PID" "$X11VNC_PID" "$BROWSER_PID" "$OPENBOX_PID" "$XVFB_PID")
    for pid in "${pids[@]}"; do
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
        fi
    done
}
trap cleanup EXIT INT TERM

log "Starting Xvfb on ${PORTAL_DISPLAY} (${PORTAL_SCREEN})"
Xvfb "$PORTAL_DISPLAY" -screen 0 "$PORTAL_SCREEN" -nolisten tcp -ac \
    >"$PORTAL_RUNTIME_DIR/xvfb.log" 2>&1 &
XVFB_PID=$!

display_num="${PORTAL_DISPLAY#:}"
x_socket="/tmp/.X11-unix/X${display_num}"
for _ in $(seq 1 50); do
    if [[ -S "$x_socket" ]]; then
        break
    fi
    sleep 0.1
done
if [[ ! -S "$x_socket" ]]; then
    log "ERROR: X display did not come up at $x_socket"
    exit 1
fi

export DISPLAY="$PORTAL_DISPLAY"

log "Starting openbox"
openbox >"$PORTAL_RUNTIME_DIR/openbox.log" 2>&1 &
OPENBOX_PID=$!

declare -a browser_args
read -r -a browser_args <<< "$PORTAL_BROWSER_ARGS"
log "Starting browser: $BROWSER_BIN $PORTAL_START_URL"
"$BROWSER_BIN" "${browser_args[@]}" "--user-data-dir=$PORTAL_BROWSER_PROFILE" "$PORTAL_START_URL" \
    >"$PORTAL_RUNTIME_DIR/browser.log" 2>&1 &
BROWSER_PID=$!

declare -a auth_args
if [[ -n "${PORTAL_VNC_PASSWORD:-}" ]]; then
    passwd_file="$PORTAL_RUNTIME_DIR/x11vnc.pass"
    x11vnc -storepasswd "$PORTAL_VNC_PASSWORD" "$passwd_file" >/dev/null 2>&1
    chmod 0600 "$passwd_file"
    auth_args=(-rfbauth "$passwd_file")
else
    log "VNC password auth disabled (PORTAL_VNC_PASSWORD is empty)"
    auth_args=(-nopw)
fi

log "Starting x11vnc on localhost:${PORTAL_VNC_PORT}"
x11vnc -display "$PORTAL_DISPLAY" -forever -shared -rfbport "$PORTAL_VNC_PORT" -localhost \
    "${auth_args[@]}" \
    >"$PORTAL_RUNTIME_DIR/x11vnc.log" 2>&1 &
X11VNC_PID=$!

log "Starting noVNC/websockify on ${PORTAL_NOVNC_BIND}:${PORTAL_NOVNC_PORT}"
websockify --web "$PORTAL_NOVNC_WEB" "${PORTAL_NOVNC_BIND}:${PORTAL_NOVNC_PORT}" "127.0.0.1:${PORTAL_VNC_PORT}" \
    >"$PORTAL_RUNTIME_DIR/websockify.log" 2>&1 &
WEBSOCKIFY_PID=$!

cat >"$PORTAL_RUNTIME_DIR/viewer-info.txt" <<EOF
start_url=$PORTAL_START_URL
novnc_bind=$PORTAL_NOVNC_BIND
novnc_port=$PORTAL_NOVNC_PORT
novnc_path=/vnc.html?autoconnect=true&resize=scale
EOF

log "Portal viewer ready: /vnc.html?autoconnect=true&resize=scale"
wait -n "$XVFB_PID" "$OPENBOX_PID" "$BROWSER_PID" "$X11VNC_PID" "$WEBSOCKIFY_PID"
log "A child process exited; shutting down"
