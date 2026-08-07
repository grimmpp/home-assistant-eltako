"""The central device catalog: templates for the device form, knowledge for the device page."""
import unittest
from unittest import TestCase

from custom_components.eltako.catalog.device_catalog import (
    DEVICE_CATALOG,
    describe_hw_type,
    get_device_templates,
)


class TestCatalogConsistency(TestCase):

    def test_entries_are_complete(self):
        for entry in DEVICE_CATALOG:
            self.assertIn('hw_type', entry, msg=entry)
            self.assertIn('description', entry, msg=entry)
            self.assertIn('brand', entry, msg=entry)
            # a template (platform set) must carry an EEP
            if entry.get('platform'):
                self.assertIn('eep', entry, msg=entry)

    def test_eep_format(self):
        import re
        # first byte allows Eltako pseudo profiles (M5, G5, H5), the rest is hex
        pattern = re.compile(r'^[0-9A-Z]{2}-[0-9A-F]{2}-[0-9A-F]{2}$')
        for entry in DEVICE_CATALOG:
            for key in ('eep', 'sender_eep'):
                if entry.get(key):
                    self.assertRegex(entry[key], pattern, msg=f"{entry['hw_type']}: {key}")

    def test_every_discoverable_bus_device_is_in_the_catalog(self):
        """The catalog replaces the old HW_TYPE_INFO of bus_members - it must still
        describe every device class the eltakobus library can detect."""
        from custom_components.eltako.observation.bus_members import MODEL_MAP

        catalog_types = {entry['hw_type'] for entry in DEVICE_CATALOG if entry.get('bus_device')}
        discoverable = {name for names in MODEL_MAP['by_model'].values() for name in names}

        missing = sorted(discoverable - catalog_types)
        self.assertEqual(missing, [], msg=f"discoverable devices missing in the catalog: {missing}")


class TestDescribeHwType(TestCase):

    def test_primary_entry_wins(self):
        """FTS14EM has several EEP variants - the first entry is its primary use."""
        info = describe_hw_type('FTS14EM')
        self.assertEqual(info['eep'], 'F6-02-01')
        self.assertEqual(info['platform'], 'binary_sensor')

    def test_bus_members_compatibility(self):
        """The fields bus_members.get_members() spreads into its rows."""
        fsr = describe_hw_type('FSR14_4x')
        self.assertEqual(fsr['description'], 'Relay (4 channels)')
        self.assertEqual(fsr['eep'], 'M5-38-08')
        self.assertEqual(fsr['sender_eep'], 'A5-38-08')
        self.assertEqual(fsr['pct14_function_group'], 2)
        self.assertEqual(fsr['pct14_key_function'], 51)

    def test_unknown(self):
        self.assertEqual(describe_hw_type('DOES_NOT_EXIST'), {})
        self.assertEqual(describe_hw_type(None), {})


class TestDeviceTemplates(TestCase):

    def test_templates_carry_the_prefill_values(self):
        templates = get_device_templates('light')
        fsr14 = next(t for t in templates if t['value'] == 'FSR14_4x|M5-38-08')

        self.assertEqual(fsr14['eep'], 'M5-38-08')
        self.assertEqual(fsr14['sender_eep'], 'A5-38-08')
        self.assertEqual(fsr14['pct14_function_group'], 2)
        self.assertEqual(fsr14['address_count'], 4)
        self.assertIn('FSR14_4x - Relay (4 channels)', fsr14['label'])

    def test_multi_eep_devices_show_their_eep_in_the_label(self):
        """F3Z14D measures electricity, gas and water - three entries, disambiguated."""
        templates = get_device_templates('sensor')
        f3z = [t for t in templates if t['hw_type'] == 'F3Z14D']

        self.assertEqual(len(f3z), 3)
        for template in f3z:
            self.assertIn(template['eep'], template['label'])

    def test_unsupported_eeps_are_dropped(self):
        """Safety net: the form must never offer what the schema rejects."""
        templates = get_device_templates('light', supported_eeps=['A5-38-08'])

        self.assertTrue(templates)
        self.assertTrue(all(t['eep'] == 'A5-38-08' for t in templates))

    def test_unsupported_sender_eep_is_removed_from_the_template(self):
        templates = get_device_templates('light', supported_sender_eeps=['A5-38-08'])
        fmz14 = next(t for t in templates if t['hw_type'] == 'FMZ14')   # sender F6-02-01

        self.assertNotIn('sender_eep', fmz14)

    def test_gateways_have_no_template(self):
        """FAM14 & co are added as gateway, not as device."""
        for platform in ('binary_sensor', 'sensor', 'light', 'switch', 'cover', 'climate'):
            for template in get_device_templates(platform):
                self.assertNotIn(template['hw_type'], ('FAM14', 'FGW14_USB', 'FTD14'))

    def test_templates_are_sorted(self):
        labels = [t['label'] for t in get_device_templates('light')]
        self.assertEqual(labels, sorted(labels))


class TestFormDescriptorIntegration(TestCase):
    """The form websocket serves the catalog - the frontend hardcodes nothing."""

    def test_every_platform_offers_device_types(self):
        from custom_components.eltako.config.device_config import get_form_descriptor

        descriptor = get_form_descriptor()
        for platform in descriptor['platforms']:
            self.assertIn('device_types', platform, msg=platform['platform'])
            self.assertTrue(platform['device_types'], msg=f"{platform['platform']} has no templates")

    def test_template_eeps_validate_against_the_platform_schema(self):
        from custom_components.eltako.config.device_config import get_form_descriptor

        descriptor = get_form_descriptor()
        for platform in descriptor['platforms']:
            eep_field = next(f for f in platform['fields'] if f['name'] == 'eep')
            valid = {option['value'] for option in eep_field['options']}
            for template in platform['device_types']:
                self.assertIn(template['eep'], valid,
                              msg=f"{platform['platform']}: {template['value']}")

    def test_find_hw_type_accepts_the_names_of_other_tools(self):
        """PCT14 and the EnOcean Device Manager write the same device differently."""
        from custom_components.eltako.catalog.device_catalog import find_hw_type

        # PCT14 uses dashes, the catalog underscores
        self.assertEqual(find_hw_type('FSR14-4x')['hw_type'], 'FSR14_4x')
        self.assertEqual(find_hw_type('fsr14_4X')['hw_type'], 'FSR14_4x')
        self.assertEqual(find_hw_type('FWZ14-65A')['hw_type'], 'FWZ14_65A')
        # a variant separator: the exact entry wins, otherwise the base device
        self.assertEqual(find_hw_type('FUD14/800W')['hw_type'], 'FUD14_800W')
        self.assertEqual(find_hw_type('FUD14/500W')['hw_type'], 'FUD14')
        # gateways are found as well - they carry a gateway type instead of a platform
        self.assertEqual(find_hw_type('FGW14')['hw_type'], 'FGW14')
        self.assertEqual(find_hw_type('FGW14-USB')['gateway_type'], 'fgw14usb')
        # unknown devices are reported as such, not guessed
        self.assertEqual(find_hw_type('FSR14SSR'), {})
        self.assertEqual(find_hw_type(''), {})
        self.assertEqual(find_hw_type(None), {})

    def test_switch_reuses_the_light_actuators(self):
        from custom_components.eltako.config.device_config import get_form_descriptor

        descriptor = get_form_descriptor()
        switch = next(p for p in descriptor['platforms'] if p['platform'] == 'switch')
        hw_types = {t['hw_type'] for t in switch['device_types']}
        self.assertIn('FSR14_4x', hw_types)
        self.assertIn('FSR61-230V', hw_types)


if __name__ == '__main__':
    unittest.main()
