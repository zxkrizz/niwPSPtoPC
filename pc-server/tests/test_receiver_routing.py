from __future__ import annotations

import socket
import threading
import time
import unittest

from pc_server.protocol import (
    Buttons,
    InputPacket,
    decode_pairing_ack,
    encode_packet,
    parse_pairing_token,
)
from pc_server.receiver import ReceiverStage, SequenceEvent, UdpReceiver


def packet(
    sequence: int,
    buttons: int = 0,
    *,
    session_token: int = 0,
) -> InputPacket:
    return InputPacket(
        sequence=sequence,
        buttons=buttons,
        analog_x=128,
        analog_y=128,
        timestamp_us=100,
        session_token=session_token,
    )


class ReceiverRoutingTests(unittest.TestCase):
    def test_rejected_pairing_cache_is_bounded(self) -> None:
        expected = parse_pairing_token("ABCDE")
        receiver = UdpReceiver(
            "127.0.0.1",
            0,
            pairing_token=expected,
            require_pairing=True,
        )
        now = time.monotonic()

        for token in range(200):
            receiver._handle_packet(
                packet(token, session_token=token),
                ("10.0.0.33", 51060),
                now_monotonic=now,
            )

        self.assertEqual(receiver.rejected_pairing_cache_size, 128)
        receiver._handle_packet(
            packet(201, session_token=999),
            ("10.0.0.33", 51060),
            now_monotonic=now + 11.0,
        )
        self.assertEqual(receiver.rejected_pairing_cache_size, 1)

    def test_pairing_rejects_wrong_session_before_client_selection(self) -> None:
        expected = parse_pairing_token("ABCDE")
        states = []
        diagnostics = []
        receiver = UdpReceiver(
            "127.0.0.1",
            0,
            pairing_token=expected,
            require_pairing=True,
            on_packet=states.append,
            on_diagnostic=diagnostics.append,
        )
        address = ("10.0.0.33", 51060)

        rejected = receiver._handle_packet(
            packet(0, session_token=parse_pairing_token("FGHJK")),
            address,
        )
        accepted = receiver._handle_packet(
            packet(0, session_token=expected),
            address,
        )

        self.assertIsNone(rejected)
        self.assertIsNotNone(accepted)
        self.assertEqual(receiver.active_client, address)
        self.assertEqual(len(states), 1)
        self.assertEqual(len(diagnostics), 1)

    def test_changing_pairing_token_forgets_previous_client(self) -> None:
        first_token = parse_pairing_token("ABCDE")
        receiver = UdpReceiver(
            "127.0.0.1",
            0,
            pairing_token=first_token,
            require_pairing=True,
        )
        receiver._handle_packet(
            packet(0, session_token=first_token),
            ("10.0.0.33", 51060),
        )

        receiver.set_pairing_token(parse_pairing_token("FGHJK"))

        self.assertIsNone(receiver.active_client)
        self.assertEqual(receiver.client_count, 0)

    def test_state_callback_filters_duplicate_and_out_of_order(self) -> None:
        states = []
        diagnostics = []
        receiver = UdpReceiver(
            "127.0.0.1",
            0,
            on_packet=states.append,
            on_diagnostic=diagnostics.append,
        )
        address = ("10.0.0.33", 51060)

        for value in (packet(10), packet(10), packet(9), packet(13)):
            receiver._handle_packet(value, address)

        self.assertEqual(
            [item.packet.sequence for item in states],
            [10, 13],
        )
        self.assertEqual(
            [item.sequence_result.event for item in diagnostics],
            [
                SequenceEvent.FIRST,
                SequenceEvent.DUPLICATE,
                SequenceEvent.OUT_OF_ORDER,
                SequenceEvent.GAP,
            ],
        )
        self.assertEqual(diagnostics[-1].duplicates, 1)
        self.assertEqual(diagnostics[-1].out_of_order, 1)
        self.assertEqual(diagnostics[-1].lost, 2)

    def test_broken_diagnostic_callback_does_not_block_state_callback(self) -> None:
        states = []

        def broken_diagnostic(_snapshot: object) -> None:
            raise RuntimeError("diagnostic frontend failed")

        receiver = UdpReceiver(
            "127.0.0.1",
            0,
            on_packet=states.append,
            on_diagnostic=broken_diagnostic,
        )
        address = ("10.0.0.33", 51060)

        receiver._handle_packet(packet(1), address)
        receiver._handle_packet(packet(2), address)

        self.assertEqual(
            [snapshot.packet.sequence for snapshot in states],
            [1, 2],
        )
        self.assertEqual(receiver.callback_error_count, 2)

    def test_first_client_is_locked_until_released(self) -> None:
        states = []
        receiver = UdpReceiver("127.0.0.1", 0, on_packet=states.append)
        first = ("10.0.0.33", 51060)
        second = ("10.0.0.44", 52000)

        first_snapshot = receiver._handle_packet(
            packet(0, int(Buttons.CROSS)), first, now_monotonic=1.0
        )
        second_snapshot = receiver._handle_packet(
            packet(0, int(Buttons.CIRCLE)), second, now_monotonic=1.1
        )

        self.assertTrue(first_snapshot.is_state_update)
        self.assertFalse(second_snapshot.is_active_client)
        self.assertFalse(second_snapshot.is_state_update)
        self.assertEqual(receiver.active_client, first)
        self.assertEqual([item.address for item in states], [first])

        self.assertEqual(receiver.disconnect_active_client(), first)
        blocked_snapshot = receiver._handle_packet(
            packet(1), first, now_monotonic=1.2
        )
        selected_snapshot = receiver._handle_packet(
            packet(1), second, now_monotonic=1.3
        )

        self.assertFalse(blocked_snapshot.is_state_update)
        self.assertTrue(selected_snapshot.is_state_update)
        self.assertEqual(receiver.active_client, second)

    def test_inactive_clients_expire_and_active_lock_times_out(self) -> None:
        receiver = UdpReceiver(
            "127.0.0.1",
            0,
            active_client_timeout_s=1.5,
            client_retention_s=3.0,
        )
        first = ("10.0.0.33", 51060)
        second = ("10.0.0.44", 52000)
        receiver._handle_packet(packet(0), first, now_monotonic=10.0)

        snapshot = receiver._handle_packet(
            packet(0), second, now_monotonic=11.51
        )

        self.assertTrue(snapshot.is_state_update)
        self.assertEqual(receiver.active_client, second)
        receiver._maintain_clients(13.1)
        self.assertEqual(receiver.client_count, 1)

    def test_duplicates_do_not_keep_active_client_alive(self) -> None:
        receiver = UdpReceiver(
            "127.0.0.1",
            0,
            active_client_timeout_s=1.5,
            client_retention_s=3.0,
        )
        first = ("10.0.0.33", 51060)
        receiver._handle_packet(packet(10), first, now_monotonic=10.0)
        receiver._handle_packet(packet(10), first, now_monotonic=11.0)

        receiver._maintain_clients(11.51)

        self.assertIsNone(receiver.active_client)

    def test_same_address_can_start_new_sequence_after_session_timeout(self) -> None:
        states = []
        receiver = UdpReceiver(
            "127.0.0.1",
            0,
            on_packet=states.append,
            active_client_timeout_s=1.5,
            client_retention_s=3.0,
        )
        address = ("10.0.0.33", 51060)
        receiver._handle_packet(packet(500), address, now_monotonic=10.0)

        restarted = receiver._handle_packet(
            packet(0), address, now_monotonic=11.51
        )

        self.assertEqual(restarted.sequence_result.event, SequenceEvent.FIRST)
        self.assertTrue(restarted.is_state_update)
        self.assertEqual(restarted.received, 1)
        self.assertEqual([item.packet.sequence for item in states], [500, 0])

    def test_allowlist_rejects_other_host_in_socket_loop(self) -> None:
        diagnostics = []
        listening = threading.Event()
        address_holder: list[tuple[str, int]] = []
        receiver = UdpReceiver(
            "127.0.0.1",
            0,
            allowed_hosts={"192.0.2.10"},
            on_diagnostic=diagnostics.append,
            on_listening=lambda address: (
                address_holder.append(address),
                listening.set(),
            ),
        )
        thread = threading.Thread(target=receiver.run, daemon=True)
        thread.start()
        self.assertTrue(listening.wait(2.0))

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
            sender.sendto(encode_packet(packet(0)), address_holder[0])
        time.sleep(0.1)
        receiver.request_stop()
        thread.join(2.0)

        self.assertFalse(thread.is_alive())
        self.assertEqual(diagnostics, [])


class SocketLoopTests(unittest.TestCase):
    def test_wrong_pairing_token_receives_no_ack_or_state(self) -> None:
        expected = parse_pairing_token("ABCDE")
        wrong = parse_pairing_token("FGHJK")
        states = []
        listening = threading.Event()
        address_holder: list[tuple[str, int]] = []
        receiver = UdpReceiver(
            "127.0.0.1",
            0,
            pairing_token=expected,
            require_pairing=True,
            on_packet=states.append,
            on_listening=lambda address: (
                address_holder.append(address),
                listening.set(),
            ),
        )
        thread = threading.Thread(target=receiver.run, daemon=True)
        thread.start()
        self.assertTrue(listening.wait(2.0))

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
            sender.settimeout(0.2)
            sender.sendto(
                encode_packet(packet(0, session_token=wrong)),
                address_holder[0],
            )
            with self.assertRaises(socket.timeout):
                sender.recvfrom(128)

        receiver.request_stop()
        thread.join(2.0)

        self.assertEqual(states, [])
        self.assertIsNone(receiver.active_client)
        self.assertFalse(thread.is_alive())

    def test_authorized_socket_receives_pairing_ack(self) -> None:
        token = parse_pairing_token("ABCDE")
        state_received = threading.Event()
        listening = threading.Event()
        stages = []
        address_holder: list[tuple[str, int]] = []
        receiver = UdpReceiver(
            "127.0.0.1",
            0,
            pairing_token=token,
            require_pairing=True,
            on_packet=lambda _snapshot: state_received.set(),
            on_stage=stages.append,
            on_listening=lambda address: (
                address_holder.append(address),
                listening.set(),
            ),
        )
        thread = threading.Thread(target=receiver.run, daemon=True)
        thread.start()
        self.assertTrue(listening.wait(2.0))

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
            sender.settimeout(2.0)
            sender.sendto(
                encode_packet(packet(0, session_token=token)),
                address_holder[0],
            )
            ack, ack_address = sender.recvfrom(128)

        self.assertTrue(state_received.wait(2.0))
        receiver.request_stop()
        thread.join(2.0)

        self.assertEqual(decode_pairing_ack(ack), token)
        self.assertEqual(ack_address, address_holder[0])
        self.assertEqual(
            {event.stage for event in stages},
            {
                ReceiverStage.PORT_BOUND,
                ReceiverStage.DATAGRAM_RECEIVED,
                ReceiverStage.VALID_PACKET,
                ReceiverStage.CODE_MATCHED,
                ReceiverStage.ACK_SENT,
            },
        )
        self.assertFalse(thread.is_alive())

    def test_pairing_ack_is_rate_limited_to_ten_hz(self) -> None:
        token = parse_pairing_token("ABCDE")
        listening = threading.Event()
        address_holder: list[tuple[str, int]] = []
        receiver = UdpReceiver(
            "127.0.0.1",
            0,
            pairing_token=token,
            require_pairing=True,
            on_listening=lambda address: (
                address_holder.append(address),
                listening.set(),
            ),
        )
        thread = threading.Thread(target=receiver.run, daemon=True)
        thread.start()
        self.assertTrue(listening.wait(2.0))

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
            destination = address_holder[0]
            sender.settimeout(2.0)
            sender.sendto(
                encode_packet(packet(0, session_token=token)),
                destination,
            )
            first_ack, _ = sender.recvfrom(128)
            sender.settimeout(0.05)
            sender.sendto(
                encode_packet(packet(1, session_token=token)),
                destination,
            )
            with self.assertRaises(socket.timeout):
                sender.recvfrom(128)
            time.sleep(0.11)
            sender.settimeout(2.0)
            sender.sendto(
                encode_packet(packet(2, session_token=token)),
                destination,
            )
            second_ack, _ = sender.recvfrom(128)

        receiver.request_stop()
        thread.join(2.0)
        self.assertEqual(decode_pairing_ack(first_ack), token)
        self.assertEqual(decode_pairing_ack(second_ack), token)
        self.assertFalse(thread.is_alive())

    def test_second_client_with_same_token_receives_no_ack(self) -> None:
        token = parse_pairing_token("ABCDE")
        listening = threading.Event()
        address_holder: list[tuple[str, int]] = []
        receiver = UdpReceiver(
            "127.0.0.1",
            0,
            pairing_token=token,
            require_pairing=True,
            on_listening=lambda address: (
                address_holder.append(address),
                listening.set(),
            ),
        )
        thread = threading.Thread(target=receiver.run, daemon=True)
        thread.start()
        self.assertTrue(listening.wait(2.0))

        with (
            socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as first,
            socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as second,
        ):
            first.settimeout(2.0)
            second.settimeout(0.2)
            destination = address_holder[0]
            first.sendto(
                encode_packet(packet(0, session_token=token)),
                destination,
            )
            ack, _address = first.recvfrom(128)
            second.sendto(
                encode_packet(packet(0, session_token=token)),
                destination,
            )
            with self.assertRaises(socket.timeout):
                second.recvfrom(128)

        receiver.request_stop()
        thread.join(2.0)

        self.assertEqual(decode_pairing_ack(ack), token)
        self.assertFalse(thread.is_alive())

    def test_complete_udp_loop_keeps_only_fresh_states(self) -> None:
        states = []
        diagnostics = []
        received = threading.Event()
        listening = threading.Event()
        address_holder: list[tuple[str, int]] = []

        def on_diagnostic(snapshot: object) -> None:
            diagnostics.append(snapshot)
            if len(diagnostics) >= 4:
                received.set()

        receiver = UdpReceiver(
            "127.0.0.1",
            0,
            on_packet=states.append,
            on_diagnostic=on_diagnostic,
            on_listening=lambda address: (
                address_holder.append(address),
                listening.set(),
            ),
        )
        thread = threading.Thread(target=receiver.run, daemon=True)
        thread.start()
        self.assertTrue(listening.wait(2.0))

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
            destination = address_holder[0]
            for value in (packet(10), packet(10), packet(9), packet(13)):
                sender.sendto(encode_packet(value), destination)
            sender.sendto(b"invalid", destination)

        self.assertTrue(received.wait(2.0))
        receiver.request_stop()
        thread.join(2.0)

        self.assertFalse(thread.is_alive())
        self.assertEqual(
            [snapshot.packet.sequence for snapshot in states],
            [10, 13],
        )
        self.assertEqual(len(diagnostics), 4)

    def test_broken_callbacks_do_not_stop_receiving_packets(self) -> None:
        diagnostic_sequences: list[int] = []
        second_received = threading.Event()
        listening = threading.Event()
        address_holder: list[tuple[str, int]] = []

        def broken_packet_callback(_snapshot: object) -> None:
            raise RuntimeError("frontend failed")

        def diagnostic_callback(snapshot: object) -> None:
            sequence = snapshot.packet.sequence
            diagnostic_sequences.append(sequence)
            if sequence == 2:
                second_received.set()

        receiver = UdpReceiver(
            "127.0.0.1",
            0,
            on_packet=broken_packet_callback,
            on_diagnostic=diagnostic_callback,
            on_listening=lambda address: (
                address_holder.append(address),
                listening.set(),
            ),
        )
        thread = threading.Thread(target=receiver.run, daemon=True)
        thread.start()
        self.assertTrue(listening.wait(2.0))

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
            sender.sendto(encode_packet(packet(1)), address_holder[0])
            sender.sendto(encode_packet(packet(2)), address_holder[0])

        self.assertTrue(second_received.wait(2.0))
        receiver.request_stop()
        thread.join(2.0)

        self.assertFalse(thread.is_alive())
        self.assertEqual(diagnostic_sequences, [1, 2])
        self.assertEqual(receiver.callback_error_count, 2)
        metrics = receiver.metrics()
        self.assertEqual(metrics.datagrams_received, 2)
        self.assertEqual(metrics.valid_packets, 2)
        self.assertEqual(metrics.rejected_datagrams, 0)


if __name__ == "__main__":
    unittest.main()
