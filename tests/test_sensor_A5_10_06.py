import unittest
from custom_components.eltako.sensor import *
from unittest import mock
from tests.mocks import *
from homeassistant.helpers.entity import Entity
from homeassistant.const import Platform
from custom_components.eltako.binary_sensor import EltakoBinarySensor
from eltakobus import *

# mock update of Home Assistant
Entity.schedule_update_ha_state = mock.Mock(return_value=None)
# EltakoBinarySensor.hass.bus.fire is mocked by class HassMock


class TestSensor_A5_10_06(unittest.TestCase):
    
    msg = Regular4BSMessage (address=b'\xFF\xFF\x00\x80', data=b'\xAA\x80\x76\x0F', status=0x00)

    def create_temp_sensor(self) -> EltakoTemperatureSensor:
        gateway = GatewayMock()
        dev_id = AddressExpression.parse("FF-FF-00-80")
        dev_name = "device name"
        dev_eep = EEP.find("A5-10-06")
        s = EltakoTemperatureSensor(Platform.SENSOR, gateway, dev_id, dev_name, dev_eep)
        return s
    
    def create_target_temp_sensor(self) -> EltakoTargetTemperatureSensor:
        gateway = GatewayMock()
        dev_id = AddressExpression.parse("FF-FF-00-80")
        dev_name = "device name"
        dev_eep = EEP.find("A5-10-06")
        s = EltakoTargetTemperatureSensor(Platform.SENSOR, gateway, dev_id, dev_name, dev_eep)
        return s
    
    def test_temp_sensor(self):
        ts = self.create_temp_sensor()

        self.assertEqual(ts.native_value, None)
        ts.value_changed(self.msg)

        self.assertEqual(ts.native_value, 21.49019607843137)

    def test_target_temp_sensor(self):
        ts = self.create_target_temp_sensor()

        self.assertEqual(ts.native_value, None)
        ts.value_changed(self.msg)

        self.assertEqual(ts.native_value, 20)


    def test_heater_modes(self):
        data = {
            "NORMAL": b'\x70\x80\x76\x0F',                       # normal mode
            "STAND_BY_2_DEGREES": b'\x30\x80\x76\x0F',           # -2°K degree off-set mode              
            "NIGHT_SET_BACK_4_DEGREES": b'\x50\x80\x76\x0F',     # night set back (-4°K)
            "OFF": b'\x10\x80\x76\x0F',                          # Off
            "UNKNOWN": b'\x00\x80\x76\x0F'
        }

        for k in data:
            msg = Regular4BSMessage (address=b'\xFF\xFF\x00\x80', data=data[k], status=0x80)
            mode = A5_10_06.decode_message(msg).mode
            self.assertEqual(mode, A5_10_06.HeaterMode[k])
        
    def test_invalid_heater_mode(self):
        # invalid mode
        d = b'\xAA\x80\x76\x0F'
        msg = Regular4BSMessage (address=b'\xFF\xFF\x00\x80', data=d, status=0x80)
        mode = A5_10_06.decode_message(msg).mode
        self.assertEqual(mode, A5_10_06.HeaterMode.UNKNOWN)

    def test_controller_priorities(self):
        data = {
            "AUTO": b'\x70\x80\x76\x0E',                      # 00-TT-00-0E   no Priority (thermostat and controller have same prio)
            "HOME_AUTOMATION": b'\x70\x80\x76\x08', # 00-TT-00-08   only values from softare controller, registered in actuator, are considered 
#            "THERMOSTAT": b'\x00\x00\x00\x0E',          # 00-00-00-0E   only values from thermostat, registered in actuator, are considered (disables softeare controller)
            "LIMIT": b'\x70\x80\x76\x0A', # 00-TT-00-0A   Controller defines target temperature and thermostat can change it in a range of -3 to + 3 degree
            "ACTUATOR_ACK": b'\x70\x80\x76\x0F',
        }

        for k in data:
            msg = Regular4BSMessage (address=b'\xFF\xFF\x00\x80', data=data[k], status=0x80)
            mode = A5_10_06.decode_message(msg).priority
            self.assertEqual(mode, A5_10_06.ControllerPriority[k])