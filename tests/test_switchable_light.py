import unittest
from custom_components.eltako.sensor import *
from unittest import mock
from mocks import *
from homeassistant.helpers.entity import Entity
from eltakobus import *
from custom_components.eltako.light import EltakoSwitchableLight


# mock update of Home Assistant
Entity.schedule_update_ha_state = mock.Mock(return_value=None)
# EltakoEntity.send_message = mock.Mock(return_value=None)

class TestSwitchableLight(unittest.TestCase):

    def mock_send_message(self, msg: ESP2Message):
        self.last_sent_command = msg

    def create_switchable_light(self) -> EltakoSwitchableLight:
        gateway = GatewayMock()
        dev_id = AddressExpression.parse('00-00-00-01')
        dev_name = 'device name'
        eep_string = 'M5-38-08'
        
        sender_id = AddressExpression.parse('00-00-B0-01')
        sender_eep_string = 'A5-38-08'

        dev_eep = EEP.find(eep_string)
        sender_eep = EEP.find(sender_eep_string)

        light = EltakoSwitchableLight(Platform.LIGHT, gateway, dev_id, dev_name, dev_eep, sender_id, sender_eep)
        return light

    def test_switchable_light_value_changed(self):
        light = self.create_switchable_light()
        light._attr_is_on = None
        self.assertEquals(light.is_on, None)
        self.assertIsNone(light.state)

        # status update message from relay
        #8b 05 70 00 00 00 00 00 00 01 30
        on_msg = RPSMessage(address=b'\x00\x00\x00\x01', status=b'\x30', data=b'\x70', outgoing=False)
        # 8b 05 50 00 00 00 00 00 00 01 30
        off_msg = RPSMessage(address=b'\x00\x00\x00\x01', status=b'\x30', data=b'\x50', outgoing=False)

        light.value_changed(on_msg)
        self.assertEquals(light.is_on, True)
        self.assertEquals(light.state, 'on')

        light.value_changed(on_msg)
        self.assertEquals(light.is_on, True)
        self.assertEquals(light.state, 'on')
        
        light.value_changed(off_msg)
        self.assertEquals(light.is_on, False)
        self.assertEquals(light.state, 'off')

        light.value_changed(off_msg)
        self.assertEquals(light.is_on, False)
        self.assertEquals(light.state, 'off')

        light.value_changed(on_msg)
        self.assertEquals(light.is_on, True)
        self.assertEquals(light.state, 'on')

        light._attr_is_on = None
        self.assertEquals(light.is_on, None)
        self.assertIsNone(light.state)



    def test_switchable_light_trun_on(self):
        light = self.create_switchable_light()
        light.send_message = self.mock_send_message
        
        # test if command is sent to eltako bus
        light.turn_on()
        self.assertEqual(
            self.last_sent_command.body,
            b'k\x07\x01\x00\x00\t\x00\x00\xb0\x01\x00')
        
    def test_switchable_light_trun_off(self):
        light = self.create_switchable_light()
        light.send_message = self.mock_send_message

        # test if command is sent to eltako bus
        light.turn_off()
        self.assertEqual(
            self.last_sent_command.body,
            b'k\x07\x01\x00\x00\x08\x00\x00\xb0\x01\x00')

    def test_initial_loading_on(self):
        sl = self.create_switchable_light()
        sl._attr_is_on = None

        sl.load_value_initially(LatestStateMock('on'))
        self.assertTrue(sl._attr_is_on)
        self.assertTrue(sl.is_on)
        self.assertEquals(sl.state, 'on')

    def test_initial_loading_off(self):
        sl = self.create_switchable_light()
        sl._attr_is_on = None

        sl.load_value_initially(LatestStateMock('off'))
        self.assertFalse(sl._attr_is_on)
        self.assertFalse(sl.is_on)
        self.assertEquals(sl.state, 'off')

    def test_initial_loading_None(self):
        sl = self.create_switchable_light()
        sl._attr_is_on = True

        sl.load_value_initially(LatestStateMock('bla'))
        self.assertIsNone(sl._attr_is_on)
        self.assertIsNone(sl.is_on)
        self.assertIsNone(sl.state)