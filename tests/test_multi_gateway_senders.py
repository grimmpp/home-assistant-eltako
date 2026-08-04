"""The radio is a virtual bus with several gateways (and repeaters) attached to it.

A wireless device taught into more than one gateway gets ONE entity, but a sender per
gateway: the entity receives through all gateways anyway (shared global event bus) and
repeats every command with the sender of each taught-in gateway. Commands are idempotent,
telegrams arriving several times are fine.
"""
import unittest
from unittest import TestCase, mock

from tests.mocks import *
from tests.test_enocean_logger import HassDataMock

from custom_components.eltako import config_helpers, device as device_module
from custom_components.eltako.const import *
from custom_components.eltako.light import EltakoDimmableLight

from eltakobus.eep import EEP
from eltakobus.message import Regular4BSMessage, prettify
from eltakobus.util import AddressExpression, b2s

from homeassistant.const import CONF_DEVICES, CONF_ID, Platform
from homeassistant.helpers.entity import Entity

Entity.schedule_update_ha_state = mock.Mock(return_value=None)


def wireless_config(second_sender: dict | None = None) -> dict:
    """A wireless dimmer (FUD61) taught into gateway 1 and - optionally - gateway 2."""
    second = {CONF_ID: 'FF-13-57-9F', CONF_EEP: 'A5-38-08', 'name': 'FUD61'}
    if second_sender is not None:
        second[CONF_SENDER] = second_sender
    return {CONF_GATEWAY: [
        {CONF_ID: 1, CONF_DEVICES: {'light': [
            {CONF_ID: 'FF-13-57-9F', CONF_EEP: 'A5-38-08', 'name': 'FUD61',
             CONF_SENDER: {CONF_ID: 'FF-AA-80-01', CONF_EEP: 'A5-38-08'}}]}},
        {CONF_ID: 2, CONF_DEVICES: {'light': [second]}},
    ]}


class TestCollectAdditionalSenders(TestCase):

    def test_second_declaration_contributes_its_sender(self):
        senders = config_helpers.collect_additional_senders(
            wireless_config({CONF_ID: 'FF-BB-00-01', CONF_EEP: 'A5-38-08'}))

        self.assertEqual(senders, {('light', 'FF-13-57-9F'): [
            {CONF_ID: 'FF-BB-00-01', CONF_EEP: 'A5-38-08', CONF_GATEWAY_ID: 2}]})

    def test_declaration_without_sender_contributes_nothing(self):
        self.assertEqual(config_helpers.collect_additional_senders(wireless_config(None)), {})

    def test_bus_devices_are_not_collected(self):
        """Bus devices get one entity per gateway - no sender merge needed."""
        config = {CONF_GATEWAY: [
            {CONF_ID: 1, CONF_DEVICES: {'light': [
                {CONF_ID: '00-00-00-01', CONF_EEP: 'M5-38-08',
                 CONF_SENDER: {CONF_ID: '00-00-B0-01', CONF_EEP: 'A5-38-08'}}]}},
            {CONF_ID: 2, CONF_DEVICES: {'light': [
                {CONF_ID: '00-00-00-01', CONF_EEP: 'M5-38-08',
                 CONF_SENDER: {CONF_ID: '00-00-B0-01', CONF_EEP: 'A5-38-08'}}]}},
        ]}

        self.assertEqual(config_helpers.collect_additional_senders(config), {})

    def test_runs_before_remove_duplicate_devices(self):
        """remove_duplicate_devices drops the second declaration - the senders must be
        collected from the intact configuration first."""
        config = wireless_config({CONF_ID: 'FF-BB-00-01', CONF_EEP: 'A5-38-08'})

        senders = config_helpers.collect_additional_senders(config)
        config_helpers.remove_duplicate_devices(config, log=False)

        self.assertEqual(len(senders), 1)
        self.assertEqual(config_helpers.collect_additional_senders(config), {})


class TestCommandFanout(TestCase):
    """One entity, one command - repeated once per taught-in gateway with its sender."""

    PRIMARY_SENDER = 'FF-AA-80-01'
    SECOND_SENDER = 'FF-BB-00-01'

    def setUp(self):
        self.dispatched = []
        self._original = device_module.dispatcher_send
        device_module.dispatcher_send = lambda hass, event_id, msg: self.dispatched.append(msg)

    def tearDown(self):
        device_module.dispatcher_send = self._original

    def _light(self, additional_senders: dict) -> EltakoDimmableLight:
        gateway = GatewayMock(dev_id=1)
        light = EltakoDimmableLight(Platform.LIGHT, gateway, AddressExpression.parse('FF-13-57-9F'),
                                    'FUD61', EEP.find('A5-38-08'),
                                    AddressExpression.parse(self.PRIMARY_SENDER), EEP.find('A5-38-08'))
        light.hass = HassDataMock()
        light.hass.data[DATA_ELTAKO][DATA_ADDITIONAL_SENDERS] = additional_senders
        return light

    def _command(self) -> Regular4BSMessage:
        """A dimming command as the light builds it - with the primary sender."""
        address, _ = AddressExpression.parse(self.PRIMARY_SENDER)
        return Regular4BSMessage(address=address, status=0x00, data=b'\x02\x64\x00\x09')

    def test_command_is_repeated_with_the_sender_of_the_second_gateway(self):
        light = self._light({('light', 'FF-13-57-9F'): [
            {CONF_ID: self.SECOND_SENDER, CONF_EEP: 'A5-38-08', CONF_GATEWAY_ID: 2}]})

        light.send_message(self._command())

        self.assertEqual(len(self.dispatched), 2)
        senders = [prettify(msg).address for msg in self.dispatched]
        self.assertEqual([b2s(address) for address in senders],
                         [self.PRIMARY_SENDER, self.SECOND_SENDER])
        # the payload is identical - only the sender differs
        self.assertEqual(self.dispatched[0].body[:-5], self.dispatched[1].body[:-5])
        self.assertEqual(self.dispatched[0].body[-1:], self.dispatched[1].body[-1:])

    def test_without_additional_senders_nothing_is_repeated(self):
        light = self._light({})

        light.send_message(self._command())

        self.assertEqual(len(self.dispatched), 1)

    def test_foreign_message_is_not_repeated(self):
        """Only telegrams built with the own sender are repeated - a forwarded telegram
        of another origin passes through exactly once."""
        light = self._light({('light', 'FF-13-57-9F'): [
            {CONF_ID: self.SECOND_SENDER, CONF_EEP: 'A5-38-08', CONF_GATEWAY_ID: 2}]})
        foreign = Regular4BSMessage(address=b'\xFF\x99\x99\x99', status=0x00,
                                    data=b'\x02\x64\x00\x09')

        light.send_message(foreign)

        self.assertEqual(len(self.dispatched), 1)

    def test_broken_sender_does_not_stop_the_others(self):
        light = self._light({('light', 'FF-13-57-9F'): [
            {CONF_ID: 'not-an-address', CONF_EEP: 'A5-38-08', CONF_GATEWAY_ID: 2},
            {CONF_ID: self.SECOND_SENDER, CONF_EEP: 'A5-38-08', CONF_GATEWAY_ID: 3}]})

        light.send_message(self._command())

        self.assertEqual(len(self.dispatched), 2)   # primary + the valid one

    def test_fanout_never_breaks_the_primary_send(self):
        """Also with a hass without data dict (older tests) the primary send must work."""
        gateway = GatewayMock(dev_id=1)
        light = EltakoDimmableLight(Platform.LIGHT, gateway, AddressExpression.parse('FF-13-57-9F'),
                                    'FUD61', EEP.find('A5-38-08'),
                                    AddressExpression.parse(self.PRIMARY_SENDER), EEP.find('A5-38-08'))

        light.send_message(self._command())     # hass = HassMock without .data

        self.assertEqual(len(self.dispatched), 1)


if __name__ == '__main__':
    unittest.main()
