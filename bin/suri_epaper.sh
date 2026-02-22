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
  for candidate in \
    "$HOME/Azazel-Gadget" \
    "$HOME/Azazel-Zero" \
    "$HOME/azazel-gadget" \
    "$HOME/azazel-zero" \
    "/home/azazel/Azazel-Gadget" \
    "/home/azazel/Azazel-Zero"; do
    if [[ -d "$candidate" ]]; then
      AZAZEL_ROOT="$candidate"
      break
    fi
  done
fi

AZAZEL_ROOT="${AZAZEL_ROOT:-/home/azazel/Azazel-Gadget}"
EPD_ALERT_PY="${EPD_ALERT_PY:-${AZAZEL_ROOT}/py/azazel_epd.py}"
# Backward compatibility: if EPD_PY already points to azazel_epd.py, reuse it.
if [[ ! -f "$EPD_ALERT_PY" ]] && [[ -n "${EPD_PY:-}" ]] && [[ -f "$EPD_PY" ]] && [[ "$(basename "$EPD_PY")" == "azazel_epd.py" ]]; then
  EPD_ALERT_PY="$EPD_PY"
fi

LOCK="/run/azazel-epd.lock"
EVE="/var/log/suricata/eve.json"
command -v jq >/dev/null || { echo "jq required"; exit 1; }

render_alert() {
  local severity="$1"
  local signature="$2"
  local state="warning"
  local msg="SCAN DETECTED"

  if [[ "$severity" =~ ^[0-9]+$ ]] && (( severity <= 2 )); then
    state="danger"
    msg="ATTACK DETECTED"
  fi

  logger -t suri-epaper "suricata alert: severity=${severity} signature=${signature:0:96}" >/dev/null 2>&1 || true

  if [[ ! -f "$EPD_ALERT_PY" ]]; then
    return 0
  fi

  if command -v flock >/dev/null 2>&1; then
    flock -w 0 "$LOCK" /usr/bin/python3 "$EPD_ALERT_PY" --state "$state" --msg "$msg" >/dev/null 2>&1 || true
  else
    /usr/bin/python3 "$EPD_ALERT_PY" --state "$state" --msg "$msg" >/dev/null 2>&1 || true
  fi
}

tail -Fn0 "$EVE" | jq -rc 'select(.event_type=="alert") | [(.alert.severity // 3), (.alert.signature // "IDS alert")] | @tsv' | \
while IFS=$'\t' read -r severity signature; do
  signature="${signature//$'\r'/ }"
  signature="${signature//$'\n'/ }"
  render_alert "$severity" "$signature"
done
