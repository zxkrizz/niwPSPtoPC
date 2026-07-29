#!/usr/bin/env bash
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
EBOOT_PATH="$PROJECT_ROOT/psp-client/EBOOT.PBP"
DIST_PATH="$PROJECT_ROOT/dist/niwPSPtoPC"

if [ ! -f "$EBOOT_PATH" ] || \
    find "$PROJECT_ROOT/psp-client/src" \
         "$PROJECT_ROOT/psp-client/include" \
         "$PROJECT_ROOT/psp-client/assets" \
         "$PROJECT_ROOT/psp-client/Makefile" \
         -type f -newer "$EBOOT_PATH" -print -quit | grep -q .; then
    echo "EBOOT.PBP is missing or stale; building the PSP client first."
    "$SCRIPT_DIR/build-psp.sh"
fi

mkdir -p "$DIST_PATH"
cp "$EBOOT_PATH" "$DIST_PATH/EBOOT.PBP"
cp "$PROJECT_ROOT/psp-client/config.ini" "$DIST_PATH/config.ini"

echo "PSP package ready: $DIST_PATH"
