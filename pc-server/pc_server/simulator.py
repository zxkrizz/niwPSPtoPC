"""Generate PSP input datagrams for receiver development without a console."""

from __future__ import annotations

import argparse
import logging
import socket
import time

from .protocol import (
    Buttons,
    InputPacket,
    encode_packet,
    parse_pairing_token,
)

LOGGER = logging.getLogger(__name__)

BUTTON_PATTERN = (
    0,
    int(Buttons.UP),
    int(Buttons.RIGHT),
    int(Buttons.DOWN),
    int(Buttons.LEFT),
    int(Buttons.CROSS),
    int(Buttons.CIRCLE),
    int(Buttons.SQUARE),
    int(Buttons.TRIANGLE),
    int(Buttons.L),
    int(Buttons.R),
    int(Buttons.START | Buttons.SELECT),
)


def build_demo_packet(
    index: int,
    sequence: int,
    timestamp_us: int,
    session_token: int = 0,
) -> InputPacket:
    """Build a deterministic packet that exercises controls over time."""
    analog_x = (index * 5) % 256
    analog_y = 255 - analog_x
    buttons = BUTTON_PATTERN[(index // 30) % len(BUTTON_PATTERN)]
    return InputPacket(
        sequence=sequence,
        buttons=buttons,
        analog_x=analog_x,
        analog_y=analog_y,
        timestamp_us=timestamp_us,
        session_token=session_token,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Send simulated niwPSPtoPC controller packets over UDP."
    )
    parser.add_argument("--host", default="127.0.0.1", help="receiver IPv4 address")
    parser.add_argument(
        "--port", type=int, default=47999, help="receiver UDP port (default: 47999)"
    )
    parser.add_argument(
        "--rate", type=int, default=60, help="packets per second (default: 60)"
    )
    parser.add_argument(
        "--count",
        type=int,
        default=300,
        help="logical packets to generate; 0 runs until Ctrl+C",
    )
    parser.add_argument(
        "--scenario",
        choices=("demo", "sequence-errors"),
        default="demo",
        help="optionally inject a gap, duplicate, out-of-order and malformed packet",
    )
    parser.add_argument(
        "--token",
        default="AAAAA",
        help="five-character pairing code to send (default: AAAAA)",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not 1 <= args.port <= 65535:
        raise SystemExit("--port must be between 1 and 65535")
    if not 1 <= args.rate <= 1000:
        raise SystemExit("--rate must be between 1 and 1000")
    if args.count < 0:
        raise SystemExit("--count must be zero or greater")
    try:
        session_token = parse_pairing_token(args.token)
    except ValueError as exc:
        raise SystemExit(f"--token: {exc}") from exc

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    destination = (args.host, args.port)
    period = 1.0 / args.rate
    next_send = time.perf_counter()
    sequence = 0
    index = 0
    datagrams_sent = 0

    LOGGER.info(
        "Sending %s packets to udp://%s:%d at %d pps (%s)",
        "unlimited" if args.count == 0 else args.count,
        args.host,
        args.port,
        args.rate,
        args.scenario,
    )

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            while args.count == 0 or index < args.count:
                if args.scenario == "sequence-errors" and index == 30:
                    sequence = (sequence + 1) & 0xFFFFFFFF

                packet = build_demo_packet(
                    index,
                    sequence,
                    time.monotonic_ns() // 1_000,
                    session_token,
                )
                encoded = encode_packet(packet)
                sock.sendto(encoded, destination)
                datagrams_sent += 1

                if args.scenario == "sequence-errors" and index == 60:
                    sock.sendto(encoded, destination)
                    datagrams_sent += 1
                elif args.scenario == "sequence-errors" and index == 90:
                    old_packet = build_demo_packet(
                        index,
                        (sequence - 2) & 0xFFFFFFFF,
                        time.monotonic_ns() // 1_000,
                        session_token,
                    )
                    sock.sendto(encode_packet(old_packet), destination)
                    datagrams_sent += 1
                elif args.scenario == "sequence-errors" and index == 120:
                    sock.sendto(b"malformed-simulator-datagram", destination)
                    datagrams_sent += 1

                sequence = (sequence + 1) & 0xFFFFFFFF
                index += 1
                next_send += period
                delay = next_send - time.perf_counter()
                if delay > 0:
                    time.sleep(delay)
                elif delay < -(period * 4):
                    next_send = time.perf_counter()
    except KeyboardInterrupt:
        LOGGER.info("Stopping simulator")
    except OSError as exc:
        LOGGER.error("Network error: %s", exc)
        return 1

    LOGGER.info(
        "Simulation complete: %d logical packets, %d UDP datagrams",
        index,
        datagrams_sent,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
