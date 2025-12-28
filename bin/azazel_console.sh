#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Avoid root tmux socket confusion (sudo -> /tmp/tmux-0). Re-exec as invoking user if run with sudo.
if [ "$(id -u)" -eq 0 ]; then
  if [ -n "${SUDO_USER:-}" ]; then
    exec sudo -u "$SUDO_USER" -E "$0" "$@"
  else
    echo "Please run without sudo (tmux should run as the login user)" >&2
    exit 1
  fi
fi

# 共通設定の読込（存在しなくても続行）
[ -f /etc/default/azazel-zero ] && . /etc/default/azazel-zero || true
AZAZEL_ROOT="${AZAZEL_ROOT:-$DEFAULT_ROOT}"

SESSION="azazel"
MENU="python3 ${AZAZEL_ROOT}/py/azazel_menu.py"
STATUS="python3 ${AZAZEL_ROOT}/py/azazel_status.py"

if ! command -v tmux >/dev/null 2>&1; then
  echo "tmux not found; please install tmux." >&2
  exit 1
fi

if [ ! -f "${AZAZEL_ROOT}/py/azazel_menu.py" ] || [ ! -f "${AZAZEL_ROOT}/py/azazel_status.py" ]; then
  echo "menu/status scripts not found under ${AZAZEL_ROOT}/py" >&2
  exit 1
fi

# Ensure environment variables for curses/emoji
export TERM=xterm-256color
: "${LANG:=C.UTF-8}"
: "${LC_ALL:=$LANG}"
: "${LC_CTYPE:=$LANG}"
export LANG LC_ALL LC_CTYPE

# Safe HOME and PATH for systemd environments
: "${HOME:=/home/azazel}"
export HOME
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:$PATH"

# Ensure tmux server, then create or replace the session idempotently
set +e
tmux start-server
tmux has-session -t "$SESSION" 2>/dev/null
HAS=$?
if [ "$HAS" -ne 0 ]; then
  # Create session with top pane running the status renderer
  CMD_STATUS="bash -lc \"$STATUS; exec bash -l\""
  tmux new-session -Ad -s "$SESSION" -n status "$CMD_STATUS"
  RC=$?
  if [ "$RC" -eq 0 ]; then
    # Split vertically and run the menu in the bottom pane (70% height)
    CMD_MENU="bash -lc \"$MENU; exec bash -l\""
    tmux split-window -v -p 80 -t "$SESSION":0 "$CMD_MENU"
    # Focus the bottom (menu) pane for interaction
    tmux select-pane -t "$SESSION":0.1 2>/dev/null || true
  fi
else
  RC=0
fi
set -e

if [ "${RC:-1}" -eq 0 ]; then
  # Best-effort session configuration; never fail hard here
  tmux set-option   -t "$SESSION" status off               2>/dev/null || true
  tmux set-option   -t "$SESSION" -g escape-time 0          2>/dev/null || true
  tmux bind-key     -t "$SESSION" -n C-q  detach-client     2>/dev/null || true
  tmux bind-key     -t "$SESSION" -n F12 detach-client      2>/dev/null || true
  # Keep the server/session alive and panes visible even if commands exit
  tmux set-option   -g exit-empty off                     2>/dev/null || true
  tmux set-option   -t "$SESSION" remain-on-exit on       2>/dev/null || true
  tmux set-option   -g detach-on-destroy off              2>/dev/null || true
  tmux set-environment -t "$SESSION" TERM "$TERM"          2>/dev/null || true
  tmux set-environment -t "$SESSION" LANG "$LANG"          2>/dev/null || true
  tmux set-environment -t "$SESSION" LC_CTYPE "$LC_CTYPE"  2>/dev/null || true
  tmux set-hook -t "$SESSION" after-select-window "run-shell -b '/usr/local/bin/update_epaper_tmux.sh'" 2>/dev/null || true
  tmux select-pane -t "$SESSION":0.1 2>/dev/null || true
fi
