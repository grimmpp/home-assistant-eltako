"""The seed of the dev container (dev/) must stay in sync with the integration.

The dev container pre-provisions a config entry and example data. These tests fail when
something the seed depends on changes - e.g. the gateway naming scheme or the record
format of the telegram log - instead of silently breaking the container.
"""
import json
import os
import unittest
from unittest import TestCase

from custom_components.eltako import config_helpers
from custom_components.eltako.const import CONF_GATEWAY_DESCRIPTION, CONF_SERIAL_PATH
from custom_components.eltako.timeseries import record_to_line_protocol

DEV_DIR = os.path.join(os.path.dirname(__file__), '..', 'dev')
SEED_CONFIG = os.path.join(DEV_DIR, 'seed', 'config')


def read_json(*path: str) -> dict:
    with open(os.path.join(*path), encoding='utf-8') as file:
        return json.load(file)


class TestSeedStorage(TestCase):

    def test_storage_files_are_valid_json(self):
        for name in ('onboarding', 'auth', 'auth_provider.homeassistant', 'core.config_entries'):
            data = read_json(SEED_CONFIG, '.storage', name)
            self.assertEqual(data['key'], name)
            self.assertIn('data', data)

    def test_onboarding_is_done(self):
        onboarding = read_json(SEED_CONFIG, '.storage', 'onboarding')
        self.assertIn('user', onboarding['data']['done'])

    def test_admin_user_is_linked_to_its_credential(self):
        auth = read_json(SEED_CONFIG, '.storage', 'auth')['data']
        provider = read_json(SEED_CONFIG, '.storage', 'auth_provider.homeassistant')['data']

        user = auth['users'][0]
        credential = auth['credentials'][0]
        self.assertEqual(credential['user_id'], user['id'])
        self.assertEqual(credential['auth_provider_type'], 'homeassistant')
        self.assertEqual(credential['data']['username'], provider['users'][0]['username'])
        self.assertIn('system-admin', user['group_ids'])

    def test_password_hash_is_base64_encoded_bcrypt(self):
        """Home assistant stores base64(bcrypt hash) - a raw bcrypt string breaks the login
        with 'Invalid base64-encoded string' (found the hard way in the running container)."""
        import base64

        provider = read_json(SEED_CONFIG, '.storage', 'auth_provider.homeassistant')['data']
        decoded = base64.b64decode(provider['users'][0]['password'], validate=True)
        self.assertTrue(decoded.startswith(b'$2b$'), msg=decoded[:10])

    def test_config_entry_matches_the_gateway_naming_scheme(self):
        """The entry must describe gateway 1 of ha.yaml exactly like the config flow would."""
        entry = read_json(SEED_CONFIG, '.storage', 'core.config_entries')['data']['entries'][0]

        expected = config_helpers.get_gateway_name('FGW14-USB', 'fgw14usb', 1)
        self.assertEqual(entry['domain'], 'eltako')
        self.assertEqual(entry['title'], expected)
        self.assertEqual(entry['data'][CONF_GATEWAY_DESCRIPTION], expected)
        self.assertIn(CONF_SERIAL_PATH, entry['data'])
        self.assertEqual(config_helpers.get_id_from_gateway_name(entry['data'][CONF_GATEWAY_DESCRIPTION]), 1)


class TestSeedTelegramHistory(TestCase):

    def _records(self) -> list[dict]:
        with open(os.path.join(SEED_CONFIG, 'enocean_telegrams.jsonl'), encoding='utf-8') as file:
            return [json.loads(line) for line in file if line.strip()]

    def test_history_is_valid_jsonl(self):
        records = self._records()
        self.assertGreater(len(records), 20)
        for record in records:
            self.assertIn('timestamp', record)
            self.assertIn('address', record)

    def test_history_is_chronological(self):
        timestamps = [record['timestamp'] for record in self._records()]
        self.assertEqual(timestamps, sorted(timestamps))

    def test_history_can_be_backfilled(self):
        """Every seeded record must convert into a line protocol line."""
        for record in self._records():
            self.assertIsNotNone(record_to_line_protocol(record, 'eltako_telegram'),
                                 msg=record['seq'])

    def test_history_contains_an_unknown_device(self):
        """The 'unknown devices' demo needs at least one unconfigured address."""
        self.assertTrue(any(record.get('known') is False for record in self._records()))


class TestComposeFile(TestCase):

    def test_compose_yaml_is_valid(self):
        import yaml

        with open(os.path.join(DEV_DIR, 'docker-compose.yml'), encoding='utf-8') as file:
            compose = yaml.safe_load(file)

        services = compose['services']
        self.assertIn('homeassistant', services)
        self.assertIn('init', services)
        # analytics stays optional - a plain start must not pull influx/grafana
        self.assertEqual(services['influxdb'].get('profiles'), ['analytics'])
        self.assertEqual(services['grafana'].get('profiles'), ['analytics'])
        # the integration is mounted live from the repository
        volumes = services['homeassistant']['volumes']
        self.assertTrue(any('custom_components/eltako' in volume for volume in volumes))
        self.assertTrue(any('ha.yaml' in volume for volume in volumes))


if __name__ == '__main__':
    unittest.main()
