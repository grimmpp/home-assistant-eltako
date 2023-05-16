import unittest
from unittest import mock
from homeassistant.helpers.entity import Entity
from custom_components.eltako.light import EltakoDimmableLight, EltakoSwitchableLight
from eltakobus import *

# mock update of Home Assistant
Entity.schedule_update_ha_state = mock.Mock(return_value=None)

class TestLight(unittest.TestCase):

    def create_switchable_light(self) -> EltakoSwitchableLight:
        gateway = None
        dev_id = AddressExpression.parse('00-00-00-01')
        dev_name = 'device name'
        eep_string = 'M5-38-08'
        
        sender_id = AddressExpression.parse('00-00-B0-01')
        sender_eep_string = 'A5-38-08'

        dev_eep = EEP.find(eep_string)
        sender_eep = EEP.find(sender_eep_string)

        light = EltakoSwitchableLight(gateway, dev_id, dev_name, dev_eep, sender_id, sender_eep)
        return light

    def test_switchable_light_value_changed(self):
        light = self.create_switchable_light()
        light._on_state = False

        # status update message from relay
        #8b 05 70 00 00 00 00 00 00 01 30
        on_msg = RPSMessage(address=b'\x00\x00\x00\x01', status=b'\x30', data=b'\x70', outgoing=False)
        # 8b 05 50 00 00 00 00 00 00 01 30
        off_msg = RPSMessage(address=b'\x00\x00\x00\x01', status=b'\x30', data=b'\x50', outgoing=False)

        light.value_changed(on_msg)
        self.assertEqual(light._on_state, True)

        light.value_changed(on_msg)
        self.assertEqual(light._on_state, True)
        
        light.value_changed(off_msg)
        self.assertEqual(light._on_state, False)

        light.value_changed(off_msg)
        self.assertEqual(light._on_state, False)

        light.value_changed(on_msg)
        self.assertEqual(light._on_state, True)