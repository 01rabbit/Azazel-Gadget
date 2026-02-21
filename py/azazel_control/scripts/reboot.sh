#!/bin/bash
# Reboot: clear EPD first, then request host reboot.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
EPD_SCRIPT="${PROJECT_ROOT}/py/boot_splash_epd.py"

(
    /bin/sleep 1
    if [[ -x /usr/bin/python3 && -f "$EPD_SCRIPT" ]]; then
        /usr/bin/timeout 7s /usr/bin/python3 "$EPD_SCRIPT" --mode shutdown >/dev/null 2>&1 || true
    fi
    /bin/systemctl reboot
) >/dev/null 2>&1 &

echo "System reboot scheduled (EPD clear requested)"
