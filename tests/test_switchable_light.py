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
    last_sent_command = []

    def mock_send_message(self, msg: ESP2Message):
        self.last_sent_command.append( msg )

    def create_switchable_light(self, sender_eep_string:str = 'A5-38-08', sender_id:AddressExpression = AddressExpression.parse('00-00-B0-01')) -> EltakoSwitchableLight:
        gateway = GatewayMock()
        dev_id = AddressExpression.parse('00-00-00-01')
        dev_name = 'device name'
        eep_string = 'M5-38-08'
        
        dev_eep = EEP.find(eep_string)
        sender_eep = EEP.find(sender_eep_string)

        light = EltakoSwitchableLight(Platform.LIGHT, gateway, dev_id, dev_name, dev_eep, sender_id, sender_eep)
        return light

    def test_switchable_light_value_changed(self):
        light = self.create_switchable_light()
        light._attr_is_on = None
        self.assertEqual(light.is_on, None)
        self.assertIsNone(light.state)

        # status update message from relay
        #8b 05 70 00 00 00 00 00 00 01 30
        on_msg = RPSMessage(address=b'\x00\x00\x00\x01', status=b'\x30', data=b'\x70', outgoing=False)
        # 8b 05 50 00 00 00 00 00 00 01 30
        off_msg = RPSMessage(address=b'\x00\x00\x00\x01', status=b'\x30', data=b'\x50', outgoing=False)

        light.value_changed(on_msg)
        self.assertEqual(light.is_on, True)
        self.assertEqual(light.state, 'on')

        light.value_changed(on_msg)
        self.assertEqual(light.is_on, True)
        self.assertEqual(light.state, 'on')
        
        light.value_changed(off_msg)
        self.assertEqual(light.is_on, False)
        self.assertEqual(light.state, 'off')

        light.value_changed(off_msg)
        self.assertEqual(light.is_on, False)
        self.assertEqual(light.state, 'off')

        light.value_changed(on_msg)
        self.assertEqual(light.is_on, True)
        self.assertEqual(light.state, 'on')

        light._attr_is_on = None
        self.assertEqual(light.is_on, None)
        self.assertIsNone(light.state)


    def test_switchable_light_value_changed_with_sender_epp_F6_02_01_left(self):
        light = self.create_switchable_light('F6-02-01', AddressExpression.parse('00-00-B0-01 left'))
        light.send_message = self.mock_send_message
        light._on_state = False

        # status update message from relay
        #8b 05 70 00 00 00 00 00 00 01 30
        # data = 0x30
        on_msg = RPSMessage(address=b'\x00\x00\x00\x01', status=b'\x30', data=b'\x30', outgoing=False)
        # 8b 05 50 00 00 00 00 00 00 01 30
        # data = 0x10
        off_msg = RPSMessage(address=b'\x00\x00\x00\x01', status=b'\x30', data=b'\x10', outgoing=False)

        light.value_changed(on_msg)
        self.assertEqual(light.is_on, True)
        self.assertEqual(light.state, 'on')

        light.value_changed(on_msg)
        self.assertEqual(light.is_on, True)
        self.assertEqual(light.state, 'on')
        
        light.value_changed(off_msg)
        self.assertEqual(light.is_on, False)
        self.assertEqual(light.state, 'off')

        light.value_changed(off_msg)
        self.assertEqual(light.is_on, False)
        self.assertEqual(light.state, 'off')

        light.value_changed(on_msg)
        self.assertEqual(light.is_on, True)
        self.assertEqual(light.state, 'on')

        self.last_sent_command = []
        light.turn_on()
        self.assertEqual(len(self.last_sent_command), 2)
        self.assertEqual(type(self.last_sent_command[0]), RPSMessage)
        self.assertEqual(self.last_sent_command[0].status, 0x30)
        self.assertEqual(self.last_sent_command[0].data[0], 0x30)   # on
        self.assertEqual(self.last_sent_command[1].status, 0x30)
        self.assertEqual(self.last_sent_command[1].data[0], 0x20)

        self.last_sent_command = []
        light.turn_off()
        self.assertEqual(len(self.last_sent_command), 2)
        self.assertEqual(type(self.last_sent_command[0]), RPSMessage)
        self.assertEqual(self.last_sent_command[0].status, 0x30)
        self.assertEqual(self.last_sent_command[0].data[0], 0x10)   #off
        self.assertEqual(self.last_sent_command[1].status, 0x30)
        self.assertEqual(self.last_sent_command[1].data[0], 0x00)
        self.last_sent_command = []


    def test_switchable_light_value_changed_with_sender_epp_F6_02_01_right(self):
        light = self.create_switchable_light('F6-02-01', AddressExpression.parse('00-00-B0-01 right'))
        light.send_message = self.mock_send_message
        light._on_state = False

        # status update message from relay
        #8b 05 70 00 00 00 00 00 00 01 30
        # data = 0x70
        on_msg = RPSMessage(address=b'\x00\x00\x00\x01', status=b'\x30', data=b'\x70', outgoing=False)
        # 8b 05 50 00 00 00 00 00 00 01 30
        # data = 0x50
        off_msg = RPSMessage(address=b'\x00\x00\x00\x01', status=b'\x30', data=b'\x50', outgoing=False)

        light.value_changed(on_msg)
        self.assertEqual(light.is_on, True)
        self.assertEqual(light.state, 'on')

        light.value_changed(on_msg)
        self.assertEqual(light.is_on, True)
        self.assertEqual(light.state, 'on')
        
        light.value_changed(off_msg)
        self.assertEqual(light.is_on, False)
        self.assertEqual(light.state, 'off')

        light.value_changed(off_msg)
        self.assertEqual(light.is_on, False)
        self.assertEqual(light.state, 'off')

        light.value_changed(on_msg)
        self.assertEqual(light.is_on, True)
        self.assertEqual(light.state, 'on')

        self.last_sent_command = []
        light.turn_on()
        self.assertEqual(len(self.last_sent_command), 2)
        self.assertEqual(type(self.last_sent_command[0]), RPSMessage)
        self.assertEqual(self.last_sent_command[0].status, 0x30)
        self.assertEqual(self.last_sent_command[0].data[0], 0x70)   # on
        self.assertEqual(self.last_sent_command[1].status, 0x30)
        self.assertEqual(self.last_sent_command[1].data[0], 0x60)

        self.last_sent_command = []
        light.turn_off()
        self.assertEqual(len(self.last_sent_command), 2)
        self.assertEqual(type(self.last_sent_command[0]), RPSMessage)
        self.assertEqual(self.last_sent_command[0].status, 0x30)
        self.assertEqual(self.last_sent_command[0].data[0], 0x50)   #off
        self.assertEqual(self.last_sent_command[1].status, 0x30)
        self.assertEqual(self.last_sent_command[1].data[0], 0x40)
        self.last_sent_command = []


    def test_switchable_light_trun_on(self):
        light = self.create_switchable_light()
        light.send_message = self.mock_send_message
        
        # test if command is sent to eltako bus
        self.last_sent_command = []
        light.turn_on()
        self.assertEqual(
            self.last_sent_command[0].body,
            b'k\x07\x01\x00\x00\t\x00\x00\xb0\x01\x00')
        
    def test_switchable_light_trun_off(self):
        light = self.create_switchable_light()
        light.send_message = self.mock_send_message

        # test if command is sent to eltako bus
        self.last_sent_command = []
        light.turn_off()
        self.assertEqual(
            self.last_sent_command[0].body,
            b'k\x07\x01\x00\x00\x08\x00\x00\xb0\x01\x00')

    def test_initial_loading_on(self):
        sl = self.create_switchable_light()
        sl._attr_is_on = None

        sl.load_value_initially(LatestStateMock('on'))
        self.assertTrue(sl._attr_is_on)
        self.assertTrue(sl.is_on)
        self.assertEqual(sl.state, 'on')

    def test_initial_loading_off(self):
        sl = self.create_switchable_light()
        sl._attr_is_on = None

        sl.load_value_initially(LatestStateMock('off'))
        self.assertFalse(sl._attr_is_on)
        self.assertFalse(sl.is_on)
        self.assertEqual(sl.state, 'off')

    def test_initial_loading_None(self):
        sl = self.create_switchable_light()
        sl._attr_is_on = True

        sl.load_value_initially(LatestStateMock('bla'))
        self.assertIsNone(sl._attr_is_on)
        self.assertIsNone(sl.is_on)
        self.assertIsNone(sl.state)