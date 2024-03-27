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


class TestSensor_A5_06_01(unittest.TestCase):
    
    

    def create_illumination_sensor(self) -> EltakoIlluminationSensor:
        gateway = GatewayMock()
        dev_id = AddressExpression.parse("FF-FF-00-80")
        dev_name = "device name"
        dev_eep = EEP.find("A5-06-01")
        s = EltakoIlluminationSensor(Platform.SENSOR, gateway, dev_id, dev_name, dev_eep)
        return s
    
    def test_illumincation_sensor(self):
        s_ill = self.create_illumination_sensor()

        # check daylight
        msg = Regular4BSMessage (address=b'\xFF\xFF\x00\x80', data=b'\x60\xAA\x00\x0F', status=0x00)
        s_ill.value_changed(msg)
        self.assertEqual(s_ill.native_value, 20100.0)

        # check twilight
        msg = Regular4BSMessage (address=b'\xFF\xFF\x00\x80', data=b'\x60\x00\x00\x0F', status=0x00)
        s_ill.value_changed(msg)
        self.assertEqual(s_ill.native_value, 96.0)


        