"""Restoring the last state of a sensor after a restart.

Home Assistant hands the last state over as string. A counter ('total_increasing', e.g. of an
electricity meter) can therefore contain a decimal point - casting that directly to int raised
a ValueError and made Home Assistant drop the entity (github issue #175).
"""
import unittest
from tests.mocks import *
from unittest import mock

from homeassistant.helpers.entity import Entity
from homeassistant.const import Platform

from custom_components.eltako.config.config_helpers import parse_number_state
from custom_components.eltako.sensor import EltakoMeterSensor, SENSOR_DESC_ELECTRICITY_CUMULATIVE

# mock update of Home Assistant
Entity.schedule_update_ha_state = mock.Mock(return_value=None)


class TestParseNumberState(unittest.TestCase):

    def test_int(self):
        self.assertEqual(parse_number_state('36231'), 36231)
        self.assertIsInstance(parse_number_state('36231'), int)

    def test_float(self):
        self.assertEqual(parse_number_state('36231.4'), 36231.4)
        self.assertIsInstance(parse_number_state('36231.4'), float)

    def test_float_without_fraction_stays_int(self):
        self.assertEqual(parse_number_state('36231.0'), 36231)
        self.assertIsInstance(parse_number_state('36231.0'), int)

    def test_negative_and_comma(self):
        self.assertEqual(parse_number_state('-12.5'), -12.5)
        self.assertEqual(parse_number_state('12,5'), 12.5)

    def test_not_a_number(self):
        self.assertIsNone(parse_number_state('open'))
        self.assertIsNone(parse_number_state(''))
        self.assertIsNone(parse_number_state(None))
        self.assertIsNone(parse_number_state('1.2.3'))


class TestSensorStateRestore(unittest.TestCase):

    def create_meter_sensor(self) -> EltakoMeterSensor:
        return EltakoMeterSensor(Platform.SENSOR, GatewayMock(),
                                 AddressExpression.parse('00-00-00-40'), 'Electricity meter',
                                 EEP.find('A5-12-01'), SENSOR_DESC_ELECTRICITY_CUMULATIVE, tariff=0)

    def test_restore_cumulative_float(self):
        """github issue #175: 'invalid literal for int() with base 10: 36231.4'"""
        sensor = self.create_meter_sensor()
        sensor.load_value_initially(LatestStateMock('36231.4', {'state_class': 'total_increasing'}))

        self.assertEqual(sensor.native_value, 36231.4)

    def test_restore_cumulative_int(self):
        sensor = self.create_meter_sensor()
        sensor.load_value_initially(LatestStateMock('36231', {'state_class': 'total_increasing'}))

        self.assertEqual(sensor.native_value, 36231)
        self.assertIsInstance(sensor.native_value, int)

    def test_restore_measurement(self):
        sensor = self.create_meter_sensor()
        sensor.load_value_initially(LatestStateMock('123.45', {'state_class': 'measurement'}))

        self.assertEqual(sensor.native_value, 123.45)

    def test_restore_total(self):
        sensor = self.create_meter_sensor()
        sensor.load_value_initially(LatestStateMock('7.5', {'state_class': 'total'}))

        self.assertEqual(sensor.native_value, 7.5)

    def test_restore_unknown_and_unavailable(self):
        for state in ('unknown', 'unavailable'):
            sensor = self.create_meter_sensor()
            sensor.load_value_initially(LatestStateMock(state, {'state_class': 'total_increasing'}))

            self.assertIsNone(sensor.native_value)

    def test_restore_of_not_numeric_value_does_not_raise(self):
        sensor = self.create_meter_sensor()
        sensor.load_value_initially(LatestStateMock('open', {'state_class': 'measurement'}))

        self.assertIsNone(sensor.native_value)
