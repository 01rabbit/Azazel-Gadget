#!/bin/bash
# Normalize /etc/suricata/suricata.yaml to a single managed rules file.
set -euo pipefail

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  if command -v sudo >/dev/null 2>&1; then
    exec sudo -E bash "$0" "$@"
  fi
  echo "[yaml_minify][ERROR] run as root (or install sudo)" >&2
  exit 1
fi

# Defaults
YAML="/etc/suricata/suricata.yaml"
DEFAULT_RULE_PATH="/var/lib/suricata/rules"
RULE_FILE="suricata.rules"
BACKUP_DIR="/etc/suricata"
DO_TEST=1
DO_RESTART=1

log() { printf "[yaml_minify] %s\n" "$*"; }
warn() { printf "[yaml_minify][WARN] %s\n" "$*" 1>&2; }
die() { printf "[yaml_minify][ERROR] %s\n" "$*" 1>&2; exit 1; }

usage() {
  cat <<'USAGE'
Usage: suricata_yaml_minify.sh [OPTIONS]

Options:
  --yaml PATH
  --default-rule-path PATH
  --rule-file NAME
  --backup-dir DIR
  --no-test
  --no-restart
  -h, --help
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --yaml) shift; YAML="${1:-$YAML}" ;;
    --yaml=*) YAML="${1#*=}" ;;
    --default-rule-path) shift; DEFAULT_RULE_PATH="${1:-$DEFAULT_RULE_PATH}" ;;
    --default-rule-path=*) DEFAULT_RULE_PATH="${1#*=}" ;;
    --rule-file) shift; RULE_FILE="${1:-$RULE_FILE}" ;;
    --rule-file=*) RULE_FILE="${1#*=}" ;;
    --backup-dir) shift; BACKUP_DIR="${1:-$BACKUP_DIR}" ;;
    --backup-dir=*) BACKUP_DIR="${1#*=}" ;;
    --no-test) DO_TEST=0 ;;
    --no-restart) DO_RESTART=0 ;;
    -h|--help) usage; exit 0 ;;
    *) warn "Unknown option: $1" ;;
  esac
  shift
done

[[ -f "$YAML" ]] || die "YAML not found: $YAML"
install -d "$BACKUP_DIR"
BACKUP="$BACKUP_DIR/$(basename "$YAML").azazel.bak.$(date +%Y%m%d%H%M%S)"
cp -a "$YAML" "$BACKUP"
log "backup: $BACKUP"

# 1) Set default-rule-path (insert if missing).
if grep -q '^[[:space:]]*default-rule-path:' "$YAML"; then
  sed -i "s|^[[:space:]]*default-rule-path:.*|default-rule-path: ${DEFAULT_RULE_PATH}|" "$YAML"
else
  printf '\ndefault-rule-path: %s\n' "$DEFAULT_RULE_PATH" >> "$YAML"
fi

# 2) Replace/insert rule-files block with a single entry.
if grep -q '^[[:space:]]*rule-files:[[:space:]]*$' "$YAML"; then
  awk -v rf="$RULE_FILE" '
  BEGIN { inblock=0 }
  /^[[:space:]]*rule-files:[[:space:]]*$/ { print "rule-files:\n  - " rf; inblock=1; next }
  /^[^[:space:]]/ { if (inblock) inblock=0 }
  { if (!inblock) print $0 }
  ' "$YAML" > "${YAML}.tmp"
  mv "${YAML}.tmp" "$YAML"
else
  printf '\nrule-files:\n  - %s\n' "$RULE_FILE" >> "$YAML"
fi

if command -v suricata >/dev/null 2>&1; then
  if [[ $DO_TEST -eq 1 ]]; then
    log "Testing Suricata configuration"
    suricata -T -c "$YAML" >/dev/null
  else
    warn "Skipping suricata -T per --no-test"
  fi
else
  warn "suricata not installed; skipping test"
fi

if [[ $DO_RESTART -eq 1 ]] && command -v systemctl >/dev/null 2>&1; then
  log "Restarting Suricata"
  systemctl restart suricata || systemctl try-restart suricata || true
else
  warn "Skipping restart per --no-restart or missing systemctl"
fi

log "Applied: ${DEFAULT_RULE_PATH}/${RULE_FILE}"
