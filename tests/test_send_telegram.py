"""Arbitrary EnOcean telegrams can be sent from the web ui (raw hex or built from an EEP)."""
import unittest
from unittest import TestCase

from tests.mocks import *

from custom_components.eltako import websocket


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
        self.assertIn('Eltako Shutters', descriptors['G5-3F-7F']['description'])
        # every offered EEP is described, otherwise the dropdown is inconsistent
        undescribed = [eep for eep, d in descriptors.items() if not d['description']]
        self.assertEqual(undescribed, [])

    def test_the_description_matches_the_device_form(self):
        """Both forms must use the same source, so the labels cannot drift apart."""
        from custom_components.eltako import device_config

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
