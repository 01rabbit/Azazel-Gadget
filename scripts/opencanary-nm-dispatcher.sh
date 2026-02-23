#!/usr/bin/env bash
set -euo pipefail

IFACE="${1:-}"
ACTION="${2:-}"

WAN_IF="auto"
for defaults in /etc/default/azazel-gadget /etc/default/azazel-zero; do
  if [[ -f "$defaults" ]]; then
    # shellcheck disable=SC1091
    . "$defaults"
    WAN_IF="${WAN_IF:-auto}"
    break
  fi
done

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
    # OpenCanary lifecycle is owned by mode_manager:
    # - scapegoat: isolated canary is started
    # - portal/shield: canary remains stopped
    # Do not restart legacy global opencanary.service here.
    ;;
esac
