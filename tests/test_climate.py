import unittest
from mocks import *
from unittest import mock
from homeassistant.helpers.entity import Entity
from homeassistant.const import Platform
from homeassistant.components.climate import HVACMode
from custom_components.eltako.climate import ClimateController
from custom_components.eltako.config_helpers import *
from custom_components.eltako.device import EltakoEntity
from eltakobus.eep import *
from eltakobus import *

# mock update of Home Assistant
Entity.schedule_update_ha_state = mock.Mock(return_value=None)
EltakoEntity.send_message = mock.Mock(return_value=None)
# EltakoBinarySensor.hass.bus.fire is mocked by class HassMock

class EventDataMock():
    def __init__(self,d):
        self.data = d

def create_climate_entity(thermostat:DeviceConf=None, cooling_switch:DeviceConf=None):    
    gw = GatewayMock(dev_id=12345)
    dev_id = AddressExpression.parse("00-00-00-01") # heating cooling actuator
    dev_name = "Room 1"
    dev_eep = A5_10_06
    sender_id = AddressExpression.parse("00-00-B0-01")  # home assistant
    sender_eep = A5_10_06
    temp_unit = "°C"
    min_temp = 16
    max_temp = 25
    
    cc = ClimateController(Platform.CLIMATE, gw, dev_id, dev_name, dev_eep, sender_id, sender_eep, temp_unit, min_temp, max_temp, thermostat, cooling_switch, None)
    return cc

class TestClimate(unittest.TestCase):

    def test_climate_temp_actuator(self):
        cc = create_climate_entity()
        self.assertEquals(cc.unique_id, 'eltako_gw12345_00-00-00-01')
        self.assertEquals(cc.entity_id, 'climate.eltako_gw12345_00-00-00-01')
        self.assertEquals(cc.dev_name, 'Room 1')
        self.assertEquals(cc.temperature_unit, '°C')
        self.assertEquals(cc.cooling_sender, None)
        self.assertEquals(cc.cooling_switch, None)
        self.assertEquals(cc.thermostat, None)
        self.assertEquals(cc.hvac_mode, HVACMode.OFF)
        self.assertEquals(cc._actuator_mode, None)

        self.assertEquals(cc.target_temperature, 0)
        self.assertEquals(cc.current_temperature, 0)

        mode = A5_10_06.Heater_Mode.NORMAL
        target_temp = 24
        current_temperature = 21
        msg = A5_10_06(mode, target_temp, current_temperature, False).encode_message(b'\x00\x00\x00\x01')
        cc.value_changed(msg)
        self.assertEquals( round(cc.current_temperature), current_temperature)
        self.assertEquals( round(cc.target_temperature), target_temp)
        

    def test_climate_thermostat(self):
        thermostat = DeviceConf({
            CONF_ID: 'FF-FF-FF-01',
            CONF_EEP: 'A5-10-06',
        })
        cc = create_climate_entity(thermostat)
        self.assertEquals(cc.unique_id, 'eltako_gw12345_00-00-00-01')
        self.assertEquals(cc.entity_id, 'climate.eltako_gw12345_00-00-00-01')
        self.assertEquals(cc.dev_name, 'Room 1')
        self.assertEquals(cc.temperature_unit, '°C')
        self.assertEquals(cc.cooling_sender, None)
        self.assertEquals(cc.cooling_switch, None)
        self.assertIsNotNone(cc.thermostat)
        self.assertEquals(cc.hvac_mode, HVACMode.OFF)
        self.assertEquals(cc._actuator_mode, None)

        self.assertEquals(cc.target_temperature, 0)
        self.assertEquals(cc.current_temperature, 0)

        mode = A5_10_06.Heater_Mode.NORMAL
        target_temp = 24
        current_temperature = 21
        msg = A5_10_06(mode, target_temp, current_temperature, False).encode_message(b'\xFF\xFF\xFF\x01')
        cc.value_changed(msg)
        self.assertEquals(cc.hvac_mode, HVACMode.HEAT)
        self.assertEquals(cc._actuator_mode, A5_10_06.Heater_Mode.NORMAL);
        self.assertEquals( round(cc.current_temperature), current_temperature)
        self.assertEquals( round(cc.target_temperature), target_temp)


    def test_climate_cooling_switch(self):
        cooling_switch = DeviceConf({
            CONF_ID: 'FF-FF-FF-01',
            CONF_EEP: 'A5-10-06',
        })
        cc = create_climate_entity(cooling_switch=cooling_switch)
        self.assertEquals(cc.unique_id, 'eltako_gw12345_00-00-00-01')
        self.assertEquals(cc.entity_id, 'climate.eltako_gw12345_00-00-00-01')
        self.assertEquals(cc.dev_name, 'Room 1')
        self.assertEquals(cc.temperature_unit, '°C')
        self.assertEquals(cc.cooling_sender, None)
        self.assertIsNotNone(cc.cooling_switch)
        self.assertEquals(cc.thermostat, None)
        self.assertEquals(cc.hvac_mode, HVACMode.OFF)
        self.assertEquals(cc._actuator_mode, None)

        self.assertEquals(cc.target_temperature, 0)
        self.assertEquals(cc.current_temperature, 0)

        #0x70 = 3
        msg = F6_02_01(3, 1, 0, 0).encode_message(b'\xFF\xFF\xFF\x01')
        cc.value_changed(msg)
        # self.assertEquals(cc.hvac_mode, HVACMode.HEAT)
        # self.assertEquals(cc._actuator_mode, A5_10_06.Heater_Mode.NORMAL);
        # self.assertEquals( round(cc.current_temperature), current_temperature)
        # self.assertEquals( round(cc.target_temperature), target_temp)
    
class TestClimateAsync(unittest.IsolatedAsyncioTestCase):

    async def test_climate_cooling_switch(self):
        cooling_switch = DeviceConf({
            CONF_ID: 'FF-FF-FF-01',
            CONF_EEP: 'A5-10-06',
            CONF_SWITCH_BUTTON: 0x50
        })
        cc = create_climate_entity(cooling_switch=cooling_switch)
        self.assertEquals(cc.unique_id, 'eltako_gw12345_00-00-00-01')
        self.assertEquals(cc.entity_id, 'climate.eltako_gw12345_00-00-00-01')
        self.assertEquals(cc.dev_name, 'Room 1')
        self.assertEquals(cc.temperature_unit, '°C')
        self.assertEquals(cc.cooling_sender, None)
        self.assertIsNotNone(cc.cooling_switch)
        self.assertEquals(cc.thermostat, None)
        self.assertEquals(cc.hvac_mode, HVACMode.OFF)
        self.assertEquals(cc._actuator_mode, None)

        self.assertEquals(cc.target_temperature, 0)
        self.assertEquals(cc.current_temperature, 0)

        #0x70 = 3
        msg = F6_02_01(3, 1, 0, 0).encode_message(b'\xFF\xFF\xFF\x01')
        # cc.value_changed(msg)
        await cc.async_handle_event(EventDataMock({'switch_address': cooling_switch.id, 'data': cooling_switch[CONF_SWITCH_BUTTON]}))
        self.assertEquals(cc.hvac_mode, HVACMode.COOL)

