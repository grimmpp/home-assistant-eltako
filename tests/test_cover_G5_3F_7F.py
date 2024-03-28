import unittest
import os
from mocks import *
from unittest import mock, IsolatedAsyncioTestCase, TestCase
from homeassistant.helpers.entity import Entity
from homeassistant.const import Platform
from custom_components.eltako.cover import EltakoCover
from custom_components.eltako.device import EltakoEntity
from eltakobus import *
from custom_components.eltako.config_helpers import DEFAULT_GENERAL_SETTINGS

# mock update of Home Assistant
Entity.schedule_update_ha_state = mock.Mock(return_value=None)
# EltakoEntity.send_message = mock.Mock(return_value=None)

class TestCover(unittest.TestCase):

    def mock_send_message(self, msg):
        self.last_sent_command = msg

    def create_cover(self) -> EltakoCover:
        settings = DEFAULT_GENERAL_SETTINGS
        settings[CONF_FAST_STATUS_CHANGE] = True
        gateway = GatewayMock(settings)
        dev_id = AddressExpression.parse('00-00-00-01')
        dev_name = 'device name'
        device_class = "shutter"
        time_closes = 10
        time_opens = 10
        eep_string = "G5-3F-7F"

        sender_id = AddressExpression.parse("00-00-B1-06")
        sender_eep_string = "H5-3F-7F"

        dev_eep = EEP.find(eep_string)
        sender_eep = EEP.find(sender_eep_string)

        ec = EltakoCover(Platform.COVER, gateway, dev_id, dev_name, dev_eep, sender_id, sender_eep, device_class, time_closes, time_opens)
        ec.send_message = self.mock_send_message

        self.assertEqual(ec._attr_is_closing, False)
        self.assertEqual(ec._attr_is_opening, False)
        self.assertEqual(ec._attr_is_closed, None)
        self.assertEqual(ec._attr_current_cover_position, None)

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

        # device send acknowledgement for opened
        msg = RPSMessage(address=b'\x00\x00\x00\x01', status=b'\x30', data=b'\x70', outgoing=False)
        ec.value_changed(msg)
        self.assertEqual(ec._attr_is_closing, False)
        self.assertEqual(ec._attr_is_opening, False)
        self.assertEqual(ec._attr_is_closed, False)
        self.assertEqual(ec._attr_current_cover_position, 100)


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



    def test_initial_loading_opening(self):
        ec = self.create_cover()
        ec._attr_is_closed = None
        self.assertEqual(ec.is_closed, None)
        self.assertEqual(ec.state, None)
        
        ec.load_value_initially(LatestStateMock('opening', {'current_position': 55}))
        self.assertEqual(ec.is_closed, False)
        self.assertEqual(ec.is_opening, True)
        self.assertEqual(ec.is_closing, False)
        self.assertEqual(ec.state, 'opening')
        self.assertEqual(ec.current_cover_position, 55)

    def test_initial_loading_closing(self):
        ec = self.create_cover()
        ec._attr_is_closed = None
        self.assertEqual(ec.is_closed, None)
        self.assertEqual(ec.state, None)
        
        ec.load_value_initially(LatestStateMock('closing', {'current_position': 33}))
        self.assertEqual(ec.is_closed, False)
        self.assertEqual(ec.is_opening, False)
        self.assertEqual(ec.is_closing, True)
        self.assertEqual(ec.state, 'closing')
        self.assertEqual(ec.current_cover_position, 33)

    def test_initial_loading_open(self):
        ec = self.create_cover()
        ec._attr_is_closed = None
        self.assertEqual(ec.is_closed, None)
        self.assertEqual(ec.state, None)
        
        ec.load_value_initially(LatestStateMock('open', {'current_position': 100}))
        self.assertEqual(ec.is_closed, False)
        self.assertEqual(ec.is_opening, False)
        self.assertEqual(ec.is_closing, False)
        self.assertEqual(ec.state, 'open')
        self.assertEqual(ec.current_cover_position, 100)

    def test_initial_loading_closed(self):
        ec = self.create_cover()
        ec._attr_is_closed = None
        self.assertEqual(ec.is_closed, None)
        self.assertEqual(ec.state, None)
        
        ec.load_value_initially(LatestStateMock('closed', {'current_position': 0}))
        self.assertEqual(ec.is_closed, True)
        self.assertEqual(ec.is_opening, False)
        self.assertEqual(ec.is_closing, False)
        self.assertEqual(ec.state, 'closed')
        self.assertEqual(ec.current_cover_position, 0)



