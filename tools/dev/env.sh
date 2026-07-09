# Azazel-Gadget developer environment (macOS / plain Linux, no Pi hardware).
#
# Source this before launching the dev stack. It redirects every appliance-only
# path (/run/azazel*, control socket, Suricata eve.json) to a writable dev
# directory and turns on dev mode (dry-run, no root, no nft/tc/EPD). Nothing
# here changes appliance behavior — it only sets environment variables that the
# code reads with safe defaults.
#
# Usage:  source tools/dev/env.sh

# Resolve repo root (this file lives in tools/dev/).
_AZG_ENV_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
export AZAZEL_GADGET_ROOT="$(cd "${_AZG_ENV_DIR}/../.." && pwd)"

# All dev state lives here — never under /run, /etc, or /var.
export AZAZEL_DEV_STATE="${AZAZEL_DEV_STATE:-$HOME/.azazel-gadget-dev}"
export AZAZEL_RUNTIME_DIR="${AZAZEL_DEV_STATE}/run"
export AZAZEL_EVE_PATH="${AZAZEL_DEV_STATE}/suricata/eve.json"
export AZAZEL_CONTROL_SOCKET="${AZAZEL_RUNTIME_DIR}/control.sock"

mkdir -p "${AZAZEL_RUNTIME_DIR}" "${AZAZEL_DEV_STATE}/log" "${AZAZEL_DEV_STATE}/suricata"
: > "${AZAZEL_EVE_PATH}" 2>/dev/null || true

# Dev mode: controller skips the root/nft/tc preflight and forces dry-run.
export AZAZEL_GADGET_DEV=1

# Web UI on loopback (never 0.0.0.0 in dev).
export AZAZEL_WEB_HOST="${AZAZEL_WEB_HOST:-127.0.0.1}"
export AZAZEL_WEB_PORT="${AZAZEL_WEB_PORT:-8084}"

# Import path so `python py/...` and the web app find azazel_gadget.
export PYTHONPATH="${AZAZEL_GADGET_ROOT}:${AZAZEL_GADGET_ROOT}/py${PYTHONPATH:+:$PYTHONPATH}"

# No web token in dev -> the UI is open on loopback only (verify_token() passes
# when no token file exists). Set AZAZEL_WEB_TOKEN_FILE to change this.
