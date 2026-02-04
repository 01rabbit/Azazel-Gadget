#!/bin/sh
set -eu
# Wait for usb0 to appear, then force static IPv4
for i in $(seq 1 50); do
  ip link show usb0 >/dev/null 2>&1 && break
  sleep 0.2
done
ip link set usb0 up || true
ip addr flush dev usb0 || true
ip addr add 10.55.0.10/24 dev usb0 || true
