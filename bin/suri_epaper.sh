#!/usr/bin/env bash
set -euo pipefail
for defaults in /etc/default/azazel-gadget /etc/default/azazel-zero; do
  if [[ -r "$defaults" ]]; then
    # shellcheck disable=SC1090
    . "$defaults"
    break
  fi
done

if [[ -z "${AZAZEL_ROOT:-}" ]]; then
  for candidate in "$HOME/Azazel-Gadget" "$HOME/azazel-gadget" "/home/azazel/Azazel-Gadget"; do
    if [[ -d "$candidate" ]]; then
      AZAZEL_ROOT="$candidate"
      break
    fi
  done
fi

AZAZEL_ROOT="${AZAZEL_ROOT:-/home/azazel/Azazel-Gadget}"
EPD_PY="${EPD_PY:-${AZAZEL_ROOT}/py/boot_splash_epd.py}"
LOCK="/run/azazel-epd.lock"
EVE="/var/log/suricata/eve.json"
command -v jq >/dev/null || { echo "jq required"; exit 1; }

tail -Fn0 "$EVE" | jq -r 'select(.event_type=="alert") | .alert.signature' | \
while read -r line; do
  if command -v flock >/dev/null 2>&1; then
    flock -w 0 "$LOCK" /usr/bin/python3 "$EPD_PY" --mode alert "IDS: $line" >/dev/null 2>&1 || true
  else
    /usr/bin/python3 "$EPD_PY" --mode alert "IDS: $line" >/dev/null 2>&1 || true
  fi
done
