# niwPSPtoPC Input Protocol v2

This document is the normative specification for PSP controller input,
pairing and automatic PC discovery.

## Encoding rules

- Every multi-byte integer is unsigned and uses network byte order.
- One UDP datagram contains exactly one complete message.
- Fields are encoded explicitly; no C structure layout is sent over the wire.
- The current input packet is exactly 32 bytes.

## Input packet

Struct notation: `!IHHIIBBHIQ`.

| Offset | Size | Type | Field | Meaning |
|---:|---:|---|---|---|
| 0 | 4 | `uint32` | `magic` | `0x50535049`, ASCII `PSPI` |
| 4 | 2 | `uint16` | `version` | `2` |
| 6 | 2 | `uint16` | `packet_size` | `32` |
| 8 | 4 | `uint32` | `sequence` | Packet sequence number |
| 12 | 4 | `uint32` | `buttons` | Stable button bitmap |
| 16 | 1 | `uint8` | `analog_x` | Raw PSP X axis, `0–255` |
| 17 | 1 | `uint8` | `analog_y` | Raw PSP Y axis, `0–255` |
| 18 | 2 | `uint16` | `reserved` | Must be zero |
| 20 | 4 | `uint32` | `session_token` | Current 25-bit pairing token |
| 24 | 8 | `uint64` | `timestamp_us` | Monotonic PSP time in microseconds |

`session_token` is in `0x00000000–0x01FFFFFF`. Its five-character text form
uses `ABCDEFGHJKLMNPQRSTUVWXYZ23456789`, omitting visually ambiguous
characters. Spaces and hyphens entered in the desktop app are ignored.

## Pairing ACK

The PC sends an ACK only after accepting an input packet with the configured
pairing code.

Struct notation: `!IHHI`.

| Offset | Size | Type | Field | Value |
|---:|---:|---|---|---|
| 0 | 4 | `uint32` | `magic` | `0x50535041`, ASCII `PSPA` |
| 4 | 2 | `uint16` | `version` | `1` |
| 6 | 2 | `uint16` | `packet_size` | `12` |
| 8 | 4 | `uint32` | `session_token` | Token from the accepted packet |

The PSP generates a new token on each application start. Until a valid ACK is
received, it reports a waiting state. ACKs are refreshed while input is being
received; after two seconds without one, the PSP returns to discovery mode.

## Automatic PC discovery

The PSP does not store a PC address.

1. After Wi-Fi connects, the PSP enables UDP broadcast.
2. While unpaired, input packets are sent to `255.255.255.255` on the
   configured port, `47999` by default.
3. The desktop receiver validates the pairing token and replies to the PSP
   source address with a pairing ACK.
4. The source address of that ACK becomes the PSP's unicast destination.
5. If ACKs stop for two seconds, the destination is reset to broadcast and
   discovery begins again.

Discovery is restricted to one broadcast domain. PSP and PC must be on the
same local network, client isolation must be disabled, and the PC receiver
must listen on all interfaces.

## Button bitmap

| Bit | Mask | PSP input |
|---:|---:|---|
| 0 | `0x00000001` | Up |
| 1 | `0x00000002` | Down |
| 2 | `0x00000004` | Left |
| 3 | `0x00000008` | Right |
| 4 | `0x00000010` | Cross |
| 5 | `0x00000020` | Circle |
| 6 | `0x00000040` | Square |
| 7 | `0x00000080` | Triangle |
| 8 | `0x00000100` | L |
| 9 | `0x00000200` | R |
| 10 | `0x00000400` | Start |
| 11 | `0x00000800` | Select |

Several inputs may be active at once through bitwise OR.

## Sequence handling

The first packet in a PSP process uses sequence zero. The number advances on
every send attempt and wraps from `0xFFFFFFFF` to zero.

The receiver compares values using uint32 serial-number arithmetic:

- FIRST — no previous packet;
- IN_ORDER — forward delta equals one;
- GAP — forward delta is greater than one and lower than `0x80000000`;
- DUPLICATE — delta equals zero;
- OUT_OF_ORDER — every other delta.

Only FIRST, IN_ORDER and GAP update the virtual controller. DUPLICATE and
OUT_OF_ORDER stay in diagnostics and never restore an older state. No jitter
buffer is used.

The first valid paired `IP:port` owns the controller until it is explicitly
released or times out. Inactive client entries expire.

## Controller safety timeout

After 1.5 seconds without a fresh accepted state, the controller backend:

1. releases every button;
2. centers the analog stick;
3. disconnects the virtual device.

This watchdog belongs to the controller layer and does not depend on GUI
refreshing.

## Timestamp and latency

`timestamp_us` is PSP uptime, not Unix time and not a clock synchronized with
the PC. It must not be used to report one-way latency. Input-to-game latency
requires a separate RTT or hardware measurement.

## Legacy v1

The PC decoder can read the historical 28-byte v1 packet
(`!IHHIIBBHQ`) for diagnostic compatibility. It has no pairing token and is
rejected whenever pairing is required. Product applications use only v2.

## Validation fixture

The receiver rejects messages with an invalid length, magic, version,
declared size or token range. Unknown button bits do not invalidate a packet.

`psp-client/tests/golden_packet_v2.inc` is shared by the host C encoder test
and Python decoder test. It contains:

- sequence `0x01020304`;
- buttons `0x00000A55`;
- analog `(0x7F, 0xC9)`;
- token `0x01234567`;
- timestamp `0x0102030405060708`.

## Security boundary

The five-character code provides 25 bits of pairing space and prevents
accidental control by ordinary senders on the same LAN. It is not a
cryptographic protocol: traffic is unencrypted and the token is present in
every input packet. A device capable of capturing LAN traffic can recover it.

The protocol is for a trusted home network only. It must not be forwarded or
exposed to the Internet.

Existing button meanings must never change. Any wire-layout change must
increment `version` and update `packet_size`.
