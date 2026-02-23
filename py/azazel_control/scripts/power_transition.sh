#!/bin/bash
# Common safe power transition for shutdown/reboot actions.

set -euo pipefail

ACTION="${1:-}"
case "$ACTION" in
    shutdown|reboot) ;;
    *)
        echo "Usage: $0 {shutdown|reboot}" >&2
        exit 2
        ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
EPD_SCRIPT="${PROJECT_ROOT}/py/boot_splash_epd.py"

SYSTEMCTL_BIN="/bin/systemctl"
PYTHON3_BIN="/usr/bin/python3"
TIMEOUT_BIN="/usr/bin/timeout"

STOP_WAIT_SEC="${AZAZEL_STOP_WAIT_SEC:-8}"
EPD_CLEAR_TIMEOUT_SEC="${AZAZEL_EPD_CLEAR_TIMEOUT_SEC:-12}"

SAFE_STOP_UNITS=(
    "azazel-portal-viewer.service"
    "azazel-web.service"
    "azazel-first-minute.service"
    "opencanary.service"
    "suri-epaper.service"
    "azazel-epd-portal.timer"
    "azazel-epd-portal.service"
    "azazel-epd-refresh.timer"
    "azazel-epd-refresh.service"
)

unit_exists() {
    local unit="$1"
    local load_state
    load_state="$("${SYSTEMCTL_BIN}" show "${unit}" -p LoadState --value 2>/dev/null || true)"
    [[ -n "${load_state}" && "${load_state}" != "not-found" ]]
}

stop_managed_units() {
    local unit
    for unit in "${SAFE_STOP_UNITS[@]}"; do
        if unit_exists "${unit}"; then
            "${SYSTEMCTL_BIN}" stop "${unit}" >/dev/null 2>&1 || true
        fi
    done
}

wait_units_inactive() {
    local deadline=$((SECONDS + STOP_WAIT_SEC))
    local pending=()
    local unit
    local state

    while (( SECONDS < deadline )); do
        pending=()
        for unit in "${SAFE_STOP_UNITS[@]}"; do
            if ! unit_exists "${unit}"; then
                continue
            fi
            state="$("${SYSTEMCTL_BIN}" is-active "${unit}" 2>/dev/null || true)"
            case "${state}" in
                active|activating|deactivating|reloading)
                    pending+=("${unit}:${state}")
                    ;;
            esac
        done
        if ((${#pending[@]} == 0)); then
            return 0
        fi
        /bin/sleep 0.25
    done

    if ((${#pending[@]} > 0)); then
        printf 'Managed services did not stop in time: %s\n' "${pending[*]}" >&2
        return 1
    fi
    return 0
}

require_epd_clear() {
    if [[ ! -x "${PYTHON3_BIN}" || ! -f "${EPD_SCRIPT}" ]]; then
        echo "EPD clear script is unavailable: ${EPD_SCRIPT}" >&2
        return 1
    fi
    if ! "${TIMEOUT_BIN}" "${EPD_CLEAR_TIMEOUT_SEC}s" "${PYTHON3_BIN}" "${EPD_SCRIPT}" --mode shutdown >/dev/null 2>&1; then
        echo "EPD clear failed; aborting ${ACTION}" >&2
        return 1
    fi
    return 0
}

queue_power_action() {
    if [[ "${ACTION}" == "shutdown" ]]; then
        ("${SYSTEMCTL_BIN}" poweroff) >/dev/null 2>&1 &
        echo "System shutdown scheduled (services stopped, EPD cleared)"
        return 0
    fi
    ("${SYSTEMCTL_BIN}" reboot) >/dev/null 2>&1 &
    echo "System reboot scheduled (services stopped, EPD cleared)"
}

stop_managed_units
wait_units_inactive
require_epd_clear
queue_power_action
