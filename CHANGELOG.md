# Changelog

All notable public changes are documented here.

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
