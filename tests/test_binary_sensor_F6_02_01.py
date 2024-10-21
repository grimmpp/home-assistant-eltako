import unittest
from tests.mocks import *
from unittest import mock
from homeassistant.helpers.entity import Entity
from homeassistant.const import Platform
from custom_components.eltako.binary_sensor import EltakoBinarySensor
from custom_components.eltako.config_helpers import *
from eltakobus import *
from eltakobus.eep import *

from tests.test_binary_sensor_generic import TestBinarySensor

# mock update of Home Assistant
Entity.schedule_update_ha_state = mock.Mock(return_value=None)
# EltakoBinarySensor.hass.bus.fire is mocked by class HassMock


class TestBinarySensor_F6_02_01(unittest.TestCase):

    def test_parse_switch_config(self):
        dev_id = AddressExpression.parse("00-00-00-01 left")
        self.assertEqual(dev_id[0], b'\x00\x00\x00\x01')
        self.assertEqual(dev_id[1], "left")

        dev_id = AddressExpression.parse("FF-00-00-01 LB")
        self.assertEqual(dev_id[0], b'\xFF\x00\x00\x01')
        self.assertEqual(dev_id[1], "LB")

        dev_id = AddressExpression.parse("FF-00-00-01 LT RB")
        self.assertEqual(dev_id[0], b'\xFF\x00\x00\x01')
        self.assertEqual(dev_id[1], "LT RB")

    def test_binary_sensor_rocker_switch(self):
        bs = TestBinarySensor().create_binary_sensor()
        
        # send push button
        switch_address = b'\xfe\xdb\xb6\x40'
        msg:Regular1BSMessage = RPSMessage(switch_address, status=b'\x30', data=b'\x70')

        self.assertEqual(bs._attr_is_on, None)

        bs.value_changed(msg)
        
        # test if processing was finished and event arrived on bus
        self.assertEqual(len(bs.hass.bus.fired_events), 2)
        self.assertEqual(bs._attr_is_on, True)

        expexced_event_type = 'eltako.gw_123.btn_pressed.sid_FE-DB-B6-40'

        # check event type
        # check no button specific event
        fired_event_0 = bs.hass.bus.fired_events[0]
        self.assertEqual(fired_event_0['event_type'], get_bus_event_type(bs.gateway.dev_id, EVENT_BUTTON_PRESSED, (msg.address,None)))
        self.assertEqual(fired_event_0['event_type'], expexced_event_type)

        # check button specific event
        fired_event_1 = bs.hass.bus.fired_events[1]
        self.assertEqual(fired_event_0['event_type'], get_bus_event_type(bs.gateway.dev_id, EVENT_BUTTON_PRESSED, (msg.address,None)), "RT")
        self.assertEqual(fired_event_1['event_type'], expexced_event_type + '.d_RT')

        # check event data
        expected_data = {
            'data': 112,
            'id': expexced_event_type,
            'pressed': True,
            'pressed_buttons': ['RT'],
            'push_duration_in_sec': -1,
            'push_telegram_received_time_in_sec': 1729513695.2430093,
            'release_telegram_received_time_in_sec': -1,
            'rocker_first_action': 3,
            'rocker_second_action': 0,
            'switch_address': 'FE-DB-B6-40',
            'two_buttons_pressed': False}
        for k in expected_data:
            if k != 'push_telegram_received_time_in_sec':
                self.assertEqual(fired_event_0['event_data'][k], expected_data[k])
        self.assertTrue('push_telegram_received_time_in_sec' in fired_event_0['event_data'])
        self.assertTrue(fired_event_0['event_data']['push_telegram_received_time_in_sec'] > 0)

        self.assertEqual(bs._attr_is_on, True)

        time.sleep(0.2)

        # send release button
        msg:Regular1BSMessage = RPSMessage(switch_address, status=b'\x30', data=b'\x00')

        bs.value_changed(msg)

        # check button specific event
        fired_event_3 = bs.hass.bus.fired_events[3]
        expected_data = {
            'id': 'eltako.gw_123.btn_pressed.sid_FE-DB-B6-40.d_RT', 
            'data': 0, 
            'switch_address': 'FE-DB-B6-40', 
            'pressed_buttons': ['RT'], 
            'pressed': False, 
            'two_buttons_pressed': False, 
            'rocker_first_action': 0, 
            'rocker_second_action': 0, 
            'push_telegram_received_time_in_sec': 1729514202.6208754, 
            'release_telegram_received_time_in_sec': 1729514206.3687692, 
            'push_duration_in_sec': 3.747893810272217}
        for k in expected_data:
            if k not in ['push_telegram_received_time_in_sec', 'release_telegram_received_time_in_sec', 'push_duration_in_sec']:
                self.assertEqual(fired_event_3['event_data'][k], expected_data[k])
        
        self.assertTrue(fired_event_3['event_data']['push_telegram_received_time_in_sec'] > 0)
        self.assertTrue(fired_event_3['event_data']['release_telegram_received_time_in_sec'] > 0)
        self.assertTrue(fired_event_3['event_data']['push_duration_in_sec'] > 0)
        self.assertTrue(fired_event_3['event_data']['push_telegram_received_time_in_sec'] < fired_event_3['event_data']['release_telegram_received_time_in_sec'])
        self.assertEqual(fired_event_3['event_data']['release_telegram_received_time_in_sec'] - fired_event_3['event_data']['push_telegram_received_time_in_sec'], fired_event_3['event_data']['push_duration_in_sec'] )

        self.assertEqual(bs._attr_is_on, False)


    def test_binary_sensor_rocker_switch_button_test(self):
        bs = TestBinarySensor().create_binary_sensor()
        
        switch_address = b'\xfe\xdb\xb6\x40'

        for test_data in [(b'\x70', ['RT']), (b'\x50', ['RB']), (b'\x30', ['LT']), (b'\x10', ['LB'])]:
            msg:Regular1BSMessage = RPSMessage(switch_address, status=b'\x30', data=test_data[0])
            bs.value_changed(msg)

            last_el = len(bs.hass.bus.fired_events)-1
            pressed_buttons = bs.hass.bus.fired_events[last_el]['event_data']['pressed_buttons']
            self.assertEqual(pressed_buttons, test_data[1])
