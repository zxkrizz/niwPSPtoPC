#ifndef NIW_PSP_TO_PC_INPUT_PROTOCOL_H
#define NIW_PSP_TO_PC_INPUT_PROTOCOL_H

#include <stdint.h>

#define PSP_INPUT_MAGIC 0x50535049u
#define PSP_INPUT_VERSION 2u
#define PSP_INPUT_PACKET_SIZE 32u
#define PSP_PAIRING_TOKEN_MAX 0x01FFFFFFu

#define PSP_PAIRING_ACK_MAGIC 0x50535041u
#define PSP_PAIRING_ACK_VERSION 1u
#define PSP_PAIRING_ACK_SIZE 12u

/* Stable wire-level button bits. They intentionally do not expose PSPSDK ABI. */
#define INPUT_UP       (1u << 0)
#define INPUT_DOWN     (1u << 1)
#define INPUT_LEFT     (1u << 2)
#define INPUT_RIGHT    (1u << 3)
#define INPUT_CROSS    (1u << 4)
#define INPUT_CIRCLE   (1u << 5)
#define INPUT_SQUARE   (1u << 6)
#define INPUT_TRIANGLE (1u << 7)
#define INPUT_L        (1u << 8)
#define INPUT_R        (1u << 9)
#define INPUT_START    (1u << 10)
#define INPUT_SELECT   (1u << 11)

typedef struct PspInputState {
    uint32_t sequence;
    uint32_t buttons;
    uint8_t analog_x;
    uint8_t analog_y;
    uint32_t session_token;
    uint64_t timestamp_us;
} PspInputState;

/*
 * Serializes explicitly instead of casting a packed C structure. This makes
 * alignment and byte order deterministic on Allegrex and future platforms.
 */
void psp_input_encode(
    uint8_t output[PSP_INPUT_PACKET_SIZE],
    const PspInputState *state);

int psp_pairing_ack_matches(
    const uint8_t input[PSP_PAIRING_ACK_SIZE],
    uint32_t expected_session_token);

#endif
