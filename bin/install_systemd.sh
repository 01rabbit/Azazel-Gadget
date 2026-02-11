#!/usr/bin/env bash# ⚠️  DEPRECATED: This script is superseded by the unified installer.
# 
# **新形式は以下を使用してください：**
# 
#   sudo ./install.sh
# 
# このスクリプトは v3.0 で削除されます。
# 詳細: docs/INSTALLER_DEPRECATION_SCHEDULE.md
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
echo "AZAZEL_ROOT=${ROOT}"

install_if_exists() {
  local src="$1"
  local dest="$2"
  local mode="$3"
  if [ -f "$src" ]; then
    install -m "$mode" "$src" "$dest"
  else
    echo "[WARN] missing: ${src} (skip)" >&2
  fi
}

# スクリプトを /usr/local/bin へ
install -m 0755 "${ROOT}/bin/suri_epaper.sh"        /usr/local/bin/
install -m 0755 "${ROOT}/bin/portal_detect.sh"      /usr/local/bin/
install -m 0755 "${ROOT}/scripts/opencanary-start.sh" /usr/local/bin/opencanary-start

# sbin scripts
install -d /usr/local/sbin
install -m 0755 "${ROOT}/scripts/usb0-static.sh" /usr/local/sbin/usb0-static.sh
install -m 0755 "${ROOT}/scripts/azazel-nat.sh"  /usr/local/sbin/azazel-nat.sh

# 環境ファイル
sudo install -d /etc/default
sudo tee /etc/default/azazel-zero >/dev/null <<EOF
AZAZEL_ROOT=${ROOT}
AZAZEL_CANARY_VENV=/home/azazel/canary-venv
AZAZEL_WEBUI_VENV=/home/azazel/azazel-webui-venv

# 統一したEPDパスとロックファイル
EPD_PY=${ROOT}/py/boot_splash_epd.py
EPD_LOCK=/run/azazel-epd.lock

# ネットワーク関連（遅滞制御用）
WAN_IF=wlan0
USB_IF=usb0
SUBNET=192.168.7.0/24

# Captive Portal detector 用（WAN_IF を使うなら同じにする）
OUTIF=\${WAN_IF}
EOF

# Azazel-Zero config files
sudo install -d /etc/azazel-zero
sudo install -d /etc/azazel-zero/nftables
sudo install -m 0644 "${ROOT}/configs/first_minute.yaml" /etc/azazel-zero/first_minute.yaml
sudo install -m 0644 "${ROOT}/configs/dnsmasq-first_minute.conf" /etc/azazel-zero/dnsmasq-first_minute.conf
sudo install -m 0644 "${ROOT}/configs/known_wifi.json" /etc/azazel-zero/known_wifi.json
sudo install -m 0644 "${ROOT}/nftables/first_minute.nft" /etc/azazel-zero/nftables/first_minute.nft

# dnsmasq ディレクトリ設定
sudo install -d /var/lib/dnsmasq
sudo touch /var/lib/dnsmasq/dnsmasq.leases
sudo chown nobody:nogroup /var/lib/dnsmasq/dnsmasq.leases

# iptables-persistent rules (USB NAT)
sudo install -d /etc/iptables
sudo install -m 0644 "${ROOT}/configs/iptables-rules.v4" /etc/iptables/rules.v4

# OpenCanary config
sudo install -d /etc/opencanaryd
sudo install -m 0644 "${ROOT}/configs/opencanary.conf" /etc/opencanaryd/opencanary.conf

# NetworkManager dispatcher (restart opencanary on wlan0 IP change)
sudo install -d /etc/NetworkManager/dispatcher.d
sudo install -m 0755 "${ROOT}/scripts/opencanary-nm-dispatcher.sh" /etc/NetworkManager/dispatcher.d/50-opencanary-wlan0

# systemd unit を配置
sudo install -m 0644 "${ROOT}/systemd/azazel-epd.service"     /etc/systemd/system/
sudo install -m 0644 "${ROOT}/systemd/suri-epaper.service"    /etc/systemd/system/
sudo install -m 0644 "${ROOT}/systemd/opencanary.service"     /etc/systemd/system/
sudo install -m 0644 "${ROOT}/systemd/azazel-epd-portal.service" /etc/systemd/system/
sudo install -m 0644 "${ROOT}/systemd/azazel-epd-portal.timer"   /etc/systemd/system/
sudo install -d /etc/systemd/system/azazel-epd.service.d
sudo install -m 0644 "${ROOT}/systemd/azazel-epd.service.d/10-portal-detect.conf" /etc/systemd/system/azazel-epd.service.d/
sudo install -m 0644 "${ROOT}/systemd/azazel-first-minute.service" /etc/systemd/system/
sudo install -m 0644 "${ROOT}/systemd/azazel-control-daemon.service" /etc/systemd/system/
sudo install -m 0644 "${ROOT}/systemd/azazel-web.service" /etc/systemd/system/
sudo install -m 0644 "${ROOT}/systemd/usb0-static.service" /etc/systemd/system/
sudo install -m 0644 "${ROOT}/systemd/azazel-nat.service" /etc/systemd/system/

# 反映・起動
sudo systemctl daemon-reload
sudo systemctl enable --now suri-epaper.service
sudo systemctl enable --now azazel-epd-portal.timer
sudo systemctl enable --now azazel-first-minute.service
sudo systemctl enable --now azazel-control-daemon.service
sudo systemctl enable --now azazel-web.service
sudo systemctl enable --now usb0-static.service
sudo systemctl enable --now azazel-nat.service
echo "Units installed. Edit opencanary.service if needed, then: sudo systemctl enable --now opencanary.service"
