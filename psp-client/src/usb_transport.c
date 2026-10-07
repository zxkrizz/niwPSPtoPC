#include "usb_transport.h"

#include <kubridge.h>
#include <pspkernel.h>
#include <pspmodulemgr.h>
#include <pspsdk.h>
#include <pspusb.h>
#include <stdint.h>
#include <string.h>
#include <systemctrl.h>

#define USBHOSTFS_MODULE_NAME "USBHostFS"
#define USBHOSTFS_LIBRARY_NAME "USBHostFS"
#define USBHOSTFS_DRIVER_NAME "USBHostFSDriver"
#define USBHOSTFS_PRODUCT_ID 0x01C9u
#define NID_USB_ASYNC_REGISTER 0x75246D41u
#define NID_USB_ASYNC_UNREGISTER 0x587DDEDAu
#define NID_USB_ASYNC_READ_TIMEOUT 0xE4C00162u
#define NID_USB_ASYNC_WRITE 0x5D1F19A0u
#define NID_USB_DESCRIPTOR_DEBUG 0xDA1FCF18u

static int resolve_sibling_path(
    const char *eboot_path,
    const char *filename,
    char *output,
    size_t output_size)
{
    const char *separator;
    size_t directory_length;
    size_t filename_length = strlen(filename) + 1u;

    if (eboot_path == NULL || *eboot_path == '\0') {
        if (filename_length > output_size) {
            return -1;
        }
        memcpy(output, filename, filename_length);
        return 0;
    }
    separator = strrchr(eboot_path, '/');
    if (separator == NULL) {
        separator = strrchr(eboot_path, '\\');
    }
    directory_length =
        separator == NULL ? 0u : (size_t)(separator - eboot_path) + 1u;
    if (directory_length + filename_length > output_size) {
        return -1;
    }
    if (directory_length > 0u) {
        memcpy(output, eboot_path, directory_length);
    }
    memcpy(output + directory_length, filename, filename_length);
    return 0;
}

static uint32_t find_usbhostfs_function(uint32_t nid)
{
    return sctrlHENFindFunction(
        USBHOSTFS_MODULE_NAME,
        USBHOSTFS_LIBRARY_NAME,
        nid);
}

static int call_usbhostfs(
    uint32_t address,
    uint32_t arg1,
    uint32_t arg2,
    uint32_t arg3,
    uint32_t arg4)
{
    KernelCallArg args;
    int bridge_result;

    if (address == 0) {
        return -1;
    }
    memset(&args, 0, sizeof(args));
    args.arg1 = arg1;
    args.arg2 = arg2;
    args.arg3 = arg3;
    args.arg4 = arg4;
    bridge_result = kuKernelCall((void *)(uintptr_t)address, &args);
    if (bridge_result < 0) {
        return bridge_result;
    }
    return (int32_t)args.ret1;
}

int usb_transport_cable_connected(void)
{
    return (sceUsbGetState() & PSP_USB_CABLE_CONNECTED) != 0;
}

int usb_transport_start(
    NiwUsbTransport *transport,
    const char *eboot_path)
{
    char module_path[256];
    uint32_t address;
    int result;
    int module_status = 0;

    memset(transport, 0, sizeof(*transport));
    transport->module_id = -1;
    if (
        resolve_sibling_path(
            eboot_path,
            "usbhostfs.prx",
            module_path,
            sizeof(module_path)
        ) < 0
    ) {
        return -1;
    }

    transport->module_id = kuKernelLoadModule(module_path, 0, NULL);
    if (transport->module_id < 0) {
        return transport->module_id;
    }
    result = sceKernelStartModule(
        transport->module_id,
        0,
        NULL,
        &module_status,
        NULL);
    if (result < 0) {
        sceKernelUnloadModule(transport->module_id);
        transport->module_id = -1;
        return result;
    }

    address = find_usbhostfs_function(NID_USB_ASYNC_REGISTER);
    transport->async_register_address = address;
    address = find_usbhostfs_function(NID_USB_ASYNC_UNREGISTER);
    transport->async_unregister_address = address;
    address = find_usbhostfs_function(NID_USB_ASYNC_WRITE);
    transport->async_write_address = address;
    address = find_usbhostfs_function(NID_USB_ASYNC_READ_TIMEOUT);
    transport->async_read_with_timeout_address = address;
    address = find_usbhostfs_function(NID_USB_DESCRIPTOR_DEBUG);
    transport->descriptor_debug_address = address;
    if (
        transport->async_register_address == 0 ||
        transport->async_unregister_address == 0 ||
        transport->async_write_address == 0 ||
        transport->async_read_with_timeout_address == 0
    ) {
        usb_transport_stop(transport);
        return -2;
    }

    result = sceUsbStart(PSP_USBBUS_DRIVERNAME, 0, NULL);
    if (result != 0) {
        usb_transport_stop(transport);
        return result;
    }
    transport->bus_started = 1;
    result = sceUsbStart(USBHOSTFS_DRIVER_NAME, 0, NULL);
    if (result != 0) {
        usb_transport_stop(transport);
        return result;
    }
    transport->driver_started = 1;
    result = sceUsbActivate(USBHOSTFS_PRODUCT_ID);
    if (result != 0) {
        usb_transport_stop(transport);
        return result;
    }
    transport->activated = 1;
    result = call_usbhostfs(
        transport->async_register_address,
        NIW_USBHOSTFS_ASYNC_CHANNEL,
        (uint32_t)(uintptr_t)&transport->endpoint,
        0,
        0);
    if (result < 0) {
        usb_transport_stop(transport);
        return result;
    }
    transport->registered = 1;
    return 0;
}

int usb_transport_is_connected(const NiwUsbTransport *transport)
{
    int state;

    if (!transport->activated || !usb_transport_cable_connected()) {
        return 0;
    }
    state = sceUsbGetState();
    return (state & PSP_USB_CONNECTION_ESTABLISHED) != 0;
}

uint32_t usb_transport_descriptor_debug(const NiwUsbTransport *transport)
{
    if (transport->descriptor_debug_address == 0) {
        return 0;
    }
    return (uint32_t)call_usbhostfs(
        transport->descriptor_debug_address,
        0,
        0,
        0,
        0);
}

int usb_transport_send(
    NiwUsbTransport *transport,
    const uint8_t *data,
    size_t size)
{
    if (
        !usb_transport_is_connected(transport) ||
        size > (size_t)0x7FFFFFFF
    ) {
        return -1;
    }
    return call_usbhostfs(
        transport->async_write_address,
        NIW_USBHOSTFS_ASYNC_CHANNEL,
        (uint32_t)(uintptr_t)data,
        (uint32_t)size,
        0);
}

int usb_transport_receive(
    NiwUsbTransport *transport,
    uint8_t *data,
    size_t size)
{
    if (
        !usb_transport_is_connected(transport) ||
        size > (size_t)0x7FFFFFFF
    ) {
        return -1;
    }
    return call_usbhostfs(
        transport->async_read_with_timeout_address,
        NIW_USBHOSTFS_ASYNC_CHANNEL,
        (uint32_t)(uintptr_t)data,
        (uint32_t)size,
        0);
}

void usb_transport_stop(NiwUsbTransport *transport)
{
    int status = 0;

    if (
        transport->registered &&
        transport->async_unregister_address != 0
    ) {
        call_usbhostfs(
            transport->async_unregister_address,
            NIW_USBHOSTFS_ASYNC_CHANNEL,
            0,
            0,
            0);
        transport->registered = 0;
    }
    if (transport->activated) {
        sceUsbDeactivate(USBHOSTFS_PRODUCT_ID);
        transport->activated = 0;
    }
    if (transport->driver_started) {
        sceUsbStop(USBHOSTFS_DRIVER_NAME, 0, NULL);
        transport->driver_started = 0;
    }
    if (transport->bus_started) {
        sceUsbStop(PSP_USBBUS_DRIVERNAME, 0, NULL);
        transport->bus_started = 0;
    }
    if (transport->module_id >= 0) {
        sceKernelStopModule(
            transport->module_id,
            0,
            NULL,
            &status,
            NULL);
        sceKernelUnloadModule(transport->module_id);
        transport->module_id = -1;
    }
}
