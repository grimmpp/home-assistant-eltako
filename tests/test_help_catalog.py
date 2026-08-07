"""The help catalog must be derived, never written down.

The point of help_catalog.py is that the help page cannot go stale: a device added to the
catalog, an EEP added to eltakobus or a tutorial added to docs/ has to appear without anybody
editing a list. These tests therefore check the *derivation* - that the numbers follow the
sources - rather than pinning the contents, which would defeat the purpose.
"""

import os
from unittest import TestCase

from custom_components.eltako.catalog import device_catalog, help_catalog
from custom_components.eltako.const import PLATFORMS, GatewayDeviceType


class TestPlatforms(TestCase):

    def test_every_entity_platform_with_a_schema_is_listed(self):
        """binary_sensor and climate used to be missing.

        They keep their EEP list in a module constant / under a different attribute name, so
        anything reading `CONF_EEP_SUPPORTED` silently skipped them. The schema itself is
        walked now, which does not care how the list is stored.
        """
        listed = {platform['platform'] for platform in help_catalog.get_platforms()}

        for platform in ('binary_sensor', 'climate', 'cover', 'light', 'sensor', 'switch'):
            self.assertIn(platform, listed)

    def test_configuration_schemas_are_not_platforms(self):
        """The gateway and the general settings are schemas, but produce no entities."""
        listed = {platform['platform'] for platform in help_catalog.get_platforms()}

        self.assertNotIn('gateway', listed)
        self.assertNotIn('general_settings', listed)
        self.assertTrue(listed.issubset({str(platform) for platform in PLATFORMS}))

    def test_the_eeps_come_from_the_schema(self):
        """Spot check against a schema which is read directly."""
        from custom_components.eltako.config.schema import LightSchema

        light = next(p for p in help_catalog.get_platforms() if p['platform'] == 'light')

        self.assertEqual(sorted(LightSchema.CONF_EEP_SUPPORTED), light['eeps'])
        self.assertEqual(sorted(LightSchema.CONF_SENDER_EEP_SUPPORTED), light['sender_eeps'])

    def test_sender_eeps_are_kept_apart(self):
        """A sensor receives only - it must not claim sender EEPs."""
        sensor = next(p for p in help_catalog.get_platforms() if p['platform'] == 'sensor')

        self.assertEqual([], sensor['sender_eeps'])
        self.assertTrue(sensor['eeps'])


class TestEeps(TestCase):

    def setUp(self):
        self.eeps = help_catalog.get_eeps()
        self.by_name = {eep['eep']: eep for eep in self.eeps}

    def test_every_profile_of_the_library_is_there(self):
        for name in help_catalog._known_eep_strings():
            self.assertIn(name, self.by_name, msg=f'{name} is missing')

    def test_profiles_are_described(self):
        """The description is the docstring of the profile class, not a copy."""
        described = [eep for eep in self.eeps if eep['description']]

        self.assertGreater(len(described), len(self.eeps) * 0.8,
                           msg='most profiles should carry their docstring')
        self.assertIn('Temperature', self.by_name['A5-04-02']['description'])

    def test_an_eep_knows_which_platforms_take_it(self):
        self.assertIn('light', self.by_name['A5-38-08']['platforms'])
        self.assertIn('cover', self.by_name['G5-3F-7F']['platforms'])

    def test_an_eep_knows_its_devices(self):
        """Derived from the catalog - a device added there shows up here."""
        entry = self.by_name['A5-04-02']

        expected = {device['hw_type'] for device in device_catalog.DEVICE_CATALOG
                    if str(device.get('eep', '')).upper() == 'A5-04-02'}
        self.assertTrue(expected.issubset(set(entry['devices'])))

    def test_profiles_without_a_platform_are_marked_instead_of_dropped(self):
        """They can still be recorded and analysed, so hiding them would be wrong."""
        without = [eep for eep in self.eeps if not eep['usable_as_entity']]

        for eep in without:
            self.assertEqual([], eep['platforms'])
            self.assertFalse(eep['usable_as_entity'])

    def test_an_eep_only_the_catalog_knows_is_not_lost(self):
        """A device may name a profile the installed eltakobus cannot decode."""
        for eep in self.eeps:
            if not eep['decodable']:
                self.assertTrue(eep['devices'] or eep['platforms'],
                                msg=f"{eep['eep']} comes from nowhere")


class TestDevices(TestCase):

    def setUp(self):
        self.devices = help_catalog.get_devices()

    def test_every_hardware_type_of_the_catalog_appears_once(self):
        expected = {entry['hw_type'] for entry in device_catalog.DEVICE_CATALOG}
        listed = [device['hw_type'] for device in self.devices]

        self.assertEqual(expected, set(listed))
        self.assertEqual(len(listed), len(set(listed)), msg='a device is listed twice')

    def test_a_device_with_several_profiles_collects_them(self):
        """FTS14EM speaks more than one EEP - all of them belong to the one entry."""
        fts14em = next(device for device in self.devices if device['hw_type'] == 'FTS14EM')

        expected = {entry['eep'] for entry in device_catalog.DEVICE_CATALOG
                    if entry['hw_type'] == 'FTS14EM' and entry.get('eep')}
        self.assertEqual(expected, {profile['eep'] for profile in fts14em['profiles']})
        self.assertGreater(len(expected), 1)

    def test_gateways_come_first(self):
        first_device = next(index for index, device in enumerate(self.devices) if not device['is_gateway'])
        gateways_after = [device['hw_type'] for device in self.devices[first_device:] if device['is_gateway']]

        self.assertEqual([], gateways_after)

    def test_bus_devices_are_marked(self):
        fsr14 = next(device for device in self.devices if device['hw_type'] == 'FSR14_4x')

        self.assertTrue(fsr14['bus_device'])
        self.assertEqual(4, fsr14['address_count'])


class TestGateways(TestCase):

    def setUp(self):
        self.gateways = help_catalog.get_gateways()

    def test_every_gateway_type_appears_once(self):
        """GatewayDeviceType carries aliases - iterating the enum yields each value once."""
        listed = [gateway['gateway_type'] for gateway in self.gateways]

        self.assertEqual(len(listed), len(set(listed)), msg='an alias slipped through')
        self.assertEqual({gateway_type.value for gateway_type in GatewayDeviceType}, set(listed))

    def test_the_protocol_is_asked_from_the_enum(self):
        by_type = {gateway['gateway_type']: gateway for gateway in self.gateways}

        self.assertEqual('ESP2', by_type['fam14']['protocol'])
        self.assertEqual('ESP2', by_type['fam-usb']['protocol'])
        self.assertEqual('ESP3', by_type['enocean-usb300']['protocol'])

    def test_bus_gateways_are_marked(self):
        by_type = {gateway['gateway_type']: gateway for gateway in self.gateways}

        self.assertTrue(by_type['fam14']['bus_gateway'])
        self.assertFalse(by_type['fam-usb']['bus_gateway'])

    def test_a_gateway_carries_its_catalog_entry(self):
        by_type = {gateway['gateway_type']: gateway for gateway in self.gateways}

        self.assertEqual('FAM14', by_type['fam14']['hw_type'])
        # the brand is a display value and is written in capitals, like everywhere in the ui
        self.assertEqual('ELTAKO', by_type['fam14']['brand'])

    def test_every_gateway_links_to_documentation(self):
        for gateway in self.gateways:
            self.assertTrue(gateway['docs'], msg=gateway['gateway_type'])


class TestDocumentation(TestCase):

    def setUp(self):
        self.documents = help_catalog.get_documentation()
        self.docs_dir = os.path.join(help_catalog._repository_root(), 'docs')

    def test_every_documented_topic_is_offered(self):
        """A tutorial added to docs/ appears without registering it anywhere."""
        expected = {name for name in os.listdir(self.docs_dir)
                    if os.path.isfile(os.path.join(self.docs_dir, name, 'readme.md'))}
        listed = {document['section'] for document in self.documents}

        self.assertTrue(expected.issubset(listed), msg=f'missing: {sorted(expected - listed)}')

    def test_the_title_is_the_heading_of_the_document(self):
        grafana = next(document for document in self.documents if document['section'] == 'grafana')

        self.assertNotEqual('Grafana', grafana['title'], msg='the heading should win over the fallback')
        self.assertIn('Grafana', grafana['title'])

    def test_the_url_points_into_the_repository(self):
        for document in self.documents:
            self.assertTrue(document['url'].startswith(help_catalog.REPOSITORY_URL), msg=document['url'])
            self.assertTrue(document['url'].endswith(document['path']), msg=document['url'])

    def test_the_top_level_readme_is_not_offered_as_a_topic(self):
        """docs/readme.md is the index of the others, not a tutorial."""
        self.assertNotIn('docs/readme.md', {document['path'] for document in self.documents})

    def test_the_shipped_index_is_up_to_date(self):
        """HACS installs custom_components/eltako/ only - there is no docs/ to scan there.

        The scan result is therefore generated into the integration. This test is what keeps
        it honest: it compares the shipped file against a fresh scan of the checkout.
        """
        import json

        with open(help_catalog.DOCS_INDEX_FILE, encoding='utf-8') as handle:
            shipped = json.load(handle)['documents']

        self.assertEqual(
            help_catalog.scan_documentation(), shipped,
            msg='docs_index.json is stale - regenerate it with '
                '`python -m custom_components.eltako.catalog.help_catalog`')

    def test_the_documentation_survives_without_the_checkout(self):
        """The HACS case: no docs directory, the shipped index takes over."""
        original = help_catalog._repository_root
        help_catalog._repository_root = lambda: os.path.join(os.sep, 'nowhere', 'at', 'all')
        try:
            documents = help_catalog.get_documentation()
        finally:
            help_catalog._repository_root = original

        self.assertTrue(documents, msg='the help page would list no documentation at all')
        self.assertEqual(len(help_catalog.scan_documentation()), len(documents))
        for document in documents:
            self.assertTrue(document['url'].startswith(help_catalog.REPOSITORY_URL))

    def test_the_index_is_data_only(self):
        """It must not carry the urls: the base url is applied when it is served."""
        import json

        with open(help_catalog.DOCS_INDEX_FILE, encoding='utf-8') as handle:
            shipped = json.load(handle)['documents']

        for document in shipped:
            self.assertNotIn('url', document)


class TestWholeCatalog(TestCase):

    def setUp(self):
        self.catalog = help_catalog.build_catalog()

    def test_the_summary_counts_what_is_delivered(self):
        summary = self.catalog['summary']

        self.assertEqual(len(self.catalog['devices']), summary['device_count'])
        self.assertEqual(len(self.catalog['eeps']), summary['eep_count'])
        self.assertEqual(len(self.catalog['gateways']), summary['gateway_count'])
        self.assertEqual(len(self.catalog['platforms']), summary['platform_count'])
        self.assertEqual(len(self.catalog['documentation']), summary['document_count'])

    def test_it_is_json_serialisable(self):
        """It travels over the websocket - a set or an enum in there would break it."""
        import json

        json.dumps(self.catalog)

    def test_nothing_is_empty(self):
        for key in ('devices', 'eeps', 'gateways', 'platforms', 'links'):
            self.assertTrue(self.catalog[key], msg=f'{key} is empty')


class TestNothingIsHardcodedInTheFrontend(TestCase):
    """The user's rule: the web ui renders what the backend delivers."""

    def setUp(self):
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            'custom_components', 'eltako', 'frontend', 'pages', 'help.js')
        with open(path, encoding='utf-8') as handle:
            self.source = handle.read()

    def test_the_page_lists_no_devices_of_its_own(self):
        for hw_type in ('FSR14_4x', 'FUD14', 'FTS14EM', 'FAM14'):
            self.assertNotIn(hw_type, self.source, msg=f'{hw_type} is hardcoded in help.js')

    def test_the_page_lists_no_eeps_of_its_own(self):
        import re

        found = re.findall(r'[A-H]5-[0-9A-F]{2}-[0-9A-F]{2}', self.source)

        self.assertEqual([], found, msg=f'EEPs hardcoded in help.js: {found}')

    def test_the_page_asks_the_backend(self):
        self.assertIn('HELP_CATALOG', self.source)
