"""The burst test runs on wired gateways only - and nothing else does.

It sends with the fixed addresses FF-00-00-01.. of the EnOcean Device Manager. Those are not
derived from any base id, and a wireless transceiver only transmits telegrams whose sender
address lies inside its own base id range (base id .. base id + 127, valid base ids start at
FF-80-00-00). A transceiver therefore drops them silently and the test used to report every
single telegram as missing, without a hint at the real cause.

The restriction belongs to this one test. The cover test drives real actuators through whatever
gateway they are taught into, wireless included, so it must keep seeing all of them.
"""

import asyncio
import os
import re
from unittest import TestCase

from custom_components.eltako import device_tests
from custom_components.eltako.const import GatewayDeviceType

FRONTEND = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                        'custom_components', 'eltako', 'frontend')


class FakeBus:
    def __init__(self, active=True):
        self._active = active

    def is_active(self):
        return self._active


class FakeGateway:
    def __init__(self, dev_id, dev_type, connected=True):
        self.dev_id = dev_id
        self.dev_type = dev_type
        self.dev_name = f'Gateway {dev_id}'
        self.serial_path = f'/dev/ttyUSB{dev_id}'
        self._bus = FakeBus(connected)
        self.sent = []

    def send_message(self, message):
        self.sent.append(message)


def run(coroutine):
    return asyncio.run(coroutine)


class TestWhichGatewaysCount(TestCase):

    def test_the_bus_gateways_are_wired(self):
        for device_type in (GatewayDeviceType.GatewayEltakoFAM14, GatewayDeviceType.GatewayEltakoFGW14USB):
            self.assertTrue(device_tests.is_wired(FakeGateway(1, device_type)), msg=str(device_type))

    def test_the_transceivers_are_not(self):
        for device_type in (GatewayDeviceType.GatewayEltakoFAMUSB, GatewayDeviceType.EnOceanUSB300,
                            GatewayDeviceType.ESP3, GatewayDeviceType.LAN, GatewayDeviceType.MGW_LAN,
                            GatewayDeviceType.EUL_LAN, GatewayDeviceType.LAN_ESP2):
            self.assertFalse(device_tests.is_wired(FakeGateway(1, device_type)), msg=str(device_type))

    def test_it_follows_the_classifier_of_the_integration(self):
        """No second definition of 'wired' - is_bus_gateway() stays the single source."""
        for device_type in GatewayDeviceType:
            self.assertEqual(GatewayDeviceType.is_bus_gateway(device_type),
                             device_tests.is_wired(FakeGateway(1, device_type)),
                             msg=str(device_type))


class TestTheBurstTestRefusesTransceivers(TestCase):

    def setUp(self):
        self.logged = []

    def _run(self, gateway1, gateway2):
        gateways = [gateway1, gateway2]
        original = device_tests.get_gateways
        device_tests.get_gateways = lambda hass: gateways
        try:
            return run(device_tests.run_burst_test(
                None, {'gateway1': gateway1.dev_id, 'gateway2': gateway2.dev_id, 'count': 2},
                lambda line, style='info': self.logged.append(line), asyncio.Event()))
        finally:
            device_tests.get_gateways = original

    def test_a_wireless_sender_is_rejected(self):
        famusb = FakeGateway(1, GatewayDeviceType.GatewayEltakoFAMUSB)
        fam14 = FakeGateway(2, GatewayDeviceType.GatewayEltakoFAM14)

        with self.assertRaises(ValueError) as error:
            self._run(famusb, fam14)

        self.assertIn('transceiver', str(error.exception))
        self.assertIn('FF-00-00-01', str(error.exception))
        self.assertEqual([], famusb.sent, msg='nothing may be sent before the check')

    def test_a_wireless_receiver_is_rejected(self):
        fam14 = FakeGateway(1, GatewayDeviceType.GatewayEltakoFAM14)
        usb300 = FakeGateway(2, GatewayDeviceType.EnOceanUSB300)

        with self.assertRaises(ValueError) as error:
            self._run(fam14, usb300)

        self.assertIn('transceiver', str(error.exception))

    def test_the_message_names_a_way_out(self):
        with self.assertRaises(ValueError) as error:
            self._run(FakeGateway(1, GatewayDeviceType.GatewayEltakoFAMUSB),
                      FakeGateway(2, GatewayDeviceType.GatewayEltakoFAM14))

        self.assertIn('FAM14', str(error.exception))
        self.assertIn('FGW14-USB', str(error.exception))

    def test_a_disconnected_gateway_is_still_reported_as_such(self):
        """The older check must not be shadowed by the new one."""
        with self.assertRaises(ValueError) as error:
            self._run(FakeGateway(1, GatewayDeviceType.GatewayEltakoFAM14, connected=False),
                      FakeGateway(2, GatewayDeviceType.GatewayEltakoFAM14))

        self.assertIn('not connected', str(error.exception))


class TestOnlyTheBurstTestIsRestricted(TestCase):

    def test_the_descriptor_declares_it(self):
        burst = next(t for t in device_tests.TEST_DESCRIPTORS if t['id'] == 'burst')

        self.assertTrue(burst['wired_gateways_only'])
        self.assertIn('FF-00-00-01', burst['gateway_requirement'])

    def test_no_other_test_declares_it(self):
        others = [t for t in device_tests.TEST_DESCRIPTORS if t['id'] != 'burst']

        self.assertTrue(others, msg='there should be more than the burst test')
        for descriptor in others:
            self.assertFalse(descriptor.get('wired_gateways_only'), msg=descriptor['id'])

    def test_the_cover_test_does_not_check_for_wired(self):
        """Its covers may well hang on a wireless gateway."""
        import inspect

        source = inspect.getsource(device_tests.run_cover_test)

        self.assertNotIn('is_wired', source)


class TestTheWebUiOffersTheRightGateways(TestCase):

    def setUp(self):
        with open(os.path.join(FRONTEND, 'pages', 'tests.js'), encoding='utf-8') as handle:
            self.source = handle.read()

    def test_the_filter_is_driven_by_the_descriptor(self):
        """Not by a list of gateway types typed into the frontend."""
        self.assertIn('test.wired_gateways_only', self.source)
        self.assertIn('gateway.wired', self.source)
        self.assertNotIn('fam-usb', self.source.lower())
        self.assertNotIn('usb300', self.source.lower())

    def test_the_backend_reports_the_flag(self):
        import inspect

        source = inspect.getsource(device_tests._info)

        self.assertIn('"wired": is_wired(gw)', source)

    def _method(self, name):
        """Body of one method of the page object (the definition, not a call site)."""
        match = re.search(r'\n  ' + re.escape(name) + r'\(ctx, info\) \{(.*?)\n  \},',
                          self.source, re.DOTALL)
        self.assertIsNotNone(match, msg=f'{name} is gone')
        return match.group(1)

    def test_the_cover_test_gets_the_unfiltered_list(self):
        cover = self._method('_renderCover')

        self.assertIn('const gateways = info.gateways || [];', cover)
        self.assertNotIn('_gatewaysFor', cover)
        self.assertNotIn('wired', cover)

    def test_the_burst_test_uses_the_filtered_list(self):
        burst = self._method('_renderBurst')

        self.assertIn('this._gatewaysFor(info, test)', burst)
        self.assertNotIn('info.gateways || []', burst.split('const excluded')[0])

    def test_too_few_wired_gateways_explain_themselves(self):
        burst = self._method('_renderBurst')

        self.assertIn('gateways.length < 2', burst)
        self.assertIn('gateway_requirement', burst)

    def test_the_options_helper_takes_a_list_now(self):
        """It used to take `info` and render every gateway.

        Counting the call sites would just break whenever a test is added to the page, so what
        is pinned is the contract: the helper takes a list, and no caller hands it `info` again.
        """
        self.assertRegex(self.source, r'_gatewayOptions\(gateways, selected\)')
        self.assertNotIn('_gatewayOptions(info', self.source)

        arguments = re.findall(r'this\._gatewayOptions\(\s*([A-Za-z_][\w.]*)', self.source)
        self.assertTrue(arguments, msg='nobody renders gateway options anymore')
        for argument in arguments:
            self.assertEqual('gateways', argument,
                             msg='pass the list the page decided on, not info')
