#!/bin/sh
set -eu

for AZAZEL_DEFAULTS in /etc/default/azazel-gadget /etc/default/azazel-zero; do
  if [ -r "$AZAZEL_DEFAULTS" ]; then
    # shellcheck disable=SC1090
    . "$AZAZEL_DEFAULTS"
    break
  fi
done

IN_IF="${USB_IF:-usb0}"
MGMT_SUBNET_CIDR="${MGMT_SUBNET:-10.55.0.0/24}"

# NAT (POSTROUTING): downstream subnet to any non-downstream uplink
iptables -t nat -C POSTROUTING -s "$MGMT_SUBNET_CIDR" ! -o "$IN_IF" -j MASQUERADE 2>/dev/null || \
iptables -t nat -A POSTROUTING -s "$MGMT_SUBNET_CIDR" ! -o "$IN_IF" -j MASQUERADE

# FORWARD (downstream -> any uplink)
iptables -C FORWARD -i "$IN_IF" ! -o "$IN_IF" -s "$MGMT_SUBNET_CIDR" -j ACCEPT 2>/dev/null || \
iptables -A FORWARD -i "$IN_IF" ! -o "$IN_IF" -s "$MGMT_SUBNET_CIDR" -j ACCEPT

# FORWARD (uplink -> downstream, return traffic only)
iptables -C FORWARD ! -i "$IN_IF" -o "$IN_IF" -d "$MGMT_SUBNET_CIDR" -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT 2>/dev/null || \
iptables -A FORWARD ! -i "$IN_IF" -o "$IN_IF" -d "$MGMT_SUBNET_CIDR" -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
