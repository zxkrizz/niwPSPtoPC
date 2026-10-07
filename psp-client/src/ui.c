#include "ui.h"

#include <pspdebug.h>
#include <pspdisplay.h>
#include <pspge.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define SCREEN_WIDTH 480
#define SCREEN_HEIGHT 272
#define SCREEN_STRIDE 512

/* PSP 8888 framebuffer colors are ABGR. */
#define COLOR_BG 0xFF141006u
#define COLOR_GRID 0xFF1E1A0Bu
#define COLOR_PANEL 0xFF201C0Du
#define COLOR_PANEL_LIGHT 0xFF2B2813u
#define COLOR_BORDER 0xFF4C4B2Cu
#define COLOR_TEXT 0xFFF7FFE9u
#define COLOR_MUTED 0xFFA0A982u
#define COLOR_ACCENT 0xFFBDF164u
#define COLOR_ACCENT_DARK 0xFF343D17u
#define COLOR_BLUE 0xFFFFC870u
#define COLOR_WARN 0xFF66D1FFu
#define COLOR_DANGER 0xFF8271FFu
#define COLOR_INK 0xFF0D1004u
#define COLOR_SCREEN 0xFF1F2608u

static uint32_t *g_vram;

static const uint8_t GLYPHS[36][7] = {
    {0x0E, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11}, /* A */
    {0x1E, 0x11, 0x11, 0x1E, 0x11, 0x11, 0x1E}, /* B */
    {0x0F, 0x10, 0x10, 0x10, 0x10, 0x10, 0x0F}, /* C */
    {0x1E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x1E}, /* D */
    {0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x1F}, /* E */
    {0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x10}, /* F */
    {0x0F, 0x10, 0x10, 0x17, 0x11, 0x11, 0x0F}, /* G */
    {0x11, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11}, /* H */
    {0x1F, 0x04, 0x04, 0x04, 0x04, 0x04, 0x1F}, /* I */
    {0x07, 0x02, 0x02, 0x02, 0x12, 0x12, 0x0C}, /* J */
    {0x11, 0x12, 0x14, 0x18, 0x14, 0x12, 0x11}, /* K */
    {0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x1F}, /* L */
    {0x11, 0x1B, 0x15, 0x15, 0x11, 0x11, 0x11}, /* M */
    {0x11, 0x19, 0x19, 0x15, 0x13, 0x13, 0x11}, /* N */
    {0x0E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E}, /* O */
    {0x1E, 0x11, 0x11, 0x1E, 0x10, 0x10, 0x10}, /* P */
    {0x0E, 0x11, 0x11, 0x11, 0x15, 0x12, 0x0D}, /* Q */
    {0x1E, 0x11, 0x11, 0x1E, 0x14, 0x12, 0x11}, /* R */
    {0x0F, 0x10, 0x10, 0x0E, 0x01, 0x01, 0x1E}, /* S */
    {0x1F, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04}, /* T */
    {0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E}, /* U */
    {0x11, 0x11, 0x11, 0x11, 0x0A, 0x0A, 0x04}, /* V */
    {0x11, 0x11, 0x11, 0x15, 0x15, 0x1B, 0x11}, /* W */
    {0x11, 0x11, 0x0A, 0x04, 0x0A, 0x11, 0x11}, /* X */
    {0x11, 0x11, 0x0A, 0x04, 0x04, 0x04, 0x04}, /* Y */
    {0x1F, 0x01, 0x02, 0x04, 0x08, 0x10, 0x1F}, /* Z */
    {0x0E, 0x11, 0x13, 0x15, 0x19, 0x11, 0x0E}, /* 0 */
    {0x04, 0x0C, 0x04, 0x04, 0x04, 0x04, 0x0E}, /* 1 */
    {0x0E, 0x11, 0x01, 0x02, 0x04, 0x08, 0x1F}, /* 2 */
    {0x1E, 0x01, 0x01, 0x0E, 0x01, 0x01, 0x1E}, /* 3 */
    {0x02, 0x06, 0x0A, 0x12, 0x1F, 0x02, 0x02}, /* 4 */
    {0x1F, 0x10, 0x10, 0x1E, 0x01, 0x01, 0x1E}, /* 5 */
    {0x0E, 0x10, 0x10, 0x1E, 0x11, 0x11, 0x0E}, /* 6 */
    {0x1F, 0x01, 0x02, 0x04, 0x08, 0x08, 0x08}, /* 7 */
    {0x0E, 0x11, 0x11, 0x0E, 0x11, 0x11, 0x0E}, /* 8 */
    {0x0E, 0x11, 0x11, 0x0F, 0x01, 0x01, 0x0E}, /* 9 */
};

static void fill_rect(int x, int y, int width, int height, uint32_t color)
{
    int row;
    int column;

    if (x < 0) {
        width += x;
        x = 0;
    }
    if (y < 0) {
        height += y;
        y = 0;
    }
    if (x + width > SCREEN_WIDTH) {
        width = SCREEN_WIDTH - x;
    }
    if (y + height > SCREEN_HEIGHT) {
        height = SCREEN_HEIGHT - y;
    }
    if (width <= 0 || height <= 0) {
        return;
    }

    for (row = 0; row < height; ++row) {
        uint32_t *target = g_vram + (y + row) * SCREEN_STRIDE + x;
        for (column = 0; column < width; ++column) {
            target[column] = color;
        }
    }
}

static void draw_panel(
    int x,
    int y,
    int width,
    int height,
    uint32_t background)
{
    fill_rect(x, y, width, height, COLOR_BORDER);
    fill_rect(x + 2, y + 2, width - 4, height - 4, background);
}

static void draw_text(int x, int y, uint32_t color, const char *text)
{
    while (*text != '\0' && x <= SCREEN_WIDTH - 8) {
        unsigned char character = (unsigned char)*text++;
        if (character >= 32 && character <= 126) {
            pspDebugScreenPutChar(x, y, color, character);
        }
        x += 7;
    }
}

static void draw_text_clipped(
    int x,
    int y,
    int max_characters,
    uint32_t color,
    const char *text)
{
    char buffer[64];
    size_t length;

    if (max_characters < 1) {
        return;
    }
    if (max_characters >= (int)sizeof(buffer)) {
        max_characters = (int)sizeof(buffer) - 1;
    }
    length = strlen(text);
    if ((int)length > max_characters) {
        length = (size_t)max_characters;
    }
    memcpy(buffer, text, length);
    buffer[length] = '\0';
    draw_text(x, y, color, buffer);
}

static const uint8_t *large_glyph(char character)
{
    if (character >= 'A' && character <= 'Z') {
        return GLYPHS[character - 'A'];
    }
    if (character >= '0' && character <= '9') {
        return GLYPHS[26 + character - '0'];
    }
    return NULL;
}

static int large_text_width(const char *text, int scale)
{
    size_t length = strlen(text);
    if (length == 0) {
        return 0;
    }
    return (int)length * 6 * scale - scale;
}

static void draw_large_text(
    int x,
    int y,
    int scale,
    uint32_t color,
    const char *text)
{
    while (*text != '\0') {
        const uint8_t *glyph = large_glyph(*text++);
        int row;
        int column;

        if (glyph != NULL) {
            for (row = 0; row < 7; ++row) {
                for (column = 0; column < 5; ++column) {
                    if ((glyph[row] & (1u << (4 - column))) != 0) {
                        fill_rect(
                            x + column * scale,
                            y + row * scale,
                            scale,
                            scale,
                            color);
                    }
                }
            }
        }
        x += 6 * scale;
    }
}

static void draw_centered_large_text(
    int panel_x,
    int panel_width,
    int y,
    int scale,
    uint32_t color,
    const char *text)
{
    int width = large_text_width(text, scale);
    draw_large_text(panel_x + (panel_width - width) / 2, y, scale, color, text);
}

static void draw_logo(int x, int y)
{
    fill_rect(x + 5, y, 30, 40, COLOR_ACCENT);
    fill_rect(x, y + 5, 40, 30, COLOR_ACCENT);
    fill_rect(x + 9, y + 17, 16, 6, COLOR_INK);
    fill_rect(x + 14, y + 12, 6, 16, COLOR_INK);
    fill_rect(x + 29, y + 12, 5, 5, COLOR_INK);
    fill_rect(x + 34, y + 23, 5, 5, COLOR_INK);
}

static void draw_background(void)
{
    int x;
    int y;

    fill_rect(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, COLOR_BG);
    for (x = 0; x < SCREEN_WIDTH; x += 16) {
        fill_rect(x, 0, 1, SCREEN_HEIGHT, COLOR_GRID);
    }
    for (y = 0; y < SCREEN_HEIGHT; y += 16) {
        fill_rect(0, y, SCREEN_WIDTH, 1, COLOR_GRID);
    }
}

static void draw_header(const char *pairing_code)
{
    char code_label[20];

    draw_logo(16, 10);
    draw_large_text(64, 12, 2, COLOR_TEXT, "NIWPSP");
    draw_large_text(136, 12, 2, COLOR_ACCENT, "TOPC");
    draw_text(64, 33, COLOR_MUTED, "WIRELESS + WIRED GAMEPAD");
    if (pairing_code != NULL) {
        snprintf(code_label, sizeof(code_label), "CODE  %c %c %c %c %c",
                 pairing_code[0],
                 pairing_code[1],
                 pairing_code[2],
                 pairing_code[3],
                 pairing_code[4]);
        draw_text(326, 18, COLOR_ACCENT, code_label);
    }
    fill_rect(16, 56, 448, 2, COLOR_BORDER);
}

static void draw_footer(const char *left, const char *right)
{
    int right_x = 454 - (int)strlen(right) * 7;

    if (right_x < 220) {
        right_x = 220;
    }
    draw_panel(16, 238, 448, 22, COLOR_PANEL_LIGHT);
    draw_text(26, 245, COLOR_TEXT, left);
    draw_text(right_x, 245, COLOR_MUTED, right);
}

static void draw_status_dot(int x, int y, uint32_t color)
{
    fill_rect(x, y, 10, 10, color);
    fill_rect(x + 2, y + 2, 6, 6, COLOR_PANEL_LIGHT);
    fill_rect(x + 4, y + 4, 2, 2, color);
}

static void draw_status_layout(
    const char *pairing_code,
    const char *status,
    const char *detail,
    uint32_t color,
    unsigned int send_rate,
    int is_usb)
{
    int code_width;
    char rate_label[24];

    draw_background();
    draw_header(is_usb ? NULL : pairing_code);

    draw_panel(16, 72, 214, 150, COLOR_PANEL);
    if (is_usb) {
        draw_text(28, 84, COLOR_MUTED, "USB CONNECTION");
        fill_rect(28, 100, 190, 2, COLOR_BORDER);
        draw_centered_large_text(
            16,
            214,
            118,
            4,
            COLOR_ACCENT,
            "USB");
        draw_text(61, 180, COLOR_TEXT, "NO CODE REQUIRED");
        draw_text(68, 198, COLOR_MUTED, "LOCAL CABLE LINK");
    } else {
        draw_text(28, 84, COLOR_MUTED, "PAIRING CODE");
        fill_rect(28, 100, 190, 2, COLOR_BORDER);
        code_width = large_text_width(pairing_code, 4);
        draw_large_text(
            16 + (214 - code_width) / 2,
            119,
            4,
            COLOR_ACCENT,
            pairing_code);
        draw_text(47, 180, COLOR_MUTED, "ENTER THIS CODE ON PC");
        draw_text(78, 198, COLOR_TEXT, "NEW ON EVERY START");
    }

    draw_panel(242, 72, 222, 150, COLOR_PANEL);
    draw_text(256, 84, COLOR_MUTED, "LINK STATUS");
    fill_rect(256, 100, 194, 2, COLOR_BORDER);
    draw_status_dot(258, 122, color);
    draw_text_clipped(278, 119, 24, color, status);
    draw_text_clipped(258, 145, 27, COLOR_TEXT, detail);
    draw_text(258, 176, COLOR_MUTED, "TRANSPORT");
    draw_text(370, 176, COLOR_ACCENT, is_usb ? "USB" : "WI-FI");
    draw_text(258, 197, COLOR_MUTED, "VIRTUAL PAD");
    draw_text(
        370,
        197,
        color,
        strcmp(status, "CONTROLLER READY") == 0 ? "READY" : "WAITING");

    snprintf(
        rate_label,
        sizeof(rate_label),
        "%uHZ  L+R+START MENU",
        send_rate);
    draw_footer("HOME  EXIT", rate_label);
}

void ui_init(void)
{
    pspDebugScreenInit();
    pspDebugScreenEnableBackColor(0);
    g_vram = (uint32_t *)(
        (uintptr_t)sceGeEdramGetAddr() | (uintptr_t)0x40000000u);
}

void ui_render_startup(const char *pairing_code)
{
    (void)pairing_code;
    draw_background();
    draw_header(NULL);
    draw_panel(16, 76, 448, 142, COLOR_PANEL);
    draw_centered_large_text(
        16,
        448,
        104,
        3,
        COLOR_ACCENT,
        "STARTING");
    draw_text(150, 154, COLOR_TEXT, "PREPARING CONTROLLER LINK");
    draw_text(178, 178, COLOR_MUTED, "PLEASE WAIT...");
    draw_footer("HOME  EXIT", "NIW LINK");
}

void ui_render_transport_selector(int selected, int wifi_available)
{
    uint32_t usb_border = selected == 0 ? COLOR_ACCENT : COLOR_BORDER;
    uint32_t wifi_border =
        selected == 1 && wifi_available ? COLOR_ACCENT : COLOR_BORDER;
    uint32_t wifi_text = wifi_available ? COLOR_TEXT : COLOR_BORDER;
    uint32_t wifi_detail = wifi_available ? COLOR_MUTED : COLOR_DANGER;

    draw_background();
    draw_header(NULL);
    draw_panel(16, 72, 448, 154, COLOR_PANEL);
    draw_text(30, 84, COLOR_ACCENT, "01 // SELECT CONNECTION");
    fill_rect(30, 102, 420, 2, COLOR_BORDER);

    fill_rect(30, 114, 196, 72, usb_border);
    fill_rect(32, 116, 192, 68, COLOR_SCREEN);
    draw_centered_large_text(
        30,
        196,
        126,
        3,
        selected == 0 ? COLOR_ACCENT : COLOR_TEXT,
        "USB");
    draw_text(67, 163, COLOR_MUTED, "NO CODE REQUIRED");

    fill_rect(254, 114, 196, 72, wifi_border);
    fill_rect(256, 116, 192, 68, COLOR_SCREEN);
    draw_centered_large_text(
        254,
        196,
        126,
        3,
        selected == 1 && wifi_available ? COLOR_ACCENT : wifi_text,
        "WIFI");
    draw_text(
        wifi_available ? 303 : 286,
        163,
        wifi_detail,
        wifi_available ? "PAIR WITH CODE" : "WLAN SWITCH OFF");

    draw_text(30, 198, COLOR_TEXT, "LEFT / RIGHT  CHANGE");
    draw_text(351, 198, COLOR_ACCENT, "X  SELECT");
    draw_footer("HOME  EXIT", "CHOOSE LINK");
}

void ui_render_no_profiles(const char *pairing_code)
{
    draw_background();
    draw_header(pairing_code);
    draw_panel(16, 76, 448, 142, COLOR_PANEL);
    draw_status_dot(34, 94, COLOR_DANGER);
    draw_text(54, 92, COLOR_DANGER, "NO WI-FI PROFILE");
    fill_rect(32, 114, 416, 2, COLOR_BORDER);
    draw_text(32, 132, COLOR_TEXT, "ADD A CONNECTION IN PSP SETTINGS:");
    draw_text(32, 151, COLOR_ACCENT, "SETTINGS > NETWORK SETTINGS");
    draw_text(32, 184, COLOR_MUTED, "CIRCLE RETURNS TO CONNECTION MENU.");
    draw_footer("CIRCLE  CONNECTION MENU", "SETUP REQUIRED");
}

void ui_render_profile_selector(
    const char *pairing_code,
    const char *profile_name,
    int selected,
    int total)
{
    char counter[32];

    draw_background();
    draw_header(pairing_code);
    draw_panel(16, 72, 448, 154, COLOR_PANEL);
    draw_text(30, 84, COLOR_ACCENT, "01 // SELECT WI-FI PROFILE");
    fill_rect(30, 102, 420, 2, COLOR_BORDER);
    draw_panel(30, 116, 420, 62, COLOR_SCREEN);
    draw_text(42, 138, COLOR_ACCENT, "<");
    draw_text_clipped(70, 129, 45, COLOR_TEXT, profile_name);
    snprintf(counter, sizeof(counter), "PROFILE %d OF %d", selected + 1, total);
    draw_text(70, 149, COLOR_MUTED, counter);
    draw_text(432, 138, COLOR_ACCENT, ">");
    draw_text(30, 194, COLOR_TEXT, "LEFT / RIGHT  CHANGE");
    draw_text(274, 194, COLOR_ACCENT, "X  CONNECT");
    draw_footer("CIRCLE  CONNECTION MENU", "SELECT PROFILE");
}

void ui_render_connecting(
    const char *pairing_code,
    const char *state_name,
    int progress_stage)
{
    int index;
    int is_usb = strstr(state_name, "USB") != NULL;

    if (progress_stage < 0) {
        progress_stage = 0;
    }
    if (progress_stage > 4) {
        progress_stage = 4;
    }

    draw_background();
    draw_header(is_usb ? NULL : pairing_code);
    draw_panel(16, 76, 448, 142, COLOR_PANEL);
    draw_text(
        30,
        90,
        COLOR_ACCENT,
        is_usb ? "02 // CONNECTING USB CABLE" : "02 // CONNECTING TO WI-FI");
    fill_rect(30, 108, 420, 2, COLOR_BORDER);
    draw_text(30, 127, COLOR_MUTED, "NETWORK STATUS");
    draw_text_clipped(178, 127, 34, COLOR_TEXT, state_name);
    for (index = 0; index < 5; ++index) {
        fill_rect(
            31 + index * 82,
            157,
            68,
            14,
            index <= progress_stage ? COLOR_ACCENT : COLOR_PANEL_LIGHT);
    }
    draw_text(
        30,
        188,
        COLOR_TEXT,
        is_usb ? "WAITING FOR WINDOWS APP..." : "WAITING FOR ACCESS POINT...");
    draw_footer(
        "CIRCLE  CONNECTION MENU",
        is_usb ? "USB LINK" : "WI-FI LINK");
}

void ui_render_reconnecting(
    const char *pairing_code,
    const char *state_name,
    unsigned int attempt,
    unsigned int retry_in_seconds)
{
    char attempt_label[32];
    char retry_label[40];

    snprintf(attempt_label, sizeof(attempt_label), "ATTEMPT %u", attempt);
    if (retry_in_seconds > 0) {
        snprintf(
            retry_label,
            sizeof(retry_label),
            "RETRY IN %u SECOND%s",
            retry_in_seconds,
            retry_in_seconds == 1 ? "" : "S");
    } else {
        strcpy(retry_label, "CONNECTING NOW...");
    }

    draw_background();
    draw_header(pairing_code);
    draw_panel(16, 76, 448, 142, COLOR_PANEL);
    draw_status_dot(32, 92, COLOR_WARN);
    draw_text(52, 90, COLOR_WARN, "RECONNECTING WI-FI");
    fill_rect(30, 112, 420, 2, COLOR_BORDER);
    draw_text_clipped(30, 130, 44, COLOR_TEXT, state_name);
    draw_text(30, 158, COLOR_MUTED, attempt_label);
    draw_text(30, 184, COLOR_ACCENT, retry_label);
    draw_footer("CIRCLE  CONNECTION MENU", "AUTO RETRY");
}

void ui_render_sender(
    const char *pairing_code,
    int authorized,
    int network_error,
    unsigned int send_rate,
    int is_usb)
{
    if (is_usb && network_error == -1) {
        draw_status_layout(
            pairing_code,
            "WAITING FOR PC",
            "WINDOWS USB ENUMERATION",
            COLOR_WARN,
            send_rate,
            is_usb);
    } else if (network_error != 0) {
        char detail[32];
        snprintf(
            detail,
            sizeof(detail),
            "%s ERROR %d",
            is_usb ? "USB" : "UDP",
            network_error);
        draw_status_layout(
            pairing_code,
            is_usb ? "USB LINK ERROR" : "NETWORK ERROR",
            detail,
            COLOR_DANGER,
            send_rate,
            is_usb);
    } else if (authorized) {
        draw_status_layout(
            pairing_code,
            "CONTROLLER READY",
            is_usb ? "USB LINK ACTIVE" : "WI-FI LINK ACTIVE",
            COLOR_ACCENT,
            send_rate,
            is_usb);
    } else {
        draw_status_layout(
            pairing_code,
            "WAITING FOR PC",
            is_usb ? "USB CABLE CONNECTED" : "ENTER CODE IN DESKTOP APP",
            COLOR_WARN,
            send_rate,
            is_usb);
    }
}

void ui_render_usb_waiting(
    const char *pairing_code,
    unsigned int send_rate,
    uint32_t descriptor_debug)
{
    char detail[32];

    snprintf(
        detail,
        sizeof(detail),
        "WCID %02X REQ %02X/%02X/%02X",
        (unsigned int)(descriptor_debug & 0xFF),
        (unsigned int)((descriptor_debug >> 8) & 0xFF),
        (unsigned int)((descriptor_debug >> 16) & 0xFF),
        (unsigned int)((descriptor_debug >> 24) & 0xFF));
    draw_status_layout(
        pairing_code,
        "WAITING FOR PC",
        detail,
        COLOR_WARN,
        send_rate,
        1);
}

void ui_render_error(
    const char *pairing_code,
    const char *title,
    const char *message,
    int error)
{
    char error_code[32];

    draw_background();
    draw_header(pairing_code);
    draw_panel(16, 76, 448, 142, COLOR_PANEL);
    draw_status_dot(32, 92, COLOR_DANGER);
    draw_text_clipped(52, 90, 50, COLOR_DANGER, title);
    fill_rect(30, 112, 420, 2, COLOR_BORDER);
    draw_text_clipped(30, 132, 58, COLOR_TEXT, message);
    snprintf(error_code, sizeof(error_code), "ERROR 0x%08X", (unsigned int)error);
    draw_text(30, 158, COLOR_MUTED, error_code);
    if (strcmp(title, "STARTUP ERROR") == 0) {
        draw_text(30, 190, COLOR_WARN, "RETURNING TO PSP MENU...");
        draw_footer("HOME  EXIT", "STARTUP ERROR");
    } else {
        draw_text(30, 190, COLOR_WARN, "RETURNING TO CONNECTION MENU...");
        draw_footer("HOME  EXIT", "LINK ERROR");
    }
}

void ui_render_shutdown(const char *pairing_code)
{
    draw_background();
    draw_header(pairing_code);
    draw_panel(16, 86, 448, 120, COLOR_PANEL);
    draw_centered_large_text(
        16,
        448,
        112,
        3,
        COLOR_ACCENT,
        "GOODBYE");
    draw_text(171, 162, COLOR_TEXT, "CLOSING CONTROLLER LINK");
}
