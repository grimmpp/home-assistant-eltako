import unittest
from mocks import *
from unittest import mock
from homeassistant.helpers.entity import Entity
from homeassistant.const import Platform
from custom_components.eltako.binary_sensor import EltakoBinarySensor, GatewayConnectionState
from custom_components.eltako.config_helpers import *
from eltakobus import *
from eltakobus.eep import *

# mock update of Home Assistant
Entity.schedule_update_ha_state = mock.Mock(return_value=None)
# EltakoBinarySensor.hass.bus.fire is mocked by class HassMock


class TestBinarySensor(unittest.TestCase):

    
    def test_GatewayConnectionState(self):
        gateway=GatewayMock()
        gateway._bus._is_active = False
        gateway.hass.async_create_task = lambda a: []
        gateway.hass.create_task = lambda a: []
        bs = GatewayConnectionState(Platform.BINARY_SENSOR, gateway)

        bs.value_changed(True)
        self.assertEqual(bs._attr_is_on, True)
        
        bs.value_changed(False)
        self.assertEqual(bs._attr_is_on, False)

    def test_directly_online_GatewayConnectionState(self):
        gateway=GatewayMock()
        gateway._bus._is_active = True
        gateway.hass.async_create_task = lambda a: []
        gateway.hass.create_task = lambda a: []
        bs = GatewayConnectionState(Platform.BINARY_SENSOR, gateway)

        bs.value_changed(True)
        self.assertEqual(bs._attr_is_on, True)
        
        bs.value_changed(False)
        self.assertEqual(bs._attr_is_on, False)

