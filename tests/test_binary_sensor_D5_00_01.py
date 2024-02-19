import unittest
from mocks import *
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


class TestBinarySensor_D5_00_01(unittest.TestCase):

    def test_binary_sensor_window_contact_triggered_via_FTS14EM(self):
        bs = TestBinarySensor().create_binary_sensor(eep_string="D5-00-01", device_class = "window", invert_signal =  False)

        # test if sensor object is newly created
        self.assertEqual(bs._attr_is_on, None)       
        
        # test if state is set to no contact
        bs._attr_is_on = False
        self.assertEqual(bs._attr_is_on, False)

        msg = Regular1BSMessage(address=b'\x00\x00\x10\x08', 
                                data=b'\x09', #open
                                status=b'\x00')
        
        # test if signal is processed correctly (switch on)
        bs.value_changed(msg)
        self.assertEqual(bs._attr_is_on, False)

        # test if signal is processed correctly (switch on)
        bs.invert_signal = True
        bs.value_changed(msg)
        self.assertEqual(bs._attr_is_on, True)

        # test if signal is processed correctly (switch off)
        msg.data = b'\x08'  # closed
        bs.invert_signal = False
        bs.value_changed(msg)
        self.assertEqual(bs._attr_is_on, True)

        # test if signal is processed correctly (switch off)
        bs.invert_signal = True
        bs.value_changed(msg)
        self.assertEqual(bs._attr_is_on, False)

