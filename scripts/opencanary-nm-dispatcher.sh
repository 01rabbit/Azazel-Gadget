#!/usr/bin/env bash
set -euo pipefail

IFACE="${1:-}"
ACTION="${2:-}"

WAN_IF="auto"
if [[ -f /etc/default/azazel-zero ]]; then
  # shellcheck disable=SC1091
  . /etc/default/azazel-zero
  WAN_IF="${WAN_IF:-auto}"
fi

is_uplink_event=0
if [[ "${WAN_IF}" == "auto" ]]; then
  case "${IFACE}" in
    wlan*|eth*)
      is_uplink_event=1
      ;;
  esac
else
  if [[ "${IFACE}" == "${WAN_IF}" ]]; then
    is_uplink_event=1
  fi
fi

if [[ "${is_uplink_event}" -ne 1 ]]; then
  exit 0
fi

case "${ACTION}" in
  up|dhcp4-change|ipv4-change|connectivity-change)
    systemctl restart azazel-nat.service || true
    systemctl restart opencanary.service
    ;;
esac
