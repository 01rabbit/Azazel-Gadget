#!/bin/bash
# Shutdown: clear EPD first, then request host poweroff.

set -euo pipefail

EPD_SCRIPT="/home/azazel/Azazel-Zero/py/boot_splash_epd.py"

(
    /bin/sleep 1
    if [[ -x /usr/bin/python3 && -f "$EPD_SCRIPT" ]]; then
        /usr/bin/timeout 7s /usr/bin/python3 "$EPD_SCRIPT" --mode shutdown >/dev/null 2>&1 || true
    fi
    /bin/systemctl poweroff
) >/dev/null 2>&1 &

echo "System shutdown scheduled (EPD clear requested)"
