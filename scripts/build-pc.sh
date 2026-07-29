#!/usr/bin/env bash
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
PYTHON_BIN=${PYTHON_BIN:-python3}

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "error: Python executable not found: $PYTHON_BIN" >&2
    exit 1
fi

"$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else "Python 3.12 or newer is required")'
"$PYTHON_BIN" -m compileall -q "$PROJECT_ROOT/pc-server/pc_server"

(
    cd "$PROJECT_ROOT/pc-server"
    "$PYTHON_BIN" -m unittest discover -s tests -v
)

if command -v "${CC:-cc}" >/dev/null 2>&1; then
    sh "$PROJECT_ROOT/scripts/test-c-protocol.sh"
else
    echo "warning: C compiler not found; Python still verified the shared golden fixture" >&2
fi

echo "PC receiver checks passed."
