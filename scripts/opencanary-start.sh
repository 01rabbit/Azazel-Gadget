#!/usr/bin/env bash
set -euo pipefail

pick_best_uplink_iface() {
  local route_if
  route_if="$(ip -4 route show default 2>/dev/null | awk '{for (i=1; i<=NF; i++) if ($i == "dev") {print $(i+1); exit}}')"
  if [[ -n "$route_if" ]] && [[ "$route_if" != "usb0" ]] && ip link show "$route_if" >/dev/null 2>&1; then
    echo "$route_if"
    return 0
  fi
  for candidate in wlan0 eth0; do
    if ip link show "$candidate" >/dev/null 2>&1; then
      echo "$candidate"
      return 0
    fi
  done
  echo "wlan0"
}

IFACE="${WAN_IF:-auto}"
if [[ "$IFACE" == "auto" ]] || ! ip link show "$IFACE" >/dev/null 2>&1; then
  IFACE="$(pick_best_uplink_iface)"
fi

IP="$(ip -4 -o addr show dev "$IFACE" 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | head -n1)"

if [[ -z "${IP}" ]]; then
  IP="0.0.0.0"
  echo "opencanary-start: no IPv4 address on ${IFACE}; fallback to ${IP}" >&2
fi

export AZAZEL_WLAN_IP="${IP}"
exec /home/azazel/canary-venv/bin/opencanaryd --start --uid=nobody --gid=nogroup
