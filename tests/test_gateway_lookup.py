"""Gateway objects must be found by type, not by guessing the name of the hass.data key.

Regression test: the integration stores its own data in hass.data[DATA_ELTAKO] as well. A key
like 'ui_gateway_store' matched the prefix check `k.startswith('gateway')` and the gateway
lookup crashed with an AttributeError - which made all gateways disappear from the web ui.
"""
import unittest
from unittest import TestCase

from tests.mocks import GatewayMock
from tests.test_enocean_logger import HassDataMock

from custom_components.eltako.const import (DATA_BUS_MEMBERS, DATA_DEVICE_ACTIVITY, DATA_ELTAKO,
                                            DATA_ENTITIES, DATA_GATEWAY_STORE, DATA_SETTINGS_OVERRIDES,
                                            DATA_SETTINGS_STORE, DATA_TELEGRAM_LOGGER, DATA_UI_GATEWAYS)
from custom_components.eltako.core.websocket import get_gateways, _get_configured_gateways


class TestGatewayLookup(TestCase):

    def setUp(self):
        self.hass = HassDataMock()
        self.gateway = GatewayMock(dev_id=1)
        self.hass.data[DATA_ELTAKO]['gateway_1'] = self.gateway

    def test_gateway_is_found(self):
        self.assertEqual(get_gateways(self.hass), [self.gateway])

    def test_other_data_with_a_gateway_like_key_is_ignored(self):
        """This is what broke it: a store object under a key starting with 'gateway'."""
        self.hass.data[DATA_ELTAKO]['gateway_store'] = object()
        self.hass.data[DATA_ELTAKO][DATA_GATEWAY_STORE] = object()
        self.hass.data[DATA_ELTAKO][DATA_UI_GATEWAYS] = [{'id': 7}]

        self.assertEqual(get_gateways(self.hass), [self.gateway])

    def test_describing_the_gateways_does_not_raise(self):
        self.hass.data[DATA_ELTAKO][DATA_GATEWAY_STORE] = object()

        described = _get_configured_gateways(self.hass)

        self.assertEqual(len(described), 1)
        self.assertEqual(described[0]['id'], 1)
        self.assertIn('connected', described[0])

    def test_gateways_are_sorted_by_id(self):
        self.hass.data[DATA_ELTAKO]['gateway_0'] = GatewayMock(dev_id=0)

        self.assertEqual([g['id'] for g in _get_configured_gateways(self.hass)], [0, 1])

    def test_own_data_keys_do_not_start_with_gateway(self):
        """Keeps the collision from coming back through a new constant."""
        for key in (DATA_UI_GATEWAYS, DATA_GATEWAY_STORE, DATA_SETTINGS_STORE,
                    DATA_SETTINGS_OVERRIDES, DATA_BUS_MEMBERS, DATA_DEVICE_ACTIVITY,
                    DATA_TELEGRAM_LOGGER, DATA_ENTITIES):
            self.assertFalse(str(key).startswith('gateway'), msg=key)


if __name__ == '__main__':
    unittest.main()
