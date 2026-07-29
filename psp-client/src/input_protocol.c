#include "input_protocol.h"

static void write_u16_be(uint8_t *output, uint16_t value)
{
    output[0] = (uint8_t)(value >> 8);
    output[1] = (uint8_t)value;
}

static void write_u32_be(uint8_t *output, uint32_t value)
{
    output[0] = (uint8_t)(value >> 24);
    output[1] = (uint8_t)(value >> 16);
    output[2] = (uint8_t)(value >> 8);
    output[3] = (uint8_t)value;
}

static void write_u64_be(uint8_t *output, uint64_t value)
{
    output[0] = (uint8_t)(value >> 56);
    output[1] = (uint8_t)(value >> 48);
    output[2] = (uint8_t)(value >> 40);
    output[3] = (uint8_t)(value >> 32);
    output[4] = (uint8_t)(value >> 24);
    output[5] = (uint8_t)(value >> 16);
    output[6] = (uint8_t)(value >> 8);
    output[7] = (uint8_t)value;
}

static uint16_t read_u16_be(const uint8_t *input)
{
    return (uint16_t)(((uint16_t)input[0] << 8) | (uint16_t)input[1]);
}

static uint32_t read_u32_be(const uint8_t *input)
{
    return ((uint32_t)input[0] << 24) |
           ((uint32_t)input[1] << 16) |
           ((uint32_t)input[2] << 8) |
           (uint32_t)input[3];
}

void psp_input_encode(
    uint8_t output[PSP_INPUT_PACKET_SIZE],
    const PspInputState *state)
{
    write_u32_be(output + 0, PSP_INPUT_MAGIC);
    write_u16_be(output + 4, PSP_INPUT_VERSION);
    write_u16_be(output + 6, PSP_INPUT_PACKET_SIZE);
    write_u32_be(output + 8, state->sequence);
    write_u32_be(output + 12, state->buttons);
    output[16] = state->analog_x;
    output[17] = state->analog_y;
    write_u16_be(output + 18, 0u);
    write_u32_be(output + 20, state->session_token);
    write_u64_be(output + 24, state->timestamp_us);
}

int psp_pairing_ack_matches(
    const uint8_t input[PSP_PAIRING_ACK_SIZE],
    uint32_t expected_session_token)
{
    return read_u32_be(input + 0) == PSP_PAIRING_ACK_MAGIC &&
           read_u16_be(input + 4) == PSP_PAIRING_ACK_VERSION &&
           read_u16_be(input + 6) == PSP_PAIRING_ACK_SIZE &&
           read_u32_be(input + 8) == expected_session_token;
}
