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
