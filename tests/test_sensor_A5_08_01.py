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


class TestSensor_A5_08_01(unittest.TestCase):
    
    msg1 = Regular4BSMessage (address=b'\xFF\xFF\x00\x80', data=b'\xaa\x80\x76\x0f', status=0x00)

    def create_temperature_sensor(self) -> EltakoTemperatureSensor:
        gateway = GatewayMock()
        dev_id = AddressExpression.parse("FF-FF-00-80")
        dev_name = "device name"
        dev_eep = EEP.find("A5-08-01")
        s = EltakoTemperatureSensor(Platform.SENSOR, gateway, dev_id, dev_name, dev_eep)
        return s
    
    def create_illumination_sensor(self) -> EltakoIlluminationSensor:
        gateway = GatewayMock()
        dev_id = AddressExpression.parse("FF-FF-00-80")
        dev_name = "device name"
        dev_eep = EEP.find("A5-08-01")
        s = EltakoIlluminationSensor(Platform.SENSOR, gateway, dev_id, dev_name, dev_eep)
        return s
    
    def create_battery_voltage_sensor(self) -> EltakoBatteryVoltageSensor:
        gateway = GatewayMock()
        dev_id = AddressExpression.parse("FF-FF-00-80")
        dev_name = "device name"
        dev_eep = EEP.find("A5-08-01")
        s = EltakoBatteryVoltageSensor(Platform.SENSOR, gateway, dev_id, dev_name, dev_eep)
        return s

    def test_a5_08_01_battery_voltage_sensor(self):
        s_vlt = self.create_battery_voltage_sensor()

        s_vlt.value_changed(self.msg1)
        self.assertEquals(s_vlt.native_value, 3.3999999999999995)

    def test_a5_08_01_temperature_sensor(self):
        s_temp = self.create_temperature_sensor()

        s_temp.value_changed(self.msg1)
        self.assertEquals(s_temp.native_value, 23.6)

    def test_a5_08_01_illumincation_sensor(self):
        s_ill = self.create_illumination_sensor()

        s_ill.value_changed(self.msg1)
        self.assertEquals(s_ill.native_value, 256.0)


        