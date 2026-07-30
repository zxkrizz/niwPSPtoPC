#ifndef NIW_PSP_TO_PC_UI_H
#define NIW_PSP_TO_PC_UI_H

#include <stdint.h>

void ui_init(void);
void ui_render_startup(const char *pairing_code);
void ui_render_transport_selector(int selected, int wifi_available);
void ui_render_no_profiles(const char *pairing_code);
void ui_render_profile_selector(
    const char *pairing_code,
    const char *profile_name,
    int selected,
    int total);
void ui_render_connecting(
    const char *pairing_code,
    const char *state_name,
    int progress_stage);
void ui_render_reconnecting(
    const char *pairing_code,
    const char *state_name,
    unsigned int attempt,
    unsigned int retry_in_seconds);
void ui_render_sender(
    const char *pairing_code,
    int authorized,
    int network_error,
    unsigned int send_rate,
    int is_usb);
void ui_render_usb_waiting(
    const char *pairing_code,
    unsigned int send_rate,
    uint32_t descriptor_debug);
void ui_render_error(
    const char *pairing_code,
    const char *title,
    const char *message,
    int error);
void ui_render_shutdown(const char *pairing_code);

#endif
