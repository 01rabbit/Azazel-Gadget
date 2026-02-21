#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="${TMPDIR:-/tmp}/azazel-ui-smoke"
mkdir -p "$TMP_DIR"

TEXTUAL_LOG="$TMP_DIR/textual.log"
MENU_LOG="$TMP_DIR/menu.log"
CURSES_LOG="$TMP_DIR/curses.log"

echo "[1/4] textual monitor smoke"
timeout 6s script -q -c 'python3 py/azazel_gadget/cli_unified.py --textual --disable-epd' "$TEXTUAL_LOG" >/dev/null 2>&1 || true

echo "[2/4] menu launcher smoke"
timeout 6s script -q -c 'python3 py/azazel_menu.py --textual --disable-epd' "$MENU_LOG" >/dev/null 2>&1 || true

echo "[3/4] curses fallback smoke"
timeout 6s script -q -c 'python3 py/azazel_gadget/cli_unified.py --curses --disable-epd' "$CURSES_LOG" >/dev/null 2>&1 || true

echo "[4/4] control-plane snapshot query smoke"
python3 - <<'PY'
import sys
from pathlib import Path
repo = Path.cwd()
sys.path.insert(0, str(repo / "py"))
from azazel_gadget.control_plane import read_snapshot_payload
payload, source = read_snapshot_payload(prefer_control_plane=True)
print(f"source={source}")
if payload is None:
    raise SystemExit("snapshot payload not available")
PY

if rg -n "Traceback|MarkupError|_curses\\.error|Exception" "$TEXTUAL_LOG" "$MENU_LOG" "$CURSES_LOG" >/dev/null; then
  echo "UI smoke failed: exception pattern detected"
  rg -n "Traceback|MarkupError|_curses\\.error|Exception" "$TEXTUAL_LOG" "$MENU_LOG" "$CURSES_LOG" || true
  exit 1
fi

echo "UI stack smoke passed."
