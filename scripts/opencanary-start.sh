#!/usr/bin/env bash
set -euo pipefail

IFACE="${WAN_IF:-wlan0}"
IP="$(ip -4 -o addr show dev "$IFACE" | awk '{print $4}' | cut -d/ -f1 | head -n1)"

if [[ -z "${IP}" ]]; then
  IP="0.0.0.0"
  echo "opencanary-start: no IPv4 address on ${IFACE}; fallback to ${IP}" >&2
fi

export AZAZEL_WLAN_IP="${IP}"
exec /home/azazel/canary-venv/bin/opencanaryd --start --uid=nobody --gid=nogroup
