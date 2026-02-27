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
RUNTIME_DIR="/run/azazel"
STATE_FILE="${RUNTIME_DIR}/suri_epd_state.json"
COOLDOWN_SEC="${SURI_EPD_COOLDOWN_SEC:-90}"
MIN_GAP_SEC="${SURI_EPD_MIN_GAP_SEC:-10}"
command -v jq >/dev/null || { echo "jq required"; exit 1; }
mkdir -p "$RUNTIME_DIR"

normalize_num() {
  local val="${1:-0}"
  if [[ "$val" =~ ^[0-9]+$ ]]; then
    printf '%s' "$val"
  else
    printf '0'
  fi
}

current_mode() {
  local file mode=""
  for file in \
    /etc/azazel/mode.json \
    /etc/azazel-gadget/mode.json \
    /etc/azazel-zero/mode.json; do
    [[ -r "$file" ]] || continue
    mode="$(jq -r '.current_mode // empty' "$file" 2>/dev/null | tr '[:upper:]' '[:lower:]')"
    if [[ -n "$mode" && "$mode" != "null" ]]; then
      printf '%s' "$mode"
      return 0
    fi
  done
  printf ''
  return 0
}

should_render() {
  local state="$1"
  local msg="$2"
  local now
  now="$(date +%s)"
  local last_ts=0
  local last_state=""
  local last_msg=""

  if [[ -f "$STATE_FILE" ]]; then
    read -r last_ts last_state last_msg < <(
      jq -r '[.ts // 0, .state // "", .msg // ""] | @tsv' "$STATE_FILE" 2>/dev/null || \
      printf "0\t\t\n"
    )
  fi

  last_ts="$(normalize_num "$last_ts")"
  local delta=$(( now - last_ts ))
  if (( delta < MIN_GAP_SEC )); then
    return 1
  fi
  if [[ "$state" == "$last_state" && "$msg" == "$last_msg" && $delta -lt $COOLDOWN_SEC ]]; then
    return 1
  fi
  return 0
}

mark_rendered() {
  local state="$1"
  local msg="$2"
  local ts
  ts="$(date +%s)"
  local tmp="${STATE_FILE}.tmp"
  printf '{"ts":%s,"state":"%s","msg":"%s"}\n' \
    "$ts" \
    "${state//\"/}" \
    "${msg//\"/}" > "$tmp" || return 0
  mv -f "$tmp" "$STATE_FILE" || true
}

render_alert() {
  local severity="$1"
  local signature="$2"
  local state="warning"
  local msg="SCAN DETECTED"
  local mode_now=""

  mode_now="$(current_mode)"
  if [[ "$mode_now" == "scapegoat" ]]; then
    # Keep base mode screen while in SCAPEGOAT; do not overlay Suricata alert cards.
    return 0
  fi

  if [[ "$severity" =~ ^[0-9]+$ ]] && (( severity <= 2 )); then
    state="danger"
    msg="ATTACK DETECTED"
  fi

  logger -t suri-epaper "suricata alert: severity=${severity} signature=${signature:0:96}" >/dev/null 2>&1 || true

  if [[ ! -f "$EPD_ALERT_PY" ]]; then
    return 0
  fi

  if ! should_render "$state" "$msg"; then
    return 0
  fi

  local rc=0
  if command -v flock >/dev/null 2>&1; then
    flock -w 0 "$LOCK" /usr/bin/python3 "$EPD_ALERT_PY" --state "$state" --msg "$msg" >/dev/null 2>&1 || rc=$?
  else
    /usr/bin/python3 "$EPD_ALERT_PY" --state "$state" --msg "$msg" >/dev/null 2>&1 || rc=$?
  fi

  if [[ "$rc" -eq 0 ]]; then
    mark_rendered "$state" "$msg"
  else
    logger -t suri-epaper "render skipped/failed: state=${state} rc=${rc}" >/dev/null 2>&1 || true
  fi
}

tail -Fn0 "$EVE" | jq -rc 'select(.event_type=="alert") | [(.alert.severity // 3), (.alert.signature // "IDS alert")] | @tsv' | \
while IFS=$'\t' read -r severity signature; do
  signature="${signature//$'\r'/ }"
  signature="${signature//$'\n'/ }"
  render_alert "$severity" "$signature"
done
