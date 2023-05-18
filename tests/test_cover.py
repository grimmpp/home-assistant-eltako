import unittest
from unittest import mock
from homeassistant.helpers.entity import Entity
from custom_components.eltako.cover import EltakoCover
from custom_components.eltako.device import EltakoEntity
from eltakobus import *

# mock update of Home Assistant
Entity.schedule_update_ha_state = mock.Mock(return_value=None)
# EltakoEntity.send_message = mock.Mock(return_value=None)

class TestCover(unittest.TestCase):

    def create_cover(self) -> EltakoCover:
        gateway = None
        dev_id = AddressExpression.parse('00-00-00-01')
        dev_name = 'device name'
        device_class = "shutter"
        time_closes = 3
        time_opens = 3
        eep_string = "G5-3F-7F"

        sender_id = AddressExpression.parse("00-00-B1-06")
        sender_eep_string = "H5-3F-7F"

        dev_eep = EEP.find(eep_string)
        sender_eep = EEP.find(sender_eep_string)

        ec = EltakoCover(gateway, dev_id, dev_name, dev_eep, sender_id, sender_eep, device_class, time_closes, time_opens)
        return ec


    def test_cover_value_changed(self):
        ec = self.create_cover()
        ec._attr_is_closing = False
        ec._attr_is_opening = False
        self._attr_is_closed = False
        self._attr_current_cover_position = 100

        self.assertEqual(ec._attr_is_closing, False)
        self.assertEqual(ec._attr_is_opening, False)
        self.assertEqual(ec._attr_is_closed, False)
        self.assertEqual(ec._attr_current_cover_position, 100)

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
