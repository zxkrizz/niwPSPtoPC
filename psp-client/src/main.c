#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <kubridge.h>
#include <pspctrl.h>
#include <pspdisplay.h>
#include <pspkernel.h>
#include <pspnet_apctl.h>
#include <psppower.h>
#include <pspsdk.h>
#include <pspthreadman.h>
#include <psputility.h>
#include <pspwlan.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>
#include <systemctrl.h>

#include "config.h"
#include "input_protocol.h"
#include "ui.h"

#define APP_NAME "niwPSPtoPC"
#define MAX_NETWORK_PROFILES 16
#define CONNECTION_TIMEOUT_US (30ULL * 1000ULL * 1000ULL)
#define RECONNECT_ATTEMPT_TIMEOUT_US (8ULL * 1000ULL * 1000ULL)
#define APCTL_STATE_CHECK_INTERVAL_US 250000ULL
#define RECONNECT_BACKOFF_MAX_SECONDS 10U
#define PAIRING_ACK_TIMEOUT_US 2000000ULL
#define DISPLAY_SLEEP_DELAY_US (10ULL * 1000ULL * 1000ULL)
#define MAX_ACK_DATAGRAMS_PER_CYCLE 32U
#define PERFORMANCE_PLL_MHZ 333
#define PERFORMANCE_CPU_MHZ 333
#define PERFORMANCE_BUS_MHZ 166
#define POWER_SAVE_PLL_MHZ 111
#define POWER_SAVE_CPU_MHZ 111
#define POWER_SAVE_BUS_MHZ 55
#define DISPLAY_SET_BRIGHTNESS_NID 0x9E3C6DC6u
#define DISPLAY_GET_BRIGHTNESS_NID 0x31C4BAA8u
#define PAIRING_ALPHABET "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
#define DISCOVERY_IPV4 "255.255.255.255"

PSP_MODULE_INFO(APP_NAME, 0, 1, 0);
PSP_MAIN_THREAD_ATTR(PSP_THREAD_ATTR_USER);
PSP_MAIN_THREAD_STACK_SIZE_KB(256);

/*
 * The PSP exit callback runs on a separate callback thread. This is the only
 * global mutable state: it lets the main thread unwind sockets/network cleanly.
 */
static volatile int g_exit_requested = 0;

typedef struct BacklightControl {
    uint32_t set_brightness_address;
    uint32_t get_brightness_address;
    int saved_brightness;
    int is_off;
} BacklightControl;

static void backlight_init(BacklightControl *backlight)
{
    memset(backlight, 0, sizeof(*backlight));
    backlight->set_brightness_address = sctrlHENFindFunction(
        "sceDisplay_Service",
        "sceDisplay_driver",
        DISPLAY_SET_BRIGHTNESS_NID);
    backlight->get_brightness_address = sctrlHENFindFunction(
        "sceDisplay_Service",
        "sceDisplay_driver",
        DISPLAY_GET_BRIGHTNESS_NID);
}

static int call_display_get_brightness(
    const BacklightControl *backlight,
    int *level)
{
    KernelCallArg args;
    int unknown = 0;

    if (backlight->get_brightness_address == 0) {
        return -1;
    }
    memset(&args, 0, sizeof(args));
    args.arg1 = (uint32_t)(uintptr_t)level;
    args.arg2 = (uint32_t)(uintptr_t)&unknown;
    return kuKernelCall(
        (void *)(uintptr_t)backlight->get_brightness_address,
        &args);
}

static int call_display_set_brightness(
    const BacklightControl *backlight,
    int level)
{
    KernelCallArg args;

    if (backlight->set_brightness_address == 0) {
        return -1;
    }
    memset(&args, 0, sizeof(args));
    args.arg1 = (uint32_t)level;
    args.arg2 = 0;
    return kuKernelCall(
        (void *)(uintptr_t)backlight->set_brightness_address,
        &args);
}

static void backlight_turn_off(BacklightControl *backlight)
{
    int current_brightness = 0;

    if (backlight->is_off) {
        return;
    }
    if (
        call_display_get_brightness(backlight, &current_brightness) < 0 ||
        current_brightness < 1 ||
        current_brightness > 100
    ) {
        return;
    }
    if (call_display_set_brightness(backlight, 0) >= 0) {
        backlight->saved_brightness = current_brightness;
        backlight->is_off = 1;
    }
}

static void backlight_turn_on(BacklightControl *backlight)
{
    if (!backlight->is_off) {
        return;
    }
    if (
        call_display_set_brightness(
            backlight,
            backlight->saved_brightness
        ) >= 0
    ) {
        backlight->is_off = 0;
    }
}

static int set_performance_clock(void)
{
    return scePowerSetClockFrequency(
        PERFORMANCE_PLL_MHZ,
        PERFORMANCE_CPU_MHZ,
        PERFORMANCE_BUS_MHZ);
}

static int set_power_save_clock(void)
{
    return scePowerSetClockFrequency(
        POWER_SAVE_PLL_MHZ,
        POWER_SAVE_CPU_MHZ,
        POWER_SAVE_BUS_MHZ);
}

static uint32_t generate_session_token(void)
{
    uint64_t now = (uint64_t)sceKernelGetSystemTimeWide();
    uint32_t value = (uint32_t)now ^ (uint32_t)(now >> 32) ^ 0x6E697750u;

    /* Xorshift is sufficient for a short-lived LAN pairing code. */
    value ^= value << 13;
    value ^= value >> 17;
    value ^= value << 5;
    return value & PSP_PAIRING_TOKEN_MAX;
}

static void format_session_token(uint32_t token, char output[6])
{
    const char alphabet[] = PAIRING_ALPHABET;
    int index;

    for (index = 4; index >= 0; --index) {
        output[index] = alphabet[token & 0x1Fu];
        token >>= 5;
    }
    output[5] = '\0';
}

static int exit_callback(int arg1, int arg2, void *common)
{
    (void)arg1;
    (void)arg2;
    (void)common;
    g_exit_requested = 1;
    return 0;
}

static int callback_thread(SceSize args, void *argp)
{
    int callback_id;

    (void)args;
    (void)argp;
    callback_id = sceKernelCreateCallback("niwPSPtoPC Exit", exit_callback, NULL);
    if (callback_id >= 0) {
        sceKernelRegisterExitCallback(callback_id);
        sceKernelSleepThreadCB();
    }
    return 0;
}

static int setup_callbacks(void)
{
    int thread_id = sceKernelCreateThread(
        "niwPSPtoPC Callback",
        callback_thread,
        0x11,
        0x1000,
        PSP_THREAD_ATTR_USER,
        NULL);

    if (thread_id < 0) {
        return thread_id;
    }
    if (sceKernelStartThread(thread_id, 0, NULL) < 0) {
        return -1;
    }
    return thread_id;
}

static uint32_t map_buttons(uint32_t psp_buttons)
{
    uint32_t buttons = 0;

    if ((psp_buttons & PSP_CTRL_UP) != 0) {
        buttons |= INPUT_UP;
    }
    if ((psp_buttons & PSP_CTRL_DOWN) != 0) {
        buttons |= INPUT_DOWN;
    }
    if ((psp_buttons & PSP_CTRL_LEFT) != 0) {
        buttons |= INPUT_LEFT;
    }
    if ((psp_buttons & PSP_CTRL_RIGHT) != 0) {
        buttons |= INPUT_RIGHT;
    }
    if ((psp_buttons & PSP_CTRL_CROSS) != 0) {
        buttons |= INPUT_CROSS;
    }
    if ((psp_buttons & PSP_CTRL_CIRCLE) != 0) {
        buttons |= INPUT_CIRCLE;
    }
    if ((psp_buttons & PSP_CTRL_SQUARE) != 0) {
        buttons |= INPUT_SQUARE;
    }
    if ((psp_buttons & PSP_CTRL_TRIANGLE) != 0) {
        buttons |= INPUT_TRIANGLE;
    }
    if ((psp_buttons & PSP_CTRL_LTRIGGER) != 0) {
        buttons |= INPUT_L;
    }
    if ((psp_buttons & PSP_CTRL_RTRIGGER) != 0) {
        buttons |= INPUT_R;
    }
    if ((psp_buttons & PSP_CTRL_START) != 0) {
        buttons |= INPUT_START;
    }
    if ((psp_buttons & PSP_CTRL_SELECT) != 0) {
        buttons |= INPUT_SELECT;
    }
    return buttons;
}

static int sample_sender_controller(SceCtrlData *pad)
{
#ifdef NIW_SENDER_USE_READ
    return sceCtrlReadBufferPositive(pad, 1);
#else
    return sceCtrlPeekBufferPositive(pad, 1);
#endif
}

static int collect_network_profiles(int profiles[MAX_NETWORK_PROFILES])
{
    int profile_id;
    int count = 0;

    /* PSP firmware profile IDs are positive. Scan a bounded range and retain
     * valid IDs so a gap in the saved profile table does not end enumeration. */
    for (profile_id = 1;
         profile_id <= 100 && count < MAX_NETWORK_PROFILES;
         ++profile_id) {
        if (sceUtilityCheckNetParam(profile_id) == 0) {
            profiles[count++] = profile_id;
        }
    }
    return count;
}

static const char *network_profile_name(int profile_id, char name[128])
{
    netData data;
    memset(&data, 0, sizeof(data));
    if (sceUtilityGetNetParam(profile_id, PSP_NETPARAM_NAME, &data) < 0) {
        strcpy(name, "(name unavailable)");
    } else {
        memcpy(name, data.asString, 127);
        name[127] = '\0';
    }
    return name;
}

static int select_network_profile(const char *pairing_code)
{
    int profiles[MAX_NETWORK_PROFILES];
    int profile_count = collect_network_profiles(profiles);
    int selected = 0;
    int redraw = 1;
    SceCtrlData pad;
    uint32_t previous_buttons = 0;
    char profile_name[128];

    if (profile_count == 0) {
        ui_render_no_profiles(pairing_code);
        while (!g_exit_requested) {
            sceKernelDelayThread(100000);
        }
        return -1;
    }

    while (!g_exit_requested) {
        uint32_t pressed;
        int read_count;

        if (redraw) {
            network_profile_name(profiles[selected], profile_name);
            ui_render_profile_selector(
                pairing_code,
                profile_name,
                selected,
                profile_count);
            redraw = 0;
        }

        read_count = sceCtrlReadBufferPositive(&pad, 1);
        if (read_count > 0) {
            pressed = pad.Buttons & ~previous_buttons;
            previous_buttons = pad.Buttons;
            if ((pressed & PSP_CTRL_LEFT) != 0) {
                selected = (selected + profile_count - 1) % profile_count;
                redraw = 1;
            } else if ((pressed & PSP_CTRL_RIGHT) != 0) {
                selected = (selected + 1) % profile_count;
                redraw = 1;
            }
            if ((pressed & PSP_CTRL_CROSS) != 0) {
                return profiles[selected];
            }
        }
        sceDisplayWaitVblankStart();
    }
    return -1;
}

static const char *apctl_state_name(int state)
{
    switch (state) {
    case PSP_NET_APCTL_STATE_DISCONNECTED:
        return "disconnected";
    case PSP_NET_APCTL_STATE_SCANNING:
        return "scanning";
    case PSP_NET_APCTL_STATE_JOINING:
        return "joining";
    case PSP_NET_APCTL_STATE_GETTING_IP:
        return "getting IP";
    case PSP_NET_APCTL_STATE_GOT_IP:
        return "connected";
    case PSP_NET_APCTL_STATE_EAP_AUTH:
        return "EAP authentication";
    case PSP_NET_APCTL_STATE_KEY_EXCHANGE:
        return "key exchange";
    default:
        return "unknown";
    }
}

static int connect_wifi(
    int profile_id,
    const char *pairing_code,
    char local_ip[16],
    int *last_error,
    uint64_t timeout_us,
    unsigned int reconnect_attempt)
{
    uint64_t start_time;
    int previous_state = -1;
    int result = sceNetApctlConnect(profile_id);

    if (result < 0) {
        *last_error = result;
        return -1;
    }

    start_time = (uint64_t)sceKernelGetSystemTimeWide();
    while (!g_exit_requested) {
        uint64_t now;
        int state = PSP_NET_APCTL_STATE_DISCONNECTED;

        result = sceNetApctlGetState(&state);
        if (result < 0) {
            *last_error = result;
            return -1;
        }

        if (state != previous_state) {
            if (reconnect_attempt > 0) {
                ui_render_reconnecting(
                    pairing_code,
                    apctl_state_name(state),
                    reconnect_attempt,
                    0);
            } else {
                ui_render_connecting(
                    pairing_code,
                    apctl_state_name(state),
                    state);
            }
            previous_state = state;
        }
        if (state == PSP_NET_APCTL_STATE_GOT_IP) {
            union SceNetApctlInfo info;
            memset(&info, 0, sizeof(info));
            if (sceNetApctlGetInfo(PSP_NET_APCTL_INFO_IP, &info) < 0) {
                strcpy(local_ip, "unknown");
            } else {
                memcpy(local_ip, info.ip, 15);
                local_ip[15] = '\0';
            }
            return 0;
        }

        now = (uint64_t)sceKernelGetSystemTimeWide();
        if (now - start_time >= timeout_us) {
            *last_error = -1;
            return -1;
        }
        sceKernelDelayThread(50000);
    }
    return -1;
}

static int create_udp_socket(
    const NiwPspToPcConfig *config,
    int *socket_fd,
    struct sockaddr_in *server_address)
{
    int broadcast_enabled = 1;

    memset(server_address, 0, sizeof(*server_address));
    server_address->sin_family = AF_INET;
    server_address->sin_port = htons(config->server_port);
    if (inet_pton(
            AF_INET,
            DISCOVERY_IPV4,
            &server_address->sin_addr) != 1) {
        return -1;
    }

    *socket_fd = socket(AF_INET, SOCK_DGRAM, 0);
    if (*socket_fd < 0) {
        return -2;
    }
    if (setsockopt(
            *socket_fd,
            SOL_SOCKET,
            SO_BROADCAST,
            &broadcast_enabled,
            sizeof(broadcast_enabled)) < 0) {
        close(*socket_fd);
        *socket_fd = -1;
        return -3;
    }
    {
        int flags = fcntl(*socket_fd, F_GETFL, 0);
        if (flags < 0 || fcntl(*socket_fd, F_SETFL, flags | O_NONBLOCK) < 0) {
            close(*socket_fd);
            *socket_fd = -1;
            return -4;
        }
    }
    return 0;
}

static void reset_pc_discovery(struct sockaddr_in *server_address)
{
    inet_pton(
        AF_INET,
        DISCOVERY_IPV4,
        &server_address->sin_addr);
}

static void render_sender_status(
    const char *pairing_code,
    int authorized,
    int network_error,
    unsigned int send_rate)
{
    ui_render_sender(pairing_code, authorized, network_error, send_rate);
}

static int wait_for_reconnect_backoff(
    const char *pairing_code,
    unsigned int attempt,
    unsigned int seconds)
{
    unsigned int remaining;

    for (remaining = seconds; remaining > 0 && !g_exit_requested; --remaining) {
        unsigned int slice;
        ui_render_reconnecting(
            pairing_code,
            "ACCESS POINT NOT AVAILABLE",
            attempt,
            remaining);
        for (slice = 0; slice < 10 && !g_exit_requested; ++slice) {
            sceKernelDelayThread(100000);
        }
    }
    return g_exit_requested ? -1 : 0;
}

static int reconnect_wifi_and_socket(
    int profile_id,
    const char *pairing_code,
    char local_ip[16],
    const NiwPspToPcConfig *config,
    int *socket_fd,
    struct sockaddr_in *server_address,
    int *last_error)
{
    unsigned int attempt = 1;
    unsigned int backoff_seconds = 1;

    if (*socket_fd >= 0) {
        close(*socket_fd);
        *socket_fd = -1;
    }
    sceNetApctlDisconnect();

    while (!g_exit_requested) {
        if (
            wait_for_reconnect_backoff(
                pairing_code,
                attempt,
                backoff_seconds
            ) < 0
        ) {
            return -1;
        }

        /*
         * APCTL can retain a half-open association after an access point
         * disappears. Start every attempt from a known disconnected state.
         */
        sceNetApctlDisconnect();
        sceKernelDelayThread(100000);
        if (
            connect_wifi(
                profile_id,
                pairing_code,
                local_ip,
                last_error,
                RECONNECT_ATTEMPT_TIMEOUT_US,
                attempt
            ) == 0
        ) {
            *last_error = create_udp_socket(
                config,
                socket_fd,
                server_address);
            if (*last_error == 0) {
                return 0;
            }
            sceNetApctlDisconnect();
        }

        ++attempt;
        if (backoff_seconds < RECONNECT_BACKOFF_MAX_SECONDS) {
            backoff_seconds *= 2;
            if (backoff_seconds > RECONNECT_BACKOFF_MAX_SECONDS) {
                backoff_seconds = RECONNECT_BACKOFF_MAX_SECONDS;
            }
        }
    }
    return -1;
}

static void run_controller_sender(
    int *socket_fd,
    struct sockaddr_in *server_address,
    const NiwPspToPcConfig *config,
    int profile_id,
    char local_ip[16],
    uint32_t session_token,
    const char *pairing_code,
    BacklightControl *backlight)
{
    uint8_t packet_buffer[PSP_INPUT_PACKET_SIZE];
    uint8_t ack_buffer[PSP_PAIRING_ACK_SIZE];
    PspInputState input;
    SceCtrlData pad;
    uint32_t sequence = 0;
    uint64_t period_us =
        (1000000ULL + (uint64_t)config->send_rate - 1ULL) /
        (uint64_t)config->send_rate;
    uint64_t next_send = (uint64_t)sceKernelGetSystemTimeWide();
    uint64_t next_apctl_check = next_send;
    uint64_t last_pairing_ack = 0;
    uint64_t display_sleep_due = 0;
    int authorized = 0;
    int last_network_error = 0;
    int rendered_authorized = -1;
    int rendered_network_error = -1;

    memset(&input, 0, sizeof(input));
    memset(&pad, 0, sizeof(pad));

    while (!g_exit_requested) {
        uint64_t now = (uint64_t)sceKernelGetSystemTimeWide();
        ssize_t bytes_sent;

        if (now >= next_apctl_check) {
            int apctl_state = PSP_NET_APCTL_STATE_DISCONNECTED;
            int apctl_result = sceNetApctlGetState(&apctl_state);

            next_apctl_check = now + APCTL_STATE_CHECK_INTERVAL_US;
            if (
                apctl_result < 0 ||
                apctl_state != PSP_NET_APCTL_STATE_GOT_IP
            ) {
                backlight_turn_on(backlight);
                /*
                 * Reconnection and discovery are short-lived and benefit from
                 * the full clock. A failed clock change is non-fatal; the
                 * current firmware-selected profile remains usable.
                 */
                set_performance_clock();
                last_network_error =
                    apctl_result < 0 ? apctl_result : apctl_state;
                authorized = 0;
                last_pairing_ack = 0;
                reset_pc_discovery(server_address);
                if (
                    reconnect_wifi_and_socket(
                        profile_id,
                        pairing_code,
                        local_ip,
                        config,
                        socket_fd,
                        server_address,
                        &last_network_error
                    ) < 0
                ) {
                    return;
                }
                now = (uint64_t)sceKernelGetSystemTimeWide();
                next_send = now;
                next_apctl_check =
                    now + APCTL_STATE_CHECK_INTERVAL_US;
                last_network_error = 0;
                rendered_authorized = -1;
                rendered_network_error = -1;
            }
        }

        if (now < next_send) {
            sceKernelDelayThread((SceUInt)(next_send - now));
            continue;
        }

        if (sample_sender_controller(&pad) <= 0) {
            last_network_error = -3;
        } else {
            if (
                backlight->is_off &&
                (pad.Buttons & (PSP_CTRL_HOME | PSP_CTRL_SCREEN)) != 0
            ) {
                backlight_turn_on(backlight);
                display_sleep_due = now + DISPLAY_SLEEP_DELAY_US;
            }
            input.sequence = sequence;
            input.buttons = map_buttons(pad.Buttons);
            input.analog_x = pad.Lx;
            input.analog_y = pad.Ly;
            input.session_token = session_token;
            input.timestamp_us = now;
            psp_input_encode(packet_buffer, &input);

            bytes_sent = sendto(
                *socket_fd,
                packet_buffer,
                sizeof(packet_buffer),
                0,
                (const struct sockaddr *)server_address,
                sizeof(*server_address));
            ++sequence; /* uint32 wrap is intentional and protocol-defined. */

            if (bytes_sent == (ssize_t)sizeof(packet_buffer)) {
                last_network_error = 0;
            } else {
                last_network_error = bytes_sent < 0 ? errno : -2;
            }
        }

        {
            unsigned int ack_count;

            /*
             * Bound receive work so a UDP flood cannot trap the sender in the
             * nonblocking drain loop and keep the PSP continuously busy.
             */
            for (
                ack_count = 0;
                ack_count < MAX_ACK_DATAGRAMS_PER_CYCLE;
                ++ack_count
            ) {
                struct sockaddr_in ack_address;
                socklen_t ack_address_size = sizeof(ack_address);
                ssize_t bytes_received;

                memset(&ack_address, 0, sizeof(ack_address));
                bytes_received = recvfrom(
                    *socket_fd,
                    ack_buffer,
                    sizeof(ack_buffer),
                    0,
                    (struct sockaddr *)&ack_address,
                    &ack_address_size);
                if (bytes_received <= 0) {
                    break;
                }
                if (bytes_received == (ssize_t)sizeof(ack_buffer) &&
                    ack_address.sin_port == htons(config->server_port) &&
                    (
                        server_address->sin_addr.s_addr ==
                            htonl(INADDR_BROADCAST) ||
                        ack_address.sin_addr.s_addr ==
                            server_address->sin_addr.s_addr
                    ) &&
                    psp_pairing_ack_matches(ack_buffer, session_token)) {
                    /*
                     * Before pairing the destination is the limited broadcast
                     * address. The ACK source identifies the receiver PC and
                     * becomes the unicast destination for subsequent input.
                     */
                    server_address->sin_addr = ack_address.sin_addr;
                    last_pairing_ack = now;
                    if (!authorized) {
                        /*
                         * The steady-state 60 Hz sender is lightweight. Drop to
                         * a standard 111/55 MHz profile after authentication to
                         * reduce heat and battery drain.
                         */
                        set_power_save_clock();
                        display_sleep_due = now + DISPLAY_SLEEP_DELAY_US;
                    }
                    authorized = 1;
                }
            }
        }
        if (authorized &&
            now - last_pairing_ack > PAIRING_ACK_TIMEOUT_US) {
            backlight_turn_on(backlight);
            set_performance_clock();
            authorized = 0;
            display_sleep_due = 0;
            reset_pc_discovery(server_address);
        }
        if (
            authorized &&
            display_sleep_due != 0 &&
            now >= display_sleep_due
        ) {
            backlight_turn_off(backlight);
            display_sleep_due = 0;
        }

        next_send += period_us;
        now = (uint64_t)sceKernelGetSystemTimeWide();
        if (now > next_send + period_us * 4ULL) {
            /* Do not burst packets after a long scheduler pause. */
            next_send = now + period_us;
        }
        if (
            authorized != rendered_authorized ||
            last_network_error != rendered_network_error
        ) {
            render_sender_status(
                pairing_code,
                authorized,
                last_network_error,
                config->send_rate);
            rendered_authorized = authorized;
            rendered_network_error = last_network_error;
        }
    }
}

static void show_fatal_error(
    const char *pairing_code,
    const char *message,
    int error)
{
    ui_render_error(pairing_code, "STARTUP ERROR", message, error);
    sceKernelDelayThread(3000000);
}

int main(int argc, char *argv[])
{
    NiwPspToPcConfig config;
    struct sockaddr_in server_address;
    char local_ip[16] = "unknown";
    int callback_thread_id;
    int profile_id = -1;
    int socket_fd = -1;
    int common_module_loaded = 0;
    int inet_module_loaded = 0;
    int inet_initialized = 0;
    int wifi_connected = 0;
    int error = 0;
    uint32_t session_token;
    char pairing_code[6];
    char config_path[256];
    BacklightControl backlight;

    backlight_init(&backlight);
    ui_init();
    session_token = generate_session_token();
    format_session_token(session_token, pairing_code);
    ui_render_startup(pairing_code);

    callback_thread_id = setup_callbacks();
    if (callback_thread_id < 0) {
        show_fatal_error(
            pairing_code,
            "Could not register HOME callback",
            callback_thread_id);
        sceKernelExitGame();
        return 1;
    }

    error = set_performance_clock();
    if (error != 0) {
        show_fatal_error(
            pairing_code,
            "Could not set CPU clock to 333 MHz",
            error);
        sceKernelExitGame();
        return 1;
    }

    config_set_defaults(&config);
    if (
        config_resolve_path(
            argc > 0 ? argv[0] : NULL,
            config_path,
            sizeof(config_path)
        ) != 0
    ) {
        show_fatal_error(
            pairing_code,
            "Could not resolve config.ini path",
            -1);
        sceKernelExitGame();
        return 1;
    }
    error = config_load(config_path, &config);
    if (error < 0) {
        show_fatal_error(
            pairing_code,
            config_error_string(error),
            error);
        sceKernelExitGame();
        return 1;
    }

    error = sceCtrlSetSamplingCycle(0);
    if (error < 0) {
        show_fatal_error(
            pairing_code,
            "Controller sampling setup failed",
            error);
        sceKernelExitGame();
        return 1;
    }
    error = sceCtrlSetSamplingMode(PSP_CTRL_MODE_ANALOG);
    if (error < 0) {
        show_fatal_error(
            pairing_code,
            "Analog controller mode failed",
            error);
        sceKernelExitGame();
        return 1;
    }

    if (sceWlanGetSwitchState() == 0) {
        show_fatal_error(
            pairing_code,
            "WLAN unavailable/off; PSP Street is unsupported",
            0);
        sceKernelExitGame();
        return 1;
    }

    error = sceUtilityLoadNetModule(PSP_NET_MODULE_COMMON);
    if (error < 0) {
        show_fatal_error(
            pairing_code,
            "Could not load network module",
            error);
        goto cleanup;
    }
    common_module_loaded = 1;

    error = sceUtilityLoadNetModule(PSP_NET_MODULE_INET);
    if (error < 0) {
        show_fatal_error(
            pairing_code,
            "Could not load internet module",
            error);
        goto cleanup;
    }
    inet_module_loaded = 1;

    profile_id = select_network_profile(pairing_code);
    if (profile_id < 0 || g_exit_requested) {
        goto cleanup;
    }

    ui_render_connecting(pairing_code, "INITIALIZING", 0);

    error = pspSdkInetInit();
    if (error != 0) {
        show_fatal_error(
            pairing_code,
            "Internet subsystem init failed",
            error);
        goto cleanup;
    }
    inet_initialized = 1;

    if (
        connect_wifi(
            profile_id,
            pairing_code,
            local_ip,
            &error,
            CONNECTION_TIMEOUT_US,
            0
        ) < 0
    ) {
        if (!g_exit_requested) {
            show_fatal_error(
                pairing_code,
                "Wi-Fi connection failed or timed out",
                error);
        }
        goto cleanup;
    }
    wifi_connected = 1;

    error = create_udp_socket(
        &config,
        &socket_fd,
        &server_address);
    if (error < 0) {
        show_fatal_error(
            pairing_code,
            "Server address or UDP socket error",
            error);
        goto cleanup;
    }

    run_controller_sender(
        &socket_fd,
        &server_address,
        &config,
        profile_id,
        local_ip,
        session_token,
        pairing_code,
        &backlight);

cleanup:
    backlight_turn_on(&backlight);
    ui_render_shutdown(pairing_code);
    if (socket_fd >= 0) {
        close(socket_fd);
    }
    if (wifi_connected) {
        sceNetApctlDisconnect();
    }
    if (inet_initialized) {
        pspSdkInetTerm();
    }
    if (inet_module_loaded) {
        sceUtilityUnloadNetModule(PSP_NET_MODULE_INET);
    }
    if (common_module_loaded) {
        sceUtilityUnloadNetModule(PSP_NET_MODULE_COMMON);
    }

    sceKernelExitGame();
    return 0;
}
