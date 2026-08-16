import asyncio
import unittest
import voluptuous as vol
from tests.mocks import GatewayMock, LatestStateMock
from unittest import mock
from homeassistant.helpers.entity import Entity
from homeassistant.const import Platform
from homeassistant.components.climate import HVACMode, PRESET_ECO, PRESET_HOME
from custom_components.eltako.climate import ClimateController, _get_cooling_components
from custom_components.eltako.config.config_helpers import CONF_EEP, CONF_ID, DeviceConf
from custom_components.eltako.core.entity import EltakoEntity
from eltakobus.eep import A5_10_06, F6_02_01
from eltakobus import AddressExpression
from custom_components.eltako.const import (CONF_COOLING_MODE, CONF_OFF_TEMPERATURE,
                                             CONF_ROOM_SENSOR, CONF_SENSOR, CONF_SENDER,
                                             CONF_SWITCH_BUTTON)
from custom_components.eltako.config.schema import ClimateSchema

# mock update of Home Assistant
Entity.schedule_update_ha_state = mock.Mock(return_value=None)
ClimateController.schedule_update_ha_state = mock.Mock(return_value=None)
# EltakoBinarySensor.hass.bus.fire is mocked by class HassMock

# send_message is mocked for this module only. A module-level class patch would leak into
# every later test of the pytest process (e.g. the fanout tests of the real send_message).
_original_send_message = EltakoEntity.send_message

def setUpModule():
    EltakoEntity.send_message = mock.Mock(return_value=None)

def tearDownModule():
    EltakoEntity.send_message = _original_send_message

class EventDataMock():
    def __init__(self,d):
        self.data = d

def create_climate_entity(thermostat:DeviceConf=None, cooling_switch:DeviceConf=None,
                          room_sensor: str = None, off_temperature: float = None):
    gw = GatewayMock(dev_id=12345)
    dev_id = AddressExpression.parse("00-00-00-01") # heating cooling actuator
    dev_name = "Room 1"
    dev_eep = A5_10_06
    sender_id = AddressExpression.parse("00-00-B0-01")  # home assistant
    sender_eep = A5_10_06
    temp_unit = "°C"
    min_temp = 16
    max_temp = 25

    cc = ClimateController(Platform.CLIMATE, gw, dev_id, dev_name, dev_eep, sender_id,
                           sender_eep, temp_unit, min_temp, max_temp, thermostat,
                           cooling_switch, None, None, room_sensor, off_temperature)
    return cc

class TestClimate(unittest.TestCase):

    def test_climate_temp_actuator(self):
        cc = create_climate_entity()
        self.assertEqual(cc.unique_id, 'eltako_gw_12345_00_00_00_01')
        self.assertEqual(cc.entity_id, 'climate.eltako_gw_12345_00_00_00_01')
        self.assertEqual(cc.dev_name, 'Room 1')
        self.assertEqual(cc.temperature_unit, '°C')
        self.assertEqual(cc.cooling_sender, None)
        self.assertEqual(cc.cooling_switch, None)
        self.assertEqual(cc.thermostat, None)
        self.assertEqual(cc.hvac_mode, HVACMode.OFF)
        self.assertEqual(cc._attr_actuator_mode, A5_10_06.HeaterMode.NORMAL)

        self.assertIsNone(cc.target_temperature)
        self.assertIsNone(cc.current_temperature)

        mode = A5_10_06.HeaterMode.NORMAL
        target_temp = 24
        current_temperature = 21
        prio = A5_10_06.ControllerPriority.AUTO
        msg = A5_10_06(mode, target_temp, current_temperature, prio).encode_message(b'\x00\x00\x00\x01')
        cc.value_changed(msg)
        self.assertEqual(cc.hvac_mode, HVACMode.HEAT)
        self.assertEqual( cc._attr_actuator_mode, mode)
        self.assertEqual( round(cc.current_temperature), current_temperature)
        self.assertEqual( round(cc.target_temperature), target_temp)
        # priority is handled in select entity
        self.assertEqual( A5_10_06.decode_message(msg).priority, prio)


    def test_climate_thermostat(self):
        thermostat = DeviceConf({
            CONF_ID: 'FF-FF-FF-01',
            CONF_EEP: 'A5-10-06',
        })
        cc = create_climate_entity(thermostat)
        self.assertEqual(cc.unique_id, 'eltako_gw_12345_00_00_00_01')
        self.assertEqual(cc.entity_id, 'climate.eltako_gw_12345_00_00_00_01')
        self.assertEqual(cc.dev_name, 'Room 1')
        self.assertEqual(cc.temperature_unit, '°C')
        self.assertEqual(cc.cooling_sender, None)
        self.assertEqual(cc.cooling_switch, None)
        self.assertIsNotNone(cc.thermostat)
        self.assertEqual(cc.hvac_mode, HVACMode.OFF)
        self.assertEqual(cc._attr_actuator_mode, A5_10_06.HeaterMode.NORMAL)
        self.assertEqual(cc.listen_to_addresses, [cc._external_dev_id[0], cc.thermostat.id[0]])

        self.assertIsNone(cc.target_temperature)
        self.assertIsNone(cc.current_temperature)

        mode = A5_10_06.HeaterMode.NORMAL
        target_temp = 24
        current_temperature = 21
        prio = A5_10_06.ControllerPriority.AUTO
        msg = A5_10_06(mode, target_temp, current_temperature, prio).encode_message(b'\xFF\xFF\xFF\x01')
        cc.value_changed(msg)
        self.assertEqual(cc.hvac_mode, HVACMode.HEAT)
        self.assertEqual( cc._attr_actuator_mode, mode)
        self.assertEqual( round(cc.current_temperature), current_temperature)
        self.assertEqual( round(cc.target_temperature), target_temp)


    def test_missing_current_temperature_logs_warning_and_uses_protocol_fallback(self):
        cc = create_climate_entity()
        EltakoEntity.send_message.reset_mock()

        with self.assertLogs('eltako', level='WARNING') as logs:
            cc._send_command(A5_10_06.HeaterMode.NORMAL, 21, cc._attr_priority)

        self.assertTrue(any('No valid current temperature' in message for message in logs.output))
        message = EltakoEntity.send_message.call_args.args[0]
        decoded = A5_10_06.decode_message(message)
        self.assertAlmostEqual(decoded.current_temperature, 40, delta=0.2)


    def test_climate_cooling_switch(self):
        cooling_switch = DeviceConf({
            CONF_ID: 'FF-FF-FF-01',
            CONF_EEP: 'A5-10-06',
        })
        cc = create_climate_entity(cooling_switch=cooling_switch)
        self.assertEqual(cc.unique_id, 'eltako_gw_12345_00_00_00_01')
        self.assertEqual(cc.entity_id, 'climate.eltako_gw_12345_00_00_00_01')
        self.assertEqual(cc.dev_name, 'Room 1')
        self.assertEqual(cc.temperature_unit, '°C')
        self.assertEqual(cc.cooling_sender, None)
        self.assertIsNotNone(cc.cooling_switch)
        self.assertEqual(cc.thermostat, None)
        self.assertEqual(cc.hvac_mode, HVACMode.OFF)
        self.assertEqual(cc._attr_actuator_mode, A5_10_06.HeaterMode.NORMAL)

        self.assertIsNone(cc.target_temperature)
        self.assertIsNone(cc.current_temperature)

        #0x70 = 3
        msg = F6_02_01(3, 1, 0, 0).encode_message(b'\xFF\xFF\xFF\x01')
        cc.value_changed(msg)
        ##TODO:
        # self.assertEqual(cc.hvac_mode, HVACMode.HEAT)
        # self.assertEqual(cc._actuator_mode, A5_10_06.Heater_Mode.NORMAL);
        # self.assertEqual( round(cc.current_temperature), current_temperature)
        # self.assertEqual( round(cc.target_temperature), target_temp)


    def test_initial_loading(self):
        cc = create_climate_entity()

        cc.load_value_initially(LatestStateMock('heat',
                                                attributes={'hvac_modes': ['heat', 'off'],
                                                            'min_temp': 17,
                                                            'max_temp': 25,
                                                            'current_temperature': 19.8,
                                                            'temperature': 22.5,
                                                            'friendly_name': 'Bad Room',
                                                            'supported_features': 385}))
        self.assertEqual(cc.current_temperature, 19.8)
        self.assertEqual(cc.target_temperature, 22.5)
        self.assertEqual(cc.state, 'heat')


    def test_initial_loading_None(self):
        cc = create_climate_entity()

        cc.load_value_initially(LatestStateMock(None))
        self.assertEqual(cc.current_temperature, None)
        # When no target temperature was previously stored, fall back to the configured min_temp
        # so the UI starts at a sensible, in-range value instead of "Unknown".
        self.assertEqual(cc.target_temperature, cc._attr_min_temp)
        self.assertEqual(cc.state, 'off')

    def test_priority_uses_actuator_ack_without_physical_thermostat(self):
        self.assertEqual(create_climate_entity()._attr_priority,
                         A5_10_06.ControllerPriority.ACTUATOR_ACK)

    def test_priority_uses_auto_with_physical_thermostat(self):
        thermostat = DeviceConf({CONF_ID: 'FF-FF-FF-01', CONF_EEP: 'A5-10-06'})
        self.assertEqual(create_climate_entity(thermostat)._attr_priority,
                         A5_10_06.ControllerPriority.AUTO)

    def test_off_temperature_sends_anti_frost_target_and_restores_last_target(self):
        cc = create_climate_entity(off_temperature=8)
        cc._attr_hvac_mode = HVACMode.HEAT
        cc._attr_target_temperature = 21
        EltakoEntity.send_message.reset_mock()

        cc._send_mode_off()

        message = EltakoEntity.send_message.call_args.args[0]
        decoded = A5_10_06.decode_message(message)
        self.assertEqual(decoded.target_temperature, 8)
        self.assertEqual(cc.hvac_mode, HVACMode.OFF)
        self.assertEqual(cc.target_temperature, 8)

        EltakoEntity.send_message.reset_mock()
        cc._send_set_normal_mode()
        decoded = A5_10_06.decode_message(EltakoEntity.send_message.call_args.args[0])
        self.assertAlmostEqual(decoded.target_temperature, 21, delta=0.2)

    def test_room_sensor_is_used_in_outgoing_a5_10_06_message(self):
        cc = create_climate_entity(room_sensor='sensor.room_temperature')
        cc._attr_target_temperature = 22
        EltakoEntity.send_message.reset_mock()

        return_event = EventDataMock({'new_state': mock.Mock(state='20.5')})
        asyncio.run(cc._async_room_sensor_changed(return_event))

        self.assertEqual(cc.current_temperature, 20.5)
        decoded = A5_10_06.decode_message(EltakoEntity.send_message.call_args.args[0])
        self.assertAlmostEqual(decoded.current_temperature, 20.5, delta=0.2)

    def test_climate_schema_accepts_room_sensor_and_off_temperature(self):
        config = {
            CONF_ID: '00-00-00-01',
            CONF_EEP: 'A5-10-06',
            'sender': {CONF_ID: '00-00-B0-01', CONF_EEP: 'A5-10-06'},
            CONF_ROOM_SENSOR: 'sensor.room_temperature',
            CONF_OFF_TEMPERATURE: 8,
        }
        result = ClimateSchema.ENTITY_SCHEMA(config)
        self.assertEqual(result[CONF_ROOM_SENSOR], 'sensor.room_temperature')
        self.assertEqual(result[CONF_OFF_TEMPERATURE], 8)

    def test_climate_schema_rejects_invalid_room_sensor_and_off_temperature(self):
        base = {
            CONF_ID: '00-00-00-01',
            CONF_EEP: 'A5-10-06',
            'sender': {CONF_ID: '00-00-B0-01', CONF_EEP: 'A5-10-06'},
        }
        with self.assertRaises(vol.Invalid):
            ClimateSchema.ENTITY_SCHEMA({**base, CONF_ROOM_SENSOR: 'not-an-entity'})
        with self.assertRaises(vol.Invalid):
            ClimateSchema.ENTITY_SCHEMA({**base, CONF_OFF_TEMPERATURE: 41})

    def test_cooling_mode_configuration_builds_sensor_and_sender(self):
        sensor, sender = _get_cooling_components({
            CONF_COOLING_MODE: {
                CONF_SENSOR: {CONF_ID: '00-00-10-08', CONF_SWITCH_BUTTON: 0x70},
                CONF_SENDER: {CONF_ID: '00-00-B0-08', CONF_EEP: 'A5-10-06'},
            }
        })
        self.assertIsNotNone(sensor)
        self.assertEqual(sensor.id, AddressExpression.parse('00-00-10-08'))
        self.assertEqual(sensor.get(CONF_SWITCH_BUTTON), 0x70)
        self.assertEqual(sender.id, AddressExpression.parse('00-00-B0-08'))

    def test_cooling_mode_is_optional(self):
        self.assertEqual(_get_cooling_components({}), (None, None))

class TestClimateAsync(unittest.IsolatedAsyncioTestCase):

    async def test_hvac_mode_waits_for_actuator_status(self):
        cc = create_climate_entity()
        cc._attr_hvac_mode = HVACMode.HEAT
        EltakoEntity.send_message.reset_mock()

        await cc.async_set_hvac_mode(HVACMode.OFF)

        # The command is sent, but the displayed state remains the last
        # confirmed actuator state until a status telegram arrives.
        self.assertEqual(EltakoEntity.send_message.call_count, 1)
        self.assertEqual(cc.hvac_mode, HVACMode.HEAT)

        status = A5_10_06(
            A5_10_06.HeaterMode.OFF,
            21,
            20,
            A5_10_06.ControllerPriority.ACTUATOR_ACK,
        ).encode_message(cc.dev_id[0])
        cc.value_changed(status)

        self.assertEqual(cc.hvac_mode, HVACMode.OFF)
        self.assertEqual(cc._attr_actuator_mode, A5_10_06.HeaterMode.OFF)

    async def test_preset_sends_only_mode_command(self):
        cc = create_climate_entity()
        cc._attr_target_temperature = 21
        EltakoEntity.send_message.reset_mock()

        await cc.async_set_preset_mode(PRESET_ECO)

        # The requested preset is sent, but the entity state is updated only
        # after the actuator confirms it with a telegram.
        self.assertEqual(EltakoEntity.send_message.call_count, 1)
        self.assertEqual(cc.preset_mode, PRESET_HOME)

        status = A5_10_06(
            A5_10_06.HeaterMode.STAND_BY_2_DEGREES,
            21,
            20,
            A5_10_06.ControllerPriority.ACTUATOR_ACK,
        ).encode_message(cc.dev_id[0])
        cc.value_changed(status)
        self.assertEqual(cc.preset_mode, PRESET_ECO)

    async def test_climate_cooling_switch(self):
        cooling_switch = DeviceConf({
            CONF_ID: 'FF-FF-FF-01',
            CONF_EEP: 'A5-10-06',
            CONF_SWITCH_BUTTON: 0x50
        })
        cc = create_climate_entity(cooling_switch=cooling_switch)
        self.assertEqual(cc.unique_id, 'eltako_gw_12345_00_00_00_01')
        self.assertEqual(cc.entity_id, 'climate.eltako_gw_12345_00_00_00_01')
        self.assertEqual(cc.dev_name, 'Room 1')
        self.assertEqual(cc.temperature_unit, '°C')
        self.assertEqual(cc.cooling_sender, None)
        self.assertIsNotNone(cc.cooling_switch)
        self.assertEqual(cc.thermostat, None)
        self.assertEqual(cc.hvac_mode, HVACMode.OFF)
        self.assertEqual(cc._attr_actuator_mode, A5_10_06.HeaterMode.NORMAL)

        self.assertIsNone(cc.target_temperature)
        self.assertIsNone(cc.current_temperature)

        await cc.async_handle_cooling_switch_event(EventDataMock({'switch_address': cooling_switch.id, 'data': cooling_switch[CONF_SWITCH_BUTTON]}))
        self.assertEqual(cc.hvac_mode, HVACMode.COOL)

    async def test_home_assistant_cooling_selection_overrides_input_signal(self):
        cooling_switch = DeviceConf({
            CONF_ID: 'FF-FF-FF-01', CONF_EEP: 'F6-02-01', CONF_SWITCH_BUTTON: 0x70,
        })
        cc = create_climate_entity(cooling_switch=cooling_switch)

        await cc.async_handle_cooling_selection(EventDataMock({'cooling': True}))
        self.assertEqual(cc.hvac_mode, HVACMode.COOL)
        self.assertEqual(cc._get_mode(), HVACMode.COOL)

        await cc.async_handle_cooling_selection(EventDataMock({'cooling': False}))
        self.assertEqual(cc.hvac_mode, HVACMode.HEAT)
        self.assertEqual(cc._get_mode(), HVACMode.HEAT)
