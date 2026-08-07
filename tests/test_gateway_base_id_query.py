"""The base id query must run only once per connection.

Reading the base id of a FAM14 locks the bus and disables the receive callback until the
request is answered (eltakobus.serial.request_fam14_base_id restores both in its `finally`).
A second concurrent request deadlocks and leaves the callback disabled, which stops all
telegram reception. This happened on a real installation, see the regression tests below.
"""
import asyncio
import unittest
from unittest import IsolatedAsyncioTestCase

from tests.mocks import *

from custom_components.eltako.const import GatewayDeviceType
from custom_components.eltako.core.gateway import BASE_ID_REQUEST_TIMEOUT


class BusMockWithRequests(EltakoBusMock):
    """Counts the base id/version requests and can simulate a hanging gateway."""

    def __init__(self, hang: bool = False, delay: float = 0):
        super().__init__()
        self.base_id_requests = 0
        self.version_requests = 0
        self.hang = hang
        self.delay = delay
        self.concurrent = 0
        self.max_concurrent = 0

    async def send_base_id_request(self):
        self.base_id_requests += 1
        self.concurrent += 1
        self.max_concurrent = max(self.max_concurrent, self.concurrent)
        try:
            if self.hang:
                await asyncio.Event().wait()        # never answers
            elif self.delay:
                await asyncio.sleep(self.delay)
        finally:
            self.concurrent -= 1

    async def send_version_request(self):
        self.version_requests += 1


class TestBaseIdQuery(IsolatedAsyncioTestCase):

    def create_gateway(self, bus: BusMockWithRequests, dev_type=GatewayDeviceType.GatewayEltakoFAM14):
        gateway = GatewayMock()
        gateway._attr_dev_type = dev_type
        gateway._bus = bus
        gateway._base_id_query_done = False
        gateway._base_id_query_lock = asyncio.Lock()
        return gateway

    async def test_query_runs_once(self):
        bus = BusMockWithRequests()
        gateway = self.create_gateway(bus)

        await gateway.query_for_base_id_and_version(True)

        self.assertEqual(bus.base_id_requests, 1)
        self.assertEqual(bus.version_requests, 1)

    async def test_second_event_of_the_same_connection_is_skipped(self):
        """This is the bug: the connection state event fires more than once."""
        bus = BusMockWithRequests()
        gateway = self.create_gateway(bus)

        await gateway.query_for_base_id_and_version(True)
        await gateway.query_for_base_id_and_version(True)
        await gateway.query_for_base_id_and_version(True)

        self.assertEqual(bus.base_id_requests, 1)

    async def test_concurrent_events_never_overlap(self):
        bus = BusMockWithRequests(delay=0.05)
        gateway = self.create_gateway(bus)

        await asyncio.gather(*[gateway.query_for_base_id_and_version(True) for _ in range(5)])

        self.assertEqual(bus.base_id_requests, 1)
        self.assertEqual(bus.max_concurrent, 1)     # never two requests at the same time

    async def test_query_runs_again_after_a_reconnect(self):
        bus = BusMockWithRequests()
        gateway = self.create_gateway(bus)

        await gateway.query_for_base_id_and_version(True)
        await gateway.query_for_base_id_and_version(False)      # disconnected
        await gateway.query_for_base_id_and_version(True)       # reconnected

        self.assertEqual(bus.base_id_requests, 2)

    async def test_hanging_gateway_does_not_block_forever(self):
        """Without the timeout this call would never return and block the startup of HA."""
        bus = BusMockWithRequests(hang=True)
        gateway = self.create_gateway(bus)

        import custom_components.eltako.core.gateway as gateway_module
        original = gateway_module.BASE_ID_REQUEST_TIMEOUT
        gateway_module.BASE_ID_REQUEST_TIMEOUT = 0.05
        try:
            await asyncio.wait_for(gateway.query_for_base_id_and_version(True), timeout=5)
        finally:
            gateway_module.BASE_ID_REQUEST_TIMEOUT = original

        # after a timeout the query may be tried again
        self.assertFalse(gateway._base_id_query_done)

    async def test_fam_usb_queries_its_base_id(self):
        """A FAM-USB is a transceiver with its own base id and answers the ESP2 request
        (ORG 0x58). Verified against real hardware: it replies with its base id, so it must
        not be excluded - otherwise the base id stays 00-00-00-00 (the default of the web ui
        wizard) and no sender/device address of that gateway validates."""
        bus = BusMockWithRequests()
        gateway = self.create_gateway(bus, dev_type=GatewayDeviceType.GatewayEltakoFAMUSB)

        await gateway.query_for_base_id_and_version(True)

        self.assertEqual(bus.base_id_requests, 1)

    async def test_fgw14usb_does_not_query_a_base_id(self):
        """A FGW14-USB has no base id of its own - it uses the one of the FAM14 on its bus."""
        bus = BusMockWithRequests()
        gateway = self.create_gateway(bus, dev_type=GatewayDeviceType.GatewayEltakoFGW14USB)

        await gateway.query_for_base_id_and_version(True)

        self.assertEqual(bus.base_id_requests, 0)

    async def test_reverse_network_bridge_does_not_query_a_base_id(self):
        bus = BusMockWithRequests()
        gateway = self.create_gateway(bus, dev_type=GatewayDeviceType.VirtualNetworkAdapter)

        await gateway.query_for_base_id_and_version(True)

        self.assertEqual(bus.base_id_requests, 0)


class TestGatewayTypeClassification(unittest.TestCase):
    """A FAM-USB is a wireless transceiver, not a bus gateway.

    EltakoFAMUSB used to be listed in is_bus_gateway(). Since it has the same enum value as
    GatewayEltakoFAMUSB it is an ALIAS of it, so the FAM-USB was classified as bus gateway
    AND transceiver at once - it was offered for the RS485 memory scan and labelled
    'bus gateway (RS485)' in the gateway wizard.
    """

    def test_fam_usb_is_a_transceiver_only(self):
        famusb = GatewayDeviceType.find('fam-usb')

        self.assertTrue(GatewayDeviceType.is_transceiver(famusb))
        self.assertFalse(GatewayDeviceType.is_bus_gateway(famusb))
        self.assertTrue(GatewayDeviceType.is_esp2_gateway(famusb))

    def test_the_alias_is_the_same_member(self):
        self.assertIs(GatewayDeviceType.EltakoFAMUSB, GatewayDeviceType.GatewayEltakoFAMUSB)

    def test_bus_gateways_are_not_transceivers(self):
        for name in ('fam14', 'fgw14usb'):
            device_type = GatewayDeviceType.find(name)
            self.assertTrue(GatewayDeviceType.is_bus_gateway(device_type), msg=name)
            self.assertFalse(GatewayDeviceType.is_transceiver(device_type), msg=name)

    def test_timeout_constant_is_sane(self):
        self.assertGreater(BASE_ID_REQUEST_TIMEOUT, 5)
        self.assertLess(BASE_ID_REQUEST_TIMEOUT, 120)


class TestEsp2ConnectionUrl(unittest.TestCase):
    """An ESP2 gateway reached over tcp is opened with a pyserial url.

    This is what makes a serial gateway usable from a container which has no usb access: the
    port is published on the host (dev/share-serial.sh runs socat) and the gateway is
    configured as `lan-gw-esp2`. Verified against real hardware: a FAM-USB published with
    socat answers the base id request through the bridge.
    """

    def _gateway(self, dev_type, serial_path, port=5100, baud_rate=None):
        gateway = GatewayMock()
        gateway._attr_dev_type = dev_type
        gateway._attr_serial_path = serial_path
        gateway.port = port
        if baud_rate is not None:
            gateway.baud_rate = baud_rate
        return gateway

    def test_serial_gateway_keeps_its_device_path(self):
        gateway = self._gateway(GatewayDeviceType.GatewayEltakoFAM14, '/dev/ttyUSB0',
                                baud_rate=57600)

        self.assertEqual(gateway._esp2_connection(), ('/dev/ttyUSB0', 57600))

    def test_lan_esp2_becomes_a_socket_url(self):
        gateway = self._gateway(GatewayDeviceType.LAN_ESP2, 'host.docker.internal',
                                port=5100, baud_rate=-1)

        url, baud_rate = gateway._esp2_connection()

        self.assertEqual(url, 'socket://host.docker.internal:5100')
        # pyserial rejects -1 with "Not a valid baudrate" even for a socket url, which crashed
        # the reader thread in an endless retry loop
        self.assertGreater(baud_rate, 0)

    def test_an_explicit_pyserial_url_is_kept(self):
        gateway = self._gateway(GatewayDeviceType.LAN_ESP2, 'socket://192.168.1.5:5000',
                                baud_rate=-1)

        url, _ = gateway._esp2_connection()

        self.assertEqual(url, 'socket://192.168.1.5:5000')

    def test_lan_esp2_queries_its_base_id(self):
        """Whatever hangs behind the tcp endpoint answers the request - so it is asked."""
        async def scenario():
            bus = BusMockWithRequests()
            gateway = self._gateway(GatewayDeviceType.LAN_ESP2, 'host.docker.internal')
            gateway._bus = bus
            gateway._base_id_query_done = False
            gateway._base_id_query_lock = asyncio.Lock()

            await gateway.query_for_base_id_and_version(True)

            self.assertEqual(bus.base_id_requests, 1)
        asyncio.run(scenario())


if __name__ == '__main__':
    unittest.main()
