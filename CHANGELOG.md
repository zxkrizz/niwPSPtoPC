# Changelog

All notable public changes are documented here.

## 1.2.0 — 2026-07-30

- promoted wired USB input from a development preview to a supported
  transport after physical PSP-2004 validation;
- added an explicit USB/Wi-Fi selector on the PSP, with Wi-Fi disabled when
  the WLAN switch is off and safe return to the selector after cable removal;
- added matching large USB/Wi-Fi fields in the Windows application, with
  transport-specific setup, code-free USB authorization and a simplified
  connected state;
- added live USB <-> Wi-Fi switching without restarting either application or
  recreating the virtual Xbox 360 controller;
- implemented a reconnectable PSP USBHostFS transport that reuses protocol v2,
  active-client routing, packet ordering, timeouts and controller mapping;
- added Microsoft OS descriptors for automatic inbox WinUSB selection and a
  narrowly scoped, one-time elevated repair when Windows omits the device
  interface;
- fixed WCID descriptor responses and Windows USB enumeration failures found
  during physical end-to-end testing;
- kept the PSP application running when neither a USB cable nor an available
  Wi-Fi connection is present;
- added pinned, reproducible USBHostFS builds and included `usbhostfs.prx` in
  PSP packages with its license notice;
- refreshed the product as the Ultimate Wireless and Wired Gamepad, simplified
  the Windows connection diagnostics and expanded USB routing, packaging and
  provisioning tests.

## 1.1.0 — 2026-07-30

- added automatic PSP backlight shutoff ten seconds after pairing, with the
  previous brightness restored on HOME/SCREEN, connection loss and exit;
- resolved backlight functions dynamically through the CFW user bridge so the
  user-mode EBOOT has no direct kernel display-driver import;
- added dynamic PSP clock scaling: 333/333/166 MHz for startup, discovery and
  recovery, then 111/111/55 MHz while the controller link is stable;
- bounded PSP pairing-ACK processing to 32 datagrams per sender cycle so a UDP
  flood cannot trap the client in an unbounded receive loop;
- documented WPA2 operation through recent ARK-4 and ARK-5 CFW releases while
  retaining guidance for legacy WPA, 2.4 GHz and client-isolation constraints;
- added automatic PSP Wi-Fi recovery with socket recreation, broadcast
  rediscovery, cancellable reconnect UI and capped exponential backoff;
- changed the time-critical PSP sender to non-blocking controller peeks;
- hardened the receiver with bounded rejection caches, callback isolation,
  raw/valid packet diagnostics and active-client expiry;
- added safe virtual-gamepad recovery, including one automatic retry and
  distinct missing-library, missing-driver, connection and update errors;
- expanded Connection Doctor 2.0 with Windows IPv4, profile, firewall and VPN
  checks, live UDP health metrics and a copyable report;
- added persistent GUI settings for the bind address, UDP port and PSP IP
  allowlist, with receiver-only restart;
- strengthened release engineering with immutable GitHub Action pins,
  Dependabot, cancellable CI, tag ancestry checks, provenance attestations,
  idempotent uploads and an embedded PerMonitorV2 Windows manifest;
- retained ViGEmBus 1.22.0 as the single Windows virtual-gamepad backend and
  documented its end-of-life status.

## 1.0.1 — 2026-07-29

- kept the ViGEm XInput target connected across PSP packet and session
  timeouts;
- neutralized controls after 0.5 seconds and released the PSP session after
  1.75 seconds of silence;
- added Connection Doctor stages, ViGEmBus preflight and network isolation
  guidance;
- added a Windows single-instance guard and forwarded the GUI host allowlist;
- added PSP Go `ef0:` configuration discovery and safe missing-config defaults;
- constrained `send_rate` to 15–60 Hz and displayed the observed/configured
  value;
- rejected non-zero protocol reserved fields;
- rate-limited pairing ACKs to 10 Hz and made PSP status redraw event-driven;
- made `pc_server._version` the product version source and generated Windows
  metadata from it;
- made local release packaging rebuild, test, smoke-test and verify artifacts;
- pinned PSPDEV and split branch CI from tag-driven GitHub Releases.

## 1.0.0 — 2026-07-29

- added automatic PC discovery on the local network;
- added five-character session pairing and pairing acknowledgements;
- added exclusive active-client selection and inactive-client expiry;
- added a safe 1.5-second controller watchdog;
- filtered duplicate and out-of-order states from gameplay;
- added the Windows Xbox 360 virtual-gamepad backend;
- added the final English pixel-art Windows interface;
- added the graphical PSP interface, XMB icon and background;
- added C/Python golden-packet, UDP loop, routing, timeout and GUI tests;
- added reproducible Windows, PSP and release packaging.
