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
from custom_components.eltako.gateway import BASE_ID_REQUEST_TIMEOUT


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

        import custom_components.eltako.gateway as gateway_module
        original = gateway_module.BASE_ID_REQUEST_TIMEOUT
        gateway_module.BASE_ID_REQUEST_TIMEOUT = 0.05
        try:
            await asyncio.wait_for(gateway.query_for_base_id_and_version(True), timeout=5)
        finally:
            gateway_module.BASE_ID_REQUEST_TIMEOUT = original

        # after a timeout the query may be tried again
        self.assertFalse(gateway._base_id_query_done)

    async def test_transceivers_do_not_query_the_base_id_of_a_fam14(self):
        """Only FAM14 (and non-esp2 gateways) know this request."""
        bus = BusMockWithRequests()
        gateway = self.create_gateway(bus, dev_type=GatewayDeviceType.GatewayEltakoFAMUSB)

        await gateway.query_for_base_id_and_version(True)

        self.assertEqual(bus.base_id_requests, 0)

    async def test_timeout_constant_is_sane(self):
        self.assertGreater(BASE_ID_REQUEST_TIMEOUT, 5)
        self.assertLess(BASE_ID_REQUEST_TIMEOUT, 120)


if __name__ == '__main__':
    unittest.main()
