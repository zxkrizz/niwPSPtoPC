#!/usr/bin/env bash
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)

if [ -z "${PSPDEV:-}" ]; then
    echo "error: PSPDEV is not set (example: export PSPDEV=/usr/local/pspdev)" >&2
    exit 1
fi

if [ ! -d "$PSPDEV" ]; then
    echo "error: PSPDEV does not point to a directory: $PSPDEV" >&2
    exit 1
fi

case ":$PATH:" in
    *":$PSPDEV/bin:"*) ;;
    *)
        echo "error: PSPDEV/bin is not present in PATH" >&2
        echo "       export PATH=\"\$PSPDEV/bin:\$PATH\"" >&2
        exit 1
        ;;
esac

if ! command -v psp-config >/dev/null 2>&1; then
    echo "error: psp-config was not found in PATH" >&2
    exit 1
fi
if ! command -v make >/dev/null 2>&1; then
    echo "error: GNU make was not found in PATH" >&2
    exit 1
fi

PSPSDK_PATH=$(psp-config --pspsdk-path)
if [ ! -f "$PSPSDK_PATH/lib/build.mak" ]; then
    echo "error: PSPSDK build.mak was not found under: $PSPSDK_PATH" >&2
    exit 1
fi

bash "$SCRIPT_DIR/build-usbhostfs.sh"
make -C "$PROJECT_ROOT/psp-client" all

if [ ! -f "$PROJECT_ROOT/psp-client/EBOOT.PBP" ]; then
    echo "error: build completed without psp-client/EBOOT.PBP" >&2
    exit 1
fi

echo "PSP build ready: $PROJECT_ROOT/psp-client/EBOOT.PBP"
