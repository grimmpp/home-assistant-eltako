import unittest
from custom_components.eltako.sensor import *
from unittest import mock
from mocks import *

from homeassistant.helpers.entity import Entity
from homeassistant.components.light import ATTR_BRIGHTNESS

from eltakobus import *
from custom_components.eltako.light import EltakoDimmableLight


# mock update of Home Assistant
Entity.schedule_update_ha_state = mock.Mock(return_value=None)
# EltakoEntity.send_message = mock.Mock(return_value=None)

class TestDimmableLight(unittest.TestCase):

    def mock_send_message(self, msg: ESP2Message):
        self.last_sent_command = msg

    def create_switchable_light(self) -> EltakoDimmableLight:
        settings = DEFAULT_GENERAL_SETTINGS
        settings[CONF_FAST_STATUS_CHANGE] = True
        gateway = GatewayMock(settings)
        dev_id = AddressExpression.parse('00-00-00-01')
        dev_name = 'device name'
        eep_string = 'A5-38-08'
        
        sender_id = AddressExpression.parse('00-00-B0-01')
        sender_eep_string = 'A5-38-08'

        dev_eep = EEP.find(eep_string)
        sender_eep = EEP.find(sender_eep_string)

        light = EltakoDimmableLight(Platform.LIGHT, gateway, dev_id, dev_name, dev_eep, sender_id, sender_eep)
        return light

    def test_switchable_light_value_changed(self):
        light = self.create_switchable_light()
        light._attr_is_on = None
        self.assertEquals(light.is_on, None)
        self.assertIsNone(light.state)

        # status update message from relay
        #8b 05 70 00 00 00 00 00 00 01 30
        on_msg = Regular4BSMessage(address=b'\x00\x00\x00\x01', status=b'\x00', data=b'\x02\x64\x00\x09')
        # 8b 05 50 00 00 00 00 00 00 01 30
        off_msg = Regular4BSMessage(address=b'\x00\x00\x00\x01', status=b'\x00', data=b'\x02\x00\x00\x08')

        dimmed_msg = Regular4BSMessage(address=b'\x00\x00\x00\x01', status=b'\x00', data=b'\x02\x2d\x00\x09')

        light.value_changed(on_msg)
        self.assertEquals(light.is_on, True)
        self.assertEquals(light.brightness, 255)
        self.assertEquals(light.state, 'on')

        light.value_changed(on_msg)
        self.assertEquals(light.is_on, True)
        self.assertEquals(light.brightness, 255)
        self.assertEquals(light.state, 'on')
        
        light.value_changed(off_msg)
        self.assertEquals(light.is_on, False)
        self.assertEquals(light.brightness, 0)
        self.assertEquals(light.state, 'off')

        light.value_changed(off_msg)
        self.assertEquals(light.is_on, False)
        self.assertEquals(light.brightness, 0)
        self.assertEquals(light.state, 'off')

        light.value_changed(on_msg)
        self.assertEquals(light.is_on, True)
        self.assertEquals(light.brightness, 255)
        self.assertEquals(light.state, 'on')

        light.value_changed(dimmed_msg)
        self.assertEquals(light.is_on, True)
        self.assertEquals(light.brightness, 114)
        self.assertEquals(light.state, 'on')

        light._attr_is_on = None
        self.assertEquals(light.is_on, None)
        self.assertIsNone(light.state)



    def test_switchable_light_trun_on(self):
        light = self.create_switchable_light()
        light.send_message = self.mock_send_message
        
        # test if command is sent to eltako bus
        light.turn_on()
        self.assertEqual(light.brightness, 255)
        self.assertEqual(
            self.last_sent_command.body,
            b'k\x07\x02d\x00\t\x00\x00\xb0\x01\x00')
        
    def test_switchable_light_trun_off(self):
        light = self.create_switchable_light()
        light.send_message = self.mock_send_message

        # test if command is sent to eltako bus
        light.turn_off()
        self.assertEqual(light.brightness, 0)
        self.assertEqual(
            self.last_sent_command.body,
            b'k\x07\x02\x00\x00\x08\x00\x00\xb0\x01\x00')

    def test_dim_light(self):
        light = self.create_switchable_light()
        light.send_message = self.mock_send_message

        light.turn_on(brightness=100)
        self.assertEqual(light.brightness, 100)
        self.assertEqual(
            self.last_sent_command.body,
            b"k\x07\x02'\x00\t\x00\x00\xb0\x01\x00")


    def test_initial_loading_on(self):
        sl = self.create_switchable_light()
        sl._attr_is_on = None

        sl.load_value_initially(LatestStateMock('on'))
        self.assertTrue(sl._attr_is_on)
        self.assertTrue(sl.is_on)
        self.assertEqual(sl.brightness, None)
        self.assertEqual(sl.state, 'on')

    def test_initial_loading_on_with_brightness(self):
        sl = self.create_switchable_light()
        sl._attr_is_on = None

        sl.load_value_initially(LatestStateMock('on', {'brightness': 100}))
        self.assertTrue(sl._attr_is_on)
        self.assertTrue(sl.is_on)
        self.assertEqual(sl.brightness, 100)
        self.assertEqual(sl.state, 'on')

    def test_initial_loading_dimmed(self):
        sl = self.create_switchable_light()
        sl._attr_is_on = None

        sl.load_value_initially(LatestStateMock('on', {'brightness': 100}))
        self.assertTrue(sl._attr_is_on)
        self.assertTrue(sl.is_on)
        self.assertEqual(sl.brightness, 100)
        self.assertEquals(sl.state, 'on')

    def test_initial_loading_off(self):
        sl = self.create_switchable_light()
        sl._attr_is_on = None

        sl.load_value_initially(LatestStateMock('off'))
        self.assertFalse(sl._attr_is_on)
        self.assertFalse(sl.is_on)
        self.assertEqual(sl.brightness, None)
        self.assertEquals(sl.state, 'off')

    def test_initial_loading_off_with_brightness(self):
        sl = self.create_switchable_light()
        sl._attr_is_on = None

        sl.load_value_initially(LatestStateMock('off', {'brightness': 0}))
        self.assertFalse(sl._attr_is_on)
        self.assertFalse(sl.is_on)
        self.assertEqual(sl.brightness, 0)
        self.assertEquals(sl.state, 'off')

    def test_initial_loading_None(self):
        sl = self.create_switchable_light()
        sl._attr_is_on = True

        sl.load_value_initially(LatestStateMock('bla'))
        self.assertIsNone(sl._attr_is_on)
        self.assertIsNone(sl.is_on)
        self.assertIsNone(sl.brightness)
        self.assertIsNone(sl.state)