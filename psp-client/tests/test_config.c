#define _POSIX_C_SOURCE 200809L

#include "config.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static int write_config(const char *path, const char *contents)
{
    FILE *file = fopen(path, "w");
    if (file == NULL) {
        return -1;
    }
    if (fputs(contents, file) == EOF || fclose(file) != 0) {
        return -1;
    }
    return 0;
}

int main(void)
{
    char path[] = "/tmp/niwpsptopc-config-XXXXXX";
    char resolved[128];
    NiwPspToPcConfig config;
    int file_descriptor = mkstemp(path);

    if (file_descriptor < 0) {
        fputs("Could not create temporary config file\n", stderr);
        return 1;
    }
    close(file_descriptor);

    config_set_defaults(&config);
    if (config.server_port != NIW_PSP_TO_PC_DEFAULT_SERVER_PORT ||
        config.send_rate != NIW_PSP_TO_PC_DEFAULT_SEND_RATE) {
        fputs("Unexpected configuration defaults\n", stderr);
        unlink(path);
        return 1;
    }

    if (config_resolve_path(
            "ms0:/PSP/GAME/niwPSPtoPC/EBOOT.PBP",
            resolved,
            sizeof(resolved)) != 0 ||
        strcmp(resolved, "ms0:/PSP/GAME/niwPSPtoPC/config.ini") != 0 ||
        config_resolve_path(
            "ef0:/PSP/GAME/niwPSPtoPC/EBOOT.PBP",
            resolved,
            sizeof(resolved)) != 0 ||
        strcmp(resolved, "ef0:/PSP/GAME/niwPSPtoPC/config.ini") != 0) {
        fputs("EBOOT-relative config path resolution failed\n", stderr);
        unlink(path);
        return 1;
    }

    if (config_load("/tmp/niwpsptopc-definitely-missing.ini", &config) !=
        NIW_PSP_TO_PC_CONFIG_NOT_FOUND) {
        fputs("Missing config did not preserve defaults\n", stderr);
        unlink(path);
        return 1;
    }

    if (write_config(path, "server_port=48000\nsend_rate=30\n") != 0 ||
        config_load(path, &config) != 0 ||
        config.server_port != 48000u ||
        config.send_rate != 30u) {
        fputs("Automatic-discovery configuration was not parsed\n", stderr);
        unlink(path);
        return 1;
    }

    if (write_config(path, "send_rate=14\n") != 0 ||
        config_load(path, &config) >= 0) {
        fputs("Unsafe send rate below 15 Hz was accepted\n", stderr);
        unlink(path);
        return 1;
    }

    if (write_config(
            path,
            "server_ip=192.168.1.100\nserver_port=47999\nsend_rate=60\n"
        ) != 0 ||
        config_load(path, &config) >= 0) {
        fputs("Legacy manual server_ip setting was unexpectedly accepted\n", stderr);
        unlink(path);
        return 1;
    }

    unlink(path);
    return 0;
}
