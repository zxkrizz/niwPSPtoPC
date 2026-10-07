# Wired USB mode

USB is a supported transport in niwPSPtoPC 1.2.0. It uses the same input
protocol, session tracking, safety timeout, ViGEm mapping and Windows input
path as Wi-Fi. The physical cable is the authorization boundary, so USB does
not use the five-character Wi-Fi pairing code.

The 1.2.0 implementation has been physically verified on a PSP-2004 for input,
hot-plugging and switching USB -> Wi-Fi -> USB. Other supported PSP families
share the same PSP USB stack, but hardware-specific results are welcome. PSP
Street/E1000 has no Wi-Fi hardware and its expected USB-only operation remains
unverified.

## Connecting and switching

1. Start the Windows and PSP applications in either order.
2. Select USB or Wi-Fi using the two large fields at the top of the Windows
   application.
3. On the PSP, choose USB or WIFI with LEFT/RIGHT and confirm with CROSS. WIFI
   is disabled while the physical WLAN switch is off.
4. For USB, connect a PSP data cable. No code is required.
5. For Wi-Fi, choose a saved network profile and enter the code shown by the
   PSP in the Windows application.
6. Hold L+R+START for 0.75 seconds during an active PSP link to return to the
   transport selector. CIRCLE cancels a waiting, profile-selection or
   reconnect screen.

The Windows application listens for both transports and keeps one virtual
controller. Selecting another transport does not interrupt the current link
while the replacement is being prepared. The connected state hides the Wi-Fi
code field and shows only connection status and Disconnect.

Removing the USB cable releases held controls and returns the PSP to its
transport selector instead of closing the application.

## Automatic Windows driver setup

No Zadig package or unsigned kernel driver is used. The PSP reports Microsoft
OS 1.0 descriptors that ask Windows 10/11 to bind the inbox, Microsoft-signed
WinUSB driver:

- compatible ID `WINUSB`;
- device-interface GUID
  `{25B21F00-3140-49D7-9625-1F109B77ECFA}`.

Windows matches the compatible ID to its inbox `winusb.inf` and loads
Microsoft's signed `winusb.sys`. The Windows executable bundles only the
user-space libusb client used to communicate through WinUSB.

If Windows binds WinUSB but omits the application interface, niwPSPtoPC
detects that exact state and requests one UAC confirmation. The narrowly
scoped helper registers the interface for USB ID `054C:01C9`, restarts only
that device instance and exits. Later connections through the same Windows
device instance run without elevation.

The PSP firmware does not currently expose a stable USB serial number.
Windows can therefore create a separate device instance when the cable is
connected through another physical USB port, causing one more UAC prompt.

The first connection can take several seconds while Windows creates the
device. Leave both applications running; the PSP continues retrying.

## Existing PSPLink or Zadig installations

Windows can retain an older driver choice for USB ID `054C:01C9`. Existing
WinUSB assignments continue to work. If the device remains unavailable:

1. Open Device Manager and locate the PSPLink/USBHostFS device.
2. Uninstall that device. Remove its old third-party driver package if Windows
   offers that checkbox.
3. Disconnect the cable.
4. Start niwPSPtoPC on the PSP and reconnect the cable.

Windows should enumerate the firmware descriptors and select its inbox WinUSB
driver. Do not install a new Zadig or unsigned driver package for niwPSPtoPC.

## Required PSP files

Keep all three files together:

```text
niwPSPtoPC/
  EBOOT.PBP
  config.ini
  usbhostfs.prx
```

`usbhostfs.prx` is built from the pinned PSPDEV/PSPLink revision recorded in
`scripts/build-usbhostfs.sh`. Release archives also include the applicable
license and third-party notices.

## Troubleshooting checklist

- Confirm that the cable carries data, not charging only.
- Keep the PSP application on the USB connection screen during initial
  Windows enumeration.
- Try reconnecting through the same physical USB port first.
- Check that Device Manager reports Microsoft as the driver provider and
  `winusb.sys` as the driver.
- If a UAC prompt appears, approve it once so the application interface can be
  registered.
- Disconnect PSPLink, RemoteJoyLite or other software that may already own the
  same PSP USB interface.
- Use Connection Doctor in the Windows application when the virtual
  controller or transport does not become ready.

## Release acceptance matrix

Before publishing a new release, verify:

- launch with USB connected and with the PSP WLAN switch both on and off;
- all buttons and analog-stick extremes over USB and Wi-Fi;
- neutral input immediately after cable removal;
- cable removal returns to the selector without exiting;
- USB -> Wi-Fi -> USB switching with one virtual controller;
- USB remains active while a Wi-Fi code is being entered;
- reconnect and relaunch into USB with a clean packet sequence;
- suspend, resume and HOME exit behavior;
- first connection on clean Windows 10 and Windows 11 installations;
- no unsigned-driver warning and no requirement for Zadig.
