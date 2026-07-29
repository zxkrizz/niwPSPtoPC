"""UDP receive loop and sequence/rate tracking."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum
import logging
import socket
import threading
import time
from typing import Callable

from .display import ControllerDisplay
from .protocol import (
    PAIRING_TOKEN_MAX,
    InputPacket,
    PacketError,
    decode_packet,
    encode_pairing_ack,
)

LOGGER = logging.getLogger(__name__)
UINT32_MASK = 0xFFFFFFFF
UINT32_HALF_RANGE = 0x80000000
MAX_CLOCK_SKEW_US = 5 * 60 * 1_000_000
DEFAULT_ACTIVE_CLIENT_TIMEOUT_S = 1.5
DEFAULT_CLIENT_RETENTION_S = 10.0


class SequenceEvent(Enum):
    FIRST = "first"
    IN_ORDER = "in-order"
    GAP = "gap"
    DUPLICATE = "duplicate"
    OUT_OF_ORDER = "out-of-order"


@dataclass(frozen=True, slots=True)
class SequenceResult:
    event: SequenceEvent
    lost: int = 0


@dataclass(slots=True)
class SequenceTracker:
    """Track a uint32 sequence in serial-number arithmetic."""

    last_sequence: int | None = None
    received: int = 0
    lost: int = 0
    duplicates: int = 0
    out_of_order: int = 0

    def observe(self, sequence: int) -> SequenceResult:
        if not 0 <= sequence <= UINT32_MASK:
            raise ValueError("sequence must be an unsigned 32-bit integer")

        self.received += 1
        if self.last_sequence is None:
            self.last_sequence = sequence
            return SequenceResult(SequenceEvent.FIRST)

        delta = (sequence - self.last_sequence) & UINT32_MASK
        if delta == 0:
            self.duplicates += 1
            return SequenceResult(SequenceEvent.DUPLICATE)

        # A forward delta smaller than half the sequence space is newer.
        # This handles 0xFFFFFFFF -> 0 without a special case.
        if delta < UINT32_HALF_RANGE:
            self.last_sequence = sequence
            if delta == 1:
                return SequenceResult(SequenceEvent.IN_ORDER)

            lost_now = delta - 1
            self.lost += lost_now
            return SequenceResult(SequenceEvent.GAP, lost=lost_now)

        self.out_of_order += 1
        return SequenceResult(SequenceEvent.OUT_OF_ORDER)


@dataclass(slots=True)
class RateTracker:
    arrivals: deque[float] = field(default_factory=deque)

    def observe(self, now: float) -> float:
        self.arrivals.append(now)
        cutoff = now - 1.0
        while self.arrivals and self.arrivals[0] < cutoff:
            self.arrivals.popleft()
        return float(len(self.arrivals))


@dataclass(slots=True)
class ClientState:
    sequences: SequenceTracker = field(default_factory=SequenceTracker)
    rate: RateTracker = field(default_factory=RateTracker)
    last_seen: float = 0.0
    last_fresh_state: float = 0.0
    inactive_warning_logged: bool = False


@dataclass(frozen=True, slots=True)
class ReceiverSnapshot:
    """One validated datagram with diagnostic and routing information."""

    packet: InputPacket
    address: tuple[str, int]
    packets_per_second: float
    latency_ms: float | None
    sequence_result: SequenceResult
    received: int
    lost: int
    duplicates: int
    out_of_order: int
    is_active_client: bool
    is_state_update: bool


def estimate_latency_ms(
    packet_timestamp_us: int, arrival_epoch_us: int | None = None
) -> float | None:
    """Return one-way latency only when timestamps look epoch-synchronized.

    PSP packets normally contain PSP uptime, so this deliberately returns
    None for them instead of presenting a misleading absolute latency.
    """
    if arrival_epoch_us is None:
        arrival_epoch_us = time.time_ns() // 1_000
    latency_us = arrival_epoch_us - packet_timestamp_us
    if latency_us < 0 or latency_us > MAX_CLOCK_SKEW_US:
        return None
    return latency_us / 1_000.0


class UdpReceiver:
    def __init__(
        self,
        host: str,
        port: int,
        *,
        display: ControllerDisplay | None = None,
        on_packet: Callable[[ReceiverSnapshot], None] | None = None,
        on_diagnostic: Callable[[ReceiverSnapshot], None] | None = None,
        on_listening: Callable[[tuple[str, int]], None] | None = None,
        allowed_hosts: set[str] | frozenset[str] | None = None,
        pairing_token: int | None = None,
        require_pairing: bool = False,
        active_client_timeout_s: float = DEFAULT_ACTIVE_CLIENT_TIMEOUT_S,
        client_retention_s: float = DEFAULT_CLIENT_RETENTION_S,
        socket_factory: Callable[..., socket.socket] = socket.socket,
    ) -> None:
        if active_client_timeout_s <= 0:
            raise ValueError("active_client_timeout_s must be positive")
        if client_retention_s < active_client_timeout_s:
            raise ValueError(
                "client_retention_s must be at least active_client_timeout_s"
            )
        self.host = host
        self.port = port
        self.display = display
        self.on_packet = on_packet
        self.on_diagnostic = on_diagnostic
        self.on_listening = on_listening
        self.allowed_hosts = (
            frozenset(allowed_hosts) if allowed_hosts is not None else None
        )
        if pairing_token is not None and not 0 <= pairing_token <= PAIRING_TOKEN_MAX:
            raise ValueError("pairing_token must be an unsigned 25-bit integer")
        self.require_pairing = require_pairing
        self._pairing_token = pairing_token
        self.active_client_timeout_s = active_client_timeout_s
        self.client_retention_s = client_retention_s
        self._socket_factory = socket_factory
        self._clients: dict[tuple[str, int], ClientState] = {}
        self._active_client: tuple[str, int] | None = None
        self._blocked_clients: set[tuple[str, int]] = set()
        self._rejected_hosts: set[str] = set()
        self._rejected_pairings: set[tuple[str, int | None]] = set()
        self._clients_lock = threading.RLock()
        self._stop_event = threading.Event()

    @property
    def active_client(self) -> tuple[str, int] | None:
        with self._clients_lock:
            return self._active_client

    @property
    def client_count(self) -> int:
        with self._clients_lock:
            return len(self._clients)

    @property
    def pairing_token(self) -> int | None:
        with self._clients_lock:
            return self._pairing_token

    def set_pairing_token(self, pairing_token: int | None) -> None:
        """Replace the authorized session and forget all previous clients."""
        if pairing_token is not None and not 0 <= pairing_token <= PAIRING_TOKEN_MAX:
            raise ValueError("pairing_token must be an unsigned 25-bit integer")
        with self._clients_lock:
            self._pairing_token = pairing_token
            self._clients.clear()
            self._active_client = None
            self._blocked_clients.clear()
            self._rejected_pairings.clear()

    def disconnect_active_client(self) -> tuple[str, int] | None:
        """Release and temporarily block the current client for device change."""
        with self._clients_lock:
            address = self._active_client
            if address is not None:
                self._blocked_clients.add(address)
                self._active_client = None
            return address

    def request_stop(self) -> None:
        """Ask a running receive loop to stop within its socket timeout."""
        self._stop_event.set()

    def run(self) -> None:
        try:
            with self._socket_factory(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.bind((self.host, self.port))
                sock.settimeout(0.2)
                listening_address = sock.getsockname()
                LOGGER.info(
                    "Listening for PSP input on udp://%s:%d",
                    listening_address[0],
                    listening_address[1],
                )
                if self.on_listening is not None:
                    self.on_listening(
                        (listening_address[0], listening_address[1])
                    )

                while not self._stop_event.is_set():
                    try:
                        data, address = sock.recvfrom(2048)
                    except socket.timeout:
                        self._maintain_clients(time.monotonic())
                        continue

                    try:
                        packet = decode_packet(data)
                    except PacketError as exc:
                        if self.display is not None:
                            self.display.break_line()
                        LOGGER.warning(
                            "Rejected %d-byte datagram from %s:%d: %s",
                            len(data),
                            address[0],
                            address[1],
                            exc,
                        )
                        continue

                    if (
                        self.allowed_hosts is not None
                        and address[0] not in self.allowed_hosts
                    ):
                        if address[0] not in self._rejected_hosts:
                            self._rejected_hosts.add(address[0])
                            LOGGER.warning(
                                "Ignoring client %s:%d: address is not allowed",
                                address[0],
                                address[1],
                            )
                        continue

                    snapshot = self._handle_packet(packet, address)
                    if (
                        snapshot is not None
                        and snapshot.is_active_client
                        and self._pairing_token is not None
                        and packet.session_token == self._pairing_token
                    ):
                        try:
                            sock.sendto(
                                encode_pairing_ack(self._pairing_token),
                                address,
                            )
                        except OSError as exc:
                            LOGGER.debug(
                                "Could not send pairing ACK to %s:%d: %s",
                                address[0],
                                address[1],
                                exc,
                            )
        finally:
            if self.display is not None:
                self.display.finish()

    def _handle_packet(
        self,
        packet: InputPacket,
        address: tuple[str, int],
        *,
        now_monotonic: float | None = None,
    ) -> ReceiverSnapshot | None:
        if now_monotonic is None:
            now_monotonic = time.monotonic()
        with self._clients_lock:
            if self.require_pairing and (
                self._pairing_token is None
                or packet.session_token != self._pairing_token
            ):
                rejected = (address[0], packet.session_token)
                if rejected not in self._rejected_pairings:
                    self._rejected_pairings.add(rejected)
                    LOGGER.info(
                        "Waiting for pairing: ignored session from %s:%d",
                        address[0],
                        address[1],
                    )
                return None
            self._maintain_clients_locked(now_monotonic)
            state = self._clients.setdefault(address, ClientState())
            if (
                state.last_seen > 0
                and now_monotonic - state.last_seen
                >= self.active_client_timeout_s
            ):
                # After a full safety timeout, treat the next accepted packet
                # as a new session so a PSP process restart at the same
                # IP:port can restart at seq=0.
                state.sequences = SequenceTracker()
                state.rate = RateTracker()
                state.inactive_warning_logged = False
            state.last_seen = now_monotonic
            sequence_result = state.sequences.observe(packet.sequence)
            packets_per_second = state.rate.observe(now_monotonic)
            if sequence_result.event in {
                SequenceEvent.FIRST,
                SequenceEvent.IN_ORDER,
                SequenceEvent.GAP,
            }:
                state.last_fresh_state = now_monotonic

            if (
                self._active_client is None
                and address not in self._blocked_clients
            ):
                self._active_client = address
                state.inactive_warning_logged = False
                LOGGER.info(
                    "Selected active PSP client %s:%d", address[0], address[1]
                )

            is_active_client = address == self._active_client
            if not is_active_client and not state.inactive_warning_logged:
                state.inactive_warning_logged = True
                LOGGER.warning(
                    "Ignoring controller state from inactive client %s:%d",
                    address[0],
                    address[1],
                )

            is_state_update = is_active_client and sequence_result.event in {
                SequenceEvent.FIRST,
                SequenceEvent.IN_ORDER,
                SequenceEvent.GAP,
            }
            snapshot = ReceiverSnapshot(
                packet=packet,
                address=address,
                packets_per_second=packets_per_second,
                latency_ms=estimate_latency_ms(packet.timestamp_us),
                sequence_result=sequence_result,
                received=state.sequences.received,
                lost=state.sequences.lost,
                duplicates=state.sequences.duplicates,
                out_of_order=state.sequences.out_of_order,
                is_active_client=is_active_client,
                is_state_update=is_state_update,
            )

        latency_ms = snapshot.latency_ms

        if sequence_result.event is SequenceEvent.GAP:
            if self.display is not None:
                self.display.break_line()
            LOGGER.warning(
                "Lost %d packet(s) from %s:%d before sequence %d",
                sequence_result.lost,
                address[0],
                address[1],
                packet.sequence,
            )
        elif sequence_result.event in {
            SequenceEvent.DUPLICATE,
            SequenceEvent.OUT_OF_ORDER,
        }:
            if self.display is not None:
                self.display.break_line()
            LOGGER.warning(
                "%s packet from %s:%d: sequence %d",
                sequence_result.event.value,
                address[0],
                address[1],
                packet.sequence,
            )

        if self.display is not None and is_active_client:
            self.display.render(
                packet=packet,
                address=address,
                packets_per_second=packets_per_second,
                latency_ms=latency_ms,
                sequence_result=sequence_result,
                tracker=state.sequences,
            )
        if self.on_diagnostic is not None:
            self.on_diagnostic(snapshot)
        if self.on_packet is not None and is_state_update:
            self.on_packet(snapshot)
        return snapshot

    def _maintain_clients(self, now: float) -> None:
        with self._clients_lock:
            self._maintain_clients_locked(now)

    def _maintain_clients_locked(self, now: float) -> None:
        if self._active_client is not None:
            active_state = self._clients.get(self._active_client)
            if (
                active_state is None
                or now - active_state.last_fresh_state
                >= self.active_client_timeout_s
            ):
                LOGGER.info("Active PSP client timed out")
                self._active_client = None

        expired = [
            address
            for address, state in self._clients.items()
            if now - state.last_seen >= self.client_retention_s
        ]
        for address in expired:
            del self._clients[address]
            self._blocked_clients.discard(address)
