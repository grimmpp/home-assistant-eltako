import unittest
from custom_components.eltako.sensor import *
from mocks import HassMock
from unittest import mock
from mocks import *
from homeassistant.helpers.entity import Entity
from homeassistant.const import Platform
from custom_components.eltako.binary_sensor import EltakoBinarySensor
from eltakobus import *

# mock update of Home Assistant
Entity.schedule_update_ha_state = mock.Mock(return_value=None)
# EltakoBinarySensor.hass.bus.fire is mocked by class HassMock


class TestSensor(unittest.TestCase):

    def create_window_handle_sensor(self) -> EltakoWindowHandle:
        gateway = GatewayMock()
        dev_id = AddressExpression.parse("51-E8-00-01")
        dev_name = "dev name"
        dev_eep = EEP.find("F6-10-00")
        ews = EltakoWindowHandle(Platform.SENSOR, gateway, dev_id, dev_name, dev_eep, SENSOR_DESC_WINDOWHANDLE)

        return ews

    
    def test_window_handle(self):
        whs = self.create_window_handle_sensor()

        whs.entity_description = SENSOR_DESC_WINDOWHANDLE
        whs._attr_native_value = -1

        msg = RPSMessage(address=b'\x05\x1e\x83\x15', status=b'\x20', data=b'\xF0', outgoing=False)
        whs.value_changed(msg)
        self.assertEqual(whs._attr_native_value, STATE_CLOSED)

        msg = RPSMessage(address=b'\x05\x1e\x83\x15', status=b'\x20', data=b'\xC0', outgoing=False)
        whs.value_changed(msg)
        self.assertEqual(whs._attr_native_value, STATE_OPEN)

        msg = RPSMessage(address=b'\x05\x1e\x83\x15', status=b'\x20', data=b'\xE0', outgoing=False)
        whs.value_changed(msg)
        self.assertEqual(whs._attr_native_value, STATE_OPEN)

        msg = RPSMessage(address=b'\x05\x1e\x83\x15', status=b'\x20', data=b'\xD0', outgoing=False)
        whs.value_changed(msg)
        self.assertEqual(whs._attr_native_value, 'tilt')