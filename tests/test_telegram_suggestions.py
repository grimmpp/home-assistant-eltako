"""EEP and device candidates for addresses which are not configured yet.

All of this logic lives in the backend on purpose: the web ui only renders the fields, so the
suggestions cannot drift away from the schemas and the device catalog of the integration.
"""
import unittest
from unittest import TestCase

from custom_components.eltako.observation import telegram_suggestions as suggestions
from custom_components.eltako.observation.telegram_suggestions import (
    best_candidate,
    devices_for_eep,
    enrich_unknown,
    suggest,
    yaml_snippet,
)


class TestMessageTypeLimitsTheProfiles(TestCase):
    """An RPS telegram can never carry an A5 profile - the type is the hard limit."""

    def test_rps_only_suggests_f6(self):
        candidates = suggest(msg_types={'RPSMessage': 12}, data='70', status='0x30')

        self.assertTrue(candidates)
        for candidate in candidates:
            self.assertTrue(candidate['eep'].startswith('F6'), msg=candidate['eep'])

    def test_1bs_suggests_the_contact_profile(self):
        candidates = suggest(msg_types={'Regular1BSMessage': 3}, data='09')

        self.assertEqual([candidate['eep'] for candidate in candidates], ['D5-00-01'])

    def test_4bs_suggests_a5_profiles_only(self):
        candidates = suggest(msg_types={'Regular4BSMessage': 5}, data='00-50-64-0A')

        self.assertTrue(candidates)
        for candidate in candidates:
            self.assertTrue(candidate['eep'].startswith('A5'), msg=candidate['eep'])

    def test_wrapped_bus_messages_are_recognized_too(self):
        """A bus gateway wraps the telegrams (EltakoWrappedRPS etc.)."""
        candidates = suggest(msg_types={'EltakoWrappedRPS': 4}, data='70')

        self.assertTrue(all(candidate['eep'].startswith('F6') for candidate in candidates))


class TestDataDecidesBetweenProfiles(TestCase):
    """The data bytes are decoded with every candidate - implausible values drop out."""

    def test_temperature_and_humidity_ranks_first(self):
        candidates = suggest(msg_types={'Regular4BSMessage': 7}, data='00-50-64-0A', status='0x00')

        self.assertEqual(candidates[0]['eep'], 'A5-04-02')
        self.assertEqual(candidates[0]['confidence'], 'likely')
        self.assertIn('humidity', candidates[0]['reason'])

    def test_implausible_values_are_dropped(self):
        """A5-13-01 (weather station) does not survive data which yields absurd values."""
        candidates = suggest(msg_types={'Regular4BSMessage': 7}, data='00-50-64-0A')
        eeps = [candidate['eep'] for candidate in candidates]

        self.assertNotIn('A5-13-01', eeps)

    def test_candidates_carry_the_checked_values(self):
        candidates = suggest(msg_types={'Regular4BSMessage': 1}, data='00-50-64-0A')

        self.assertTrue(candidates[0]['values'])
        self.assertTrue(any('=' in value for value in candidates[0]['values']))

    def test_every_candidate_says_what_the_telegram_would_mean(self):
        """The values per profile are what lets a human pick the right one.

        The range check only looks at the few physical values it knows; the web ui shows the
        complete decoding next to each candidate ("22.4 °C, 41 %" against "button B pressed"),
        so the whole dict has to be part of the answer.
        """
        candidates = suggest(msg_types={'Regular4BSMessage': 1}, data='00-50-64-0A')

        for candidate in candidates:
            self.assertIsInstance(candidate['decoded'], dict, msg=candidate['eep'])
            self.assertTrue(candidate['decoded'], msg=candidate['eep'])

        best = candidates[0]
        self.assertEqual('A5-04-02', best['eep'])
        self.assertIn('humidity', best['decoded'])
        self.assertIn('current_temperature', best['decoded'])

    def test_the_values_differ_per_profile(self):
        """Two profiles read the same bytes differently - that is the point of showing them."""
        candidates = suggest(msg_types={'Regular4BSMessage': 1}, data='00-50-64-0A')
        by_eep = {candidate['eep']: candidate['decoded'] for candidate in candidates}

        self.assertGreater(len(by_eep), 1, 'only one candidate - nothing to compare')
        self.assertNotEqual(list(by_eep.values())[0], list(by_eep.values())[1])

    def test_a_candidate_without_data_has_nothing_decoded(self):
        candidates = suggest(msg_types={'Regular4BSMessage': 1})

        self.assertTrue(candidates)
        self.assertTrue(all(candidate['decoded'] is None for candidate in candidates))

    def test_without_data_the_type_is_the_only_evidence(self):
        candidates = suggest(msg_types={'Regular4BSMessage': 1}, data=None)

        self.assertTrue(candidates)
        self.assertEqual({candidate['confidence'] for candidate in candidates}, {'possible'})


class TestTeachInWins(TestCase):

    def test_teach_in_profile_is_confirmed_and_first(self):
        candidates = suggest(msg_types={'Regular4BSMessage': 3}, data='00-50-64-0A',
                             teach_in_profile='A5-10-06')

        self.assertEqual(candidates[0]['eep'], 'A5-10-06')
        self.assertEqual(candidates[0]['confidence'], 'confirmed')
        self.assertIn('teach-in', candidates[0]['reason'])

    def test_the_teach_in_profile_is_not_listed_twice(self):
        candidates = suggest(msg_types={'Regular4BSMessage': 3}, data='00-50-64-0A',
                             teach_in_profile='A5-04-02')

        self.assertEqual([c['eep'] for c in candidates].count('A5-04-02'), 1)


class TestAddressNarrowsItDown(TestCase):

    def test_low_local_address_is_an_fts14em_input(self):
        candidates = suggest(msg_types={'EltakoWrappedRPS': 5}, data='70', address='00-00-00-05')

        rocker = next(c for c in candidates if c['eep'] == 'F6-02-01')
        self.assertEqual(rocker['confidence'], 'likely')
        self.assertIn('FTS14EM', rocker['reason'])

    def test_wireless_address_keeps_the_plain_suggestion(self):
        candidates = suggest(msg_types={'RPSMessage': 5}, data='70', address='FE-DB-B6-40')

        rocker = next(c for c in candidates if c['eep'] == 'F6-02-01')
        self.assertNotIn('FTS14EM', rocker['reason'])


class TestDeviceCandidatesComeFromTheCatalog(TestCase):

    def test_devices_of_a_known_eep(self):
        devices = devices_for_eep('A5-04-02')

        self.assertTrue(devices)
        self.assertIn('FLGTF', [device['hw_type'] for device in devices])
        for device in devices:
            self.assertIn('description', device)
            self.assertEqual(device['platform'], 'sensor')

    def test_hardware_types_are_not_repeated(self):
        hw_types = [device['hw_type'] for device in devices_for_eep('M5-38-08')]

        self.assertEqual(len(hw_types), len(set(hw_types)))

    def test_unknown_eep_has_no_devices(self):
        self.assertEqual(devices_for_eep('A5-99-99'), [])
        self.assertEqual(devices_for_eep(None), [])

    def test_every_candidate_carries_its_devices(self):
        for candidate in suggest(msg_types={'Regular4BSMessage': 1}, data='00-50-64-0A'):
            self.assertIn('devices', candidate)

    def test_profiles_with_devices_rank_before_those_without(self):
        """An EEP nobody sells a device for is a worse suggestion."""
        candidates = suggest(msg_types={'Regular4BSMessage': 1}, data='00-50-64-0A')
        with_devices = [bool(c['devices']) for c in candidates]

        self.assertEqual(with_devices, sorted(with_devices, reverse=True))


class TestBestCandidateAndYaml(TestCase):

    def _device(self):
        return {'address': 'FF-AA-DD-81', 'count': 42, 'last_data': '00-50-64-0A',
                'msg_types': {'Regular4BSMessage': 42}, 'last_status': '0x00'}

    def test_best_candidate_carries_the_platform_of_its_device(self):
        device = enrich_unknown(self._device())

        self.assertEqual(device['suggested']['eep'], 'A5-04-02')
        self.assertEqual(device['suggested']['platform'], 'sensor')
        self.assertTrue(device['suggested']['hw_type'])

    def test_best_candidate_without_suggestions(self):
        empty = best_candidate([])

        self.assertIsNone(empty['eep'])
        self.assertIsNone(empty['platform'])

    def test_yaml_snippet_is_pastable(self):
        device = enrich_unknown(self._device())
        lines = device['yaml'].splitlines()

        self.assertTrue(lines[0].strip().startswith('#'))
        self.assertEqual(lines[1], '      - id: FF-AA-DD-81')
        self.assertEqual(lines[2], '        eep: A5-04-02')
        self.assertIn('name:', lines[3])

    def test_yaml_snippet_without_a_candidate_marks_the_gap(self):
        snippet = yaml_snippet({'address': 'FF-11-22-33', 'count': 1}, [])

        self.assertIn('eep: <EEP>', snippet)

    def test_enrich_adds_all_three_fields(self):
        device = enrich_unknown(self._device())

        for key in ('suggestions', 'suggested', 'yaml'):
            self.assertIn(key, device)


class TestRobustness(TestCase):
    """A suggestion must never break the statistics."""

    def test_broken_input_is_survived(self):
        self.assertEqual(suggest(msg_types=None, data=None), [])
        self.assertEqual(suggest(msg_types={}, data='not-hex'), [])

    def test_unknown_message_type_falls_back_to_the_data_length(self):
        """A message type the library names differently must not lose the address: one data
        byte behaves like RPS, four like 4BS."""
        single = suggest(msg_types={'Nonsense': 1}, data='00')
        four = suggest(msg_types={'Nonsense': 1}, data='00-50-64-0A')

        self.assertTrue(all(candidate['eep'].startswith('F6') for candidate in single))
        self.assertTrue(all(candidate['eep'].startswith('A5') for candidate in four))

    def test_enrich_survives_a_broken_record(self):
        device = enrich_unknown({'address': None, 'msg_types': 'not-a-dict'})

        self.assertEqual(device['suggestions'], [])
        self.assertIn('yaml', device)

    def test_limit_is_respected(self):
        candidates = suggest(msg_types={'Regular4BSMessage': 1}, data='00-50-64-0A', limit=2)

        self.assertLessEqual(len(candidates), 2)

    def test_every_catalogued_eep_is_reachable_by_a_message_type(self):
        """A device of the catalog which can never be suggested would be a gap."""
        from custom_components.eltako.catalog.device_catalog import DEVICE_CATALOG

        reachable = {eep for eeps in suggestions.EEP_BY_MESSAGE_TYPE.values() for eep in eeps}
        # actuator profiles (M5/G5/H5) are not received from an unknown device - they belong to
        # a configured actuator, so they are deliberately not candidates
        catalogued = {entry['eep'] for entry in DEVICE_CATALOG
                      if entry.get('eep') and entry['eep'][:2] in ('A5', 'F6', 'D5')}

        self.assertEqual(catalogued - reachable, set())


class TestTheSuggestionsOfOneTelegram(TestCase):
    """`eltako/telegram_log/suggestions`: the same question for the telegram in front of you.

    The statistics answer it for the *last* telegram of an address. A user who clicks a row in
    the live view means that row - and the values shown next to each profile have to belong to
    it, otherwise they prove nothing.
    """
    def call(self, **payload):
        from unittest import mock

        from custom_components.eltako.observation import enocean_logger

        connection = mock.Mock()
        connection.results = []
        connection.send_result = lambda _id, result: connection.results.append(result)
        handler = enocean_logger.ws_telegram_log_suggestions
        while hasattr(handler, '__wrapped__'):
            handler = handler.__wrapped__
        handler(mock.Mock(), connection, {'id': 1, 'limit': 6, **payload})
        return connection.results[0]

    def test_it_answers_for_the_data_of_that_telegram(self):
        result = self.call(msg_type='Regular4BSMessage', data='00-50-64-0A', status='0x00')

        self.assertTrue(result['suggestions'])
        self.assertEqual('A5-04-02', result['suggestions'][0]['eep'])
        self.assertEqual('A5-04-02', result['best']['eep'])

    def test_every_candidate_carries_the_values_of_that_telegram(self):
        result = self.call(msg_type='Regular4BSMessage', data='00-50-64-0A', status='0x00')

        for candidate in result['suggestions']:
            self.assertIsInstance(candidate['decoded'], dict, msg=candidate['eep'])
        self.assertIn('humidity', result['suggestions'][0]['decoded'])

    def test_a_telegram_without_data_still_answers(self):
        result = self.call(msg_type='RPSMessage')

        self.assertTrue(all(candidate['eep'].startswith('F6')
                            for candidate in result['suggestions']))

    def test_a_teach_in_telegram_wins(self):
        result = self.call(msg_type='Regular4BSMessage', data='00-50-64-0A',
                           teach_in_profile='A5-02-05')

        self.assertEqual('A5-02-05', result['suggestions'][0]['eep'])
        self.assertEqual('confirmed', result['suggestions'][0]['confidence'])


if __name__ == '__main__':
    unittest.main()
