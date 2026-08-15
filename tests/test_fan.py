"""Tests for Eltako ventilation fans."""
import unittest
from unittest import mock

from eltakobus import AddressExpression, EEP
from eltakobus.eep import CentralCommandDimming
from eltakobus.message import ESP2Message, RPSMessage, Regular4BSMessage
from homeassistant.helpers.entity import Entity

from custom_components.eltako.fan import EltakoFan, Platform
from tests.mocks import GatewayMock


Entity.schedule_update_ha_state = mock.Mock(return_value=None)


class TestEltakoFan(unittest.TestCase):
    """Test fan commands, status decoding and restore behavior."""

    def setUp(self) -> None:
        self.sent: list[ESP2Message] = []
        self.gateway = GatewayMock()
        self.sender_id = AddressExpression.parse("00-00-B0-01")
        self.device_id = AddressExpression.parse("00-00-00-01")

    def create_fan(self, eep: str) -> EltakoFan:
        fan = EltakoFan(
            Platform.FAN,
            self.gateway,
            self.device_id,
            "Fan",
            EEP.find(eep),
            self.sender_id,
            EEP.find("A5-38-08"),
        )
        fan.send_message = self.sent.append
        return fan

    def test_dimmable_fan_sends_percentage(self) -> None:
        fan = self.create_fan("A5-38-08")

        fan.set_percentage(45)

        self.assertEqual(len(self.sent), 1)
        self.assertIsInstance(self.sent[0], Regular4BSMessage)
        decoded = EEP.find("A5-38-08").decode_message(self.sent[0])
        self.assertEqual(decoded.command, 2)
        self.assertEqual(decoded.dimming.dimming_value, 45)
        self.assertEqual(decoded.dimming.switching_command, 1)

    def test_switchable_fan_sends_on_and_off(self) -> None:
        fan = self.create_fan("M5-38-08")

        fan.turn_on()
        fan.turn_off()

        self.assertEqual(len(self.sent), 2)
        self.assertTrue(all(isinstance(message, Regular4BSMessage) for message in self.sent))
        on = EEP.find("A5-38-08").decode_message(self.sent[0])
        off = EEP.find("A5-38-08").decode_message(self.sent[1])
        self.assertEqual(on.switching.switching_command, 1)
        self.assertEqual(off.switching.switching_command, 0)

    def test_dimmable_fan_decodes_status(self) -> None:
        fan = self.create_fan("A5-38-08")
        message = EEP.find("A5-38-08")(  # type: ignore[operator]
            command=2,
            dimming=CentralCommandDimming(63, 0, 1, 0, 0, 1),
        ).encode_message(self.device_id[0])

        fan.value_changed(message)

        self.assertEqual(fan.percentage, 63)
        self.assertEqual(fan.state, "on")

    def test_switchable_fan_decodes_status(self) -> None:
        fan = self.create_fan("M5-38-08")
        message = EEP.find("M5-38-08")(1).encode_message(self.device_id[0])  # type: ignore[operator]

        fan.value_changed(message)

        self.assertEqual(fan.percentage, 100)
        self.assertEqual(fan.state, "on")

    def test_invalid_message_is_ignored(self) -> None:
        fan = self.create_fan("M5-38-08")
        message = RPSMessage(
            address=self.device_id[0], status=b"\x30", data=b"\x50", outgoing=False
        )

        fan.value_changed(message)

        self.assertEqual(fan.percentage, 0)
