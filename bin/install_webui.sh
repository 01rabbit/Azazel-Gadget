#!/usr/bin/env bash
# Azazel-Zero Web UI installer
# Purpose: Reproducible Web UI setup for remote monitoring
# Usage: sudo bin/install_webui.sh [--no-systemd] [--dry-run]

set -euo pipefail

# ---------- Configuration ----------
ENABLE_SYSTEMD=1
DRY_RUN=0
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AZAZEL_ROOT="${AZAZEL_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
LOG="${LOG:-/var/log/azazel-webui-install.log}"
WEBUI_USER="${WEBUI_USER:-azazel}"
WEBUI_VENV="${WEBUI_VENV:-/home/azazel/azazel-webui-venv}"
WEBUI_PY="${WEBUI_VENV}/bin/python"
WEBUI_PIP="${WEBUI_VENV}/bin/pip"
WEBUI_VERIFY="${WEBUI_VERIFY:-1}"

# ---------- Helpers ----------
log() { echo "[+] $*" | tee -a "$LOG"; }
warn() { echo "[!] $*" | tee -a "$LOG" >&2; }
fail() { echo "[x] $*" | tee -a "$LOG" >&2; exit 1; }
require_root() { if [ "${EUID:-$(id -u)}" -ne 0 ]; then fail "Run as root"; fi; }
cmd() {
    echo "+ $*" | tee -a "$LOG"
    if [ "$DRY_RUN" -eq 0 ]; then
        eval "$@" 2>&1 | tee -a "$LOG"
    else
        echo "  (dry-run: skipped)" | tee -a "$LOG"
    fi
}

ensure_webui_user() {
    if ! id "$WEBUI_USER" >/dev/null 2>&1; then
        cmd "useradd -m -s /bin/bash $WEBUI_USER"
    fi
}

ensure_webui_venv() {
    log "Preparing Web UI venv: $WEBUI_VENV"
    ensure_webui_user
    cmd "apt-get update -y"
    cmd "apt-get install -y python3-full python3-venv"
    if [ ! -x "$WEBUI_PY" ]; then
        cmd "runuser -u $WEBUI_USER -- python3 -m venv $WEBUI_VENV"
    fi
    cmd "runuser -u $WEBUI_USER -- $WEBUI_PIP install --upgrade pip wheel"
}

# ---------- Parse arguments ----------
while [ $# -gt 0 ]; do
    case "$1" in
        --no-systemd) ENABLE_SYSTEMD=0; shift ;;
        --dry-run) DRY_RUN=1; shift ;;
        -h|--help)
            cat <<EOF
Azazel-Zero Web UI installer

Usage: sudo bin/install_webui.sh [OPTIONS]

Options:
  --no-systemd       Do not install/enable systemd services
  --dry-run          Show what would be done without executing
  -h, --help         Show this help message

Web UI features:
  - Flask web server (port 8084)
  - Real-time dashboard with system metrics
  - Remote access via USB gadget network (10.55.0.10:8084)
  - Control daemon for action execution
  - Shared state with TUI (/run/azazel-zero/ui_snapshot.json)

Requirements:
  - Python 3.8+
  - Flask 3.1.1+
  - nftables with port 8084 whitelisted
  - Existing Azazel-Zero installation
EOF
            exit 0
            ;;
        *) fail "Unknown option: $1 (use --help for usage)" ;;
    esac
done

# ---------- Preflight ----------
require_root
log "Starting Web UI installation (AZAZEL_ROOT=$AZAZEL_ROOT)"
log "Options: ENABLE_SYSTEMD=$ENABLE_SYSTEMD, DRY_RUN=$DRY_RUN"

# ---------- Step 1: Install Python dependencies ----------
install_python_deps() {
    log "Installing Python dependencies for Web UI (venv)"
    log "System Python may be externally managed (PEP 668); using venv for Flask."
    ensure_webui_venv

    # Check if Flask is already installed in venv
    if runuser -u "$WEBUI_USER" -- "$WEBUI_PY" -c "import flask" >/dev/null 2>&1; then
        local flask_version
        flask_version=$(runuser -u "$WEBUI_USER" -- "$WEBUI_PY" -c "import flask; print(flask.__version__)")
        log "Flask already installed in venv: version $flask_version"
    else
        log "Installing Flask into venv..."
        cmd "runuser -u $WEBUI_USER -- $WEBUI_PIP install 'Flask>=3.1.1'"
    fi

    # Verify installation (non-fatal; low-memory systems may OOM-kill python)
    local mem_kb=0
    if [ -r /proc/meminfo ]; then
        mem_kb=$(awk '/^MemTotal:/ {print $2}' /proc/meminfo 2>/dev/null || echo 0)
    fi
    if [ "$WEBUI_VERIFY" -eq 1 ] && [ "${mem_kb:-0}" -ge 800000 ]; then
        log "Verifying Flask import/version (non-fatal)"
        if ! runuser -u "$WEBUI_USER" -- "$WEBUI_PY" -c 'import flask; print("Flask version:", flask.__version__)' 2>&1 | tee -a "$LOG"; then
            warn "Flask version check failed (possibly low memory). Continuing."
        fi
    else
        warn "Skipping Flask version check (WEBUI_VERIFY=0 or low memory: ${mem_kb} kB)"
    fi
}

# ---------- Step 2: Verify directory structure ----------
verify_structure() {
    log "Verifying Web UI directory structure"
    
    local required_dirs=(
        "$AZAZEL_ROOT/azazel_web"
        "$AZAZEL_ROOT/azazel_web/templates"
        "$AZAZEL_ROOT/azazel_web/static"
        "$AZAZEL_ROOT/py/azazel_control"
        "$AZAZEL_ROOT/py/azazel_control/scripts"
    )
    
    for dir in "${required_dirs[@]}"; do
        if [ ! -d "$dir" ]; then
            fail "Required directory not found: $dir"
        fi
        log "✓ Found: $dir"
    done
    
    local required_files=(
        "$AZAZEL_ROOT/azazel_web/app.py"
        "$AZAZEL_ROOT/azazel_web/templates/index.html"
        "$AZAZEL_ROOT/azazel_web/static/app.js"
        "$AZAZEL_ROOT/azazel_web/static/style.css"
        "$AZAZEL_ROOT/py/azazel_control/daemon.py"
    )
    
    for file in "${required_files[@]}"; do
        if [ ! -f "$file" ]; then
            fail "Required file not found: $file"
        fi
        log "✓ Found: $file"
    done
}

# ---------- Step 3: Create runtime directories ----------
create_runtime_dirs() {
    log "Creating runtime directories"
    
    cmd "mkdir -p /run/azazel"
    cmd "mkdir -p /run/azazel-zero"
    cmd "chmod 755 /run/azazel /run/azazel-zero"
    
    log "Runtime directories created"
}

# ---------- Step 4: Install systemd services ----------
install_systemd_services() {
    if [ "$ENABLE_SYSTEMD" -eq 0 ]; then
        log "Skipping systemd installation (--no-systemd)"
        return 0
    fi
    
    log "Installing Web UI systemd services"
    
    # Control daemon service
    local daemon_service="$AZAZEL_ROOT/systemd/azazel-control-daemon.service"
    if [ ! -f "$daemon_service" ]; then
        fail "Control daemon service file not found: $daemon_service"
    fi
    
    cmd "cp $daemon_service /etc/systemd/system/"
    log "✓ Installed azazel-control-daemon.service"
    
    # Reload systemd
    cmd "systemctl daemon-reload"
    
    # Enable services
    log "Enabling Web UI services"
    cmd "systemctl enable azazel-control-daemon.service"
    
    log "✓ Web UI services enabled (not started yet)"
    log "  To start: sudo systemctl start azazel-control-daemon"
}

# ---------- Step 5: Verify nftables configuration ----------
verify_nftables() {
    log "Verifying nftables configuration for Web UI"
    
    local nft_template="$AZAZEL_ROOT/nftables/first_minute.nft"
    if [ ! -f "$nft_template" ]; then
        warn "nftables template not found: $nft_template"
        return 0
    fi
    
    # Check if port 8084 is in the template
    if grep -q '8084' "$nft_template"; then
        log "✓ Port 8084 found in nftables template"
    else
        warn "Port 8084 not found in nftables template!"
        warn "You may need to add it to the mgmt_ports set"
    fi
    
    # Check current nftables rules
    if command -v nft >/dev/null 2>&1; then
        if nft list table inet azazel_fmc >/dev/null 2>&1; then
            log "Checking active firewall rules..."
            if nft list table inet azazel_fmc | grep -q '8084'; then
                log "✓ Port 8084 is active in firewall"
            else
                warn "Port 8084 not active in firewall"
                warn "Restart azazel-first-minute to apply: sudo systemctl restart azazel-first-minute"
            fi
        else
            log "azazel_fmc table not loaded yet (normal for new installation)"
        fi
    fi
}

# ---------- Step 6: Test Web UI ----------
test_webui() {
    log "Testing Web UI components"
    
    # Test Flask app syntax
    log "Checking Flask app syntax..."
    cmd "$WEBUI_PY -m py_compile $AZAZEL_ROOT/azazel_web/app.py"
    
    # Test control daemon syntax
    log "Checking control daemon syntax..."
    cmd "python3 -m py_compile $AZAZEL_ROOT/py/azazel_control/daemon.py"
    
    # Check action scripts permissions
    log "Checking action scripts..."
    local scripts_dir="$AZAZEL_ROOT/py/azazel_control/scripts"
    local script_count=$(find "$scripts_dir" -name "*.sh" -type f | wc -l)
    log "Found $script_count action scripts in $scripts_dir"
    
    for script in "$scripts_dir"/*.sh; do
        if [ ! -x "$script" ]; then
            log "Making executable: $script"
            cmd "chmod +x $script"
        fi
    done
    
    log "✓ All components validated"
}

# ---------- Main execution ----------
main() {
    log "========================================="
    log "Azazel-Zero Web UI Installer"
    log "========================================="
    
    install_python_deps
    verify_structure
    create_runtime_dirs
    install_systemd_services
    verify_nftables
    test_webui
    
    log "========================================="
    log "Web UI installation complete!"
    log "========================================="
    
    cat <<EOF | tee -a "$LOG"

Next steps:
  1. Start the control daemon:
     sudo systemctl start azazel-control-daemon

  2. Access the Web UI:
     - Local: http://127.0.0.1:8084
     - USB gadget: http://10.55.0.10:8084 (from MacBook)
     - Wi-Fi: http://<raspberry-pi-ip>:8084

  3. Verify services:
     sudo systemctl status azazel-control-daemon
     sudo systemctl status azazel-first-minute

  4. Check firewall:
     sudo nft list table inet azazel_fmc | grep 8084

  5. View logs:
     journalctl -u azazel-control-daemon -f
     journalctl -u azazel-first-minute -f

Documentation: $AZAZEL_ROOT/docs/WEB_UI.md
EOF
}

main "$@"
