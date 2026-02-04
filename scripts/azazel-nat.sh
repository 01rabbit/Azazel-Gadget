#!/bin/sh
set -eu

OUT_IF="wlan0"
IN_IF="usb0"

# NAT (POSTROUTING) - avoid duplicates
iptables -t nat -C POSTROUTING -o "$OUT_IF" -j MASQUERADE 2>/dev/null || \
iptables -t nat -A POSTROUTING -o "$OUT_IF" -j MASQUERADE

# FORWARD (usb0 -> wlan0)
iptables -C FORWARD -i "$IN_IF" -o "$OUT_IF" -j ACCEPT 2>/dev/null || \
iptables -A FORWARD -i "$IN_IF" -o "$OUT_IF" -j ACCEPT

# FORWARD (wlan0 -> usb0 established/related)
iptables -C FORWARD -i "$OUT_IF" -o "$IN_IF" -m state --state ESTABLISHED,RELATED -j ACCEPT 2>/dev/null || \
iptables -A FORWARD -i "$OUT_IF" -o "$IN_IF" -m state --state ESTABLISHED,RELATED -j ACCEPT
