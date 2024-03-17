import unittest
from custom_components.eltako.sensor import *
from unittest import mock
from mocks import *
from homeassistant.helpers.entity import Entity
from eltakobus import *
from custom_components.eltako.switch import EltakoSwitch


# mock update of Home Assistant
Entity.schedule_update_ha_state = mock.Mock(return_value=None)
# EltakoEntity.send_message = mock.Mock(return_value=None)

class TestSwitch(unittest.TestCase):
    last_sent_command = []

    def mock_send_message(self, msg: ESP2Message):
        self.last_sent_command.append( msg )

    def create_switch(self, sender_eep_string:str, sender_id:AddressExpression = AddressExpression.parse('00-00-B0-01')) -> EltakoSwitch:
        gateway = GatewayMock()
        dev_id = AddressExpression.parse('00-00-00-01')
        dev_name = 'device name'
        eep_string = 'M5-38-08'
        
        dev_eep = EEP.find(eep_string)
        sender_eep = EEP.find(sender_eep_string)

        switch = EltakoSwitch(Platform.SWITCH, gateway, dev_id, dev_name, dev_eep, sender_id, sender_eep)
        return switch

    def test_switch_value_changed_with_sender_epp_A5_38_08(self):
        switch = self.create_switch('A5-38-08')
        switch.send_message = self.mock_send_message
        switch._attr_is_on = None
        self.assertEqual(switch._attr_is_on, None)
        self.assertEqual(switch.is_on, None)
        self.assertEqual(switch.state, None)

        # status update message from relay
        #8b 05 70 00 00 00 00 00 00 01 30
        on_msg = RPSMessage(address=b'\x00\x00\x00\x01', status=b'\x30', data=b'\x70', outgoing=False)
        # 8b 05 50 00 00 00 00 00 00 01 30
        off_msg = RPSMessage(address=b'\x00\x00\x00\x01', status=b'\x30', data=b'\x50', outgoing=False)

        switch.value_changed(on_msg)
        self.assertEqual(switch.is_on, True)
        self.assertEqual(switch.state, 'on')

        switch.value_changed(on_msg)
        self.assertEqual(switch.is_on, True)
        self.assertEqual(switch.state, 'on')
        
        switch.value_changed(off_msg)
        self.assertEqual(switch.is_on, False)
        self.assertEqual(switch.state, 'off')

        switch.value_changed(off_msg)
        self.assertEqual(switch.is_on, False)
        self.assertEqual(switch.state, 'off')

        switch.value_changed(on_msg)
        self.assertEqual(switch.is_on, True)
        self.assertEqual(switch.state, 'on')

        switch.turn_on()
        self.assertEqual(len(self.last_sent_command), 1)
        self.assertEqual(type(self.last_sent_command[0]), Regular4BSMessage)
        self.assertEqual(self.last_sent_command[0].data[3], 9)
        self.last_sent_command = []

        switch.turn_off()
        self.assertEqual(len(self.last_sent_command), 1)
        self.assertEqual(type(self.last_sent_command[0]), Regular4BSMessage)
        self.assertEqual(self.last_sent_command[0].data[3], 8)
        self.last_sent_command = []

    def test_switch_value_changed_with_sender_epp_F6_02_01_left(self):
        switch = self.create_switch('F6-02-01', AddressExpression.parse('00-00-B0-01 left'))
        switch.send_message = self.mock_send_message
        switch._on_state = False

        # status update message from relay
        #8b 05 70 00 00 00 00 00 00 01 30
        # data = 0x30
        on_msg = RPSMessage(address=b'\x00\x00\x00\x01', status=b'\x30', data=b'\x30', outgoing=False)
        # 8b 05 50 00 00 00 00 00 00 01 30
        # data = 0x10
        off_msg = RPSMessage(address=b'\x00\x00\x00\x01', status=b'\x30', data=b'\x10', outgoing=False)

        switch.value_changed(on_msg)
        self.assertEqual(switch.is_on, True)
        self.assertEqual(switch.state, 'on')

        switch.value_changed(on_msg)
        self.assertEqual(switch.is_on, True)
        self.assertEqual(switch.state, 'on')
        
        switch.value_changed(off_msg)
        self.assertEqual(switch.is_on, False)
        self.assertEqual(switch.state, 'off')

        switch.value_changed(off_msg)
        self.assertEqual(switch.is_on, False)
        self.assertEqual(switch.state, 'off')

        switch.value_changed(on_msg)
        self.assertEqual(switch.is_on, True)
        self.assertEqual(switch.state, 'on')

        self.last_sent_command = []
        switch.turn_on()
        self.assertEqual(len(self.last_sent_command), 2)
        self.assertEqual(type(self.last_sent_command[0]), RPSMessage)
        self.assertEqual(self.last_sent_command[0].status, 0x30)
        self.assertEqual(self.last_sent_command[0].data[0], 0x30)   # on
        self.assertEqual(self.last_sent_command[1].status, 0x30)
        self.assertEqual(self.last_sent_command[1].data[0], 0x20)

        self.last_sent_command = []
        switch.turn_off()
        self.assertEqual(len(self.last_sent_command), 2)
        self.assertEqual(type(self.last_sent_command[0]), RPSMessage)
        self.assertEqual(self.last_sent_command[0].status, 0x30)
        self.assertEqual(self.last_sent_command[0].data[0], 0x10)   #off
        self.assertEqual(self.last_sent_command[1].status, 0x30)
        self.assertEqual(self.last_sent_command[1].data[0], 0x00)
        self.last_sent_command = []


    def test_switch_value_changed_with_sender_epp_F6_02_01_right(self):
        switch = self.create_switch('F6-02-01', AddressExpression.parse('00-00-B0-01 right'))
        switch.send_message = self.mock_send_message
        switch._on_state = False

        # status update message from relay
        #8b 05 70 00 00 00 00 00 00 01 30
        # data = 0x70
        on_msg = RPSMessage(address=b'\x00\x00\x00\x01', status=b'\x30', data=b'\x70', outgoing=False)
        # 8b 05 50 00 00 00 00 00 00 01 30
        # data = 0x50
        off_msg = RPSMessage(address=b'\x00\x00\x00\x01', status=b'\x30', data=b'\x50', outgoing=False)

        switch.value_changed(on_msg)
        self.assertEqual(switch.is_on, True)
        self.assertEqual(switch.state, 'on')

        switch.value_changed(on_msg)
        self.assertEqual(switch.is_on, True)
        self.assertEqual(switch.state, 'on')
        
        switch.value_changed(off_msg)
        self.assertEqual(switch.is_on, False)
        self.assertEqual(switch.state, 'off')

        switch.value_changed(off_msg)
        self.assertEqual(switch.is_on, False)
        self.assertEqual(switch.state, 'off')

        switch.value_changed(on_msg)
        self.assertEqual(switch.is_on, True)
        self.assertEqual(switch.state, 'on')

        self.last_sent_command = []
        switch.turn_on()
        self.assertEqual(len(self.last_sent_command), 2)
        self.assertEqual(type(self.last_sent_command[0]), RPSMessage)
        self.assertEqual(self.last_sent_command[0].status, 0x30)
        self.assertEqual(self.last_sent_command[0].data[0], 0x70)   # on
        self.assertEqual(self.last_sent_command[1].status, 0x30)
        self.assertEqual(self.last_sent_command[1].data[0], 0x60)

        self.last_sent_command = []
        switch.turn_off()
        self.assertEqual(len(self.last_sent_command), 2)
        self.assertEqual(type(self.last_sent_command[0]), RPSMessage)
        self.assertEqual(self.last_sent_command[0].status, 0x30)
        self.assertEqual(self.last_sent_command[0].data[0], 0x50)   #off
        self.assertEqual(self.last_sent_command[1].status, 0x30)
        self.assertEqual(self.last_sent_command[1].data[0], 0x40)
        self.last_sent_command = []


    def test_initial_loading_on(self):
        switch = self.create_switch('F6-02-01')
        switch._attr_is_on = None

        switch.load_value_initially(LatestStateMock('on'))
        self.assertTrue(switch._attr_is_on)
        self.assertTrue(switch.is_on)
        self.assertEqual(switch.state, 'on')

    def test_initial_loading_off(self):
        switch = self.create_switch('F6-02-01')
        switch._attr_is_on = None

        switch.load_value_initially(LatestStateMock('off'))
        self.assertFalse(switch._attr_is_on)
        self.assertFalse(switch.is_on)
        self.assertEqual(switch.state, 'off')

    def test_initial_loading_None(self):
        switch = self.create_switch('F6-02-01')
        switch._attr_is_on = True

        switch.load_value_initially(LatestStateMock('bla'))
        self.assertIsNone(switch._attr_is_on)
        self.assertIsNone(switch.is_on)
        self.assertIsNone(switch.state)