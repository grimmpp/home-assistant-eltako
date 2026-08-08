"""The serial reader thread must survive every telegram.

Regression test for a total loss of reception on a real installation: an EltakoDiscoveryReply
reports its address as int, b2s() raised a TypeError in telegram2json(), the exception escaped
the receive callback and killed the reader thread of the library
(eltakobus.serial.run -> self.__callback(parsed_msg)). The connection still reported
'active' while no telegram was received anymore - not even bus polling.
"""
import unittest
from unittest import TestCase

from tests.mocks import GatewayMock

from custom_components.eltako.config import config_helpers

from eltakobus.message import (
    EltakoDiscoveryReply,
    EltakoDiscoveryRequest,
    RPSMessage,
    Regular4BSMessage,
)


def discovery_reply() -> EltakoDiscoveryReply:
    """The telegram which killed the reader thread. Its reported_address is an int."""
    return EltakoDiscoveryReply(reported_address=1, reported_size=4, memory_size=0x72,
                                model=b'\x04\x01\x72\x00', is_fam=False)


class TestAddressToStr(TestCase):

    def test_bytes_become_a_hex_string(self):
        self.assertEqual(config_helpers.address_to_str(b'\xFF\xAA\x80\x01'), 'FF-AA-80-01')

    def test_int_stays_an_int(self):
        """Bus messages report the position on the bus as int."""
        self.assertEqual(config_helpers.address_to_str(8), 8)

    def test_none(self):
        self.assertIsNone(config_helpers.address_to_str(None))

    def test_address_expression(self):
        from eltakobus.util import AddressExpression
        self.assertEqual(config_helpers.address_to_str(AddressExpression.parse('FF-AA-80-01')), 'FF-AA-80-01')


class TestTelegram2Json(TestCase):

    def test_discovery_reply_does_not_raise(self):
        """This raised TypeError: 'int' object is not iterable."""
        result = config_helpers.telegram2json(discovery_reply())

        self.assertEqual(result['msg_type'], 'EltakoDiscoveryReply')
        self.assertIsNotNone(result['reported_address'])

    def test_all_values_are_serializable(self):
        import json

        for telegram in [discovery_reply(),
                         EltakoDiscoveryRequest(8),
                         RPSMessage(address=b'\x12\x34\x56\x78', status=0x30, data=b'\x10'),
                         Regular4BSMessage(address=b'\xFF\xAA\xDD\x81', status=0x00, data=b'\x01\x02\x03\x04')]:
            result = config_helpers.telegram2json(telegram)
            json.dumps(result)      # must not raise

    def test_rps_message_keeps_its_address(self):
        result = config_helpers.telegram2json(RPSMessage(address=b'\x12\x34\x56\x78', status=0x30, data=b'\x10'))

        self.assertEqual(result['address'], '12-34-56-78')
        self.assertEqual(result['data'], '10')


class TestReceiveCallbackNeverRaises(TestCase):
    """Whatever happens while processing a telegram, the reader thread has to survive."""

    def test_discovery_reply_is_processed_without_raising(self):
        """The exception of this telegram used to kill the reader thread of the library."""
        gateway = GatewayMock()

        gateway._callback_receive_message_from_serial_bus(discovery_reply())
        # reaching this line is the assertion: no exception escaped into the reader thread

    def test_a_broken_telegram_does_not_escape(self):
        gateway = GatewayMock()

        class ExplodingTelegram:
            org = 0x05
            @property
            def address(self):
                raise RuntimeError("boom")

        # must not raise
        gateway._callback_receive_message_from_serial_bus(ExplodingTelegram())

    def test_every_telegram_type_reaches_the_handler(self):
        """The wrapper must not filter anything - all telegrams have to be processed."""
        gateway = GatewayMock()
        handled = []
        gateway._handle_received_message = handled.append

        telegrams = [discovery_reply(),
                     EltakoDiscoveryRequest(8),
                     RPSMessage(address=b'\x12\x34\x56\x78', status=0x30, data=b'\x10'),
                     Regular4BSMessage(address=b'\xFF\xAA\xDD\x81', status=0x00, data=b'\x01\x02\x03\x04')]
        for telegram in telegrams:
            gateway._callback_receive_message_from_serial_bus(telegram)

        self.assertEqual(len(handled), len(telegrams))

    def test_callback_delegates_to_the_handler(self):
        """The wrapper must not swallow the processing itself."""
        gateway = GatewayMock()
        seen = []
        gateway._handle_received_message = seen.append

        gateway._callback_receive_message_from_serial_bus("telegram")

        self.assertEqual(seen, ["telegram"])


if __name__ == '__main__':
    unittest.main()
