#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
CC_BIN=${CC:-cc}
PROTOCOL_TEST_BINARY="${TMPDIR:-/tmp}/niwpsptopc-protocol-test-$$"
CONFIG_TEST_BINARY="${TMPDIR:-/tmp}/niwpsptopc-config-test-$$"

cleanup() {
    rm -f "$PROTOCOL_TEST_BINARY" "$CONFIG_TEST_BINARY"
}
trap cleanup EXIT HUP INT TERM

"$CC_BIN" \
    -std=c11 -Wall -Wextra -Werror \
    -I"$PROJECT_ROOT/psp-client/include" \
    "$PROJECT_ROOT/psp-client/src/input_protocol.c" \
    "$PROJECT_ROOT/psp-client/tests/test_input_protocol.c" \
    -o "$PROTOCOL_TEST_BINARY"
"$PROTOCOL_TEST_BINARY"

"$CC_BIN" \
    -std=c11 -Wall -Wextra -Werror \
    -I"$PROJECT_ROOT/psp-client/include" \
    "$PROJECT_ROOT/psp-client/src/config.c" \
    "$PROJECT_ROOT/psp-client/tests/test_config.c" \
    -o "$CONFIG_TEST_BINARY"
"$CONFIG_TEST_BINARY"
