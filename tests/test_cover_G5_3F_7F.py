import unittest
from tests.mocks import GatewayMock, LatestStateMock
from unittest import mock
from homeassistant.helpers.entity import Entity
from homeassistant.const import Platform
from homeassistant.components.cover import CoverEntityFeature
from custom_components.eltako.cover import EltakoCover
from eltakobus import AddressExpression, EEP, RPSMessage, Regular4BSMessage, asyncio
from custom_components.eltako.config.config_helpers import DEFAULT_GENERAL_SETTINGS
from custom_components.eltako.const import CONF_FAST_STATUS_CHANGE

# mock update of Home Assistant
Entity.schedule_update_ha_state = mock.Mock(return_value=None)
# EltakoEntity.send_message = mock.Mock(return_value=None)

class TestCover(unittest.TestCase):

    def mock_send_message(self, msg):
        self.last_sent_command = msg

    def create_cover(self, invert_direction=False) -> EltakoCover:
        settings = DEFAULT_GENERAL_SETTINGS
        settings[CONF_FAST_STATUS_CHANGE] = True
        gateway = GatewayMock(settings)
        dev_id = AddressExpression.parse('00-00-00-01')
        dev_name = 'device name'
        device_class = "shutter"
        time_closes = 10
        time_opens = 10
        time_tilts = None
        eep_string = "G5-3F-7F"

        sender_id = AddressExpression.parse("00-00-B1-06")
        sender_eep_string = "H5-3F-7F"

        dev_eep = EEP.find(eep_string)
        sender_eep = EEP.find(sender_eep_string)

        ec = EltakoCover(Platform.COVER, gateway, dev_id, dev_name, dev_eep, sender_id, sender_eep, device_class, time_closes, time_opens, time_tilts,
                         invert_direction=invert_direction)
        ec.send_message = self.mock_send_message

        self.assertEqual(ec._attr_is_closing, False)
        self.assertEqual(ec._attr_is_opening, False)
        self.assertEqual(ec._attr_is_closed, None)
        self.assertEqual(ec._attr_current_cover_position, None)

        return ec

    def create_blind(self) -> EltakoCover:
        settings = DEFAULT_GENERAL_SETTINGS
        settings[CONF_FAST_STATUS_CHANGE] = True
        gateway = GatewayMock(settings)
        dev_id = AddressExpression.parse('00-00-00-01')
        dev_name = 'device name'
        device_class = "blind"
        time_closes = 10
        time_opens = 10
        time_tilts = 15
        eep_string = "G5-3F-7F"

        sender_id = AddressExpression.parse("00-00-B1-07")
        sender_eep_string = "H5-3F-7F"

        dev_eep = EEP.find(eep_string)
        sender_eep = EEP.find(sender_eep_string)

        ec = EltakoCover(Platform.COVER, gateway, dev_id, dev_name, dev_eep, sender_id, sender_eep, device_class, time_closes, time_opens, time_tilts)
        ec.send_message = self.mock_send_message

        self.assertEqual(ec._attr_is_closing, False)
        self.assertEqual(ec._attr_is_opening, False)
        self.assertEqual(ec._attr_is_closed, None)
        self.assertEqual(ec._attr_current_cover_position, None)
        self.assertEqual(ec._attr_current_cover_tilt_position, None)

        return ec


    def test_cover_value_changed(self):
        ec = self.create_cover()

        # status update message form device
        # device send acknowledgement for opening
        msg = RPSMessage(address=b'\x00\x00\x00\x01', status=b'\x30', data=b'\x01', outgoing=False)
        ec.value_changed(msg)
        self.assertEqual(ec._attr_is_closing, False)
        self.assertEqual(ec._attr_is_opening, True)

        # device send acknowledgement for closing
        msg = RPSMessage(address=b'\x00\x00\x00\x01', status=b'\x30', data=b'\x02', outgoing=False)
        ec.value_changed(msg)
        self.assertEqual(ec._attr_is_closing, True)
        self.assertEqual(ec._attr_is_opening, False)

        # device send acknowledgement for closed
        msg = RPSMessage(address=b'\x00\x00\x00\x01', status=b'\x30', data=b'\x50', outgoing=False)
        ec.value_changed(msg)
        self.assertEqual(ec._attr_is_closing, False)
        self.assertEqual(ec._attr_is_opening, False)
        self.assertEqual(ec._attr_is_closed, True)
        self.assertEqual(ec._attr_current_cover_position, 0)
        self.assertEqual(ec._attr_current_cover_tilt_position, 0)

        # device send acknowledgement for opened
        msg = RPSMessage(address=b'\x00\x00\x00\x01', status=b'\x30', data=b'\x70', outgoing=False)
        ec.value_changed(msg)
        self.assertEqual(ec._attr_is_closing, False)
        self.assertEqual(ec._attr_is_opening, False)
        self.assertEqual(ec._attr_is_closed, False)
        self.assertEqual(ec._attr_current_cover_position, 100)
        self.assertEqual(ec._attr_current_cover_tilt_position, 100)



        ec = self.create_blind()

        # status update message form device
        # device send acknowledgement for opening
        msg = RPSMessage(address=b'\x00\x00\x00\x01', status=b'\x30', data=b'\x01', outgoing=False)
        ec.value_changed(msg)
        self.assertEqual(ec._attr_is_closing, False)
        self.assertEqual(ec._attr_is_opening, True)

        # device send acknowledgement for closing
        msg = RPSMessage(address=b'\x00\x00\x00\x01', status=b'\x30', data=b'\x02', outgoing=False)
        ec.value_changed(msg)
        self.assertEqual(ec._attr_is_closing, True)
        self.assertEqual(ec._attr_is_opening, False)

        # device send acknowledgement for closed
        msg = RPSMessage(address=b'\x00\x00\x00\x01', status=b'\x30', data=b'\x50', outgoing=False)
        ec.value_changed(msg)
        self.assertEqual(ec._attr_is_closing, False)
        self.assertEqual(ec._attr_is_opening, False)
        self.assertEqual(ec._attr_is_closed, True)
        self.assertEqual(ec._attr_current_cover_position, 0)
        self.assertEqual(ec._attr_current_cover_tilt_position, 0)


        # device send acknowledgement for opened
        msg = RPSMessage(address=b'\x00\x00\x00\x01', status=b'\x30', data=b'\x70', outgoing=False)
        ec.value_changed(msg)
        self.assertEqual(ec._attr_is_closing, False)
        self.assertEqual(ec._attr_is_opening, False)
        self.assertEqual(ec._attr_is_closed, False)
        self.assertEqual(ec._attr_current_cover_position, 100)
        self.assertEqual(ec._attr_current_cover_tilt_position, 100)



    def test_cover_intermediate_cover_positions(self):
        ec = self.create_cover()

        msg = Regular4BSMessage(address=b'\x00\x00\x00\x01', status=b'\x20', data=b'\x00\x1e\x01\x0a', outgoing=False)
        ec._attr_current_cover_position = 10
        ec.value_changed(msg)
        self.assertEqual(ec._attr_is_closing, False)
        self.assertEqual(ec._attr_is_opening, False)
        self.assertEqual(ec._attr_is_closed, False)
        self.assertEqual(ec._attr_current_cover_position, 40)

        msg = Regular4BSMessage(address=b'\x00\x00\x00\x01', status=b'\x20', data=b'\x00\x0a\x01\x0a', outgoing=False)
        ec._attr_current_cover_position = 0
        ec.value_changed(msg)
        self.assertEqual(ec._attr_is_closing, False)
        self.assertEqual(ec._attr_is_opening, False)
        self.assertEqual(ec._attr_is_closed, False)
        self.assertEqual(ec._attr_current_cover_position, 10)

        inverted = self.create_cover(invert_direction=True)
        inverted._attr_current_cover_position = 50
        msg = Regular4BSMessage(address=b'\x00\x00\x00\x01', status=b'\x20', data=b'\x00\x0a\x01\x0a', outgoing=False)
        inverted.value_changed(msg)
        self.assertEqual(inverted.current_cover_position, 40)

        msg = Regular4BSMessage(address=b'\x00\x00\x00\x01', status=b'\x20', data=b'\x00\x5a\x02\x0a', outgoing=False)
        ec._attr_current_cover_position = 100
        ec.value_changed(msg)
        self.assertEqual(ec._attr_is_closing, False)
        self.assertEqual(ec._attr_is_opening, False)
        self.assertEqual(ec._attr_is_closed, False)
        self.assertEqual(ec._attr_current_cover_position, 10)



    def test_open_cover(self):
        ec = self.create_cover()

        ec.open_cover()
        self.assertEqual(
            self.last_sent_command.body,
            b'k\x07\x00\x0b\x01\x08\x00\x00\xb1\x06\x00')

    def test_close_cover(self):
        ec = self.create_cover()

        ec.close_cover()
        self.assertEqual(
            self.last_sent_command.body,
            b'k\x07\x00\x0b\x02\x08\x00\x00\xb1\x06\x00')

    def test_inverted_direction_translates_commands_and_status(self):
        ec = self.create_cover(invert_direction=True)

        ec.open_cover()
        self.assertEqual(self.last_sent_command.body[4], 0x02)  # logical open -> physical down

        ec.close_cover()
        self.assertEqual(self.last_sent_command.body[4], 0x01)  # logical close -> physical up

        closed = RPSMessage(address=b'\x00\x00\x00\x01', status=b'\x30', data=b'\x50', outgoing=False)
        ec.value_changed(closed)
        self.assertFalse(ec.is_closed)
        self.assertEqual(ec.current_cover_position, 100)

        opened = RPSMessage(address=b'\x00\x00\x00\x01', status=b'\x30', data=b'\x70', outgoing=False)
        ec.value_changed(opened)
        self.assertTrue(ec.is_closed)
        self.assertEqual(ec.current_cover_position, 0)

    def test_stop_cover(self):
        ec = self.create_cover()

        ec.stop_cover()
        self.assertEqual(
            self.last_sent_command.body,
            b'k\x07\x00\x00\x00\x08\x00\x00\xb1\x06\x00')

    def test_set_cover_position(self):
        ec = self.create_cover()

        ec._attr_current_cover_position = 100
        ec.set_cover_position(position=50)
        self.assertEqual(
            self.last_sent_command.body,
            b'k\x07\x00\x05\x02\x08\x00\x00\xb1\x06\x00')
        self.assertEqual(ec._attr_is_closing, True)
        self.assertEqual(ec._attr_is_opening, False)
        self.last_sent_command = None

        ec._attr_current_cover_position = 0
        ec.set_cover_position(position=50)
        self.assertEqual(
            self.last_sent_command.body,
            b'k\x07\x00\x05\x01\x08\x00\x00\xb1\x06\x00')
        self.assertEqual(ec._attr_is_closing, False)
        self.assertEqual(ec._attr_is_opening, True)
        self.last_sent_command = None

        ec._attr_current_cover_position = 100
        ec.set_cover_position(position=0)
        self.assertEqual(
            self.last_sent_command.body,
            b'k\x07\x00\x0b\x02\x08\x00\x00\xb1\x06\x00')
        self.assertEqual(ec._attr_is_closing, True)
        self.assertEqual(ec._attr_is_opening, False)
        self.last_sent_command = None

        ec._attr_current_cover_position = 0
        ec.set_cover_position(position=100)
        self.assertEqual(
            self.last_sent_command.body,
            b'k\x07\x00\x0b\x01\x08\x00\x00\xb1\x06\x00')
        self.assertEqual(ec._attr_is_closing, False)
        self.assertEqual(ec._attr_is_opening, True)
        self.last_sent_command = None

        ec._attr_current_cover_position = 100
        ec.set_cover_position(position=100)
        self.assertEqual(self.last_sent_command, None)
        self.last_sent_command = None

#############################################################################################
    def test_set_cover_tilt_position(self):
        ec = self.create_blind()

        ec._attr_current_cover_position = 100
        ec.set_cover_position(position=50)
        self.assertEqual(
            self.last_sent_command.body,
            b'k\x07\x00\x05\x02\x08\x00\x00\xb1\x07\x00')
        self.assertEqual(ec._attr_is_closing, True)
        self.assertEqual(ec._attr_is_opening, False)
        self.last_sent_command = None

        ec._attr_current_cover_position = 0
        ec.set_cover_position(position=50)
        self.assertEqual(
            self.last_sent_command.body,
            b'k\x07\x00\x05\x01\x08\x00\x00\xb1\x07\x00')
        self.assertEqual(ec._attr_is_closing, False)
        self.assertEqual(ec._attr_is_opening, True)
        self.last_sent_command = None

        ec._attr_current_cover_position = 100
        ec.set_cover_position(position=0)
        self.assertEqual(
            self.last_sent_command.body,
            b'k\x07\x00\x0b\x02\x08\x00\x00\xb1\x07\x00')
        self.assertEqual(ec._attr_is_closing, True)
        self.assertEqual(ec._attr_is_opening, False)
        self.last_sent_command = None

        ec._attr_current_cover_position = 0
        ec.set_cover_position(position=100)
        self.assertEqual(
            self.last_sent_command.body,
            b'k\x07\x00\x0b\x01\x08\x00\x00\xb1\x07\x00')
        self.assertEqual(ec._attr_is_closing, False)
        self.assertEqual(ec._attr_is_opening, True)
        self.last_sent_command = None

        ec._attr_current_cover_position = 100
        ec.set_cover_position(position=100)
        self.assertEqual(self.last_sent_command, None)
        self.last_sent_command = None
#############################################################################################


    def test_initial_loading_opening(self):
        ec = self.create_cover()
        ec._attr_is_closed = None
        self.assertEqual(ec.is_closed, None)
        self.assertEqual(ec.state, None)

        ec.load_value_initially(LatestStateMock('opening', {'current_position': 55, 'current_tilt_position': 20}))
        self.assertEqual(ec.is_closed, False)
        self.assertEqual(ec.is_opening, True)
        self.assertEqual(ec.is_closing, False)
        self.assertEqual(ec.state, 'opening')
        self.assertEqual(ec.current_cover_position, 55)
        self.assertEqual(ec.current_cover_tilt_position, 20)

    def test_initial_loading_closing(self):
        ec = self.create_cover()
        ec._attr_is_closed = None
        self.assertEqual(ec.is_closed, None)
        self.assertEqual(ec.state, None)

        ec.load_value_initially(LatestStateMock('closing', {'current_position': 33, 'current_tilt_position': 10}))
        self.assertEqual(ec.is_closed, False)
        self.assertEqual(ec.is_opening, False)
        self.assertEqual(ec.is_closing, True)
        self.assertEqual(ec.state, 'closing')
        self.assertEqual(ec.current_cover_position, 33)
        self.assertEqual(ec.current_cover_tilt_position, 10)

    def test_initial_loading_open(self):
        ec = self.create_cover()
        ec._attr_is_closed = None
        self.assertEqual(ec.is_closed, None)
        self.assertEqual(ec.state, None)

        ec.load_value_initially(LatestStateMock('open', {'current_position': 100, 'current_tilt_position': 100}))
        self.assertEqual(ec.is_closed, False)
        self.assertEqual(ec.is_opening, False)
        self.assertEqual(ec.is_closing, False)
        self.assertEqual(ec.state, 'open')
        self.assertEqual(ec.current_cover_position, 100)
        self.assertEqual(ec.current_cover_tilt_position, 100)

    def test_initial_loading_closed(self):
        ec = self.create_cover()
        ec._attr_is_closed = None
        self.assertEqual(ec.is_closed, None)
        self.assertEqual(ec.state, None)

        ec.load_value_initially(LatestStateMock('closed', {'current_position': 0, 'current_tilt_position': 0}))
        self.assertEqual(ec.is_closed, True)
        self.assertEqual(ec.is_opening, False)
        self.assertEqual(ec.is_closing, False)
        self.assertEqual(ec.state, 'closed')
        self.assertEqual(ec.current_cover_position, 0)
        self.assertEqual(ec.current_cover_tilt_position, 0)


    def test_runtime_of_end_position_is_not_bigger_than_the_telegram_allows(self):
        """The runtime is one byte. time_opens/time_closes may be 255 (max of the schema),
        so full runtime + 1 must be capped - otherwise encoding the telegram fails."""
        settings = DEFAULT_GENERAL_SETTINGS
        settings[CONF_FAST_STATUS_CHANGE] = True
        ec = EltakoCover(Platform.COVER, GatewayMock(settings), AddressExpression.parse('00-00-00-01'),
                         'device name', EEP.find("G5-3F-7F"), AddressExpression.parse("00-00-B1-06"),
                         EEP.find("H5-3F-7F"), "shutter", 255, 255, None)
        ec.send_message = self.mock_send_message

        ec.open_cover()
        self.assertEqual(self.last_sent_command.body[3], 255)

        ec.close_cover()
        self.assertEqual(self.last_sent_command.body[3], 255)

        ec._attr_current_cover_position = 50
        ec.set_cover_position(position=100)
        self.assertEqual(self.last_sent_command.body[3], 255)


    def test_set_position_without_known_position(self):
        """Without a known position no runtime can be calculated - only the end positions work."""
        ec = self.create_cover()
        self.last_sent_command = None

        ec._attr_current_cover_position = None
        ec.set_cover_position(position=50)
        self.assertEqual(self.last_sent_command, None)

        # end positions are reached blindly and recalibrate the cover
        ec.set_cover_position(position=0)
        self.assertEqual(self.last_sent_command.body[3], 11)   # time_closes + 1
        self.assertEqual(self.last_sent_command.body[4], 0x02)


class TestCoverTilt(unittest.IsolatedAsyncioTestCase):
    """Tilting sends a move telegram, waits and sends a stop telegram. The wait must not
    block the event loop, therefore it is implemented as async_set_cover_tilt_position."""

    def mock_send_message(self, msg):
        self.sent_commands.append(msg)

    def create_blind(self, time_tilts=15, invert_direction=False) -> EltakoCover:
        settings = DEFAULT_GENERAL_SETTINGS
        settings[CONF_FAST_STATUS_CHANGE] = True
        ec = EltakoCover(Platform.COVER, GatewayMock(settings), AddressExpression.parse('00-00-00-01'),
                         'device name', EEP.find("G5-3F-7F"), AddressExpression.parse("00-00-B1-07"),
                         EEP.find("H5-3F-7F"), "blind", 10, 10, time_tilts,
                         invert_direction=invert_direction)
        self.sent_commands = []
        ec.send_message = self.mock_send_message
        return ec

    def test_tilt_is_offered_to_home_assistant(self):
        """github issue #95: the tilt position of blinds can be set from Home Assistant as soon
        as time_tilts is configured."""
        self.assertTrue(self.create_blind()._attr_supported_features & CoverEntityFeature.SET_TILT_POSITION)
        self.assertFalse(self.create_blind(time_tilts=None)._attr_supported_features & CoverEntityFeature.SET_TILT_POSITION)

    def test_tilt_is_async(self):
        """A sync implementation would be run in an executor thread and block it while sleeping."""
        self.assertIn('async_set_cover_tilt_position', EltakoCover.__dict__)
        self.assertNotIn('set_cover_tilt_position', EltakoCover.__dict__)
        self.assertTrue(asyncio.iscoroutinefunction(EltakoCover.async_set_cover_tilt_position))

    async def test_tilt_sends_move_and_stop(self):
        ec = self.create_blind()
        ec._attr_current_cover_tilt_position = 0

        with mock.patch('asyncio.sleep') as sleep_mock:
            await ec.async_set_cover_tilt_position(tilt_position=100)

        self.assertEqual(len(self.sent_commands), 2)
        self.assertEqual(self.sent_commands[0].body[4], 0x01)   # up
        self.assertEqual(self.sent_commands[1].body[4], 0x00)   # stop
        # 100% of 15 * 0.1s
        sleep_mock.assert_awaited_once_with(1.5)

        # the movement is over when the stop telegram was sent
        self.assertEqual(ec._attr_is_opening, False)
        self.assertEqual(ec._attr_is_closing, False)

    async def test_tilt_down(self):
        ec = self.create_blind()
        ec._attr_current_cover_tilt_position = 100

        with mock.patch('asyncio.sleep') as sleep_mock:
            await ec.async_set_cover_tilt_position(tilt_position=50)

        self.assertEqual(self.sent_commands[0].body[4], 0x02)   # down
        sleep_mock.assert_awaited_once_with(0.75)

    async def test_inverted_tilt_translates_direction(self):
        ec = self.create_blind(invert_direction=True)
        ec._attr_current_cover_tilt_position = 0

        with mock.patch('asyncio.sleep'):
            await ec.async_set_cover_tilt_position(tilt_position=100)

        self.assertEqual(self.sent_commands[0].body[4], 0x02)  # logical up -> physical down

    async def test_tilt_to_current_position_does_nothing(self):
        ec = self.create_blind()
        ec._attr_current_cover_tilt_position = 40

        await ec.async_set_cover_tilt_position(tilt_position=40)
        self.assertEqual(self.sent_commands, [])

    async def test_tilt_without_known_position(self):
        """After a restart without restored state the tilt position is unknown. The slats are
        moved from the assumed end position instead of crashing on a comparison with None."""
        ec = self.create_blind()
        self.assertEqual(ec._attr_current_cover_tilt_position, None)

        with mock.patch('asyncio.sleep') as sleep_mock:
            await ec.async_set_cover_tilt_position(tilt_position=100)

        self.assertEqual(self.sent_commands[0].body[4], 0x01)   # up, starting from 0
        sleep_mock.assert_awaited_once_with(1.5)

    async def test_tilt_without_configured_tilt_time(self):
        ec = self.create_blind(time_tilts=None)
        await ec.async_set_cover_tilt_position(tilt_position=100)
        self.assertEqual(self.sent_commands, [])

