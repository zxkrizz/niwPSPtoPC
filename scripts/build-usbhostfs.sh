#!/usr/bin/env bash
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
OUTPUT="$PROJECT_ROOT/psp-client/usbhostfs.prx"
REVISION=8cc9876a868d202c0ef4197395c5278aeeff2829
SOURCE_URL=https://github.com/pspdev/psplinkusb.git
BUILD_DIR=$(mktemp -d)

cleanup()
{
    rm -rf "$BUILD_DIR"
}
trap cleanup EXIT INT TERM

git -C "$BUILD_DIR" init --quiet
git -C "$BUILD_DIR" remote add origin "$SOURCE_URL"
git -C "$BUILD_DIR" fetch --quiet --depth 1 origin "$REVISION"
git -C "$BUILD_DIR" checkout --quiet --detach FETCH_HEAD

if [ "$(git -C "$BUILD_DIR" rev-parse HEAD)" != "$REVISION" ]; then
    echo "error: PSPLink/USBHostFS revision verification failed" >&2
    exit 1
fi

git -C "$BUILD_DIR" apply --recount \
    "$PROJECT_ROOT/psp-client/vendor/usbhostfs-winusb.patch"
make -C "$BUILD_DIR/usbhostfs" clean all
cp "$BUILD_DIR/usbhostfs/usbhostfs.prx" "$OUTPUT"
echo "USBHostFS module ready: $OUTPUT"
