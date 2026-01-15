#!/usr/bin/env bash
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
install_if_exists "${ROOT}/bin/update_epaper_tmux.sh" /usr/local/bin/ 0755
install -m 0755 "${ROOT}/bin/suri_epaper.sh"        /usr/local/bin/
install -m 0755 "${ROOT}/bin/portal_detect.sh"      /usr/local/bin/

# 環境ファイル
sudo install -d /etc/default
sudo tee /etc/default/azazel-zero >/dev/null <<EOF
AZAZEL_ROOT=${ROOT}
AZAZEL_CANARY_VENV=/home/azazel/canary-venv

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

# systemd unit を配置
sudo install -m 0644 "${ROOT}/systemd/azazel-epd.service"     /etc/systemd/system/
sudo install -m 0644 "${ROOT}/systemd/suri-epaper.service"    /etc/systemd/system/
sudo install -m 0644 "${ROOT}/systemd/opencanary.service"     /etc/systemd/system/
sudo install -m 0644 "${ROOT}/systemd/azazel-epd-portal.service" /etc/systemd/system/
sudo install -m 0644 "${ROOT}/systemd/azazel-epd-portal.timer"   /etc/systemd/system/
sudo install -d /etc/systemd/system/azazel-epd.service.d
sudo install -m 0644 "${ROOT}/systemd/azazel-epd.service.d/10-portal-detect.conf" /etc/systemd/system/azazel-epd.service.d/
sudo install -m 0644 "${ROOT}/systemd/azazel-first-minute.service" /etc/systemd/system/

# 反映・起動
sudo systemctl daemon-reload
sudo systemctl enable --now suri-epaper.service
sudo systemctl enable --now azazel-epd-portal.timer
sudo systemctl enable --now azazel-first-minute.service
echo "Units installed. Edit opencanary.service if needed, then: sudo systemctl enable --now opencanary.service"
