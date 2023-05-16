import unittest
from mocks import HassMock
from unittest import mock
from homeassistant.helpers.entity import Entity
from custom_components.eltako.binary_sensor import EltakoBinarySensor
from eltakobus import *

# mock update of Home Assistant
Entity.schedule_update_ha_state = mock.Mock(return_value=None)
# EltakoBinarySensor.hass.bus.fire is mocked by class HassMock


class TestBinarySensor(unittest.TestCase):

    def test_binary_sensor_rocker_switch(self):
        gateway = None
        dev_id = AddressExpression.parse("00-00-00-01")
        dev_name = "device name"
        device_class = "none"
        eep_string = "F6-02-01"
        dev_eep = EEP.find(eep_string)
        invert_signal =  False

        bs = EltakoBinarySensor(gateway, dev_id, dev_name, dev_eep, device_class, invert_signal)
        self.assertEqual(bs._attr_is_on, None)       

        bs.hass = HassMock()
        
        switch_address = b'\xfe\xdb\xb6\x40'
        msg = RPSMessage(switch_address, data=b'\x70', status=b'\x30')
        bs.value_changed(msg)

        # test if processing was finished and event arrived on bus
        self.assertEqual(len(bs.hass.bus.fired_events), 1)

        # check event type
        fired_event = bs.hass.bus.fired_events[0]
        self.assertEqual(fired_event['event_type'], 'eltako_button_pressed_FE-DB-B6-40')

        # check event data
        exprected_data = {
            'id': 'eltako_button_pressed_FE-DB-B6-40', 
            'switch_address': 'FE-DB-B6-40', 
            'pressed_buttons': ['RT'], 
            'pressed': True, 
            'two_buttons_pressed': False, 
            'rocker_first_action': 3, 
            'rocker_second_action': 0
        }
        self.assertEqual(fired_event['event_data'], exprected_data)


    def test_binary_sensor_window_contact_triggered_via_FTS14EM(self):
        gateway = None
        dev_id = AddressExpression.parse("00-00-00-01")
        dev_name = "device name"
        device_class = "window"
        eep_string = "D5-00-01"
        dev_eep = EEP.find(eep_string)
        invert_signal =  True

        bs = EltakoBinarySensor(gateway, dev_id, dev_name, dev_eep, device_class, invert_signal)
        # test if sensor object is newly created
        self.assertEqual(bs._attr_is_on, None)       
        
        # test if state is set to no contact
        bs._attr_is_on = False
        self.assertEqual(bs._attr_is_on, False)

        msg = Regular1BSMessage(address=b'\x00\x00\x10\x08', data=b'\x09', status=b'\x00')
        
        # test if signal is processed correctly (switch on)
        bs.value_changed(msg)
        self.assertEqual(bs._attr_is_on, True)

        # test if signal is processed correctly (switch on)
        bs.value_changed(msg)
        self.assertEqual(bs._attr_is_on, True)

        # test if signal is processed correctly (switch off)
        msg.data = b'\x08'
        bs.value_changed(msg)
        self.assertEqual(bs._attr_is_on, False)

        # test if signal is processed correctly (switch off)
        bs.value_changed(msg)
        self.assertEqual(bs._attr_is_on, False)