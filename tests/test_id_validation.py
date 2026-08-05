import unittest
from unittest import mock

from tests.mocks import *

from homeassistant.const import Platform
from homeassistant.helpers.entity import Entity

from custom_components.eltako.config_helpers import compare_enocean_ids
from custom_components.eltako.const import GatewayDeviceType
from custom_components.eltako.device import validate_actuators_dev_and_sender_id
from custom_components.eltako.switch import EltakoSwitch
from custom_components.eltako.sensor import (GatewayBaseId, GatewayInfoField,
                                            GatewayLastReceivedMessage,
                                            GatewayReceivedMessagesInActiveSession,
                                            StaticInfoField)
from custom_components.eltako.select import RepeaterMode
from eltakobus import AddressExpression, b2s

# mock update of Home Assistant
Entity.schedule_update_ha_state = mock.Mock(return_value=None)


class TestActuatorIdValidation(unittest.TestCase):
    """Only entities of configured devices are validated.

    Gateway-level, metadata and configuration entities use the base id of the gateway or
    00-00-00-00 by design. Validating them as actuators produced warnings which hid the real
    configuration problems (github issue #203).
    """

    def create_gateway(self, dev_type=GatewayDeviceType.GatewayEltakoFGW14USB,
                       base_id='FF-E7-C1-80') -> GatewayMock:
        gateway = GatewayMock(base_id=AddressExpression.parse(base_id))
        gateway._attr_dev_type = dev_type
        return gateway

    def collect_warnings(self, entities):
        with mock.patch('custom_components.eltako.gateway.LOGGER') as logger:
            validate_actuators_dev_and_sender_id(entities)
        return [str(call.args[0]) for call in logger.warning.call_args_list]

    def gateway_and_metadata_entities(self, gateway):
        platform = Platform.SENSOR
        return [
            GatewayLastReceivedMessage(platform, gateway),
            GatewayReceivedMessagesInActiveSession(platform, gateway),
            GatewayBaseId(platform, gateway),
            GatewayInfoField(platform, gateway, "Id", str(gateway.dev_id)),
            StaticInfoField(platform, gateway, AddressExpression.parse('00-00-00-39'),
                            "Küchenfenster", None, "Id", '00-00-00-39'),
            RepeaterMode(Platform.SELECT, gateway),
        ]

    def test_gateway_and_metadata_entities_are_not_validated(self):
        gateway = self.create_gateway()
        entities = self.gateway_and_metadata_entities(gateway)

        self.assertEqual(self.collect_warnings(entities), [])

    def test_gateway_and_metadata_entities_of_a_transceiver_are_not_validated(self):
        # a wireless transceiver expects FF-XX-XX-XX, so 00-00-00-00 of the gateway entities
        # would be reported as wrong
        gateway = self.create_gateway(GatewayDeviceType.GatewayEltakoFAMUSB, 'FF-AA-80-00')
        entities = self.gateway_and_metadata_entities(gateway)

        self.assertEqual(self.collect_warnings(entities), [])

    def create_switch(self, gateway, dev_id: str, sender_id: str) -> EltakoSwitch:
        return EltakoSwitch(Platform.SWITCH, gateway, AddressExpression.parse(dev_id),
                            'device name', EEP.find('M5-38-08'),
                            AddressExpression.parse(sender_id), EEP.find('A5-38-08'))

    def test_local_actuator_id_of_a_bus_gateway_is_valid(self):
        gateway = self.create_gateway()
        switch = self.create_switch(gateway, '00-00-00-39', '00-00-B1-05')

        self.assertEqual(self.collect_warnings([switch]), [])

    def test_wireless_id_on_a_bus_gateway_is_reported(self):
        gateway = self.create_gateway()
        switch = self.create_switch(gateway, 'FF-AA-BB-CC', '00-00-B1-05')

        warnings = self.collect_warnings([switch])
        self.assertEqual(len(warnings), 1)
        self.assertIn('FF-AA-BB-CC', warnings[0])
        self.assertIn('00-00-XX-XX', warnings[0])          # names the expected format
        self.assertIn('fgw14usb', warnings[0])             # names the gateway type

    def test_local_id_on_a_transceiver_is_reported(self):
        gateway = self.create_gateway(GatewayDeviceType.GatewayEltakoFAMUSB, 'FF-AA-80-00')
        switch = self.create_switch(gateway, '00-00-00-39', 'FF-AA-80-05')

        warnings = self.collect_warnings([switch])
        self.assertEqual(len(warnings), 1)
        self.assertIn('FF-XX-XX-XX', warnings[0])

    def test_sender_id_outside_the_base_id_range_is_reported(self):
        """A transceiver only sends telegrams of its own base id range - a sender id from
        somewhere else silently does nothing."""
        gateway = self.create_gateway(GatewayDeviceType.GatewayEltakoFAMUSB, 'FF-AA-80-00')
        switch = self.create_switch(gateway, 'FF-BB-CC-DD', 'FF-11-22-33')

        warnings = self.collect_warnings([switch])
        self.assertEqual(len(warnings), 1)
        self.assertIn('FF-11-22-33', warnings[0])
        self.assertIn('FF-AA-80', warnings[0])

    def test_sender_id_is_not_validated_without_a_known_base_id(self):
        """The base id is queried from the gateway after the connection is established. Until
        then every sender id would look wrong."""
        gateway = self.create_gateway(GatewayDeviceType.GatewayEltakoFAMUSB, '00-00-00-00')
        switch = self.create_switch(gateway, 'FF-BB-CC-DD', 'FF-11-22-33')

        self.assertEqual(self.collect_warnings([switch]), [])


class TestIdComparison(unittest.TestCase):

    def mock_send_message(self, msg):
        self.last_sent_command = msg

    def test_id_validation(self):
        id1 = AddressExpression.parse('00-12-FA-50')
        id2 = AddressExpression.parse('00-12-FA-50')
        result = compare_enocean_ids(id1[0], id2[0], len=4)

        self.assertTrue(result)

    def test_neg_id_validation(self):
        id1 = AddressExpression.parse('00-12-FA-FF')
        id2 = AddressExpression.parse('00-12-FA-50')
        result = compare_enocean_ids(id1[0], id2[0], len=4)

        self.assertTrue(not result)

        id1 = AddressExpression.parse('11-12-FA-FF')
        id2 = AddressExpression.parse('00-12-FA-FF')
        result = compare_enocean_ids(id1[0], id2[0], len=4)

        self.assertTrue(not result)

    def test_base_id_comparison(self):
        id1 = AddressExpression.parse('FF-BB-FA-00')
        id2 = AddressExpression.parse('FF-BB-FA-50')
        result = compare_enocean_ids(id1[0], id2[0], len=3)

        self.assertTrue(result)

        id1 = AddressExpression.parse('00-00-00-00')
        id2 = AddressExpression.parse('00-00-00-50')
        result = compare_enocean_ids(id1[0], id2[0], len=3)

        self.assertTrue(result)

    def test_neg_base_id_comparison(self):
        id1 = AddressExpression.parse('00-BB-FA-00')
        id2 = AddressExpression.parse('FF-BB-FA-50')
        result = compare_enocean_ids(id1[0], id2[0], len=3)

        self.assertTrue(not result)

        id1 = AddressExpression.parse('FF-BB-00-00')
        id2 = AddressExpression.parse('00-00-00-50')
        result = compare_enocean_ids(id1[0], id2[0], len=3)

        self.assertTrue(not result)


    def test_b2s(self):
        rawdata = b'\x01\x02\x03\xFF'
        self.assertEqual(b2s(rawdata), '01-02-03-FF')

        rawdata = [0x1, 0x2, 0x3, 0xFF]
        self.assertEqual(b2s(rawdata), '01-02-03-FF')

        rawdata = AddressExpression.parse('01-02-03-FF')
        self.assertEqual(b2s(rawdata), '01-02-03-FF')