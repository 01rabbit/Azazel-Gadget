#!/bin/bash
# Reboot wrapper that delegates to the common safe power transition.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMMON_SCRIPT="${SCRIPT_DIR}/power_transition.sh"

if [[ ! -x "${COMMON_SCRIPT}" ]]; then
    echo "Common power script not executable: ${COMMON_SCRIPT}" >&2
    exit 1
fi

"${COMMON_SCRIPT}" reboot
