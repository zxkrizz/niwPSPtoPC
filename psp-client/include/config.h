#ifndef NIW_PSP_TO_PC_CONFIG_H
#define NIW_PSP_TO_PC_CONFIG_H

#include <stddef.h>
#include <stdint.h>

#define NIW_PSP_TO_PC_DEFAULT_SERVER_PORT 47999u
#define NIW_PSP_TO_PC_DEFAULT_SEND_RATE 60u
#define NIW_PSP_TO_PC_MIN_SEND_RATE 15u
#define NIW_PSP_TO_PC_MAX_SEND_RATE 60u
#define NIW_PSP_TO_PC_CONFIG_NOT_FOUND 1

typedef struct NiwPspToPcConfig {
    uint16_t server_port;
    uint8_t send_rate;
} NiwPspToPcConfig;

void config_set_defaults(NiwPspToPcConfig *config);
int config_resolve_path(
    const char *eboot_path,
    char *config_path,
    size_t config_path_size);

/*
 * Parses only server_port and send_rate. The PC address is discovered
 * automatically on the local network. Unknown keys, duplicate keys, overlong
 * lines, and values outside their allowed range are rejected.
 * Returns 0 on success, NIW_PSP_TO_PC_CONFIG_NOT_FOUND when the file does not
 * exist and defaults should be used, or a negative ConfigError value.
 */
int config_load(const char *path, NiwPspToPcConfig *config);
const char *config_error_string(int error);

#endif
