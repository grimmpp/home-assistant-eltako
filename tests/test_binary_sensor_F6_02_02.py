from unittest import mock
from homeassistant.helpers.entity import Entity

from tests.test_binary_sensor_F6_02_01 import TestBinarySensor_F6_02_01

# mock update of Home Assistant
Entity.schedule_update_ha_state = mock.Mock(return_value=None)
# EltakoBinarySensor.hass.bus.fire is mocked by class HassMock


class TestBinarySensor_F6_02_02(TestBinarySensor_F6_02_01):
    """Same as F6-02-01"""
