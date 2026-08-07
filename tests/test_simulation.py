"""The simulation inside the integration: storage, marking, detection and the gateway object.

The hardware independent part is covered by test_simulation_core.py. Here everything is tested
which connects the simulation to the integration:

* a gateway of the configuration marked `simulated: True` is validated without hardware
* the store keeps the simulated devices and follows the configuration
* the plug & play detection offers every simulated device as a candidate
* every list of the web ui marks a simulated device (`simulated` flag)
* the gateway object opens nothing and answers the commands of Home Assistant
"""
import asyncio
import unittest
from unittest import IsolatedAsyncioTestCase, TestCase, mock

import voluptuous as vol

from tests.mocks import *
from tests.test_enocean_logger import HassDataMock

from custom_components.eltako import simulation
from custom_components.eltako.config import config_helpers, device_config, gateway_config
from custom_components.eltako.const import *
from custom_components.eltako.simulation import core as sim
from custom_components.eltako.simulation.store import SimulatorRegistry
from custom_components.eltako.tools import plug_and_play

from homeassistant.const import CONF_ID, CONF_NAME


SIMULATED_FAM14 = {CONF_ID: 2, CONF_DEVICE_TYPE: 'fam14', CONF_NAME: 'Simulated FAM14',
                   CONF_BASE_ID: 'FF-C0-02-00', CONF_SIMULATED: True}
SIMULATED_USB300 = {CONF_ID: 3, CONF_DEVICE_TYPE: 'enocean-usb300', CONF_NAME: 'Simulated USB300',
                    CONF_BASE_ID: 'FF-C0-03-00', CONF_SIMULATED: True}
REAL_FGW14 = {CONF_ID: 1, CONF_DEVICE_TYPE: 'fgw14usb', CONF_BASE_ID: 'FF-AA-80-00',
              CONF_SERIAL_PATH: '/dev/ttyUSB0'}


class ConfigEntriesMock:
    """Just enough of hass.config_entries: the device list iterates the entries."""

    def __init__(self, entries: list = None):
        self._entries = list(entries or [])

    def async_entries(self, domain: str = None) -> list:
        return list(self._entries)


class StoreMock:
    def __init__(self, data: dict = None):
        self.data = data
        self.saved = None

    async def async_load(self):
        return self.data

    async def async_save(self, data):
        self.saved = data
        self.data = data


def hass_with(*gateways, stored: dict = None) -> HassDataMock:
    hass = HassDataMock(config={CONF_GATEWAY: list(gateways)})
    hass.config_entries = ConfigEntriesMock()
    registry = SimulatorRegistry(hass)
    registry._store = StoreMock(stored)
    hass.data[DATA_ELTAKO][DATA_SIMULATOR] = registry
    return hass


async def registry_of(hass) -> SimulatorRegistry:
    """The registry, loaded and synced with the configuration - like the setup does it."""
    registry = simulation.get_registry(hass)
    await registry.async_load()
    registry.sync_with_config()
    return registry


class TestTheConfigurationOfASimulatedGateway(TestCase):

    def test_it_needs_neither_a_port_nor_an_address(self):
        """The whole point: a simulated gateway has no hardware to point at."""
        validated = gateway_config.validate_gateway(
            {CONF_ID: 2, CONF_DEVICE_TYPE: 'fam14', CONF_SIMULATED: True})

        self.assertTrue(validated[CONF_SIMULATED])
        self.assertEqual(validated[CONF_SERIAL_PATH], 'simulator-2')

    def test_a_simulated_lan_gateway_needs_no_address(self):
        validated = gateway_config.validate_gateway(
            {CONF_ID: 4, CONF_DEVICE_TYPE: 'mgw-lan', CONF_SIMULATED: True})

        # both fields carry the synthetic name - nothing ever opens them
        self.assertEqual(validated[CONF_GATEWAY_ADDRESS], 'simulator-4')
        self.assertEqual(validated[CONF_SERIAL_PATH], 'simulator-4')

    def test_a_real_gateway_still_needs_its_port(self):
        with self.assertRaises(vol.Invalid):
            gateway_config.validate_gateway({CONF_ID: 1, CONF_DEVICE_TYPE: 'fam14'})

    def test_an_unknown_type_cannot_be_simulated_either(self):
        with self.assertRaises(vol.Invalid):
            gateway_config.validate_gateway({CONF_ID: 1, CONF_DEVICE_TYPE: 'nonsense',
                                             CONF_SIMULATED: True})

    def test_the_flag_is_off_by_default(self):
        validated = gateway_config.validate_gateway(REAL_FGW14)
        self.assertFalse(validated[CONF_SIMULATED])

    def test_the_web_ui_is_told_which_gateway_is_simulated(self):
        hass = hass_with(REAL_FGW14, SIMULATED_FAM14)

        descriptor = gateway_config.get_form_descriptor(hass)

        simulated = {gateway['id']: gateway['simulated'] for gateway in descriptor['gateways']}
        self.assertEqual(simulated, {1: False, 2: True})


class TestTheStore(IsolatedAsyncioTestCase):

    async def test_it_takes_over_the_gateways_of_the_configuration(self):
        hass = hass_with(REAL_FGW14, SIMULATED_FAM14, SIMULATED_USB300)

        registry = await registry_of(hass)

        # only the simulated ones, and with their type - it decides the addresses
        self.assertEqual(registry.model.get_gateway_ids(), [2, 3])
        self.assertTrue(registry.model.get_gateway(2).is_bus_gateway)
        self.assertFalse(registry.model.get_gateway(3).is_bus_gateway)
        self.assertEqual(registry.model.get_gateway(2).base_id, 'FF-C0-02-00')

    async def test_a_device_survives_a_restart(self):
        hass = hass_with(SIMULATED_FAM14)
        registry = await registry_of(hass)
        await registry.async_add_device(2, registry.model.suggest_device(2, 'sensor', 'A5-04-02'))
        await registry.async_update_device(2, '00-00-00-01', {'state': {'temperature': 23}})
        stored = registry._store.saved

        # a second start reads the store again
        restarted = hass_with(SIMULATED_FAM14, stored=stored)
        registry = await registry_of(restarted)

        device = registry.find(2, '00-00-00-01')
        self.assertIsNotNone(device)
        self.assertEqual(device.eep, 'A5-04-02')
        self.assertEqual(device.state['temperature'], 23)

    async def test_a_gateway_which_is_gone_takes_its_devices_with_it(self):
        hass = hass_with(SIMULATED_FAM14)
        registry = await registry_of(hass)
        await registry.async_add_device(2, registry.model.suggest_device(2, 'sensor', 'A5-04-02'))
        stored = registry._store.saved

        # the gateway is not configured anymore
        without = hass_with(REAL_FGW14, stored=stored)
        registry = await registry_of(without)

        self.assertEqual(registry.model.get_gateway_ids(), [])
        self.assertEqual(registry.get_devices(), [])

    async def test_nothing_is_dropped_before_the_configuration_was_read(self):
        """During startup the configuration is not there yet - that is no reason to forget."""
        hass = hass_with(SIMULATED_FAM14)
        registry = await registry_of(hass)
        await registry.async_add_device(2, registry.model.suggest_device(2, 'sensor', 'A5-04-02'))
        stored = registry._store.saved

        fresh = HassDataMock()
        del fresh.data[DATA_ELTAKO][ELTAKO_CONFIG]
        registry = SimulatorRegistry(fresh)
        registry._store = StoreMock(stored)
        await registry.async_load()
        registry.sync_with_config()

        self.assertEqual(len(registry.get_devices()), 1)

    async def test_a_device_of_an_unknown_gateway_is_refused(self):
        hass = hass_with(SIMULATED_FAM14)
        registry = await registry_of(hass)

        with self.assertRaises(sim.SimulationError):
            await registry.async_add_device(9, {'address': '00-00-00-01', 'platform': 'sensor',
                                                'eep': 'A5-04-02'})


class TestAChosenAddressOnARealGateway(IsolatedAsyncioTestCase):
    """A virtual device on a real gateway may get a typed address - but only one the hardware
    can transmit: a wireless transceiver refuses everything outside base id .. base id + 127,
    a bus gateway addresses freely."""

    REAL_USB300 = {CONF_ID: 5, CONF_DEVICE_TYPE: 'enocean-usb300', CONF_BASE_ID: 'FF-80-14-00',
                   CONF_SERIAL_PATH: '/dev/ttyUSB1'}

    async def test_a_wireless_gateway_only_accepts_its_base_id_range(self):
        from custom_components.eltako.simulation import service

        hass = hass_with(self.REAL_USB300)
        added = await service.async_add_device(hass, 5, {'platform': 'sensor',
                                                         'eep': 'A5-04-02',
                                                         'address': 'ff-80-14-7f'})
        self.assertEqual(added['address'], 'FF-80-14-7F')

        with self.assertRaises(sim.SimulationError) as context:
            await service.async_add_device(hass, 5, {'platform': 'sensor', 'eep': 'A5-04-02',
                                                     'address': 'FF-80-14-80'})
        self.assertIn('FF-80-14-00 to FF-80-14-7F', str(context.exception))

    async def test_a_bus_gateway_takes_any_well_formed_address(self):
        from custom_components.eltako.simulation import service

        hass = hass_with(REAL_FGW14)
        added = await service.async_add_device(hass, 1, {'platform': 'sensor',
                                                         'eep': 'A5-04-02',
                                                         'address': '00-00-00-63'})
        self.assertEqual(added['address'], '00-00-00-63')

    async def test_a_derived_address_still_needs_no_input(self):
        """Without a typed address everything works as before - the free range is used."""
        from custom_components.eltako.simulation import service

        hass = hass_with(self.REAL_USB300)
        added = await service.async_add_device(hass, 5, {'platform': 'sensor',
                                                         'eep': 'A5-04-02'})
        self.assertTrue(added['address'].startswith('FF-80-14-'))


class TestWhichGatewaysAreSimulated(TestCase):

    def test_only_the_marked_ones(self):
        hass = hass_with(REAL_FGW14, SIMULATED_FAM14, SIMULATED_USB300)

        self.assertEqual(simulation.get_simulated_gateway_ids(hass), {2, 3})
        self.assertTrue(simulation.is_simulated_gateway(hass, 2))
        self.assertFalse(simulation.is_simulated_gateway(hass, 1))
        self.assertFalse(simulation.is_simulated_gateway(hass, None))

    def test_it_survives_a_hass_without_any_configuration(self):
        self.assertEqual(simulation.get_simulated_gateway_ids(HassMock()), set())
        self.assertIsNone(simulation.get_registry(HassMock()))


class TestTheDetectionFindsSimulatedDevices(IsolatedAsyncioTestCase):

    async def _registry_with_examples(self, *gateways) -> tuple:
        hass = hass_with(*gateways)
        registry = await registry_of(hass)
        for gateway in registry.model.get_gateways():
            for device in sim.add_preset_devices(gateway):
                pass
        return hass, registry

    async def test_every_simulated_device_is_a_candidate(self):
        hass, _registry = await self._registry_with_examples(SIMULATED_FAM14)

        result = simulation.derive_candidates(hass, {'by_gateway': {}, 'all': set()})

        self.assertEqual(len(result['candidates']), len(sim.DEVICE_PRESETS))
        self.assertEqual(result['skipped'], [])
        for candidate in result['candidates']:
            self.assertEqual(candidate['gateway_id'], 2)
            self.assertEqual(candidate['source'], 'simulator')
            self.assertTrue(candidate['simulated'])
            self.assertIn(CONF_ID, candidate['device'])
            self.assertIn(CONF_EEP, candidate['device'])

    async def test_an_actuator_brings_its_sender_along(self):
        hass, _registry = await self._registry_with_examples(SIMULATED_FAM14)

        candidates = simulation.derive_candidates(hass, {'by_gateway': {}, 'all': set()})['candidates']
        light = next(candidate for candidate in candidates
                     if candidate['device'][CONF_EEP] == 'M5-38-08')

        self.assertEqual(light['platform'], 'light')
        self.assertEqual(light['device'][CONF_SENDER][CONF_ID], '00-00-B0-01')
        self.assertEqual(light['device'][CONF_SENDER][CONF_EEP], 'A5-38-08')

    async def test_a_device_which_is_configured_is_not_offered_again(self):
        hass, _registry = await self._registry_with_examples(SIMULATED_FAM14)
        configured = {'by_gateway': {2: {'00-00-00-01', '00-00-00-05'}},
                      'all': {'00-00-00-01', '00-00-00-05'}}

        result = simulation.derive_candidates(hass, configured)

        addresses = {candidate['device'][CONF_ID] for candidate in result['candidates']}
        self.assertNotIn('00-00-00-01', addresses)
        self.assertNotIn('00-00-00-05', addresses)
        self.assertEqual(len(result['candidates']), len(sim.DEVICE_PRESETS) - 2)

    async def test_the_detection_prefers_the_simulation_over_a_guess(self):
        """merge_candidates keeps the first source - the simulation knows its devices."""
        hass, _registry = await self._registry_with_examples(SIMULATED_FAM14)
        simulated = simulation.derive_candidates(hass, {'by_gateway': {}, 'all': set()})
        guessed = {'candidates': [{'gateway_id': 2, 'platform': 'sensor', 'source': 'guess',
                                   'device': {CONF_ID: '00-00-00-05', CONF_EEP: 'A5-02-05'}}],
                   'skipped': []}

        merged = plug_and_play.merge_candidates(simulated, guessed)

        sensor = next(candidate for candidate in merged['candidates']
                      if candidate['device'][CONF_ID] == '00-00-00-05')
        self.assertEqual(sensor['source'], 'simulator')

    async def test_nothing_happens_without_a_simulation(self):
        result = simulation.derive_candidates(HassMock(), {'by_gateway': {}, 'all': set()})

        self.assertEqual(result, {'candidates': [], 'skipped': []})


class TestSimulatedDevicesAreMarked(TestCase):
    """"Which of these devices are real?" has to be answerable at a glance - everywhere."""

    def _devices(self, *gateways) -> list[dict]:
        hass = hass_with(*gateways)
        # devices as the web ui gets them (configuration.yaml devices are enough here)
        return device_config._describe_devices(hass)

    def test_a_device_of_a_simulated_gateway_is_flagged(self):
        simulated = dict(SIMULATED_FAM14, devices={'sensor': [
            {CONF_ID: '00-00-00-05', CONF_EEP: 'A5-04-02', CONF_NAME: 'Simulated sensor'}]})
        real = dict(REAL_FGW14, devices={'sensor': [
            {CONF_ID: '00-00-00-05', CONF_EEP: 'A5-04-02', CONF_NAME: 'Real sensor'}]})

        devices = {device['name']: device for device in self._devices(real, simulated)}

        self.assertTrue(devices['Simulated sensor']['simulated'])
        self.assertFalse(devices['Real sensor']['simulated'])

    def test_the_frontend_shows_the_flag(self):
        """The backend flag is useless if no page reads it."""
        import os
        import re

        pages_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                 'custom_components', 'eltako', 'frontend', 'pages')
        marked = set()
        reads_the_flag = set()
        for name in os.listdir(pages_dir):
            if not name.endswith('.js'):
                continue
            with open(os.path.join(pages_dir, name), encoding='utf-8') as handle:
                content = handle.read()
            if 'tag simulated' in content:
                marked.add(name)
                if re.search(r'\.simulated', content):
                    reads_the_flag.add(name)

        # the device table, the simple device cards and the gateway tiles read the flag of the
        # backend; the simulation page marks its gateways anyway - everything there is simulated
        for name in ('devices_config.js', 'home.js', 'overview.js'):
            self.assertIn(name, reads_the_flag,
                          msg=f"{name} does not mark simulated devices/gateways")
        self.assertIn('simulation.js', marked)


class SimulatedGatewayMock(simulation.SimulatedGateway):
    """The real gateway without the Home Assistant registries (see tests.mocks.GatewayMock)."""

    def _register_device(self) -> None:
        pass

    def _fire_connection_state_changed_event(self, status):
        pass

    def add_connection_state_changed_handler(self, handler):
        pass


class TestTheGatewayObject(IsolatedAsyncioTestCase):
    """The gateway of a simulation opens nothing and answers the commands of Home Assistant."""

    def _gateway(self, device_type=GatewayDeviceType.GatewayEltakoFAM14, dev_id=2):
        hass = hass_with(SIMULATED_FAM14)
        gateway = SimulatedGatewayMock(
            DEFAULT_GENERAL_SETTINGS, hass, dev_id, device_type,
            AddressExpression.parse('FF-C0-02-00'), 'Simulated FAM14', 5100, ConfigEntryMock())
        return hass, gateway

    def test_the_integration_builds_exactly_this_gateway(self):
        """create_gateway is what core/integration.py calls for a simulated gateway."""
        self.assertIs(simulation.create_gateway.__module__,
                      simulation.SimulatedGateway.__module__)
        self.assertTrue(issubclass(SimulatedGatewayMock, simulation.SimulatedGateway))

    async def test_it_needs_no_hardware_and_is_connected_after_the_start(self):
        _hass, gateway = self._gateway()

        self.assertTrue(gateway.is_simulated)
        self.assertEqual(gateway.serial_path, 'simulator-2')
        self.assertIn('simulated', gateway.model)
        self.assertFalse(gateway._bus.is_active())

        gateway._bus.start()
        self.assertTrue(gateway._bus.is_active())
        gateway._bus.stop()
        self.assertFalse(gateway._bus.is_active())

    async def test_a_telegram_is_injected_where_a_real_one_arrives(self):
        _hass, gateway = self._gateway()
        received = []
        gateway._handle_received_message = received.append

        device = sim.SimulatedDevice.create(address='00-00-00-05', platform='sensor',
                                            eep='A5-04-02')
        gateway.simulate_incoming(device.state_telegram())

        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].address, b'\x00\x00\x00\x05')

    async def test_a_command_makes_the_actuator_report_its_new_state(self):
        hass, gateway = self._gateway()
        registry = await registry_of(hass)
        await registry.async_add_device(2, registry.model.suggest_device(
            2, 'light', 'M5-38-08', 'A5-38-08'))
        received = []
        gateway._handle_received_message = received.append

        # Home Assistant switches the light on: A5-38-08 with its sender address
        command = sim.encode_eep_telegram('00-00-B0-01', 'A5-38-08',
                                          {'command': 1, 'switching_command': 1, 'learn_button': 1})
        await gateway.async_handle_command(command)

        self.assertEqual(len(received), 1)
        answer = received[0]
        self.assertEqual(answer.address, b'\x00\x00\x00\x01')
        self.assertEqual(registry.find(2, '00-00-00-01').state['state'], 1)

    async def test_a_command_for_nothing_simulated_is_ignored(self):
        hass, gateway = self._gateway()
        await registry_of(hass)
        received = []
        gateway._handle_received_message = received.append

        await gateway.async_handle_command(sim.encode_eep_telegram(
            '00-00-B0-63', 'A5-38-08', {'command': 1, 'switching_command': 1}))

        self.assertEqual(received, [])

    async def test_it_reports_its_base_id_on_demand(self):
        """The button 'send base id': the info telegram a real gateway answers with."""
        _hass, gateway = self._gateway()
        received = []
        gateway._handle_received_message = received.append

        telegram = gateway.simulate_base_id_telegram()

        self.assertEqual(len(received), 1)
        # 8B 98 is the base id info telegram, followed by the four bytes of the base id
        self.assertEqual(telegram.body[:2], b'\x8b\x98')
        self.assertEqual(telegram.body[2:6], b'\xff\xc0\x02\x00')

    async def test_the_reported_base_id_arrives_in_the_gateway(self):
        """The real receive path reads the base id out of that telegram.

        That is the point of the button: a gateway which does not know its base id yet gets it
        from this very telegram - exactly as it happens with real hardware.
        """
        _hass, gateway = self._gateway()
        telegram = gateway.simulate_base_id_telegram()
        reported = []
        gateway._fire_base_id_change_handlers = reported.append

        gateway._attr_base_id = AddressExpression.parse('00-00-00-00')
        gateway._callback_receive_message_from_serial_bus(telegram)

        self.assertEqual(config_helpers.b2s(gateway.base_id[0]), 'FF-C0-02-00')
        self.assertEqual(len(reported), 1)

    async def test_reading_the_bus_memory_is_refused_instead_of_hanging(self):
        """A simulated bus has nothing to talk to - the real request would time out."""
        _hass, gateway = self._gateway()

        await gateway.read_memory_of_all_bus_members()      # must return right away

    async def test_the_detection_does_not_read_a_simulated_bus(self):
        source = _read_source('tools/plug_and_play.py')
        self.assertIn("getattr(gateway, 'is_simulated', False)", source)

    async def test_the_port_scan_ignores_a_simulated_gateway(self):
        """Its 'port' is a synthetic name - it would look like an unplugged stick."""
        source = _read_source('tools/gateway_scan.py')
        self.assertIn("getattr(gateway, 'is_simulated', False)", source)


def _read_source(relative_path: str) -> str:
    import os

    path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                        'custom_components', 'eltako', relative_path)
    with open(path, encoding='utf-8') as handle:
        return handle.read()


class TestTheScheduler(IsolatedAsyncioTestCase):
    """The timers of the devices which send on their own - started, stopped and cleaned up."""

    def setUp(self):
        from custom_components.eltako.simulation import scheduler

        self.scheduler = scheduler
        # the timer itself belongs to Home Assistant; here only the bookkeeping is of interest
        self.started = []
        self.cancelled = []

        def fake_tracker(hass, action, interval, name=None, **kwargs):
            self.started.append((name, interval.total_seconds()))
            index = len(self.started) - 1

            def cancel():
                self.cancelled.append(self.started[index])
            return cancel

        self.patch = mock.patch.object(scheduler, 'async_track_time_interval', fake_tracker)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()

    async def _with_device(self, interval=0):
        hass = hass_with(SIMULATED_FAM14)
        registry = await registry_of(hass)
        device = await registry.async_add_device(2, {
            **registry.model.suggest_device(2, 'sensor', 'A5-04-02'), 'interval': interval})
        return hass, registry, device

    async def test_no_timer_without_an_interval(self):
        hass, _registry, device = await self._with_device()

        self.assertFalse(self.scheduler.apply(hass, 2, device))
        self.assertEqual(self.started, [])
        self.assertEqual(self.scheduler.get_running(hass), [])

    async def test_an_interval_starts_one_timer(self):
        hass, _registry, device = await self._with_device(interval=30)

        self.assertTrue(self.scheduler.apply(hass, 2, device))

        self.assertEqual(len(self.started), 1)
        self.assertEqual(self.started[0][1], 30.0)
        self.assertTrue(self.scheduler.is_running(hass, 2, device.address))
        self.assertEqual(self.scheduler.get_running(hass), [(2, device.address)])

    async def test_applying_it_again_replaces_the_timer(self):
        hass, registry, device = await self._with_device(interval=30)
        self.scheduler.apply(hass, 2, device)

        changed = await registry.async_update_device(2, device.address, {'interval': 5})
        self.scheduler.apply(hass, 2, changed)

        self.assertEqual(len(self.started), 2)
        self.assertEqual(len(self.cancelled), 1)        # the old one is gone
        self.assertEqual(self.started[1][1], 5.0)
        self.assertEqual(len(self.scheduler.get_running(hass)), 1)

    async def test_zero_stops_it(self):
        hass, registry, device = await self._with_device(interval=30)
        self.scheduler.apply(hass, 2, device)

        stopped = await registry.async_update_device(2, device.address, {'interval': 0})
        self.assertFalse(self.scheduler.apply(hass, 2, stopped))

        self.assertEqual(len(self.cancelled), 1)
        self.assertEqual(self.scheduler.get_running(hass), [])

    async def test_a_removed_device_takes_its_timer_with_it(self):
        hass, registry, device = await self._with_device(interval=30)
        self.scheduler.apply(hass, 2, device)

        await simulation.async_remove_device(hass, 2, device.address)

        self.assertEqual(self.scheduler.get_running(hass), [])

    async def test_apply_all_starts_what_is_stored_and_drops_what_is_gone(self):
        hass, registry, device = await self._with_device(interval=10)

        running = self.scheduler.apply_all(hass)
        self.assertEqual(running, 1)

        # the gateway is not configured anymore: no timer of it may stay behind
        hass.data[DATA_ELTAKO][ELTAKO_CONFIG] = {CONF_GATEWAY: []}
        registry.sync_with_config()
        self.assertEqual(self.scheduler.apply_all(hass), 0)
        self.assertEqual(self.scheduler.get_running(hass), [])

    async def test_cancel_all_stops_everything(self):
        hass, _registry, device = await self._with_device(interval=10)
        self.scheduler.apply(hass, 2, device)

        self.assertEqual(self.scheduler.cancel_all(hass), 1)
        self.assertEqual(self.scheduler.get_running(hass), [])


class TestTheTwoTeachInTelegrams(IsolatedAsyncioTestCase):
    """A device can announce its profile, and a sender can be taught into an actuator."""

    async def _devices(self):
        hass = hass_with(SIMULATED_FAM14)
        registry = await registry_of(hass)
        gateway = registry.model.require_gateway(2)
        sim.add_preset_devices(gateway)
        return hass, gateway

    async def test_an_actuator_offers_the_eltako_telegram_of_its_sender(self):
        from custom_components.eltako.catalog.teach_in import get_teach_in_payload
        from custom_components.eltako.simulation.service import eltako_teach_in_of

        _hass, gateway = await self._devices()
        light = next(device for device in gateway.devices if device.eep == 'M5-38-08')

        eltako = eltako_teach_in_of(light)

        self.assertIsNotNone(eltako)
        # it belongs to the SENDER: its profile, its address - not the ones of the device
        self.assertEqual(eltako['eep'], light.sender_eep)
        self.assertEqual(eltako['address'], light.sender_id)
        # and its payload is the one of the catalog, not a second copy of that knowledge
        self.assertEqual(eltako['payload'], bytes(get_teach_in_payload(light.sender_eep)).hex())

    async def test_a_sensor_profile_without_a_payload_has_none(self):
        from custom_components.eltako.simulation.service import eltako_teach_in_of

        _hass, gateway = await self._devices()
        sensor = next(device for device in gateway.devices if device.eep == 'A5-04-02')

        self.assertIsNone(eltako_teach_in_of(sensor))
        # ... but it can still announce its profile
        self.assertTrue(sensor.has_teach_in)

    async def test_the_two_telegrams_differ(self):
        from custom_components.eltako.simulation.service import eltako_teach_in_of

        _hass, gateway = await self._devices()
        cover = next(device for device in gateway.devices if device.eep == 'G5-3F-7F')

        profile = cover.teach_in_telegrams()
        eltako = eltako_teach_in_of(cover)

        self.assertEqual(eltako['eep'], 'H5-3F-7F')          # the sender profile of a cover
        self.assertNotIn(bytes.fromhex(eltako['payload']),
                         [telegram.body for telegram in profile])

    async def test_every_actuator_of_the_starter_set_can_be_taught_in(self):
        from custom_components.eltako.simulation.service import eltako_teach_in_of

        _hass, gateway = await self._devices()

        for device in gateway.devices:
            if not device.is_actuator:
                continue
            self.assertIsNotNone(eltako_teach_in_of(device),
                                 msg=f"{device.name} ({device.sender_eep}) has no Eltako teach-in")


class TestTelegramsAreMarked(TestCase):
    """A telegram of a simulated gateway has to be recognizable in the live view and in the log."""

    def _record(self, gateway) -> dict:
        from custom_components.eltako.observation.enocean_logger import EnOceanTelegramLogger
        from eltakobus.message import RPSMessage

        logger = EnOceanTelegramLogger(HassDataMock(), {})
        telegram = RPSMessage(b'\xff\xc0\x02\x05', 0x30, b'\x70')
        return logger._create_record(gateway, telegram, 'incoming')

    def test_a_telegram_of_a_simulated_gateway_is_flagged(self):
        simulated = SimulatedGatewayMock(
            DEFAULT_GENERAL_SETTINGS, hass_with(SIMULATED_FAM14), 2,
            GatewayDeviceType.GatewayEltakoFAM14, AddressExpression.parse('FF-C0-02-00'),
            'Simulated FAM14', 5100, ConfigEntryMock())

        self.assertTrue(self._record(simulated)['simulated'])

    def test_a_telegram_of_a_real_gateway_is_not(self):
        self.assertFalse(self._record(GatewayMock())['simulated'])

    def test_the_live_view_shows_it(self):
        import os

        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'custom_components',
                            'eltako', 'frontend', 'pages', 'telegrams.js')
        with open(path, encoding='utf-8') as handle:
            content = handle.read()

        self.assertIn('telegram.simulated', content)
        self.assertIn('tag simulated', content)
        # and it is part of an export, so a recording can be told apart afterwards
        self.assertIn('"simulated"', content)


class TestAnInstallationWithoutGateways(TestCase):
    """A deactivated simulation can leave an installation with only the core entry.

    Everything which reads a gateway description out of a config entry has to cope with that -
    otherwise the device page and the device form fail instead of showing an empty list.
    """

    def _hass_with_core_entry_only(self):
        from custom_components.eltako.const import CONF_CORE_ENTRY

        class Entry:
            data = {CONF_CORE_ENTRY: True}
            options = {}
            entry_id = 'core'
            title = 'ELTAKO Core'

        hass = hass_with()
        hass.config_entries = ConfigEntriesMock([Entry()])
        return hass

    def test_the_device_list_is_empty_instead_of_failing(self):
        hass = self._hass_with_core_entry_only()

        self.assertEqual(device_config._get_gateway_entries(hass), [])
        self.assertEqual(device_config._describe_devices(hass), [])

    def test_asking_a_gateway_less_entry_for_its_gateway_answers_none(self):
        from custom_components.eltako.core.integration import get_gateway_from_hass
        from custom_components.eltako.const import CONF_CORE_ENTRY

        class Entry:
            data = {CONF_CORE_ENTRY: True}

        self.assertIsNone(get_gateway_from_hass(hass_with(), Entry()))


class TestTheWebUiApi(TestCase):

    def test_every_command_of_the_page_is_registered(self):
        from custom_components.eltako.simulation import websocket

        registered = []

        class ConnectionMock:
            pass

        class HassApiMock(HassMock):
            pass

        # the register function only calls async_register_command - collect what it gets
        import homeassistant.components.websocket_api as websocket_api

        original = websocket_api.async_register_command
        websocket_api.async_register_command = lambda hass, handler: registered.append(handler)
        try:
            websocket.register_websocket_commands(HassApiMock())
        finally:
            websocket_api.async_register_command = original

        self.assertEqual(len(registered), 11)

    def test_the_form_descriptor_offers_what_the_page_needs(self):
        hass = hass_with(SIMULATED_FAM14)

        overview = simulation.get_overview(hass)

        self.assertEqual([gateway['id'] for gateway in overview['gateways']], [2])
        self.assertTrue(overview['gateways'][0]['bus_gateway'])
        # the presets of the starter set and the profiles per platform
        self.assertEqual({preset['key'] for preset in overview['presets']},
                         {'lan', 'usb300', 'fam14'})
        platforms = {platform['platform'] for platform in overview['platforms']}
        self.assertEqual(platforms, set(sim.SIMULATED_PLATFORMS))
        sensor = next(platform for platform in overview['platforms']
                      if platform['platform'] == 'sensor')
        temperature = next(eep for eep in sensor['eeps'] if eep['value'] == 'A5-04-02')
        self.assertIn('temperature', temperature['fields'])
        self.assertTrue(temperature['teach_in'])
        self.assertIn('device_presets', overview)

    def test_every_offered_template_is_accepted_by_its_platform(self):
        """A template whose profile the schema rejects would create a device which never becomes
        an entity: the simulation stores it, the detection refuses it ("value must be one of ...")
        and it is missing under *Devices* without any visible reason."""
        for platform in simulation.describe_platforms():
            supported = {eep['value'] for eep in platform['eeps']}
            senders = set(platform['sender_eeps'])
            for template in platform['device_types']:
                self.assertIn(template['eep'], supported,
                              msg=f"{platform['platform']}: the template '{template['label']}' "
                                  f"offers {template['eep']}, which the schema rejects")
                if template.get('sender_eep') and senders:
                    self.assertIn(template['sender_eep'], senders,
                                  msg=f"{platform['platform']}: the template "
                                      f"'{template['label']}' offers the sender profile "
                                      f"{template['sender_eep']}, which the schema rejects")

    def test_a_profile_which_does_not_fit_the_kind_is_refused(self):
        from custom_components.eltako.simulation.service import validate_profiles

        # a switch is an actuator: it speaks M5-38-08 or a rocker profile, never a dimmer profile
        with self.assertRaises(sim.SimulationError) as context:
            validate_profiles('switch', 'A5-38-08')
        self.assertIn('M5-38-08', str(context.exception))
        # the message points at the kind which can do it
        self.assertIn('binary sensor', str(context.exception))

        with self.assertRaises(sim.SimulationError):
            validate_profiles('sensor', 'M5-38-08')
        with self.assertRaises(sim.SimulationError):
            validate_profiles('light', 'M5-38-08', 'A5-04-02')

        validate_profiles('switch', 'M5-38-08', 'A5-38-08')      # must not raise
        validate_profiles('binary_sensor', 'F6-02-01')

    def test_every_kind_explains_itself(self):
        """'Switch' is an actuator and a wall switch is a binary sensor - that has to be said."""
        for platform in simulation.describe_platforms():
            self.assertTrue(platform['help'], msg=platform['platform'])
        switch = next(platform for platform in simulation.describe_platforms()
                      if platform['platform'] == 'switch')
        self.assertIn('binary sensor', switch['help'])

    def test_only_supported_profiles_are_offered(self):
        """A simulated device has to fit the configuration - otherwise it cannot be taken over."""
        from custom_components.eltako.config.schema import SensorSchema

        overview = simulation.get_overview(hass_with())
        sensor = next(platform for platform in overview['platforms']
                      if platform['platform'] == 'sensor')

        offered = {eep['value'] for eep in sensor['eeps']}
        self.assertLessEqual(offered, set(SensorSchema.CONF_EEP_SUPPORTED))


if __name__ == '__main__':
    unittest.main()
