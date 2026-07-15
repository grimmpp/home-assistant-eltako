import asyncio
import unittest
from unittest import mock

from eltakobus import AddressExpression, EEP, Regular4BSMessage
from homeassistant.const import Platform
from homeassistant.helpers.entity import Entity

from custom_components.eltako.config_helpers import (
    CONF_FAST_STATUS_CHANGE,
    DEFAULT_GENERAL_SETTINGS,
)
from custom_components.eltako.cover import EltakoCover
from tests.mocks import GatewayMock, LatestStateMock


Entity.schedule_update_ha_state = mock.Mock(return_value=None)


class TestDefensiveCoverState(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.last_sent_command = None

    def tearDown(self):
        asyncio.set_event_loop(None)
        self.loop.close()

    def _capture_message(self, msg):
        self.last_sent_command = msg

    def _create_cover(self, *, with_tilt=False):
        settings = DEFAULT_GENERAL_SETTINGS.copy()
        settings[CONF_FAST_STATUS_CHANGE] = True
        gateway = GatewayMock(settings)
        cover = EltakoCover(
            Platform.COVER,
            gateway,
            AddressExpression.parse("00-00-00-01"),
            "device name",
            EEP.find("G5-3F-7F"),
            AddressExpression.parse("00-00-B1-07"),
            EEP.find("H5-3F-7F"),
            "blind" if with_tilt else "shutter",
            10,
            10,
            15 if with_tilt else None,
        )
        cover.send_message = self._capture_message
        return cover

    def test_restore_missing_tilt_attribute_keeps_cover_state(self):
        cover = self._create_cover()

        cover.load_value_initially(
            LatestStateMock("opening", {"current_position": 55})
        )

        self.assertEqual(cover.current_cover_position, 55)
        self.assertIsNone(cover.current_cover_tilt_position)
        self.assertTrue(cover.is_opening)
        self.assertFalse(cover.is_closing)
        self.assertFalse(cover.is_closed)

    def test_restore_missing_position_attribute_keeps_motion_state(self):
        cover = self._create_cover(with_tilt=True)

        cover.load_value_initially(
            LatestStateMock("closing", {"current_tilt_position": 10})
        )

        self.assertIsNone(cover.current_cover_position)
        self.assertEqual(cover.current_cover_tilt_position, 10)
        self.assertFalse(cover.is_opening)
        self.assertTrue(cover.is_closing)
        self.assertFalse(cover.is_closed)

    def test_restore_invalid_values_are_ignored_and_bounds_are_clamped(self):
        cover = self._create_cover(with_tilt=True)

        cover.load_value_initially(
            LatestStateMock(
                "opening",
                {
                    "current_position": "unknown",
                    "current_tilt_position": 125,
                },
            )
        )

        self.assertIsNone(cover.current_cover_position)
        self.assertEqual(cover.current_cover_tilt_position, 100)

        cover.load_value_initially(
            LatestStateMock(
                "closing",
                {
                    "current_position": -5,
                    "current_tilt_position": 20,
                },
            )
        )
        self.assertEqual(cover.current_cover_position, 0)
        self.assertEqual(cover.current_cover_tilt_position, 20)

    def test_intermediate_target_is_ignored_when_current_position_is_unknown(self):
        cover = self._create_cover()
        cover._attr_current_cover_position = None

        cover.set_cover_position(position=50)

        self.assertIsNone(self.last_sent_command)
        self.assertIsNone(cover.current_cover_position)

    def test_end_positions_work_when_current_position_is_unknown(self):
        cover = self._create_cover()
        cover._attr_current_cover_position = None

        cover.set_cover_position(position=100)
        self.assertEqual(
            self.last_sent_command.body,
            b"k\x07\x00\x0b\x01\x08\x00\x00\xb1\x07\x00",
        )

        self.last_sent_command = None
        cover._attr_current_cover_position = None
        cover.set_cover_position(position=0)
        self.assertEqual(
            self.last_sent_command.body,
            b"k\x07\x00\x0b\x02\x08\x00\x00\xb1\x07\x00",
        )

    def test_intermediate_telegram_initializes_unknown_tilt_position(self):
        cover = self._create_cover(with_tilt=True)
        cover._attr_current_cover_position = 10
        cover._attr_current_cover_tilt_position = None
        msg = Regular4BSMessage(
            address=b"\x00\x00\x00\x01",
            status=b"\x20",
            data=b"\x00\x1e\x01\x0a",
            outgoing=False,
        )

        cover.value_changed(msg)

        self.assertEqual(cover.current_cover_position, 40)
        self.assertEqual(cover.current_cover_tilt_position, 100)

    def test_tilt_target_is_ignored_when_current_tilt_is_unknown(self):
        cover = self._create_cover(with_tilt=True)
        cover._attr_current_cover_tilt_position = None

        cover.set_cover_tilt_position(tilt_position=50)

        self.assertIsNone(self.last_sent_command)
        self.assertIsNone(cover.current_cover_tilt_position)


if __name__ == "__main__":
    unittest.main()
