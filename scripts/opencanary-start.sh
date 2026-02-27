#!/usr/bin/env bash
set -euo pipefail

pick_best_uplink_iface() {
  # Prefer Wi-Fi when available so honeypot exposure matches wlan0 policy.
  if ip link show wlan0 >/dev/null 2>&1; then
    local wlan_ip
    wlan_ip="$(ip -4 -o addr show dev wlan0 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | head -n1)"
    if [[ -n "$wlan_ip" ]]; then
      echo "wlan0"
      return 0
    fi
  fi

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

OPENCANARY_BIN="${OPENCANARY_BIN:-/home/azazel/canary-venv/bin/opencanaryd}"
RUN_USER="${OPENCANARY_RUN_USER:-}"
RUN_GROUP="${OPENCANARY_RUN_GROUP:-}"

# Default to the opencanary binary owner so venv assets under /home/* stay readable
# after privilege drop (common when /home/<user> is 0700).
if [[ -z "$RUN_USER" ]] && [[ -e "$OPENCANARY_BIN" ]]; then
  RUN_USER="$(stat -c '%U' "$OPENCANARY_BIN" 2>/dev/null || true)"
fi

if [[ -z "$RUN_USER" ]] || ! id -u "$RUN_USER" >/dev/null 2>&1 || [[ "$RUN_USER" == "root" ]]; then
  RUN_USER="nobody"
fi

if [[ -z "$RUN_GROUP" ]]; then
  RUN_GROUP="$(id -gn "$RUN_USER" 2>/dev/null || true)"
fi
if [[ -z "$RUN_GROUP" ]] || ! getent group "$RUN_GROUP" >/dev/null 2>&1; then
  RUN_GROUP="nogroup"
fi

drop_priv_args=()
if [[ "$(id -u)" -eq 0 ]]; then
  drop_priv_args=(--uid="$RUN_USER" --gid="$RUN_GROUP")
fi

exec "$OPENCANARY_BIN" --start "${drop_priv_args[@]}"
