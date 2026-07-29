#include "config.h"

#include <ctype.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum ConfigError {
    CONFIG_ERROR_OPEN = -1,
    CONFIG_ERROR_LINE_TOO_LONG = -2,
    CONFIG_ERROR_SYNTAX = -3,
    CONFIG_ERROR_UNKNOWN_KEY = -4,
    CONFIG_ERROR_DUPLICATE_KEY = -5,
    CONFIG_ERROR_VALUE = -6,
    CONFIG_ERROR_READ = -7
};

enum ConfigKey {
    CONFIG_KEY_SERVER_PORT = 1u << 0,
    CONFIG_KEY_SEND_RATE = 1u << 1
};

static char *trim(char *text)
{
    char *end;

    while (isspace((unsigned char)*text)) {
        ++text;
    }

    end = text + strlen(text);
    while (end > text && isspace((unsigned char)end[-1])) {
        --end;
    }
    *end = '\0';
    return text;
}

static int parse_unsigned(
    const char *text,
    unsigned long minimum,
    unsigned long maximum,
    unsigned long *result)
{
    char *end = NULL;
    unsigned long value;

    if (*text == '\0' || *text == '-') {
        return -1;
    }

    errno = 0;
    value = strtoul(text, &end, 10);
    if (errno != 0 || end == text || *end != '\0') {
        return -1;
    }
    if (value < minimum || value > maximum) {
        return -1;
    }

    *result = value;
    return 0;
}

void config_set_defaults(NiwPspToPcConfig *config)
{
    memset(config, 0, sizeof(*config));
    config->server_port = (uint16_t)NIW_PSP_TO_PC_DEFAULT_SERVER_PORT;
    config->send_rate = (uint8_t)NIW_PSP_TO_PC_DEFAULT_SEND_RATE;
}

int config_resolve_path(
    const char *eboot_path,
    char *config_path,
    size_t config_path_size)
{
    const char *separator;
    size_t directory_length;
    const char filename[] = "config.ini";

    if (config_path == NULL || config_path_size == 0u) {
        return -1;
    }
    if (eboot_path == NULL || *eboot_path == '\0') {
        if (sizeof(filename) > config_path_size) {
            return -1;
        }
        memcpy(config_path, filename, sizeof(filename));
        return 0;
    }

    separator = strrchr(eboot_path, '/');
    if (separator == NULL) {
        separator = strrchr(eboot_path, '\\');
    }
    directory_length =
        separator == NULL ? 0u : (size_t)(separator - eboot_path) + 1u;
    if (directory_length + sizeof(filename) > config_path_size) {
        return -1;
    }
    if (directory_length > 0u) {
        memcpy(config_path, eboot_path, directory_length);
    }
    memcpy(config_path + directory_length, filename, sizeof(filename));
    return 0;
}

int config_load(const char *path, NiwPspToPcConfig *config)
{
    char line[160];
    unsigned int seen_keys = 0;
    FILE *file = fopen(path, "r");

    if (file == NULL) {
        if (errno == ENOENT) {
            return NIW_PSP_TO_PC_CONFIG_NOT_FOUND;
        }
        return CONFIG_ERROR_OPEN;
    }

    while (fgets(line, sizeof(line), file) != NULL) {
        char *key;
        char *value;
        char *separator;
        size_t length = strlen(line);
        unsigned int key_flag;

        if (length > 0 && line[length - 1] != '\n' && !feof(file)) {
            int character;
            do {
                character = fgetc(file);
            } while (character != '\n' && character != EOF);
            fclose(file);
            return CONFIG_ERROR_LINE_TOO_LONG;
        }

        key = trim(line);
        if (*key == '\0' || *key == '#' || *key == ';') {
            continue;
        }

        separator = strchr(key, '=');
        if (separator == NULL) {
            fclose(file);
            return CONFIG_ERROR_SYNTAX;
        }
        *separator = '\0';
        value = trim(separator + 1);
        key = trim(key);
        if (*key == '\0' || *value == '\0') {
            fclose(file);
            return CONFIG_ERROR_SYNTAX;
        }

        if (strcmp(key, "server_port") == 0) {
            key_flag = CONFIG_KEY_SERVER_PORT;
        } else if (strcmp(key, "send_rate") == 0) {
            key_flag = CONFIG_KEY_SEND_RATE;
        } else {
            fclose(file);
            return CONFIG_ERROR_UNKNOWN_KEY;
        }

        if ((seen_keys & key_flag) != 0) {
            fclose(file);
            return CONFIG_ERROR_DUPLICATE_KEY;
        }
        seen_keys |= key_flag;

        {
            unsigned long number;
            unsigned long maximum =
                key_flag == CONFIG_KEY_SERVER_PORT
                    ? 65535u
                    : NIW_PSP_TO_PC_MAX_SEND_RATE;
            unsigned long minimum =
                key_flag == CONFIG_KEY_SERVER_PORT
                    ? 1u
                    : NIW_PSP_TO_PC_MIN_SEND_RATE;
            if (parse_unsigned(value, minimum, maximum, &number) != 0) {
                fclose(file);
                return CONFIG_ERROR_VALUE;
            }
            if (key_flag == CONFIG_KEY_SERVER_PORT) {
                config->server_port = (uint16_t)number;
            } else {
                config->send_rate = (uint8_t)number;
            }
        }
    }

    if (ferror(file)) {
        fclose(file);
        return CONFIG_ERROR_READ;
    }
    fclose(file);
    return 0;
}

const char *config_error_string(int error)
{
    switch (error) {
    case CONFIG_ERROR_OPEN:
        return "cannot open config.ini";
    case CONFIG_ERROR_LINE_TOO_LONG:
        return "config.ini contains an overlong line";
    case CONFIG_ERROR_SYNTAX:
        return "config.ini has invalid key=value syntax";
    case CONFIG_ERROR_UNKNOWN_KEY:
        return "config.ini contains an unknown key";
    case CONFIG_ERROR_DUPLICATE_KEY:
        return "config.ini contains a duplicate key";
    case CONFIG_ERROR_VALUE:
        return "config.ini contains an invalid value";
    case CONFIG_ERROR_READ:
        return "failed while reading config.ini";
    default:
        return "unknown configuration error";
    }
}
