# Security policy

## Supported version

Security fixes are provided for the latest public release.

## Reporting a vulnerability

Please use the repository's private **Report a vulnerability** form under the
GitHub Security tab. Do not publish pairing bypasses or memory-safety issues
as a public issue before a fix is available.

Include the affected version, Windows and PSP models, network setup,
reproduction steps and any relevant packet capture with unrelated private
traffic removed.

## Security boundary

niwPSPtoPC is intended for a trusted home LAN. Its five-character pairing
code is not cryptographic authentication, UDP input is not encrypted, and a
device capable of capturing local traffic can recover the session token.

Never forward UDP 47999 through a router and never expose the receiver
directly to the Internet.

USB mode is authorized by physical access to the connected PSP and does not
use the Wi-Fi pairing code. It uses the Microsoft-signed inbox WinUSB driver;
the application must not be distributed with an unsigned replacement kernel
driver. Treat an unattended, connected PSP and cable as access to the virtual
controller.
