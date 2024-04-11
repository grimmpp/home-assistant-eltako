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


class TestBinarySensor_A5_30_01(unittest.TestCase):

    def test_digital_input(self):
        bs = TestBinarySensor().create_binary_sensor(A5_30_01.eep_string)

        msg = Regular4BSMessage(b'\00\x00\x00\x01', 0x20, b'\00\x92\x00\x0E')
        bs.value_changed(msg)

        self.assertEqual(bs.is_on, True)

        msg = Regular4BSMessage(b'\00\x00\x00\x01', 0x20, b'\00\x92\xFF\x0E')
        bs.value_changed(msg)

        self.assertEqual(bs.is_on, False)


    def test_inverted_digital_input(self):
        bs = TestBinarySensor().create_binary_sensor(A5_30_01.eep_string)
        bs.invert_signal = True

        msg = Regular4BSMessage(b'\00\x00\x00\x01', 0x20, b'\00\x92\x00\x0E')
        bs.value_changed(msg)

        self.assertEqual(bs.is_on, False)

        msg = Regular4BSMessage(b'\00\x00\x00\x01', 0x20, b'\00\x92\xFF\x0E')
        bs.value_changed(msg)

        self.assertEqual(bs.is_on, True)
        

    def test_battery(self):
        bs = TestBinarySensor().create_binary_sensor(A5_30_01.eep_string, description_key="low_battery")

        msg = Regular4BSMessage(b'\00\x00\x00\x01', 0x20, b'\00\x92\x00\x0E')
        bs.value_changed(msg)

        self.assertEqual(bs.is_on, False)

        msg = Regular4BSMessage(b'\00\x00\x00\x01', 0x20, b'\FF\x92\xFF\x0E')
        bs.value_changed(msg)

        self.assertEqual(bs.is_on, True)