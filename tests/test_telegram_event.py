"""Incoming telegrams are fired as Home Assistant event `eltako_global_event_bus`.

Automations can subscribe to it independently of whether a device is configured for that
address - the button events of rocker switches only exist for configured devices
(github issue #201). The address of the event is always the external (wireless) address, so
that senders of the RS485 bus and radio senders can be told apart by one automation.
See docs/telegram-events/readme.md.
"""
import unittest
from unittest import TestCase, mock

from tests.mocks import *

from custom_components.eltako.const import ELTAKO_GLOBAL_EVENT_BUS_ID
from eltakobus.message import EltakoWrappedRPS, EltakoDiscoveryRequest, RPSMessage


class TestTelegramEvent(TestCase):

    def create_gateway(self, base_id='FF-AA-80-00') -> GatewayMock:
        gateway = GatewayMock(base_id=AddressExpression.parse(base_id))
        gateway._record_telegram = mock.Mock(return_value=None)
        return gateway

    def receive(self, gateway, telegram):
        """The dispatcher needs a real event loop, the mocked hass has none."""
        with mock.patch('custom_components.eltako.gateway.dispatcher_send'):
            gateway._callback_receive_message_from_serial_bus(telegram)

    def fired_telegram_events(self, gateway):
        return [e for e in gateway.hass.bus.fired_events
                if e['event_type'] == ELTAKO_GLOBAL_EVENT_BUS_ID]

    def test_event_of_a_radio_telegram(self):
        gateway = self.create_gateway()

        self.receive(gateway, RPSMessage(address=b'\xFF\xBB\xCC\xDD', status=0x30, data=b'\x10'))

        events = self.fired_telegram_events(gateway)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['event_data']['msg']['address'], 'FF-BB-CC-DD')
        self.assertEqual(events[0]['event_data']['gateway']['id'], gateway.dev_id)
        self.assertEqual(events[0]['event_data']['gateway']['name'], gateway.dev_name)

    def test_local_bus_address_is_reported_as_external_address(self):
        """A bus device sends 00-00-00-05; automations need the address as the rest of the
        radio network sees it (base id + address), the local one stays available."""
        gateway = self.create_gateway('FF-AA-80-00')

        self.receive(gateway, EltakoWrappedRPS(address=b'\x00\x00\x00\x05', status=0x30, data=b'\x70'))

        event_data = self.fired_telegram_events(gateway)[0]['event_data']
        self.assertEqual(event_data['msg']['address'], 'FF-AA-80-05')
        self.assertEqual(event_data['msg']['local_address'], '00-00-00-05')

    def test_no_event_without_a_known_base_id(self):
        gateway = self.create_gateway('00-00-00-00')

        self.receive(gateway, RPSMessage(address=b'\xFF\xBB\xCC\xDD', status=0x30, data=b'\x10'))

        self.assertEqual(self.fired_telegram_events(gateway), [])

    def test_discovery_requests_are_not_forwarded(self):
        gateway = self.create_gateway()

        self.receive(gateway, EltakoDiscoveryRequest(8))

        self.assertEqual(self.fired_telegram_events(gateway), [])


if __name__ == '__main__':
    unittest.main()
