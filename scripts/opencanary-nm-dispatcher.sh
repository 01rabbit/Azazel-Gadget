#!/usr/bin/env bash
set -euo pipefail

IFACE="${1:-}"
ACTION="${2:-}"

WAN_IF="wlan0"
if [[ -f /etc/default/azazel-zero ]]; then
  # shellcheck disable=SC1091
  . /etc/default/azazel-zero
  WAN_IF="${WAN_IF:-wlan0}"
fi

if [[ "${IFACE}" != "${WAN_IF}" ]]; then
  exit 0
fi

case "${ACTION}" in
  up|dhcp4-change|ipv4-change|connectivity-change)
    systemctl restart opencanary.service
    ;;
esac
