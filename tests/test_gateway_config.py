"""Gateways can be created in the user interface without configuration.yaml."""
import unittest
from unittest import IsolatedAsyncioTestCase, TestCase

import voluptuous as vol

from tests.mocks import *
from tests.test_enocean_logger import HassDataMock

from custom_components.eltako.config import config_helpers, gateway_config
from custom_components.eltako.const import *

from homeassistant.const import CONF_ID, CONF_NAME


class StoreMock:
    def __init__(self, data: dict = None):
        self.data = data
        self.saved = None

    async def async_load(self):
        return self.data

    async def async_save(self, data):
        self.saved = data


def hass_with(yaml_gateways: list = None, stored: list = None) -> HassDataMock:
    config = {CONF_GATEWAY: yaml_gateways or []}
    hass = HassDataMock(config=config)
    hass.data[DATA_ELTAKO][DATA_GATEWAY_STORE] = StoreMock({'gateways': stored} if stored is not None else None)
    return hass


SERIAL_GATEWAY = {CONF_ID: 3, CONF_DEVICE_TYPE: 'fgw14usb', CONF_NAME: 'Cellar',
                  CONF_SERIAL_PATH: '/dev/ttyUSB3'}
LAN_GATEWAY = {CONF_ID: 4, CONF_DEVICE_TYPE: 'mgw-lan', CONF_GATEWAY_ADDRESS: '192.168.1.50'}


class TestValidation(TestCase):

    def test_serial_gateway(self):
        validated = gateway_config.validate_gateway(SERIAL_GATEWAY)

        self.assertEqual(validated[CONF_ID], 3)
        self.assertEqual(validated[CONF_BASE_ID], '00-00-00-00')      # default of the schema
        self.assertTrue(validated[CONF_GATEWAY_AUTO_RECONNECT])

    def test_lan_gateway(self):
        validated = gateway_config.validate_gateway(LAN_GATEWAY)

        self.assertEqual(validated[CONF_GATEWAY_ADDRESS], '192.168.1.50')
        self.assertEqual(validated[CONF_GATEWAY_PORT], 5100)

    def test_serial_gateway_without_port_is_rejected(self):
        with self.assertRaises(vol.Invalid) as context:
            gateway_config.validate_gateway({CONF_ID: 1, CONF_DEVICE_TYPE: 'fgw14usb'})
        self.assertIn('serial_path', str(context.exception))

    def test_lan_gateway_without_address_is_rejected(self):
        with self.assertRaises(vol.Invalid) as context:
            gateway_config.validate_gateway({CONF_ID: 1, CONF_DEVICE_TYPE: 'mgw-lan'})
        self.assertIn('address', str(context.exception))

    def test_unknown_type_is_rejected(self):
        with self.assertRaises(vol.Invalid):
            gateway_config.validate_gateway({CONF_ID: 1, CONF_DEVICE_TYPE: 'nonsense',
                                             CONF_SERIAL_PATH: '/dev/ttyUSB0'})

    def test_invalid_base_id_is_rejected(self):
        with self.assertRaises(vol.Invalid):
            gateway_config.validate_gateway({**SERIAL_GATEWAY, CONF_BASE_ID: 'not-an-address'})

    def test_devices_are_not_stored_with_the_gateway(self):
        validated = gateway_config.validate_gateway({**SERIAL_GATEWAY, 'devices': {'light': []}})

        self.assertNotIn('devices', validated)

    def test_description_and_serial_path(self):
        validated = gateway_config.validate_gateway(SERIAL_GATEWAY)

        self.assertEqual(gateway_config.get_description(validated), 'Cellar - fgw14usb (Id: 3)')
        self.assertEqual(gateway_config.get_serial_path(validated), '/dev/ttyUSB3')

    def test_lan_gateway_uses_its_address_as_serial_path(self):
        validated = gateway_config.validate_gateway(LAN_GATEWAY)

        self.assertEqual(gateway_config.get_serial_path(validated), '192.168.1.50')

    def test_every_type_has_a_descriptor(self):
        descriptors = gateway_config.get_gateway_type_descriptors()
        types = {d['device_type'] for d in descriptors}

        self.assertEqual(types, {t.value for t in GatewayDeviceType})
        for descriptor in descriptors:
            self.assertIn(descriptor['protocol'], ('ESP2', 'ESP3'))
            self.assertTrue(descriptor['fields'])


class TestMerge(TestCase):

    def test_ui_gateways_are_added(self):
        merged = gateway_config.merge_gateways([{CONF_ID: 1}], [{CONF_ID: 2}])

        self.assertEqual([g[CONF_ID] for g in merged], [1, 2])

    def test_yaml_wins_on_the_same_id(self):
        merged = gateway_config.merge_gateways([{CONF_ID: 1, CONF_NAME: 'from yaml'}],
                                              [{CONF_ID: 1, CONF_NAME: 'from ui'}])

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0][CONF_NAME], 'from yaml')

    def test_merge_without_sources(self):
        self.assertEqual(gateway_config.merge_gateways([], []), [])


class TestStorage(IsolatedAsyncioTestCase):

    async def test_nothing_stored(self):
        hass = hass_with()

        self.assertEqual(await gateway_config.async_load_ui_gateways(hass), [])

    async def test_stored_gateways_are_validated_on_load(self):
        hass = hass_with(stored=[SERIAL_GATEWAY, {CONF_ID: 9, CONF_DEVICE_TYPE: 'nonsense'}])

        gateways = await gateway_config.async_load_ui_gateways(hass)

        self.assertEqual([g[CONF_ID] for g in gateways], [3])      # the broken one is ignored

    async def test_add_and_remove(self):
        hass = hass_with()
        await gateway_config.async_load_ui_gateways(hass)

        await gateway_config.async_add_gateway(hass, SERIAL_GATEWAY)

        self.assertEqual(len(gateway_config.get_ui_gateways(hass)), 1)
        self.assertEqual(hass.data[DATA_ELTAKO][DATA_GATEWAY_STORE].saved['gateways'][0][CONF_ID], 3)

        self.assertTrue(await gateway_config.async_remove_gateway(hass, 3))
        self.assertEqual(gateway_config.get_ui_gateways(hass), [])
        self.assertFalse(await gateway_config.async_remove_gateway(hass, 3))

    async def test_id_which_is_used_in_the_yaml_is_rejected(self):
        hass = hass_with(yaml_gateways=[{CONF_ID: 3, CONF_DEVICE_TYPE: 'fam14'}])
        await gateway_config.async_load_ui_gateways(hass)

        with self.assertRaises(vol.Invalid) as context:
            await gateway_config.async_add_gateway(hass, SERIAL_GATEWAY)

        self.assertIn('already used', str(context.exception))

    async def test_next_free_id(self):
        hass = hass_with(yaml_gateways=[{CONF_ID: 0}, {CONF_ID: 1}], stored=[SERIAL_GATEWAY])
        await gateway_config.async_load_ui_gateways(hass)
        config = hass.data[DATA_ELTAKO][ELTAKO_CONFIG]

        # 0 and 1 from the yaml, 3 from the ui -> 2 is free
        self.assertEqual(gateway_config.get_next_free_id(hass, config), 2)


class TestConfigMerge(IsolatedAsyncioTestCase):
    """The ui gateways must be visible for every consumer of the configuration."""

    async def test_config_contains_ui_gateways(self):
        hass = hass_with(yaml_gateways=[{CONF_ID: 1, CONF_DEVICE_TYPE: 'fam14'}], stored=[SERIAL_GATEWAY])
        await gateway_config.async_load_ui_gateways(hass)

        config = config_helpers.add_ui_gateways_to_config(
            hass, {CONF_GATEWAY: [{CONF_ID: 1, CONF_DEVICE_TYPE: 'fam14'}]})

        self.assertEqual(sorted(g[CONF_ID] for g in config[CONF_GATEWAY]), [1, 3])

    async def test_config_without_ui_gateways_is_unchanged(self):
        hass = hass_with()
        await gateway_config.async_load_ui_gateways(hass)
        original = {CONF_GATEWAY: [{CONF_ID: 1}]}

        self.assertEqual(config_helpers.add_ui_gateways_to_config(hass, original), original)

    async def test_without_hass(self):
        original = {CONF_GATEWAY: []}
        self.assertEqual(config_helpers.add_ui_gateways_to_config(None, original), original)


class ConfigEntryMock:
    """Config entry of a gateway - its data carries description and connection."""

    def __init__(self, gateway_id: int = 3, name: str = 'Cellar', device_type: str = 'fgw14usb',
                 serial_path: str = '/dev/ttyUSB3'):
        self.entry_id = f"entry_{gateway_id}"
        self.data = {CONF_GATEWAY_DESCRIPTION: config_helpers.get_gateway_name(
                         name, device_type, gateway_id),
                     CONF_SERIAL_PATH: serial_path}
        self.options = {}


class ConfigEntriesMock:
    def __init__(self, entries: list = None):
        self.entries = entries or []
        self.updated = []
        self.reloaded = []

    def async_entries(self, domain):
        return self.entries

    def async_update_entry(self, entry, data=None, options=None, **kwargs):
        if data is not None:
            entry.data = data
        if options is not None:
            entry.options = options
        self.updated.append(entry.entry_id)

    async def async_reload(self, entry_id):
        self.reloaded.append(entry_id)


class TestUpdate(IsolatedAsyncioTestCase):
    """Gateways of the web ui can be edited, not only created and removed."""

    async def _hass(self, stored=None, yaml_gateways=None, entries=None):
        hass = hass_with(yaml_gateways=yaml_gateways,
                         stored=stored if stored is not None else [SERIAL_GATEWAY])
        await gateway_config.async_load_ui_gateways(hass)
        hass.config_entries = ConfigEntriesMock(entries)
        return hass

    async def test_name_and_base_id_are_changed(self):
        hass = await self._hass()

        updated = await gateway_config.async_update_gateway(
            hass, 3, {CONF_NAME: 'Attic', CONF_BASE_ID: 'FF-BB-00-00'})

        self.assertEqual(updated[CONF_NAME], 'Attic')
        self.assertEqual(updated[CONF_BASE_ID], 'FF-BB-00-00')
        self.assertEqual(gateway_config.get_ui_gateways(hass)[0][CONF_NAME], 'Attic')
        stored = hass.data[DATA_ELTAKO][DATA_GATEWAY_STORE].saved
        self.assertEqual(stored['gateways'][0][CONF_NAME], 'Attic')

    async def test_fields_which_are_not_sent_keep_their_value(self):
        hass = await self._hass()

        updated = await gateway_config.async_update_gateway(hass, 3, {CONF_NAME: 'Attic'})

        self.assertEqual(updated[CONF_SERIAL_PATH], '/dev/ttyUSB3')
        self.assertEqual(updated[CONF_DEVICE_TYPE], 'fgw14usb')

    async def test_the_id_cannot_be_changed(self):
        """It is part of every entity id of the gateway - changing it would orphan them."""
        hass = await self._hass()

        updated = await gateway_config.async_update_gateway(hass, 3, {CONF_ID: 9, CONF_NAME: 'x'})

        self.assertEqual(updated[CONF_ID], 3)
        self.assertEqual([g[CONF_ID] for g in gateway_config.get_ui_gateways(hass)], [3])

    async def test_serial_port_can_be_corrected(self):
        hass = await self._hass()

        updated = await gateway_config.async_update_gateway(
            hass, 3, {CONF_SERIAL_PATH: '/dev/ttyUSB7'})

        self.assertEqual(updated[CONF_SERIAL_PATH], '/dev/ttyUSB7')

    async def test_switching_to_a_lan_gateway_drops_the_serial_port(self):
        hass = await self._hass()

        updated = await gateway_config.async_update_gateway(
            hass, 3, {CONF_DEVICE_TYPE: 'mgw-lan', CONF_GATEWAY_ADDRESS: '192.168.1.50'})

        self.assertEqual(updated[CONF_GATEWAY_ADDRESS], '192.168.1.50')
        self.assertNotIn(CONF_SERIAL_PATH, updated)

    async def test_switching_to_a_serial_gateway_drops_the_address(self):
        hass = await self._hass(stored=[LAN_GATEWAY])

        updated = await gateway_config.async_update_gateway(
            hass, 4, {CONF_DEVICE_TYPE: 'fam14', CONF_SERIAL_PATH: '/dev/ttyUSB0'})

        self.assertEqual(updated[CONF_SERIAL_PATH], '/dev/ttyUSB0')
        self.assertNotIn(CONF_GATEWAY_ADDRESS, updated)

    async def test_invalid_values_are_rejected_and_nothing_is_stored(self):
        hass = await self._hass()

        with self.assertRaises(vol.Invalid):
            await gateway_config.async_update_gateway(hass, 3, {CONF_BASE_ID: 'nonsense'})

        self.assertEqual(gateway_config.get_ui_gateways(hass)[0][CONF_BASE_ID], '00-00-00-00')
        self.assertIsNone(hass.data[DATA_ELTAKO][DATA_GATEWAY_STORE].saved)

    async def test_a_gateway_of_the_yaml_is_not_editable(self):
        hass = await self._hass(stored=[], yaml_gateways=[{CONF_ID: 1, CONF_DEVICE_TYPE: 'fam14'}])

        with self.assertRaises(vol.Invalid) as context:
            await gateway_config.async_update_gateway(hass, 1, {CONF_NAME: 'x'})

        self.assertIn('configuration.yaml', str(context.exception))

    async def test_unknown_gateway(self):
        hass = await self._hass()

        with self.assertRaises(vol.Invalid) as context:
            await gateway_config.async_update_gateway(hass, 99, {CONF_NAME: 'x'})

        self.assertIn('99', str(context.exception))

    async def test_a_renamed_gateway_updates_its_config_entry(self):
        entry = ConfigEntryMock()
        hass = await self._hass(entries=[entry])

        updated = await gateway_config.async_update_gateway(hass, 3, {CONF_NAME: 'Attic'})
        applied = await gateway_config.async_apply_to_config_entry(hass, updated)

        self.assertTrue(applied['config_entry_updated'])
        self.assertIn('Attic', entry.data[CONF_GATEWAY_DESCRIPTION])
        self.assertEqual(hass.config_entries.updated, [entry.entry_id])

    async def test_a_new_serial_port_reaches_the_config_entry(self):
        entry = ConfigEntryMock()
        hass = await self._hass(entries=[entry])

        updated = await gateway_config.async_update_gateway(
            hass, 3, {CONF_SERIAL_PATH: '/dev/ttyUSB7'})
        await gateway_config.async_apply_to_config_entry(hass, updated)

        self.assertEqual(entry.data[CONF_SERIAL_PATH], '/dev/ttyUSB7')

    async def test_a_change_which_the_entry_does_not_see_reloads_it(self):
        """auto_reconnect lives in the store only - the gateway still has to be rebuilt."""
        entry = ConfigEntryMock()
        hass = await self._hass(entries=[entry])

        updated = await gateway_config.async_update_gateway(
            hass, 3, {CONF_GATEWAY_AUTO_RECONNECT: False})
        applied = await gateway_config.async_apply_to_config_entry(hass, updated)

        self.assertFalse(updated[CONF_GATEWAY_AUTO_RECONNECT])
        self.assertFalse(applied['config_entry_updated'])
        self.assertEqual(hass.config_entries.reloaded, [entry.entry_id])

    async def test_a_gateway_without_config_entry_is_only_stored(self):
        hass = await self._hass(entries=[])

        updated = await gateway_config.async_update_gateway(hass, 3, {CONF_NAME: 'Attic'})
        applied = await gateway_config.async_apply_to_config_entry(hass, updated)

        self.assertFalse(applied['config_entry_updated'])
        self.assertFalse(applied['reloaded'])

    async def test_the_form_marks_which_gateway_is_editable(self):
        hass = await self._hass(yaml_gateways=[{CONF_ID: 1, CONF_DEVICE_TYPE: 'fam14',
                                               CONF_SERIAL_PATH: '/dev/ttyUSB1'}])
        config = config_helpers.add_ui_gateways_to_config(
            hass, hass.data[DATA_ELTAKO][ELTAKO_CONFIG])
        hass.data[DATA_ELTAKO][ELTAKO_CONFIG] = config

        descriptor = gateway_config.get_form_descriptor(hass)
        editable = {gateway['id']: gateway['editable'] for gateway in descriptor['gateways']}

        self.assertFalse(editable[1])        # configuration.yaml
        self.assertTrue(editable[3])         # created in the web ui
        self.assertIn(CONF_NAME, descriptor['editable_fields'])
        self.assertNotIn(CONF_ID, descriptor['editable_fields'])


class TestReportedBaseId(IsolatedAsyncioTestCase):
    """Gateways report their base id after connecting - it is stored for ui gateways."""

    async def _hass_with_ui_gateway(self, base_id=None):
        gateway = dict(SERIAL_GATEWAY)
        if base_id:
            gateway[CONF_BASE_ID] = base_id
        hass = hass_with(stored=[gateway])
        await gateway_config.async_load_ui_gateways(hass)
        return hass

    async def test_reported_base_id_is_stored(self):
        hass = await self._hass_with_ui_gateway()

        changed = await gateway_config.async_update_gateway_base_id(hass, 3, 'ff-aa-00-00')

        self.assertTrue(changed)
        self.assertEqual(gateway_config.get_ui_gateways(hass)[0][CONF_BASE_ID], 'FF-AA-00-00')
        stored = hass.data[DATA_ELTAKO][DATA_GATEWAY_STORE].saved
        self.assertEqual(stored['gateways'][0][CONF_BASE_ID], 'FF-AA-00-00')

    async def test_unchanged_base_id_is_not_saved_again(self):
        hass = await self._hass_with_ui_gateway(base_id='FF-AA-00-00')

        changed = await gateway_config.async_update_gateway_base_id(hass, 3, 'FF-AA-00-00')

        self.assertFalse(changed)
        self.assertIsNone(hass.data[DATA_ELTAKO][DATA_GATEWAY_STORE].saved)

    async def test_empty_report_is_ignored(self):
        hass = await self._hass_with_ui_gateway()

        self.assertFalse(await gateway_config.async_update_gateway_base_id(hass, 3, '00-00-00-00'))
        self.assertFalse(await gateway_config.async_update_gateway_base_id(hass, 3, None))

    async def test_unknown_gateway_is_ignored(self):
        hass = await self._hass_with_ui_gateway()

        self.assertFalse(await gateway_config.async_update_gateway_base_id(hass, 99, 'FF-AA-00-00'))


if __name__ == '__main__':
    unittest.main()
