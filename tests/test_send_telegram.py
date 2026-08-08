"""Arbitrary EnOcean telegrams can be sent from the web ui (raw hex or built from an EEP)."""
import unittest
from unittest import TestCase


from custom_components.eltako.core import websocket


class TestEepDescriptors(TestCase):

    def test_every_descriptor_has_eep_and_fields(self):
        descriptors = websocket.get_eep_descriptors()
        self.assertGreater(len(descriptors), 20)
        for descriptor in descriptors:
            self.assertRegex(descriptor['eep'], r'^[0-9A-Z]{2}-[0-9A-Z]{2}-[0-9A-Z]{2}$')
            self.assertIsInstance(descriptor['fields'], list)
            self.assertIsInstance(descriptor['description'], str)

    def test_the_dropdown_shows_a_description(self):
        """Nobody remembers the EEP numbers - the send form labels them like the device form."""
        descriptors = {d['eep']: d for d in websocket.get_eep_descriptors()}

        self.assertIn('Central Command', descriptors['A5-38-08']['description'])
        self.assertIn('PREFERRED', descriptors['A5-38-08']['description'])
        # the brand is written in capitals wherever a text is shown to a user, also in the
        # profile descriptions which come from the eltakobus library
        self.assertIn('ELTAKO Shutters', descriptors['G5-3F-7F']['description'])
        # every offered EEP is described, otherwise the dropdown is inconsistent
        undescribed = [eep for eep, d in descriptors.items() if not d['description']]
        self.assertEqual(undescribed, [])

    def test_the_description_matches_the_device_form(self):
        """Both forms must use the same source, so the labels cannot drift apart."""
        from custom_components.eltako.config import device_config

        descriptors = {d['eep']: d for d in websocket.get_eep_descriptors()}
        for eep, descriptor in descriptors.items():
            self.assertEqual(descriptor['description'], device_config.describe_eep(eep))

    def test_the_switching_eep_is_offered(self):
        descriptors = {d['eep']: d for d in websocket.get_eep_descriptors()}
        self.assertIn('A5-38-08', descriptors)
        self.assertIn('command', descriptors['A5-38-08']['fields'])
        self.assertIn('switching_command', descriptors['A5-38-08']['fields'])


class TestRawTelegram(TestCase):

    def test_body_hex(self):
        telegram = websocket.parse_raw_esp2('6b 05 50 00 00 00 fe db b6 40 30')
        self.assertEqual(telegram.body.hex(), '6b05500000 00fedbb640 30'.replace(' ', ''))

    def test_full_frame_with_checksum(self):
        body = bytes.fromhex('6b05500000 00fedbb640 30'.replace(' ', ''))
        frame = b'\xa5\x5a' + body + bytes([sum(body) % 256])

        telegram = websocket.parse_raw_esp2(frame.hex())

        self.assertEqual(telegram.body, body)

    def test_wrong_checksum_is_rejected(self):
        body = bytes.fromhex('6b05500000 00fedbb640 30'.replace(' ', ''))
        frame = b'\xa5\x5a' + body + bytes([(sum(body) + 1) % 256])
        with self.assertRaises(Exception):
            websocket.parse_raw_esp2(frame.hex())

    def test_wrong_length_is_rejected(self):
        with self.assertRaises(ValueError):
            websocket.parse_raw_esp2('6b 05')


class TestEepTelegram(TestCase):

    def test_switching_command(self):
        telegram = websocket.build_eep_telegram('00-00-B0-01', 'A5-38-08',
                                                {'command': '1', 'switching_command': '1'})
        self.assertEqual(telegram.address, b'\x00\x00\xb0\x01')
        self.assertEqual(telegram.data[0], 0x01)    # command byte
        self.assertEqual(telegram.data[3] & 0x01, 1)    # switching on

    def test_string_numbers_are_coerced(self):
        telegram = websocket.build_eep_telegram('00-00-B0-01', 'A5-38-08',
                                                {'command': '0x02', 'dimming_value': '80'})
        self.assertEqual(telegram.data[1], 80)      # dimming value byte

    def test_missing_fields_default_to_zero(self):
        telegram = websocket.build_eep_telegram('00-00-B0-01', 'A5-38-08', {})
        self.assertIsNotNone(telegram)

    def test_invalid_eep_raises(self):
        with self.assertRaises(Exception):
            websocket.build_eep_telegram('00-00-B0-01', 'X9-99-99', {})


if __name__ == '__main__':
    unittest.main()


class TestEveryDeviceCanBeSentTo(TestCase):
    """For every device there have to be input fields - that is what the web ui builds on.

    The control page offers a telegram per device: the values of its profile, prefilled, and a
    send button. It gets them from `websocket.get_eep_descriptors()`, so an EEP which the device catalog
    offers but the descriptors do not know would leave that device without any fields.
    """

    def test_every_eep_of_the_catalog_has_fields(self):
        from custom_components.eltako.catalog.device_catalog import DEVICE_CATALOG

        descriptors = {descriptor['eep']: descriptor for descriptor in websocket.get_eep_descriptors()}
        catalog_eeps = {entry[key] for entry in DEVICE_CATALOG
                        for key in ('eep', 'sender_eep') if entry.get(key)}

        missing = sorted(eep for eep in catalog_eeps if eep not in descriptors)
        self.assertEqual([], missing,
                         msg="devices of these profiles would have no input fields")

        without_fields = sorted(eep for eep in catalog_eeps if not descriptors[eep]['fields'])
        self.assertEqual([], without_fields)

    def test_every_field_has_a_start_value(self):
        """An empty form is useless: a telegram of zeros is not decodable for every profile."""
        for descriptor in websocket.get_eep_descriptors():
            defaults = descriptor.get('defaults') or {}
            for field in descriptor['fields']:
                self.assertIn(field, defaults,
                              msg=f"{descriptor['eep']}: no start value for '{field}'")

    # the library can only decode these - `encode_message` raises. They carry sendable=False
    # so that no form is offered for them instead of one which always fails.
    DECODE_ONLY = {'A5-09-0C'}

    def test_the_start_values_produce_a_telegram_which_can_be_sent(self):
        for descriptor in websocket.get_eep_descriptors():
            if descriptor['eep'] in self.DECODE_ONLY:
                continue
            telegram = websocket.build_eep_telegram('FF-AA-80-01', descriptor['eep'],
                                                    descriptor['defaults'])
            self.assertIsNotNone(telegram.serialize(),
                                 msg=f"{descriptor['eep']} cannot be encoded with its defaults")

    def test_the_sendable_flag_says_the_truth(self):
        for descriptor in websocket.get_eep_descriptors():
            try:
                websocket.build_eep_telegram('FF-AA-80-01', descriptor['eep'],
                                             descriptor['defaults'])
                encodable = True
            except Exception:   # noqa: BLE001
                encodable = False

            self.assertEqual(encodable, descriptor['sendable'],
                             msg=f"{descriptor['eep']}: sendable={descriptor['sendable']} "
                                 f"but encoding {'works' if encodable else 'fails'}")

    def test_only_the_known_profiles_cannot_be_sent(self):
        """A new profile which cannot be encoded should be noticed here, not by a user."""
        not_sendable = {descriptor['eep'] for descriptor in websocket.get_eep_descriptors()
                        if not descriptor['sendable']}

        self.assertEqual(self.DECODE_ONLY, not_sendable)


class TestFieldMeaning(TestCase):
    """The values of a profile must be nameable - a number nobody can guess is unusable.

    The descriptors say per field whether it is a choice with named options or a number with a
    unit; the tables live in `simulation/core/field_info.py` next to the encoders they were
    taken from.
    """

    def descriptor(self, eep: str) -> dict:
        return next(item for item in websocket.get_eep_descriptors() if item['eep'] == eep)

    def field(self, eep: str, name: str) -> dict:
        return next(item for item in self.descriptor(eep)['field_info'] if item['name'] == name)

    def test_every_field_is_described(self):
        for descriptor in websocket.get_eep_descriptors():
            described = {item['name'] for item in descriptor['field_info']}
            self.assertEqual(set(descriptor['fields']), described,
                             msg=f"{descriptor['eep']}: fields without a description")

    def test_a_switching_state_is_a_choice(self):
        state = self.field('M5-38-08', 'state')

        self.assertEqual('choice', state['kind'])
        self.assertEqual([(1, 'on'), (0, 'off')],
                         [(option['value'], option['label']) for option in state['options']])

    def test_a_temperature_carries_its_unit(self):
        temperature = self.field('A5-04-02', 'temperature')

        self.assertEqual('number', temperature['kind'])
        self.assertEqual('°C', temperature['unit'])
        self.assertLessEqual(temperature['min'], 0)

    def test_the_enum_of_a_profile_becomes_its_options(self):
        """A5-10-06 takes enums - their names are what the form shows."""
        mode = self.field('A5-10-06', 'mode')

        self.assertEqual('choice', mode['kind'])
        labels = {option['label'] for option in mode['options']}
        self.assertIn('Normal', labels)
        self.assertIn('Off', labels)

    def test_two_enum_members_with_one_code_become_one_option(self):
        """The telegram cannot tell 'Auto' and 'Thermostat' apart - both are 0x0E."""
        priority = self.field('A5-10-06', 'priority')

        values = [option['value'] for option in priority['options']]
        self.assertEqual(len(values), len(set(values)), msg=f"duplicate values: {values}")
        self.assertIn('Auto / Thermostat', [option['label'] for option in priority['options']])

    def test_the_options_of_a_choice_can_really_be_sent(self):
        """Every offered value has to produce a telegram - an option which fails is a trap."""
        for descriptor in websocket.get_eep_descriptors():
            if not descriptor['sendable']:
                continue
            for info in descriptor['field_info']:
                for option in info.get('options') or []:
                    fields = dict(descriptor['defaults'])
                    fields[info['name']] = option['value']
                    try:
                        websocket.build_eep_telegram('FF-AA-80-01', descriptor['eep'], fields)
                    except Exception as e:  # noqa: BLE001
                        self.fail(f"{descriptor['eep']}.{info['name']} = {option['value']} "
                                  f"({option['label']}) cannot be sent: {e}")

    def test_a_profile_which_writes_different_bytes_says_which_fields_it_reads(self):
        from custom_components.eltako.simulation.core import relevant_fields

        switching = relevant_fields('A5-38-08', {'command': 1})
        dimming = relevant_fields('A5-38-08', {'command': 2})

        self.assertIn('lock', switching)
        self.assertNotIn('dimming_value', switching)
        self.assertIn('dimming_value', dimming)
        self.assertNotIn('lock', dimming)
