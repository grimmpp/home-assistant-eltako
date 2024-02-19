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


class TestBinarySensor_A5_07_01(unittest.TestCase):

    def test_occupancy_sensor(self):
        bs = TestBinarySensor().create_binary_sensor(eep_string="A5-07-01")

        self.assertEqual(bs._attr_is_on, None)

        msg = Regular4BSMessage(address=b'\x00\x00\x10\x08', data=b'\x00\x96\xC8\x09', status=b'\x00')

        bs.value_changed(msg)
        self.assertEqual(bs._attr_is_on, True)

        msg.data = b'\x00\x96\x0A\x09'
        bs.value_changed(msg)
        self.assertEqual(bs._attr_is_on, False)

