"""The unique id of a stick: what can be read from it and what it is good for."""

from unittest import TestCase

from custom_components.eltako.const import GatewayDeviceType
from custom_components.eltako.tools import gateway_identity


class TestFormatId(TestCase):

    def test_four_bytes_become_the_notation_used_everywhere_else(self):
        self.assertEqual(gateway_identity.format_id(b'\xFF\x9B\x8C\x00'), 'FF-9B-8C-00')

    def test_a_list_of_ints_is_accepted(self):
        """The esp3 library returns the base id as a list, not as bytes."""
        self.assertEqual(gateway_identity.format_id([0x01, 0x93, 0x8B, 0x2C]), '01-93-8B-2C')

    def test_anything_which_is_no_id_is_none(self):
        for value in (None, b'', b'\x01\x02\x03', 'FF-9B-8C-00', 42):
            self.assertIsNone(gateway_identity.format_id(value), msg=repr(value))


class TestVersionResponse(TestCase):
    """CO_RD_VERSION answers 32 bytes: app version, api version, chip id, chip version, name."""

    RESPONSE = (bytes([2, 6, 0, 1])                 # app version 2.6.0.1
                + bytes([2, 5, 0, 0])               # api version 2.5.0.0
                + bytes([0x01, 0x93, 0x8B, 0x2C])   # chip id
                + bytes([0x65, 0x00, 0x00, 0x00])   # chip version
                + b'GATEWAYCTRL\x00\x00\x00\x00\x00')

    def test_the_chip_id_is_taken_from_the_right_place(self):
        """The base id sits in another request - mixing the two would identify the wrong thing."""
        parsed = gateway_identity.parse_version_response(self.RESPONSE)

        self.assertEqual(parsed['chip_id'], '01-93-8B-2C')

    def test_the_versions_and_the_name_are_reported_as_well(self):
        parsed = gateway_identity.parse_version_response(self.RESPONSE)

        self.assertEqual(parsed['app_version'], '2.6.0.1')
        self.assertEqual(parsed['api_version'], '2.5.0.0')
        self.assertEqual(parsed['chip_version'], '101.0.0.0')
        self.assertEqual(parsed['app_description'], 'GATEWAYCTRL')

    def test_a_truncated_answer_is_no_identity(self):
        """A shorter response is another common command's answer, not a version."""
        self.assertEqual(gateway_identity.parse_version_response(self.RESPONSE[:16]), {})
        self.assertEqual(gateway_identity.parse_version_response(None), {})


class TestWhoCanBeAsked(TestCase):
    """Opening a port costs seconds, so only the gateways which can answer are asked."""

    def test_the_transceivers_can_report_an_id(self):
        for device_type in (GatewayDeviceType.ESP3, GatewayDeviceType.EnOceanUSB300,
                            GatewayDeviceType.GatewayEltakoFAMUSB):
            self.assertTrue(gateway_identity.can_identify(device_type), msg=str(device_type))
            self.assertTrue(gateway_identity.can_identify(device_type.value), msg=str(device_type))

    def test_the_bus_gateways_cannot(self):
        """A FGW14-USB uses the base id of the FAM14, and reading that one locks the bus."""
        for device_type in (GatewayDeviceType.GatewayEltakoFAM14,
                            GatewayDeviceType.GatewayEltakoFGW14USB):
            self.assertFalse(gateway_identity.can_identify(device_type), msg=str(device_type))

    def test_a_lan_gateway_has_no_port_to_open(self):
        self.assertFalse(gateway_identity.can_identify(GatewayDeviceType.MGW_LAN))

    def test_the_baud_rate_matches_the_one_the_gateway_is_opened_with(self):
        self.assertEqual(gateway_identity.baud_rate_of(GatewayDeviceType.GatewayEltakoFAMUSB), 9600)
        self.assertEqual(gateway_identity.baud_rate_of('esp3-gateway'), 57600)
        self.assertEqual(gateway_identity.baud_rate_of(GatewayDeviceType.MGW_LAN), 0)


class TestReadingIsSkippedWhereItCannotWork(TestCase):
    """`async_read_identity` must not open a port which cannot answer anyway."""

    def test_a_bus_gateway_is_not_opened(self):
        import asyncio

        # a path which does not exist: if this tried to open anything, it would raise
        result = asyncio.run(gateway_identity.async_read_identity(
            '/dev/does-not-exist', GatewayDeviceType.GatewayEltakoFAM14))

        self.assertEqual(result, {})

    def test_an_unreachable_port_is_no_identity_and_no_exception(self):
        import asyncio

        result = asyncio.run(gateway_identity.async_read_identity(
            '/dev/does-not-exist', GatewayDeviceType.ESP3))

        self.assertEqual(result, {})
