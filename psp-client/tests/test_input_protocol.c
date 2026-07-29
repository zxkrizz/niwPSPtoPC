#include "input_protocol.h"

#include <stdint.h>
#include <stdio.h>
#include <string.h>

static const uint8_t GOLDEN_PACKET[PSP_INPUT_PACKET_SIZE] = {
#include "golden_packet_v2.inc"
};

int main(void)
{
    const PspInputState state = {
        0x01020304u,
        0x00000A55u,
        0x7Fu,
        0xC9u,
        0x01234567u,
        UINT64_C(0x0102030405060708)
    };
    uint8_t encoded[PSP_INPUT_PACKET_SIZE];

    psp_input_encode(encoded, &state);
    if (memcmp(encoded, GOLDEN_PACKET, sizeof(encoded)) != 0) {
        fputs("C encoder does not match the v2 golden packet\n", stderr);
        return 1;
    }
    {
        const uint8_t ack[PSP_PAIRING_ACK_SIZE] = {
            0x50, 0x53, 0x50, 0x41, 0x00, 0x01,
            0x00, 0x0C, 0x01, 0x23, 0x45, 0x67
        };
        if (!psp_pairing_ack_matches(ack, state.session_token)) {
            fputs("C decoder rejected the pairing ACK\n", stderr);
            return 1;
        }
        if (psp_pairing_ack_matches(ack, state.session_token + 1u)) {
            fputs("C decoder accepted the wrong pairing token\n", stderr);
            return 1;
        }
    }
    return 0;
}
