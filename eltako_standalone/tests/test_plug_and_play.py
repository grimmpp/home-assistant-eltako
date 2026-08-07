"""End to end: a plug & play run on a booted runtime really creates the devices.

The unit tests of the integration (tests/test_plug_and_play.py) cover which candidate is
derived from which detection result. Here the whole chain runs on a real runtime: bus
positions of the registry -> candidates -> stored devices -> entities of the integration.

The probing of the serial ports needs hardware and is replaced; reading the bus is skipped
(the fake positions are already in the registry, and locking a bus which does not exist would
only run into its timeout).
"""

import asyncio
from unittest import mock

from eltako_standalone.runtime import EltakoRuntime


def run(coro):
    return asyncio.run(coro)


# a FAM14 on position 1 plus a four channel relay - the same shape the discovery replies of a
# real bus produce (see bus_members.BusMemberRegistry)
def _fake_bus(runtime, gateway_id: int = 1) -> None:
    from custom_components.eltako.observation import bus_members

    registry = bus_members.get_registry(runtime.hass)
    fam14 = registry._entry(gateway_id, 1)
    fam14.update({'device_class': 'FAM14', 'is_fam': True, 'size': 1, 'memory_size': 1})

    relay = registry._entry(gateway_id, 2)
    relay.update({'device_class': 'FSR14_4x', 'size': 4, 'memory_size': 10,
                  'taught_in': [
                      # a wireless push button - its key function names the EEP
                      {'sensor_id': 'FF-CC-01-02', 'role': 'button', 'channel': 1,
                       'key_function_name': 'PUSH_BUTTON', 'suggested_eep': 'F6-02-01',
                       'suggested_platform': 'binary_sensor', 'suggested_name': 'Button',
                       'function_group': 1, 'key_function': 1, 'target_address': '00-00-00-02',
                       'memory_line': 12},
                      # the sender of home assistant itself - no device
                      {'sensor_id': '00-00-B0-02', 'role': 'ha_sender',
                       'key_function_name': 'FROM_CONTROLLER', 'function_group': 2,
                       'key_function': 51, 'target_address': '00-00-00-02', 'memory_line': 13},
                  ]})

    # a position which nobody can identify - it must stay a manual decision
    registry._entry(gateway_id, 8)


async def _booted(config_dir):
    runtime = EltakoRuntime(config_dir)
    await runtime.async_start()
    await runtime.hass.async_block_till_done()
    return runtime


async def _run_detection(runtime, mdns=None, **kwargs) -> dict:
    """One detection run without touching any hardware and without going on the network.

    The serial probe and the mDNS browser are replaced: both need real hardware/network and
    would otherwise cost their timeouts in every test.
    """
    from custom_components.eltako.tools import plug_and_play

    async def announced(hass):
        """What the mDNS browser would have found, run through the real filtering."""
        return plug_and_play.mdns_candidates(mdns or [],
                                             plug_and_play.configured_lan_endpoints(hass))

    with mock.patch.object(plug_and_play, 'async_probe_ports', return_value={}), \
         mock.patch.object(plug_and_play, 'async_discover_mdns_gateways', announced), \
         mock.patch.object(plug_and_play, '_bus_was_read', return_value=True):
        report = await plug_and_play.async_run(runtime.hass, **kwargs)
    await runtime.hass.async_block_till_done()
    return report


def test_detected_devices_are_created_and_editable(config_dir):
    async def scenario():
        runtime = await _booted(config_dir)
        _fake_bus(runtime)

        report = await _run_detection(runtime)

        added = {device['address']: device for device in report['devices_added']}
        # 00-00-00-01 is the Testlampe of the configuration.yaml - it must not be touched
        assert '00-00-00-01' not in added
        # the four channels of the relay, one device each
        for address in ['00-00-00-02', '00-00-00-03', '00-00-00-04', '00-00-00-05']:
            assert added[address]['platform'] == 'light'
            assert added[address]['eep'] == 'M5-38-08'
            assert added[address]['source'] == 'bus_position'
        # the push button which was found in the memory of the relay
        assert added['FF-CC-01-02']['platform'] == 'binary_sensor'
        assert added['FF-CC-01-02']['source'] == 'device_memory'
        # the sender of home assistant is no device
        assert '00-00-B0-02' not in added

        # position 8 did not answer the discovery -> reported, not added
        skipped = {entry['address'] for entry in report['devices_skipped']}
        assert '00-00-00-08' in skipped

        # the devices are stored like devices created in the web ui, therefore they can be
        # changed and removed again (source 'ui', editable)
        from custom_components.eltako.config import device_config

        devices = {device['address']: device for device in device_config._describe_devices(runtime.hass)}
        assert devices['00-00-00-02']['source'] == 'ui'
        assert devices['00-00-00-02']['editable'] is True
        assert devices['00-00-00-01']['source'] == 'yaml'        # from configuration.yaml

        await runtime.async_stop()
    run(scenario())


def test_added_devices_become_entities(config_dir):
    async def scenario():
        runtime = await _booted(config_dir)
        _fake_bus(runtime)

        await _run_detection(runtime)
        await runtime.hass.async_block_till_done()

        from eltako_standalone.entity_api import list_entities

        entities = {entity['entity_id'] for entity in list_entities(runtime.hass)}
        assert 'light.eltako_gw_1_00_00_00_02' in entities
        assert 'binary_sensor.eltako_ff_cc_01_02' in entities

        await runtime.async_stop()
    run(scenario())


def test_attributes_of_an_added_device_can_be_changed(config_dir):
    """The point the plain 'create and delete' was missing: editing an added device."""
    async def scenario():
        runtime = await _booted(config_dir)
        _fake_bus(runtime)
        await _run_detection(runtime)

        from custom_components.eltako.config import device_config
        from custom_components.eltako.const import CONF_EEP, CONF_SENDER, CONF_UI_DEVICES
        from homeassistant.const import CONF_ID, CONF_NAME

        entry = device_config._find_gateway_entry(runtime.hass, 1)
        stored = device_config.get_ui_devices(entry)['light']
        device = next(d for d in stored if d[CONF_ID] == '00-00-00-02')

        await device_config.async_update_ui_device(runtime.hass, entry, 'light', '00-00-00-02', {
            **device, CONF_NAME: 'Kitchen ceiling', 'area': 'Kitchen',
            CONF_SENDER: {CONF_ID: '00-00-B0-42', CONF_EEP: 'A5-38-08'}})
        await runtime.hass.async_block_till_done()

        changed = next(d for d in device_config.get_ui_devices(entry)['light']
                       if d[CONF_ID] == '00-00-00-02')
        assert changed[CONF_NAME] == 'Kitchen ceiling'
        assert changed['area'] == 'Kitchen'
        assert changed[CONF_SENDER][CONF_ID] == '00-00-B0-42'

        # the entity follows the change without a restart
        from eltako_standalone.entity_api import list_entities

        light = next(entity for entity in list_entities(runtime.hass)
                     if entity['entity_id'] == 'light.eltako_gw_1_00_00_00_02')
        assert light['name'] == 'Kitchen ceiling'
        assert light['area'] == 'Kitchen'

        # and it can be removed again
        await device_config.async_remove_ui_device(runtime.hass, entry, 'light', '00-00-00-02')
        await runtime.hass.async_block_till_done()
        assert all(d[CONF_ID] != '00-00-00-02'
                   for d in device_config.get_ui_devices(entry).get('light', []))

        await runtime.async_stop()
    run(scenario())


def test_a_second_run_adds_nothing_twice(config_dir):
    async def scenario():
        runtime = await _booted(config_dir)
        _fake_bus(runtime)

        first = await _run_detection(runtime)
        second = await _run_detection(runtime)

        assert len(first['devices_added']) == 5
        assert second['devices_added'] == []

        await runtime.async_stop()
    run(scenario())


def test_status_and_report_are_available_for_the_web_ui(config_dir):
    async def scenario():
        runtime = await _booted(config_dir)
        from custom_components.eltako.tools import plug_and_play
        from homeassistant.components.websocket_api import get_commands

        commands = get_commands(runtime.hass)
        assert 'eltako/plug_and_play/status' in commands
        assert 'eltako/plug_and_play/run' in commands
        assert 'eltako/gateways/update' in commands

        _fake_bus(runtime)
        await _run_detection(runtime)

        status = plug_and_play.get_status(runtime.hass)
        assert status['running'] is False
        assert status['last_run'] is not None
        assert status['last_report']['devices_added']

        await runtime.async_stop()
    run(scenario())


def test_a_lan_gateway_which_announces_itself_is_created(config_dir):
    """An mDNS service which names its own type identifies the gateway - no probing needed."""
    async def scenario():
        runtime = await _booted(config_dir)
        # 192.0.2.x is the reserved documentation range - nothing answers there
        announced = [
            {'name': 'SmartConn-1a2b._bsc-sc-socket._tcp.local.',
             'service_type': '_bsc-sc-socket._tcp.local.', 'address': '192.0.2.50',
             'port': 5100, 'hostname': 'smartconn-1a2b.local'},
            # published by this integration itself - must never be created automatically
            {'name': 'Virtual-Network-Gateway-Adapter._bsc-sc-socket._tcp.local.',
             'service_type': '_bsc-sc-socket._tcp.local.', 'address': '192.0.2.10',
             'port': 12345, 'hostname': 'homeassistant.local'},
        ]

        report = await _run_detection(runtime, mdns=announced)

        self_test = [gw for gw in report['gateways_added'] if gw['connection'] == 'lan']
        assert len(self_test) == 1
        assert self_test[0]['device_type'] == 'lan'
        assert self_test[0]['serial_path'] == '192.0.2.50'
        assert report['mdns_found'] == 2
        assert [c['device_type'] for c in report['gateways_suggested']] == ['lan-gw-esp2']

        # it landed in the configuration with host and port
        from custom_components.eltako.config import gateway_config
        from custom_components.eltako.const import CONF_GATEWAY_ADDRESS, CONF_GATEWAY_PORT

        stored = [gw for gw in gateway_config.get_ui_gateways(runtime.hass)
                  if gw.get(CONF_GATEWAY_ADDRESS) == '192.0.2.50']
        assert len(stored) == 1
        assert stored[0][CONF_GATEWAY_PORT] == 5100

        # a second run does not add it again
        second = await _run_detection(runtime, mdns=announced)
        assert second['gateways_added'] == []

        await runtime.async_stop()
    run(scenario())


def test_the_websocket_commands_work_over_a_real_connection(config_dir):
    """The push button of the overview page and the checkbox are one switch."""
    async def scenario():
        import aiohttp

        from eltako_standalone.server import StandaloneServer
        from custom_components.eltako.tools import plug_and_play
        from custom_components.eltako.const import CONF_PLUG_AND_PLAY
        from unittest import mock

        runtime = await _booted(config_dir)
        port = 18126
        server = StandaloneServer(runtime.hass, host="127.0.0.1", port=port)
        await server.async_start()

        async def call(ws, message_id, payload) -> dict:
            await ws.send_json({'id': message_id, **payload})
            return await ws.receive_json()

        with mock.patch.object(plug_and_play, 'async_probe_ports', return_value={}), \
             mock.patch.object(plug_and_play, '_bus_was_read', return_value=True):
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(f"http://127.0.0.1:{port}/api/websocket") as ws:
                    await ws.receive_json()
                    await ws.send_json({'type': 'auth', 'access_token': 'anything'})
                    await ws.receive_json()

                    status = await call(ws, 1, {'type': 'eltako/plug_and_play/status'})
                    assert status['success']
                    assert status['result']['enabled'] is False

                    # pressing the button switches the setting on and starts a run
                    started = await call(ws, 2, {'type': 'eltako/plug_and_play/run', 'enable': True})
                    assert started['success']
                    assert started['result']['started'] is True
                    assert started['result']['status']['enabled'] is True

                    # ... and the checkbox of the configuration shows it as an override
                    settings = await call(ws, 3, {'type': 'eltako/settings/get'})
                    entry = next(setting for setting in settings['result']['settings']
                                 if setting['name'] == CONF_PLUG_AND_PLAY)
                    assert entry['value'] is True
                    assert entry['origin'] == 'ui'

                    # pressing it again switches it off without starting anything
                    stopped = await call(ws, 4, {'type': 'eltako/plug_and_play/run', 'enable': False})
                    assert stopped['result']['started'] is False
                    assert stopped['result']['status']['enabled'] is False

                    # a gateway of the web ui can be changed - here the yaml one is refused
                    refused = await call(ws, 5, {'type': 'eltako/gateways/update',
                                                 'gateway_id': 1, 'gateway': {'name': 'x'}})
                    assert not refused['success']
                    assert 'configuration.yaml' in refused['error']['message']

        await server.async_stop()
        await runtime.async_stop()
    run(scenario())


def test_nothing_is_added_when_the_detection_only_looks(config_dir):
    async def scenario():
        runtime = await _booted(config_dir)
        _fake_bus(runtime)

        report = await _run_detection(runtime, add_devices=False)

        assert report['devices_added'] == []
        assert len(report['devices_pending']) == 5

        await runtime.async_stop()
    run(scenario())


def test_several_buses_are_read_in_parallel(config_dir):
    """Every bus is its own serial or tcp connection - reading them one after the other only
    multiplies the minutes the stage takes. Each fake bus read waits for the other one to
    have started: sequential execution deadlocks and fails the timeout."""
    async def scenario():
        runtime = await _booted(config_dir)

        from custom_components.eltako.const import GatewayDeviceType
        from custom_components.eltako.core import websocket as core_websocket
        from custom_components.eltako.tools import plug_and_play

        class BusGateway:
            def __init__(self, dev_id):
                self.dev_id = dev_id
                self.dev_type = GatewayDeviceType.GatewayEltakoFAM14
                self.is_simulated = False

        started = {1: asyncio.Event(), 2: asyncio.Event()}

        async def read_bus(hass, bus_members, gateway):
            started[gateway.dev_id].set()
            other = 2 if gateway.dev_id == 1 else 1
            await asyncio.wait_for(started[other].wait(), timeout=1)
            return {'gateway_id': gateway.dev_id, 'finished': True, 'positions': 0}

        async def announced(hass):
            return []

        with mock.patch.object(plug_and_play, 'async_probe_ports', return_value={}), \
             mock.patch.object(plug_and_play, 'async_discover_mdns_gateways', announced), \
             mock.patch.object(plug_and_play, '_bus_was_read', return_value=False), \
             mock.patch.object(core_websocket, 'get_gateways',
                               return_value=[BusGateway(1), BusGateway(2)]), \
             mock.patch.object(plug_and_play, '_async_read_bus', read_bus):
            report = await plug_and_play.async_run(runtime.hass)

        assert {read['gateway_id'] for read in report['buses_read']} == {1, 2}
        assert all(read['finished'] for read in report['buses_read'])

        await runtime.async_stop()
    run(scenario())
