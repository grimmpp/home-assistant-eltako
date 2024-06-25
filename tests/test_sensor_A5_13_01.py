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


class TestSensor(unittest.TestCase):

    def create_weatherstation_sensor(self, description: EltakoSensorEntityDescription) -> EltakoWeatherStation:
        gateway = GatewayMock()
        dev_id = AddressExpression.parse("51-E8-00-01")
        dev_name = "dev name"
        dev_eep = EEP.find("A5-13-01")
        ews = EltakoWeatherStation(Platform.SENSOR, gateway, dev_id, dev_name, dev_eep, description)

        return ews
    

    def test_weatherstation_sensor(self):
        ews = self.create_weatherstation_sensor(SENSOR_DESC_WEATHER_STATION_ILLUMINANCE_DAWN)
        
        msg = Regular4BSMessage(address=b'\x05\x1e\x83\x15', status=b'\x00', data=b'\x0f\x7d\x07\x1a', outgoing=False)
        
        ews.entity_description = SENSOR_DESC_WEATHER_STATION_ILLUMINANCE_DAWN
        ews._attr_native_value = -1
        ews.value_changed(msg)
        self.assertEqual(ews.native_value, 58.76470588235294)

        ews.entity_description = SENSOR_DESC_WEATHER_STATION_TEMPERATURE
        ews._attr_native_value = -1
        ews.value_changed(msg)
        self.assertEqual(ews.native_value, 18.823529411764703)

        ews.entity_description = SENSOR_DESC_WEATHER_STATION_WIND_SPEED
        ews._attr_native_value = -1
        ews.value_changed(msg)
        self.assertEqual(ews.native_value, 1.9215686274509804)

        ews.entity_description = SENSOR_DESC_WEATHER_STATION_RAIN
        ews._attr_native_value = -1
        ews.value_changed(msg)
        self.assertEqual(ews.native_value, 1)

        msg = Regular4BSMessage(address=b'\x05\x1e\x83\x15', status=b'\x00', data=b'\x01\x0a\x08\x28', outgoing=False)

        ews.entity_description = SENSOR_DESC_WEATHER_STATION_ILLUMINANCE_EAST
        ews._attr_native_value = -1
        ews.value_changed(msg)
        self.assertEqual(ews.native_value, 4705.882352941177)

        ews.entity_description = SENSOR_DESC_WEATHER_STATION_ILLUMINANCE_CENTRAL
        ews._attr_native_value = -1
        ews.value_changed(msg)
        self.assertEqual(ews.native_value, 5882.35294117647)

        ews.entity_description = SENSOR_DESC_WEATHER_STATION_ILLUMINANCE_WEST
        ews._attr_native_value = -1
        ews.value_changed(msg)
        self.assertEqual(ews.native_value, 588.2352941176471)

