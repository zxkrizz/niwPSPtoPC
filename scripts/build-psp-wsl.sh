#!/usr/bin/env bash
set -eu

PSPDEV=${PSPDEV:-"$HOME/pspdev"}
EXPECTED_PSPSDK=7ddea00433f8dbef20a6f5d66291cd4b39417689

if [ ! -x "$PSPDEV/bin/psp-config" ] || \
    ! grep -q "pspsdk $EXPECTED_PSPSDK " "$PSPDEV/build.txt"; then
    echo "error: WSL PSPDEV is not the pinned v20260701 toolchain" >&2
    exit 1
fi

export PSPDEV
export PATH="$PSPDEV/bin:$PATH"

./scripts/test-c-protocol.sh
./scripts/build-psp.sh
