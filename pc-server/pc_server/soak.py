"""Timed receiver for repeatable physical PSP stability runs."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import ipaddress
import json
from pathlib import Path
import threading
import time

from .protocol import parse_pairing_token
from .receiver import ReceiverSnapshot, UdpReceiver


@dataclass(slots=True)
class SoakReport:
    duration_s: float
    active_client: str | None
    first_sequence: int | None
    last_sequence: int | None
    received: int
    accepted_states: int
    lost: int
    duplicates: int
    out_of_order: int
    final_pps: float


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a timed niwPSPtoPC hardware receive test."
    )
    parser.add_argument("--host", default="0.0.0.0", help="IPv4 address to bind")
    parser.add_argument("--port", type=int, default=47999, help="UDP port")
    parser.add_argument(
        "--minutes",
        type=float,
        default=30.0,
        help="test duration in minutes (default: 30)",
    )
    parser.add_argument(
        "--allow-client",
        metavar="IP",
        help="accept packets only from this PSP IPv4 address",
    )
    parser.add_argument(
        "--pairing-token",
        metavar="CODE",
        required=True,
        help="five-character code shown by the PSP",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="also write the JSON report to this path",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not 1 <= args.port <= 65535:
        raise SystemExit("--port must be between 1 and 65535")
    if not 0 < args.minutes <= 24 * 60:
        raise SystemExit("--minutes must be greater than 0 and at most 1440")
    try:
        allowed_hosts = (
            {str(ipaddress.IPv4Address(args.allow_client))}
            if args.allow_client
            else None
        )
    except ipaddress.AddressValueError as exc:
        raise SystemExit(f"--allow-client must be an IPv4 address: {exc}") from exc
    try:
        pairing_token = parse_pairing_token(args.pairing_token)
    except ValueError as exc:
        raise SystemExit(f"--pairing-token: {exc}") from exc

    first: ReceiverSnapshot | None = None
    last: ReceiverSnapshot | None = None
    accepted_states = 0

    def on_diagnostic(snapshot: ReceiverSnapshot) -> None:
        nonlocal first, last
        if not snapshot.is_active_client:
            return
        if first is None:
            first = snapshot
        last = snapshot

    def on_state(snapshot: ReceiverSnapshot) -> None:
        nonlocal accepted_states
        accepted_states += 1

    receiver = UdpReceiver(
        args.host,
        args.port,
        allowed_hosts=allowed_hosts,
        on_packet=on_state,
        on_diagnostic=on_diagnostic,
        pairing_token=pairing_token,
        require_pairing=True,
    )
    duration_s = args.minutes * 60
    timer = threading.Timer(duration_s, receiver.request_stop)
    started = time.monotonic()
    timer.start()
    try:
        receiver.run()
    except KeyboardInterrupt:
        receiver.request_stop()
    finally:
        timer.cancel()
    elapsed = time.monotonic() - started

    report = SoakReport(
        duration_s=round(elapsed, 3),
        active_client=(
            f"{last.address[0]}:{last.address[1]}" if last is not None else None
        ),
        first_sequence=first.packet.sequence if first is not None else None,
        last_sequence=last.packet.sequence if last is not None else None,
        received=last.received if last is not None else 0,
        accepted_states=accepted_states,
        lost=last.lost if last is not None else 0,
        duplicates=last.duplicates if last is not None else 0,
        out_of_order=last.out_of_order if last is not None else 0,
        final_pps=last.packets_per_second if last is not None else 0.0,
    )
    output = json.dumps(asdict(report), indent=2) + "\n"
    print(output, end="")
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        temporary.write_text(output, encoding="utf-8")
        temporary.replace(args.output)
    return 0 if last is not None else 2


if __name__ == "__main__":
    raise SystemExit(main())
