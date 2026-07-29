"""Command-line entry point for ``python -m pc_server``."""

from __future__ import annotations

import argparse
import ipaddress
import logging

from .display import ControllerDisplay
from .gamepad import ControllerService, DEFAULT_INPUT_TIMEOUT_S
from .protocol import parse_pairing_token
from .receiver import UdpReceiver


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Receive and display niwPSPtoPC controller packets."
    )
    parser.add_argument("--host", default="0.0.0.0", help="IPv4 address to bind")
    parser.add_argument(
        "--port", type=int, default=47999, help="UDP port to bind (default: 47999)"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="enable debug logging"
    )
    parser.add_argument(
        "--display",
        choices=("auto", "live", "lines"),
        default="auto",
        help="terminal output mode (default: live on a terminal, lines otherwise)",
    )
    parser.add_argument(
        "--refresh-hz",
        type=float,
        default=10.0,
        help="maximum status refresh rate (default: 10)",
    )
    parser.add_argument(
        "--virtual-gamepad",
        action="store_true",
        help="expose the active PSP as a virtual Xbox 360 controller",
    )
    parser.add_argument(
        "--input-timeout",
        type=float,
        default=DEFAULT_INPUT_TIMEOUT_S,
        help=(
            "seconds without fresh input before releasing the PSP session "
            "(default: 1.75; controls neutralize earlier)"
        ),
    )
    parser.add_argument(
        "--allow-client",
        action="append",
        default=[],
        metavar="IP",
        help="allow this PSP IPv4 address (repeatable; default: any address)",
    )
    parser.add_argument(
        "--pairing-token",
        metavar="CODE",
        help="five-character code shown by the PSP",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not 1 <= args.port <= 65535:
        raise SystemExit("--port must be between 1 and 65535")
    if not 0.5 <= args.refresh_hz <= 60:
        raise SystemExit("--refresh-hz must be between 0.5 and 60")
    if not 0.1 <= args.input_timeout <= 10:
        raise SystemExit("--input-timeout must be between 0.1 and 10 seconds")
    try:
        allowed_hosts = {
            str(ipaddress.IPv4Address(address)) for address in args.allow_client
        }
    except ipaddress.AddressValueError as exc:
        raise SystemExit(f"--allow-client must be an IPv4 address: {exc}") from exc
    try:
        pairing_token = (
            parse_pairing_token(args.pairing_token)
            if args.pairing_token is not None
            else None
        )
    except ValueError as exc:
        raise SystemExit(f"--pairing-token: {exc}") from exc
    if args.virtual_gamepad and pairing_token is None:
        raise SystemExit("--virtual-gamepad requires --pairing-token")

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    controller = (
        ControllerService(timeout_s=args.input_timeout)
        if args.virtual_gamepad
        else None
    )
    receiver = UdpReceiver(
        args.host,
        args.port,
        display=ControllerDisplay(
            refresh_hz=args.refresh_hz,
            mode=args.display,
        ),
        on_packet=controller.handle_snapshot if controller is not None else None,
        allowed_hosts=allowed_hosts or None,
        pairing_token=pairing_token,
        require_pairing=pairing_token is not None,
        active_client_timeout_s=args.input_timeout,
    )

    try:
        receiver.run()
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Stopping receiver")
    except OSError as exc:
        logging.getLogger(__name__).error("Network error: %s", exc)
        return 1
    finally:
        if controller is not None:
            controller.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
