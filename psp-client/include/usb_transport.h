#ifndef NIW_PSP_TO_PC_USB_TRANSPORT_H
#define NIW_PSP_TO_PC_USB_TRANSPORT_H

#include <stddef.h>
#include <stdint.h>

#define NIW_USBHOSTFS_ASYNC_CHANNEL 4u

typedef struct NiwUsbAsyncEndpoint {
    unsigned char buffer[4096];
    int read_position;
    int write_position;
    int size;
} NiwUsbAsyncEndpoint;

typedef struct NiwUsbTransport {
    int module_id;
    int bus_started;
    int driver_started;
    int activated;
    int registered;
    NiwUsbAsyncEndpoint endpoint;
    uint32_t async_register_address;
    uint32_t async_unregister_address;
    uint32_t async_write_address;
    uint32_t async_read_with_timeout_address;
    uint32_t descriptor_debug_address;
} NiwUsbTransport;

int usb_transport_cable_connected(void);
int usb_transport_start(
    NiwUsbTransport *transport,
    const char *eboot_path);
int usb_transport_is_connected(const NiwUsbTransport *transport);
uint32_t usb_transport_descriptor_debug(const NiwUsbTransport *transport);
int usb_transport_send(
    NiwUsbTransport *transport,
    const uint8_t *data,
    size_t size);
int usb_transport_receive(
    NiwUsbTransport *transport,
    uint8_t *data,
    size_t size);
void usb_transport_stop(NiwUsbTransport *transport);

#endif
