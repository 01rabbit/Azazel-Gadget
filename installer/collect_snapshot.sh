#!/bin/bash
################################################################################
# collect_snapshot.sh - Azazel-Gadget Infrastructure Discovery
# 旧機・新機のどちらでも実行可能（移行時は旧機で必須）
# 出力: installer/snapshot/<hostname>_<YYYYMMDD-HHMMSS>/
################################################################################

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

HOSTNAME=$(hostname)
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
SNAPSHOT_NAME="${HOSTNAME}_${TIMESTAMP}"
SNAPSHOT_DIR="$SCRIPT_DIR/snapshot/$SNAPSHOT_NAME"

echo "=== Azazel-Gadget Infrastructure Discovery ==="
echo "Hostname: $HOSTNAME"
echo "Timestamp: $TIMESTAMP"
echo "Output: $SNAPSHOT_DIR"
echo

# root権限チェック
if [[ $EUID -ne 0 ]]; then
   echo "ERROR: このスクリプトはroot権限で実行する必要があります"
   exit 1
fi

# スナップショットディレクトリ作成
mkdir -p "$SNAPSHOT_DIR"/{network,firewall,services,system,config}

echo "[1/12] Network interfaces..."
ip addr show > "$SNAPSHOT_DIR/network/ip_addr.txt" 2>&1
ip link show > "$SNAPSHOT_DIR/network/ip_link.txt" 2>&1
ip route show > "$SNAPSHOT_DIR/network/ip_route.txt" 2>&1
ip route show table all > "$SNAPSHOT_DIR/network/ip_route_all.txt" 2>&1
ip rule show > "$SNAPSHOT_DIR/network/ip_rule.txt" 2>&1

echo "[2/12] Network configuration files..."
if [[ -f /etc/dhcpcd.conf ]]; then
    cp /etc/dhcpcd.conf "$SNAPSHOT_DIR/config/dhcpcd.conf"
fi
if [[ -f /etc/resolv.conf ]]; then
    cp /etc/resolv.conf "$SNAPSHOT_DIR/config/resolv.conf"
fi
if [[ -d /etc/network ]]; then
    cp -r /etc/network "$SNAPSHOT_DIR/config/" 2>/dev/null || true
fi
if [[ -d /etc/NetworkManager ]]; then
    cp -r /etc/NetworkManager "$SNAPSHOT_DIR/config/" 2>/dev/null || true
fi

echo "[3/12] Listening sockets..."
ss -tlnp > "$SNAPSHOT_DIR/network/ss_tcp.txt" 2>&1 || true
ss -ulnp > "$SNAPSHOT_DIR/network/ss_udp.txt" 2>&1 || true
ss -tlnp46 > "$SNAPSHOT_DIR/network/ss_tcp46.txt" 2>&1 || true

echo "[4/12] Firewall state..."
# nftables
if command -v nft &>/dev/null; then
    nft list ruleset > "$SNAPSHOT_DIR/firewall/nft_ruleset.txt" 2>&1 || echo "nft failed" > "$SNAPSHOT_DIR/firewall/nft_ruleset.txt"
fi

# iptables (legacy/nft)
if command -v iptables &>/dev/null; then
    iptables -t filter -L -v -n > "$SNAPSHOT_DIR/firewall/iptables_filter.txt" 2>&1 || true
    iptables -t nat -L -v -n > "$SNAPSHOT_DIR/firewall/iptables_nat.txt" 2>&1 || true
    iptables -t mangle -L -v -n > "$SNAPSHOT_DIR/firewall/iptables_mangle.txt" 2>&1 || true
    iptables-save > "$SNAPSHOT_DIR/firewall/iptables_save.txt" 2>&1 || true
fi

if command -v ip6tables &>/dev/null; then
    ip6tables-save > "$SNAPSHOT_DIR/firewall/ip6tables_save.txt" 2>&1 || true
fi

echo "[5/12] Traffic control (tc)..."
for iface in $(ip -o link show | awk -F': ' '{print $2}'); do
    tc qdisc show dev "$iface" > "$SNAPSHOT_DIR/network/tc_${iface}.txt" 2>&1 || true
    tc class show dev "$iface" > "$SNAPSHOT_DIR/network/tc_class_${iface}.txt" 2>&1 || true
    tc filter show dev "$iface" > "$SNAPSHOT_DIR/network/tc_filter_${iface}.txt" 2>&1 || true
done

echo "[6/12] sysctl (IP forwarding, etc.)..."
sysctl -a > "$SNAPSHOT_DIR/system/sysctl.txt" 2>&1 || true
grep -E '(net.ipv4.ip_forward|net.ipv6.conf)' "$SNAPSHOT_DIR/system/sysctl.txt" > "$SNAPSHOT_DIR/system/sysctl_routing.txt" 2>&1 || true

echo "[7/12] systemd services..."
systemctl list-units --type=service --all --no-pager > "$SNAPSHOT_DIR/services/systemctl_services.txt" 2>&1
systemctl list-unit-files --type=service --no-pager > "$SNAPSHOT_DIR/services/systemctl_unit_files.txt" 2>&1

# Azazel関連サービスの詳細
for service in azazel-first-minute azazel-nat azazel-web azazel-control-daemon opencanary suri-epaper azazel-epd usb0-static; do
    if systemctl list-unit-files | grep -q "^${service}.service"; then
        systemctl show "$service.service" --no-pager > "$SNAPSHOT_DIR/services/${service}_show.txt" 2>&1 || true
        systemctl status "$service.service" --no-pager > "$SNAPSHOT_DIR/services/${service}_status.txt" 2>&1 || true
        
        # ExecStartから設定ファイルパスを抽出
        systemctl cat "$service.service" > "$SNAPSHOT_DIR/services/${service}_unit.txt" 2>&1 || true
    fi
done

echo "[8/12] Process list..."
ps auxf > "$SNAPSHOT_DIR/system/ps_auxf.txt" 2>&1

echo "[9/12] Package list (dpkg)..."
dpkg -l > "$SNAPSHOT_DIR/system/dpkg.txt" 2>&1

echo "[10/12] Python environments..."
python3 --version > "$SNAPSHOT_DIR/system/python3_version.txt" 2>&1 || echo "python3 not found" > "$SNAPSHOT_DIR/system/python3_version.txt"
pip3 list > "$SNAPSHOT_DIR/system/pip3_list.txt" 2>&1 || echo "pip3 not found" > "$SNAPSHOT_DIR/system/pip3_list.txt"

# venv確認
if [[ -d /opt/azazel/.venv ]]; then
    /opt/azazel/.venv/bin/pip list > "$SNAPSHOT_DIR/system/venv_pip_list.txt" 2>&1 || true
fi

echo "[11/12] Azazel configuration files..."
if [[ -d "$REPO_ROOT/configs" ]]; then
    cp -r "$REPO_ROOT/configs" "$SNAPSHOT_DIR/config/" 2>&1 || true
fi

if [[ -d "$REPO_ROOT/nftables" ]]; then
    cp -r "$REPO_ROOT/nftables" "$SNAPSHOT_DIR/config/" 2>&1 || true
fi

if [[ -f /etc/dnsmasq.conf ]]; then
    cp /etc/dnsmasq.conf "$SNAPSHOT_DIR/config/" 2>&1 || true
fi

if [[ -d /etc/dnsmasq.d ]]; then
    cp -r /etc/dnsmasq.d "$SNAPSHOT_DIR/config/" 2>&1 || true
fi

# Suricata
if [[ -f /etc/suricata/suricata.yaml ]]; then
    cp /etc/suricata/suricata.yaml "$SNAPSHOT_DIR/config/" 2>&1 || true
fi

# OpenCanary
if [[ -f /etc/opencanary/opencanary.conf ]]; then
    cp /etc/opencanary/opencanary.conf "$SNAPSHOT_DIR/config/opencanary.conf" 2>&1 || true
fi

echo "[12/12] Metadata..."
cat > "$SNAPSHOT_DIR/meta.json" <<EOF
{
  "hostname": "$HOSTNAME",
  "timestamp": "$TIMESTAMP",
  "snapshot_dir": "$SNAPSHOT_DIR",
  "collected_at": "$(date -Iseconds)",
  "kernel": "$(uname -r)",
  "os_release": "$(cat /etc/os-release | grep PRETTY_NAME | cut -d= -f2 | tr -d '"')"
}
EOF

echo
echo "=== Snapshot Complete ==="
echo "Location: $SNAPSHOT_DIR"
echo
echo "Next steps:"
echo "  1. Run masking: python3 installer/mask.py --snapshot $SNAPSHOT_DIR"
echo "  2. Generate profile: python3 installer/generate_profile.py --snapshot $SNAPSHOT_DIR/snapshot.json"
echo
