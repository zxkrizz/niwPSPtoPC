#!/usr/bin/env bash
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
EBOOT_PATH="$PROJECT_ROOT/psp-client/EBOOT.PBP"
USBHOSTFS_PATH="$PROJECT_ROOT/psp-client/usbhostfs.prx"
DIST_PATH="$PROJECT_ROOT/dist/niwPSPtoPC"

if [ ! -f "$EBOOT_PATH" ] || \
    [ ! -f "$USBHOSTFS_PATH" ] || \
    find "$PROJECT_ROOT/psp-client/src" \
         "$PROJECT_ROOT/psp-client/include" \
         "$PROJECT_ROOT/psp-client/assets" \
         "$PROJECT_ROOT/psp-client/Makefile" \
         -type f -newer "$EBOOT_PATH" -print -quit | grep -q . || \
    find "$PROJECT_ROOT/scripts/build-usbhostfs.sh" \
         "$PROJECT_ROOT/psp-client/vendor/usbhostfs-winusb.patch" \
         -type f -newer "$USBHOSTFS_PATH" -print -quit | grep -q .; then
    echo "PSP package inputs are missing or stale; building them first."
    "$SCRIPT_DIR/build-psp.sh"
fi

mkdir -p "$DIST_PATH"
cp "$EBOOT_PATH" "$DIST_PATH/EBOOT.PBP"
cp "$PROJECT_ROOT/psp-client/config.ini" "$DIST_PATH/config.ini"
cp "$USBHOSTFS_PATH" "$DIST_PATH/usbhostfs.prx"

echo "PSP package ready: $DIST_PATH"
