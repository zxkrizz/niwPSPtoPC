"""Wi-Fi/USB receive loop and shared sequence/rate tracking."""

from __future__ import annotations

import logging
import socket
import threading
import time
from collections import OrderedDict, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum

from .display import ControllerDisplay
from .protocol import (
    PAIRING_TOKEN_MAX,
    InputPacket,
    PacketError,
    decode_packet,
    encode_pairing_ack,
)
from .usb_transport import UsbPacketSource

LOGGER = logging.getLogger(__name__)
UINT32_MASK = 0xFFFFFFFF
UINT32_HALF_RANGE = 0x80000000
MAX_CLOCK_SKEW_US = 5 * 60 * 1_000_000
DEFAULT_ACTIVE_CLIENT_TIMEOUT_S = 1.75
DEFAULT_CLIENT_RETENTION_S = 10.0
TRANSPORT_SWITCH_GRACE_S = 0.15
PAIRING_ACK_INTERVAL_S = 0.1
REJECTION_CACHE_MAX_ENTRIES = 128
REJECTION_CACHE_TTL_S = 10.0


class SequenceEvent(Enum):
    FIRST = "first"
    IN_ORDER = "in-order"
    GAP = "gap"
    DUPLICATE = "duplicate"
    OUT_OF_ORDER = "out-of-order"


class ReceiverStage(Enum):
    PORT_BOUND = "port-bound"
    DATAGRAM_RECEIVED = "datagram-received"
    VALID_PACKET = "valid-packet"
    CODE_MATCHED = "code-matched"
    ACK_SENT = "ack-sent"


class TransportKind(Enum):
    WIFI = "wifi"
    USB = "usb"


@dataclass(frozen=True, slots=True)
class ReceiverEvent:
    stage: ReceiverStage
    address: tuple[str, int] | None = None
    transport: TransportKind = TransportKind.WIFI


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
    session_token: int | None = None
    transport: TransportKind = TransportKind.WIFI


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
    transport: TransportKind = TransportKind.WIFI


@dataclass(frozen=True, slots=True)
class ReceiverMetrics:
    """Thread-safe counters used by Connection Doctor and reports."""

    datagrams_received: int
    valid_packets: int
    rejected_datagrams: int
    pairing_rejections: int
    callback_errors: int
    last_datagram_age_s: float | None
    packets_per_second: float
    loss_percent: float


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
        on_stage: Callable[[ReceiverEvent], None] | None = None,
        pairing_ack_allowed: Callable[[], bool] | None = None,
        allowed_hosts: set[str] | frozenset[str] | None = None,
        pairing_token: int | None = None,
        require_pairing: bool = False,
        active_client_timeout_s: float = DEFAULT_ACTIVE_CLIENT_TIMEOUT_S,
        client_retention_s: float = DEFAULT_CLIENT_RETENTION_S,
        socket_factory: Callable[..., socket.socket] = socket.socket,
        enable_usb: bool = False,
        usb_source_factory: Callable[
            [Callable[[bytes, Callable[[bytes], None]], None]], UsbPacketSource
        ]
        | None = None,
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
        self.on_stage = on_stage
        self.pairing_ack_allowed = pairing_ack_allowed
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
        self.enable_usb = enable_usb
        self._usb_source_factory = usb_source_factory
        self._usb_source: UsbPacketSource | None = None
        self._usb_thread: threading.Thread | None = None
        self._clients: dict[tuple[str, int], ClientState] = {}
        self._active_client: tuple[str, int] | None = None
        self._blocked_clients: set[tuple[str, int]] = set()
        self._rejected_hosts: OrderedDict[str, float] = OrderedDict()
        self._rejected_pairings: OrderedDict[
            tuple[str, int | None], float
        ] = OrderedDict()
        self._rejection_logs: OrderedDict[tuple[object, ...], float] = (
            OrderedDict()
        )
        self._last_ack_sent: dict[tuple[str, int], float] = {}
        self._datagrams_received = 0
        self._valid_packets = 0
        self._rejected_datagrams = 0
        self._pairing_rejections = 0
        self._last_datagram_at: float | None = None
        self._callback_errors = 0
        self._callback_error_counts: dict[str, int] = {}
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

    @property
    def callback_error_count(self) -> int:
        with self._clients_lock:
            return self._callback_errors

    @property
    def rejected_pairing_cache_size(self) -> int:
        with self._clients_lock:
            self._expire_cache_locked(
                self._rejected_pairings,
                time.monotonic(),
            )
            return len(self._rejected_pairings)

    def metrics(self, *, now: float | None = None) -> ReceiverMetrics:
        checked_at = time.monotonic() if now is None else now
        with self._clients_lock:
            active_state = (
                self._clients.get(self._active_client)
                if self._active_client is not None
                else None
            )
            if active_state is not None:
                cutoff = checked_at - 1.0
                while (
                    active_state.rate.arrivals
                    and active_state.rate.arrivals[0] < cutoff
                ):
                    active_state.rate.arrivals.popleft()
            packets_per_second = (
                float(len(active_state.rate.arrivals))
                if active_state is not None
                else 0.0
            )
            received = (
                active_state.sequences.received
                if active_state is not None
                else 0
            )
            lost = (
                active_state.sequences.lost
                if active_state is not None
                else 0
            )
            loss_percent = (
                (lost * 100.0) / (received + lost)
                if received + lost > 0
                else 0.0
            )
            age = (
                max(0.0, checked_at - self._last_datagram_at)
                if self._last_datagram_at is not None
                else None
            )
            return ReceiverMetrics(
                datagrams_received=self._datagrams_received,
                valid_packets=self._valid_packets,
                rejected_datagrams=self._rejected_datagrams,
                pairing_rejections=self._pairing_rejections,
                callback_errors=self._callback_errors,
                last_datagram_age_s=age,
                packets_per_second=packets_per_second,
                loss_percent=loss_percent,
            )

    def set_pairing_token(self, pairing_token: int | None) -> None:
        """Replace Wi-Fi authorization without interrupting a USB session."""
        if pairing_token is not None and not 0 <= pairing_token <= PAIRING_TOKEN_MAX:
            raise ValueError("pairing_token must be an unsigned 25-bit integer")
        with self._clients_lock:
            self._pairing_token = pairing_token
            wifi_clients = {
                address
                for address, state in self._clients.items()
                if state.transport is TransportKind.WIFI
            }
            for address in wifi_clients:
                self._clients.pop(address, None)
                self._blocked_clients.discard(address)
                self._last_ack_sent.pop(address, None)
            if self._active_client in wifi_clients:
                self._active_client = None
            self._rejected_pairings.clear()

    def disconnect_active_client(self) -> tuple[str, int] | None:
        """Release and temporarily block the current client for device change."""
        with self._clients_lock:
            address = self._active_client
            if address is not None:
                self._blocked_clients.add(address)
                self._active_client = None
            return address

    def allow_transport(self, transport: TransportKind) -> None:
        """Allow a user-disconnected transport to become active again."""
        with self._clients_lock:
            for address, state in self._clients.items():
                if state.transport is transport:
                    self._blocked_clients.discard(address)

    def request_stop(self) -> None:
        """Ask a running receive loop to stop within its socket timeout."""
        self._stop_event.set()
        if self._usb_source is not None:
            self._usb_source.request_stop()

    def run(self) -> None:
        if self.enable_usb:
            source_factory = self._usb_source_factory or (
                lambda callback: UsbPacketSource(callback)
            )
            self._usb_source = source_factory(self._handle_usb_data)
            self._usb_thread = threading.Thread(
                target=self._usb_source.run,
                name="niwPSPtoPC USB receiver",
                daemon=True,
            )
            self._usb_thread.start()
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
                self._invoke_callback(
                    "on_listening",
                    self.on_listening,
                    (listening_address[0], listening_address[1]),
                )
                self._emit_stage(
                    ReceiverStage.PORT_BOUND,
                    (listening_address[0], listening_address[1]),
                )

                while not self._stop_event.is_set():
                    try:
                        data, address = sock.recvfrom(2048)
                    except TimeoutError:
                        self._maintain_clients(time.monotonic())
                        continue

                    self._process_data(
                        data,
                        address,
                        TransportKind.WIFI,
                        lambda ack, target=address: sock.sendto(ack, target),
                    )
        finally:
            if self._usb_source is not None:
                self._usb_source.request_stop()
            if self._usb_thread is not None:
                self._usb_thread.join(timeout=1.0)
            if self.display is not None:
                self.display.finish()

    def _handle_usb_data(
        self,
        data: bytes,
        send_reply: Callable[[bytes], None],
    ) -> None:
        self._process_data(
            data,
            ("usb", 0),
            TransportKind.USB,
            send_reply,
        )

    def _process_data(
        self,
        data: bytes,
        address: tuple[str, int],
        transport: TransportKind,
        send_ack: Callable[[bytes], object],
    ) -> ReceiverSnapshot | None:
        received_at = time.monotonic()
        with self._clients_lock:
            self._datagrams_received += 1
            self._last_datagram_at = received_at
        self._emit_stage(ReceiverStage.DATAGRAM_RECEIVED, address, transport)
        try:
            packet = decode_packet(data)
        except PacketError as exc:
            with self._clients_lock:
                self._rejected_datagrams += 1
            if self.display is not None:
                self.display.break_line()
            self._log_rejection(
                ("decode", transport.value, address[0], str(exc)),
                "Rejected %d-byte %s packet from %s:%d: %s",
                len(data),
                transport.value,
                address[0],
                address[1],
                exc,
            )
            return None

        if (
            transport is TransportKind.WIFI
            and self.allowed_hosts is not None
            and address[0] not in self.allowed_hosts
        ):
            with self._clients_lock:
                self._rejected_datagrams += 1
                should_log = self._remember_cache_entry_locked(
                    self._rejected_hosts,
                    address[0],
                    received_at,
                )
            if should_log:
                LOGGER.warning(
                    "Ignoring client %s:%d: address is not allowed",
                    address[0],
                    address[1],
                )
            return None

        self._emit_stage(ReceiverStage.VALID_PACKET, address, transport)
        snapshot = self._handle_packet(
            packet,
            address,
            transport=transport,
            now_monotonic=received_at,
        )
        with self._clients_lock:
            if snapshot is None:
                self._rejected_datagrams += 1
            else:
                self._valid_packets += 1
        if transport is TransportKind.USB:
            # A cable is a local, physical trust boundary. The session token
            # is still echoed in the ACK so the PSP can detect receiver
            # readiness, but the user does not have to type it.
            ack_token = packet.session_token
            authorization_ready = ack_token is not None
        else:
            with self._clients_lock:
                configured_token = self._pairing_token
            ack_token = configured_token
            authorization_ready = (
                configured_token is not None
                and packet.session_token == configured_token
            )
        if snapshot is not None and authorization_ready:
            self._emit_stage(ReceiverStage.CODE_MATCHED, address, transport)
        if (
            snapshot is not None
            and snapshot.is_active_client
            and authorization_ready
            and ack_token is not None
            and self._pairing_ack_is_allowed()
        ):
            now = time.monotonic()
            last_ack = self._last_ack_sent.get(address)
            if last_ack is not None and now - last_ack < PAIRING_ACK_INTERVAL_S:
                return snapshot
            try:
                send_ack(encode_pairing_ack(ack_token))
            except (OSError, RuntimeError) as exc:
                LOGGER.debug(
                    "Could not send pairing ACK over %s to %s:%d: %s",
                    transport.value,
                    address[0],
                    address[1],
                    exc,
                )
            else:
                self._last_ack_sent[address] = now
                self._emit_stage(ReceiverStage.ACK_SENT, address, transport)
        return snapshot

    def _handle_packet(
        self,
        packet: InputPacket,
        address: tuple[str, int],
        *,
        transport: TransportKind = TransportKind.WIFI,
        now_monotonic: float | None = None,
    ) -> ReceiverSnapshot | None:
        if now_monotonic is None:
            now_monotonic = time.monotonic()
        with self._clients_lock:
            if (
                self.require_pairing
                and transport is TransportKind.WIFI
                and (
                    self._pairing_token is None
                    or packet.session_token != self._pairing_token
                )
            ):
                rejected = (address[0], packet.session_token)
                self._pairing_rejections += 1
                if self._remember_cache_entry_locked(
                    self._rejected_pairings,
                    rejected,
                    now_monotonic,
                ):
                    LOGGER.info(
                        "Waiting for pairing: ignored session from %s:%d",
                        address[0],
                        address[1],
                    )
                return None
            self._maintain_clients_locked(now_monotonic)
            state = self._clients.setdefault(address, ClientState())
            if (
                state.session_token is not None
                and packet.session_token != state.session_token
            ):
                # The token identifies a PSP application session. USB always
                # uses the same synthetic address, so a relaunch must not
                # inherit sequence state from the previous process.
                state.sequences = SequenceTracker()
                state.rate = RateTracker()
                state.inactive_warning_logged = False
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
            state.session_token = packet.session_token
            state.transport = transport
            state.last_seen = now_monotonic
            transport_switched = False
            if (
                self._active_client is None
                and address not in self._blocked_clients
            ):
                self._active_client = address
                state.inactive_warning_logged = False
                LOGGER.info(
                    "Selected active PSP client %s:%d", address[0], address[1]
                )
            elif (
                self._active_client != address
                and address not in self._blocked_clients
            ):
                active_state = self._clients.get(self._active_client)
                if (
                    active_state is not None
                    and active_state.transport is not transport
                    and active_state.session_token is not None
                    and active_state.session_token == packet.session_token
                    and now_monotonic - active_state.last_fresh_state
                    >= TRANSPORT_SWITCH_GRACE_S
                ):
                    LOGGER.info(
                        "Switched active PSP transport from %s to %s",
                        active_state.transport.value,
                        transport.value,
                    )
                    self._active_client = address
                    state.inactive_warning_logged = False
                    transport_switched = True

            if transport_switched:
                # Each endpoint has its own history. Restart its tracker at the
                # handoff so packets sent through the other transport are not
                # reported as loss or mistaken for stale input on return.
                state.sequences = SequenceTracker()
                state.rate = RateTracker()
                state.last_fresh_state = 0.0

            sequence_result = state.sequences.observe(packet.sequence)
            packets_per_second = state.rate.observe(now_monotonic)
            if sequence_result.event in {
                SequenceEvent.FIRST,
                SequenceEvent.IN_ORDER,
                SequenceEvent.GAP,
            }:
                state.last_fresh_state = now_monotonic

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
                transport=transport,
            )

        latency_ms = snapshot.latency_ms

        if sequence_result.event is SequenceEvent.GAP:
            if self.display is not None:
                self.display.break_line()
            self._log_rejection(
                ("sequence-gap", address),
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
            self._log_rejection(
                ("sequence", sequence_result.event.value, address),
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
        self._invoke_callback(
            "on_diagnostic",
            self.on_diagnostic,
            snapshot,
        )
        if is_state_update:
            self._invoke_callback(
                "on_packet",
                self.on_packet,
                snapshot,
            )
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
            self._last_ack_sent.pop(address, None)

    def _emit_stage(
        self,
        stage: ReceiverStage,
        address: tuple[str, int] | None = None,
        transport: TransportKind = TransportKind.WIFI,
    ) -> None:
        self._invoke_callback(
            "on_stage",
            self.on_stage,
            ReceiverEvent(stage, address, transport),
        )

    @staticmethod
    def _expire_cache_locked(
        cache: OrderedDict[object, float],
        now: float,
    ) -> None:
        cutoff = now - REJECTION_CACHE_TTL_S
        while cache:
            _key, seen_at = next(iter(cache.items()))
            if seen_at > cutoff:
                break
            cache.popitem(last=False)

    def _remember_cache_entry_locked(
        self,
        cache: OrderedDict[object, float],
        key: object,
        now: float,
    ) -> bool:
        self._expire_cache_locked(cache, now)
        if key in cache:
            cache.move_to_end(key)
            cache[key] = now
            return False
        cache[key] = now
        while len(cache) > REJECTION_CACHE_MAX_ENTRIES:
            cache.popitem(last=False)
        return True

    def _log_rejection(
        self,
        key: tuple[object, ...],
        message: str,
        *args: object,
    ) -> None:
        now = time.monotonic()
        with self._clients_lock:
            should_log = self._remember_cache_entry_locked(
                self._rejection_logs,
                key,
                now,
            )
        if should_log:
            LOGGER.warning(message, *args)

    def _invoke_callback(
        self,
        name: str,
        callback: Callable[[object], None] | None,
        value: object,
    ) -> None:
        if callback is None:
            return
        try:
            callback(value)
        except Exception:
            with self._clients_lock:
                self._callback_errors += 1
                count = self._callback_error_counts.get(name, 0) + 1
                self._callback_error_counts[name] = count
            # Preserve the first failures and exponentially spaced reminders
            # without flooding logs at the controller packet rate.
            if count <= 3 or count & (count - 1) == 0:
                LOGGER.exception(
                    "Receiver callback %s failed (%d failure%s)",
                    name,
                    count,
                    "" if count == 1 else "s",
                )

    def _pairing_ack_is_allowed(self) -> bool:
        """Fail closed when the product cannot confirm controller readiness."""
        callback = self.pairing_ack_allowed
        if callback is None:
            return True
        try:
            return bool(callback())
        except Exception:
            with self._clients_lock:
                self._callback_errors += 1
                count = self._callback_error_counts.get(
                    "pairing_ack_allowed",
                    0,
                ) + 1
                self._callback_error_counts["pairing_ack_allowed"] = count
            if count <= 3 or count & (count - 1) == 0:
                LOGGER.exception(
                    "Receiver callback pairing_ack_allowed failed "
                    "(%d failure%s)",
                    count,
                    "" if count == 1 else "s",
                )
            return False
