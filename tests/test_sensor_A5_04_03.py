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


class TestSensor_A5_04_02(unittest.TestCase):

    msg1 = Regular4BSMessage(address=b'\xFF\xFF\x00\x80', data=b'\x99\x02\x12\x09', status=0x00)
    
    def create_temperature_sensor(self) -> EltakoTemperatureSensor:
        gateway = GatewayMock()
        dev_id = AddressExpression.parse("FF-FF-00-80")
        dev_name = "device name"
        dev_eep = EEP.find("A5-04-03")
        s = EltakoTemperatureSensor(Platform.SENSOR, gateway, dev_id, dev_name, dev_eep)
        return s
    
    def create_humidity_sensor(self) -> EltakoHumiditySensor:
        gateway = GatewayMock()
        dev_id = AddressExpression.parse("FF-FF-00-80")
        dev_name = "device name"
        dev_eep = EEP.find("A5-04-03")
        s = EltakoHumiditySensor(Platform.SENSOR, gateway, dev_id, dev_name, dev_eep)
        return s
    
    def test_temperature_sensor_A5_04_02(self):
        s_temp = self.create_temperature_sensor()

        s_temp.value_changed(self.msg1)
        self.assertEqual(s_temp.native_value, 22.8125)

    def test_humidity_sensor_A5_04_02(self):
        s_hum = self.create_humidity_sensor()

        s_hum.value_changed(self.msg1)
        self.assertEqual(s_hum.native_value, 60.0)