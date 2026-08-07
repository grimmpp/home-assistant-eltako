"""The simulation end to end: no hardware, no configuration.yaml - and it still works.

This is the test the simulation exists for. It boots the integration on an empty config folder,
creates the starter set (a LAN gateway, a USB300 and a FAM14, each with example devices), lets
the plug & play detection find those devices and then checks that

* every simulated device ends up in the configuration and is marked as simulated
* a triggered sensor telegram changes the state of the entity
* switching a light, driving a cover and setting a temperature really reach the entity - the
  simulated actuator answers like the real one
"""

import asyncio

import pytest

from eltako_standalone.runtime import EltakoRuntime


def run(coro):
    return asyncio.run(coro)


async def _booted(config_dir) -> EltakoRuntime:
    runtime = EltakoRuntime(config_dir)
    await runtime.async_start()
    await runtime.hass.async_block_till_done()
    return runtime


async def _entity_of(hass, address: str, platform: str) -> str | None:
    """entity id of a configured device - the same lookup the web ui uses."""
    from custom_components.eltako.config.device_config import _describe_devices

    for device in _describe_devices(hass):
        if device['address'] == address.upper() and device['platform'] == platform:
            return (device['entity_ids'] or [None])[0]
    return None


async def _settled(hass, seconds: float = 1.0) -> None:
    """Adding devices reloads the gateways - wait for the entities to be there again."""
    await hass.async_block_till_done()
    await asyncio.sleep(seconds)
    await hass.async_block_till_done()


def test_the_starter_set_needs_no_hardware(empty_config_dir):
    async def scenario():
        runtime = await _booted(empty_config_dir)
        from custom_components.eltako import simulation

        result = await simulation.async_add_preset(runtime.hass)

        created = {gateway['device_type']: gateway for gateway in result['created']}
        assert set(created) == {'mgw-lan', 'enocean-usb300', 'fam14'}
        assert result['device_count'] == 3 * len(simulation.core.DEVICE_PRESETS)

        overview = simulation.get_overview(runtime.hass)
        assert len(overview['gateways']) == 3
        for gateway in overview['gateways']:
            # every simulated gateway is set up and 'connected' - nothing was opened
            assert gateway['set_up'], gateway
            assert gateway['live'] and gateway['connected'], gateway
            assert gateway['serial_path'].startswith('simulator-')
            assert len(gateway['devices']) == len(simulation.core.DEVICE_PRESETS)

        # the FAM14 is a bus gateway: local addresses, senders at 00-00-B0-xx
        fam14 = next(g for g in overview['gateways'] if g['device_type'] == 'fam14')
        assert fam14['bus_gateway']
        light = next(d for d in fam14['devices'] if d['eep'] == 'M5-38-08')
        assert light['address'] == '00-00-00-01'
        assert light['sender_id'] == '00-00-B0-01'
        # the USB300 is a wireless transceiver: addresses of its base id range
        usb300 = next(g for g in overview['gateways'] if g['device_type'] == 'enocean-usb300')
        assert not usb300['bus_gateway']
        assert all(d['address'].startswith('FF-C0-') for d in usb300['devices'])

        await runtime.async_stop()
    run(scenario())


def test_the_detection_configures_every_simulated_device(empty_config_dir):
    async def scenario():
        runtime = await _booted(empty_config_dir)
        hass = runtime.hass
        from custom_components.eltako import simulation
        from custom_components.eltako.config.device_config import _describe_devices
        from custom_components.eltako.tools import plug_and_play

        await simulation.async_add_preset(hass)
        report = await plug_and_play.async_run(hass)
        await _settled(hass)

        expected = 3 * len(simulation.core.DEVICE_PRESETS)
        assert len(report['devices_added']) == expected, report['warnings']
        assert report['warnings'] == []
        assert {device['source'] for device in report['devices_added']} == {'simulator'}
        # a simulated bus is never read - there is no memory behind it
        assert report['buses_read'] == []

        devices = _describe_devices(hass)
        assert len(devices) == expected
        assert all(device['simulated'] for device in devices)
        # and they became real entities
        assert await _entity_of(hass, '00-00-00-05', 'sensor')

        # running the detection again must not add anything twice
        again = await plug_and_play.async_run(hass)
        assert again['devices_added'] == []

        await runtime.async_stop()
    run(scenario())


def test_a_simulated_sensor_updates_its_entity(empty_config_dir):
    async def scenario():
        runtime = await _booted(empty_config_dir)
        hass = runtime.hass
        from custom_components.eltako import simulation
        from custom_components.eltako.tools import plug_and_play

        await simulation.async_add_preset(hass, keys=['fam14'])
        await plug_and_play.async_run(hass)
        await _settled(hass)

        result = await simulation.async_trigger(hass, 0, '00-00-00-05',
                                                {'temperature': 23.5, 'humidity': 61})
        await _settled(hass, 0.3)

        assert result['sent']
        assert result['state']['temperature'] == 23.5
        temperature = hass.states.get('sensor.eltako_gw_0_00_00_00_05_temperature')
        humidity = hass.states.get('sensor.eltako_gw_0_00_00_00_05_humidity')
        assert temperature is not None and humidity is not None
        assert float(temperature.state) == pytest.approx(23.5, abs=0.5)
        assert float(humidity.state) == pytest.approx(61, abs=1.5)

        # the value stays until it is changed again (a real sensor repeats its measurement)
        overview = simulation.get_overview(hass)
        sensor = next(d for d in overview['gateways'][0]['devices'] if d['address'] == '00-00-00-05')
        assert sensor['state']['temperature'] == 23.5
        assert sensor['sent_count'] == 1

        await runtime.async_stop()
    run(scenario())


def test_a_simulated_actuator_reacts_to_home_assistant(empty_config_dir):
    async def scenario():
        runtime = await _booted(empty_config_dir)
        hass = runtime.hass
        from eltako_standalone.entity_api import async_call_entity
        from custom_components.eltako import simulation
        from custom_components.eltako.tools import plug_and_play

        await simulation.async_add_preset(hass, keys=['fam14'])
        await plug_and_play.async_run(hass)
        await _settled(hass)

        # a light: the simulated relay reports its new state back
        light = await _entity_of(hass, '00-00-00-01', 'light')
        assert light, "the simulated light did not become an entity"
        await async_call_entity(hass, light, 'turn_on', {})
        await _settled(hass, 0.3)
        assert hass.states.get(light).state == 'on'
        await async_call_entity(hass, light, 'turn_off', {})
        await _settled(hass, 0.3)
        assert hass.states.get(light).state == 'off'

        # a cover: up and down reach the end positions
        cover = await _entity_of(hass, '00-00-00-03', 'cover')
        assert cover
        await async_call_entity(hass, cover, 'open_cover', {})
        await _settled(hass, 0.3)
        assert hass.states.get(cover).state == 'open'
        await async_call_entity(hass, cover, 'close_cover', {})
        await _settled(hass, 0.3)
        assert hass.states.get(cover).state == 'closed'

        await runtime.async_stop()
    run(scenario())


def test_the_simulation_survives_a_restart(empty_config_dir):
    async def scenario():
        runtime = await _booted(empty_config_dir)
        from custom_components.eltako import simulation

        await simulation.async_add_preset(runtime.hass, keys=['usb300'])
        await simulation.async_update_device(runtime.hass, 0, 'FF-C0-00-05',
                                             {'state': {'temperature': 19.5}})
        await runtime.async_stop()

        # second start on the same config folder
        runtime = await _booted(empty_config_dir)
        overview = simulation.get_overview(runtime.hass)

        assert len(overview['gateways']) == 1
        gateway = overview['gateways'][0]
        assert gateway['device_type'] == 'enocean-usb300'
        assert len(gateway['devices']) == len(simulation.core.DEVICE_PRESETS)
        sensor = next(d for d in gateway['devices'] if d['address'] == 'FF-C0-00-05')
        assert sensor['state']['temperature'] == 19.5
        assert gateway['connected']

        await runtime.async_stop()
    run(scenario())


def test_removing_a_simulated_gateway_removes_its_devices(empty_config_dir):
    async def scenario():
        runtime = await _booted(empty_config_dir)
        hass = runtime.hass
        from custom_components.eltako import simulation

        created = await simulation.async_add_gateway(hass, 'fam14', 'Simulated FAM14')
        await simulation.async_add_preset_devices(hass, created['gateway_id'])

        result = await simulation.async_remove_gateway(hass, created['gateway_id'])
        await _settled(hass, 0.2)

        assert result['removed']
        assert result['removed_devices'] == len(simulation.core.DEVICE_PRESETS)
        assert result['removed_config_entries'] == 1
        assert simulation.get_overview(hass)['gateways'] == []

        await runtime.async_stop()
    run(scenario())


def test_a_device_can_send_on_its_own(empty_config_dir):
    """An interval makes a device repeat its telegram - like a real sensor."""
    async def scenario():
        runtime = await _booted(empty_config_dir)
        hass = runtime.hass
        from custom_components.eltako import simulation
        from custom_components.eltako.tools import plug_and_play

        await simulation.async_add_preset(hass, keys=['fam14'])
        await plug_and_play.async_run(hass)
        await _settled(hass)

        device = await simulation.async_set_interval(hass, 0, '00-00-00-05', 1)
        assert device['interval'] == 1
        assert device['repeating']
        assert simulation.is_repeating(hass, 0, '00-00-00-05')

        before = device['sent_count']
        await asyncio.sleep(3.2)
        overview = simulation.get_overview(hass)
        sensor = next(d for d in overview['gateways'][0]['devices'] if d['address'] == '00-00-00-05')
        assert sensor['sent_count'] >= before + 2, sensor
        assert overview['repeating_count'] == 1
        # the entity really got the values
        assert hass.states.get('sensor.eltako_gw_0_00_00_00_05_temperature').state not in (None, 'unknown')

        stopped = await simulation.async_set_interval(hass, 0, '00-00-00-05', 0)
        assert not stopped['repeating']
        assert not simulation.is_repeating(hass, 0, '00-00-00-05')
        settled = simulation.get_overview(hass)['gateways'][0]['devices']
        count = next(d['sent_count'] for d in settled if d['address'] == '00-00-00-05')
        await asyncio.sleep(2.2)
        after = next(d['sent_count'] for d in
                     simulation.get_overview(hass)['gateways'][0]['devices']
                     if d['address'] == '00-00-00-05')
        assert after == count, "the device kept sending after it was stopped"

        await runtime.async_stop()
    run(scenario())


def test_an_interval_survives_a_restart(empty_config_dir):
    async def scenario():
        runtime = await _booted(empty_config_dir)
        from custom_components.eltako import simulation

        await simulation.async_add_preset(runtime.hass, keys=['usb300'])
        await simulation.async_set_interval(runtime.hass, 0, 'FF-C0-00-05', 2)
        await runtime.async_stop()

        runtime = await _booted(empty_config_dir)
        # the timer is started by the setup, not by the first call
        assert simulation.is_repeating(runtime.hass, 0, 'FF-C0-00-05')
        overview = simulation.get_overview(runtime.hass)
        sensor = next(d for d in overview['gateways'][0]['devices'] if d['address'] == 'FF-C0-00-05')
        assert sensor['interval'] == 2
        assert sensor['repeating']

        await runtime.async_stop()
        # the timers are gone with the runtime
        assert not simulation.is_repeating(runtime.hass, 0, 'FF-C0-00-05')
    run(scenario())


def test_every_device_can_announce_its_profile(empty_config_dir):
    """The teach-in button: 4BS names the profile, 1BS learns, RPS sends a press."""
    async def scenario():
        runtime = await _booted(empty_config_dir)
        hass = runtime.hass
        from custom_components.eltako import simulation

        await simulation.async_add_preset(hass, keys=['fam14'])
        overview = simulation.get_overview(hass)

        for device in overview['gateways'][0]['devices']:
            assert device['teach_in'], device
            result = await simulation.async_trigger(hass, 0, device['address'], kind='teach_in')
            assert result['sent']
            assert result['teach_in_kind'] in ('4bs', '1bs', 'rps')
            # RPS has no teach-in telegram: a press and its release are sent instead
            assert result['telegram_count'] == (2 if result['teach_in_kind'] == 'rps' else 1)
            assert result['teach_in_description']

        await runtime.async_stop()
    run(scenario())


def test_a_gateway_can_report_its_base_id(empty_config_dir):
    """The button 'send base id' - the answer a real gateway gives after connecting."""
    async def scenario():
        runtime = await _booted(empty_config_dir)
        hass = runtime.hass
        from custom_components.eltako import simulation

        created = await simulation.async_add_gateway(hass, 'enocean-usb300', 'Simulated USB300')
        result = await simulation.async_send_base_id(hass, created['gateway_id'])

        assert result['sent']
        assert result['base_id'] == created['base_id']
        assert result['hex'].startswith('a55a8b98')      # the base id info telegram
        # the sensor of the gateway shows it
        await _settled(hass, 0.3)
        state = hass.states.get(f"sensor.eltako_gw_{created['gateway_id']}_base_id")
        assert state is not None and state.state == created['base_id']

        await runtime.async_stop()
    run(scenario())


def test_a_telegram_of_a_simulated_gateway_is_marked_in_the_log(empty_config_dir):
    """The live view has to be able to tell a simulated telegram from a real one."""
    async def scenario():
        runtime = await _booted(empty_config_dir)
        hass = runtime.hass
        from custom_components.eltako import simulation
        from custom_components.eltako.observation.enocean_logger import get_telegram_logger

        await simulation.async_add_preset(hass, keys=['fam14'])
        await _settled(hass, 0.3)
        logger = get_telegram_logger(hass)
        assert logger is not None, "the standalone runtime records telegrams by default"

        await simulation.async_trigger(hass, 0, '00-00-00-05', {'temperature': 22})
        await _settled(hass, 0.3)

        records = logger.get_recent_telegrams(limit=50)
        ours = [record for record in records if record['address'] == 'FF-C0-00-05'
                or record.get('local_address') == '00-00-00-05']
        assert ours, records
        assert all(record['simulated'] for record in ours), ours

        await runtime.async_stop()
    run(scenario())


def test_a_taught_in_switch_controls_a_simulated_actuator(empty_config_dir):
    """Any sender can be taught in - here a switch which sits behind a *different* gateway.

    That is the path a real wall switch takes: its telegram arrives at some gateway, is published
    on the global telegram bus, and the simulated actuator which knows that sender answers.
    """
    async def scenario():
        runtime = await _booted(empty_config_dir)
        hass = runtime.hass
        from custom_components.eltako import simulation
        from custom_components.eltako.tools import plug_and_play

        # two simulations: the actuator sits on the FAM14, the 'real' switch reports through the
        # USB300 - which is exactly how a real installation looks from the actuator's side
        await simulation.async_add_preset(hass, keys=['fam14'])
        usb300 = await simulation.async_add_gateway(hass, 'enocean-usb300', 'Radio')
        switch = await simulation.async_add_device(hass, usb300['gateway_id'], {
            'platform': 'binary_sensor', 'eep': 'F6-02-01', 'name': 'Wall switch'})
        await plug_and_play.async_run(hass)
        await _settled(hass)

        light = await _entity_of(hass, '00-00-00-01', 'light')
        assert light
        result = await simulation.async_teach_in(hass, 0, '00-00-00-01', switch['address'],
                                                 'F6-02-01', 'Wall switch')
        assert result['understood']
        assert [sender['id'] for sender in result['device']['senders']] == \
            ['00-00-B0-01', switch['address']]

        # press the top button of that switch - the actuator has to switch on
        await simulation.async_trigger(hass, usb300['gateway_id'], switch['address'],
                                       {'rocker_first_action': 1, 'energy_bow': 1})
        await _settled(hass, 0.4)
        assert hass.states.get(light).state == 'on'

        # the bottom button switches it off again
        await simulation.async_trigger(hass, usb300['gateway_id'], switch['address'],
                                       {'rocker_first_action': 0, 'energy_bow': 1})
        await _settled(hass, 0.4)
        assert hass.states.get(light).state == 'off'

        # and after removing the sender it does nothing anymore
        await simulation.async_forget_sender(hass, 0, '00-00-00-01', switch['address'])
        await simulation.async_trigger(hass, usb300['gateway_id'], switch['address'],
                                       {'rocker_first_action': 1, 'energy_bow': 1})
        await _settled(hass, 0.4)
        assert hass.states.get(light).state == 'off'

        await runtime.async_stop()
    run(scenario())


def test_deactivating_stops_the_periodic_telegrams(empty_config_dir):
    """Switching the simulation off stops every timer - and keeps every interval."""
    async def scenario():
        runtime = await _booted(empty_config_dir)
        hass = runtime.hass
        from custom_components.eltako import simulation

        await simulation.async_add_preset(hass, keys=['fam14'])
        await simulation.async_set_interval(hass, 0, '00-00-00-05', 1)
        assert simulation.is_repeating(hass, 0, '00-00-00-05')
        before = next(d['sent_count'] for d in
                      simulation.get_overview(hass)['gateways'][0]['devices']
                      if d['address'] == '00-00-00-05')

        result = await simulation.async_set_active(hass, False)
        assert result['devices_with_interval'] == 1
        assert not simulation.is_repeating(hass, 0, '00-00-00-05')

        await asyncio.sleep(2.5)
        overview = simulation.get_overview(hass)
        sensor = next(d for d in overview['gateways'][0]['devices'] if d['address'] == '00-00-00-05')
        assert sensor['sent_count'] == before, "a deactivated simulation must not send anything"
        assert sensor['interval'] == 1 and not sensor['repeating']      # the setting is kept

        result = await simulation.async_set_active(hass, True)
        await _settled(hass, 0.5)
        assert result['repeating_count'] == 1
        assert simulation.is_repeating(hass, 0, '00-00-00-05')
        await asyncio.sleep(2.2)
        after = next(d['sent_count'] for d in
                     simulation.get_overview(hass)['gateways'][0]['devices']
                     if d['address'] == '00-00-00-05')
        assert after > before, "after activating it has to send again"

        await runtime.async_stop()
    run(scenario())


def test_every_device_can_announce_its_profile(empty_config_dir):
    """The teach-in button: 4BS names the profile, 1BS learns, RPS sends a press."""
    async def scenario():
        runtime = await _booted(empty_config_dir)
        hass = runtime.hass
        from custom_components.eltako import simulation

        await simulation.async_add_preset(hass, keys=['fam14'])
        overview = simulation.get_overview(hass)

        for device in overview['gateways'][0]['devices']:
            assert device['teach_in'], device
            result = await simulation.async_trigger(hass, 0, device['address'], kind='teach_in')
            assert result['sent']
            assert result['teach_in_kind'] in ('4bs', '1bs', 'rps')
            # RPS has no teach-in telegram: a press and its release are sent instead
            assert result['telegram_count'] == (2 if result['teach_in_kind'] == 'rps' else 1)
            assert result['teach_in_description']

        await runtime.async_stop()
    run(scenario())


def test_a_gateway_can_report_its_base_id(empty_config_dir):
    """The button 'send base id' - the answer a real gateway gives after connecting."""
    async def scenario():
        runtime = await _booted(empty_config_dir)
        hass = runtime.hass
        from custom_components.eltako import simulation

        created = await simulation.async_add_gateway(hass, 'enocean-usb300', 'Simulated USB300')
        result = await simulation.async_send_base_id(hass, created['gateway_id'])

        assert result['sent']
        assert result['base_id'] == created['base_id']
        assert result['hex'].startswith('a55a8b98')      # the base id info telegram
        # the sensor of the gateway shows it
        await _settled(hass, 0.3)
        state = hass.states.get(f"sensor.eltako_gw_{created['gateway_id']}_base_id")
        assert state is not None and state.state == created['base_id']

        await runtime.async_stop()
    run(scenario())


def test_a_telegram_of_a_simulated_gateway_is_marked_in_the_log(empty_config_dir):
    """The live view has to be able to tell a simulated telegram from a real one."""
    async def scenario():
        runtime = await _booted(empty_config_dir)
        hass = runtime.hass
        from custom_components.eltako import simulation
        from custom_components.eltako.observation.enocean_logger import get_telegram_logger

        await simulation.async_add_preset(hass, keys=['fam14'])
        await _settled(hass, 0.3)
        logger = get_telegram_logger(hass)
        assert logger is not None, "the standalone runtime records telegrams by default"

        await simulation.async_trigger(hass, 0, '00-00-00-05', {'temperature': 22})
        await _settled(hass, 0.3)

        records = logger.get_recent_telegrams(limit=50)
        ours = [record for record in records if record['address'] == 'FF-C0-00-05'
                or record.get('local_address') == '00-00-00-05']
        assert ours, records
        assert all(record['simulated'] for record in ours), ours

        await runtime.async_stop()
    run(scenario())


def test_a_taught_in_switch_controls_a_simulated_actuator(empty_config_dir):
    """Any sender can be taught in - here a switch which sits behind a *different* gateway.

    That is the path a real wall switch takes: its telegram arrives at some gateway, is published
    on the global telegram bus, and the simulated actuator which knows that sender answers.
    """
    async def scenario():
        runtime = await _booted(empty_config_dir)
        hass = runtime.hass
        from custom_components.eltako import simulation
        from custom_components.eltako.tools import plug_and_play

        # two simulations: the actuator sits on the FAM14, the 'real' switch reports through the
        # USB300 - which is exactly how a real installation looks from the actuator's side
        await simulation.async_add_preset(hass, keys=['fam14'])
        usb300 = await simulation.async_add_gateway(hass, 'enocean-usb300', 'Radio')
        switch = await simulation.async_add_device(hass, usb300['gateway_id'], {
            'platform': 'binary_sensor', 'eep': 'F6-02-01', 'name': 'Wall switch'})
        await plug_and_play.async_run(hass)
        await _settled(hass)

        light = await _entity_of(hass, '00-00-00-01', 'light')
        assert light
        result = await simulation.async_teach_in(hass, 0, '00-00-00-01', switch['address'],
                                                 'F6-02-01', 'Wall switch')
        assert result['understood']
        assert [sender['id'] for sender in result['device']['senders']] == \
            ['00-00-B0-01', switch['address']]

        # press the top button of that switch - the actuator has to switch on
        await simulation.async_trigger(hass, usb300['gateway_id'], switch['address'],
                                       {'rocker_first_action': 1, 'energy_bow': 1})
        await _settled(hass, 0.4)
        assert hass.states.get(light).state == 'on'

        # the bottom button switches it off again
        await simulation.async_trigger(hass, usb300['gateway_id'], switch['address'],
                                       {'rocker_first_action': 0, 'energy_bow': 1})
        await _settled(hass, 0.4)
        assert hass.states.get(light).state == 'off'

        # and after removing the sender it does nothing anymore
        await simulation.async_forget_sender(hass, 0, '00-00-00-01', switch['address'])
        await simulation.async_trigger(hass, usb300['gateway_id'], switch['address'],
                                       {'rocker_first_action': 1, 'energy_bow': 1})
        await _settled(hass, 0.4)
        assert hass.states.get(light).state == 'off'

        await runtime.async_stop()
    run(scenario())


def test_deactivating_stops_the_periodic_telegrams(empty_config_dir):
    """Switching the simulation off stops every timer - and keeps every interval."""
    async def scenario():
        runtime = await _booted(empty_config_dir)
        hass = runtime.hass
        from custom_components.eltako import simulation

        await simulation.async_add_preset(hass, keys=['fam14'])
        await simulation.async_set_interval(hass, 0, '00-00-00-05', 1)
        assert simulation.is_repeating(hass, 0, '00-00-00-05')
        before = next(d['sent_count'] for d in
                      simulation.get_overview(hass)['gateways'][0]['devices']
                      if d['address'] == '00-00-00-05')

        result = await simulation.async_set_active(hass, False)
        assert result['devices_with_interval'] == 1
        assert not simulation.is_repeating(hass, 0, '00-00-00-05')

        await asyncio.sleep(2.5)
        overview = simulation.get_overview(hass)
        sensor = next(d for d in overview['gateways'][0]['devices'] if d['address'] == '00-00-00-05')
        assert sensor['sent_count'] == before, "a deactivated simulation must not send anything"
        assert sensor['interval'] == 1 and not sensor['repeating']      # the setting is kept

        result = await simulation.async_set_active(hass, True)
        await _settled(hass, 0.5)
        assert result['repeating_count'] == 1
        assert simulation.is_repeating(hass, 0, '00-00-00-05')
        await asyncio.sleep(2.2)
        after = next(d['sent_count'] for d in
                     simulation.get_overview(hass)['gateways'][0]['devices']
                     if d['address'] == '00-00-00-05')
        assert after > before, "after activating it has to send again"

        await runtime.async_stop()
    run(scenario())


def test_a_paused_simulation_stays_paused_after_a_restart(empty_config_dir):
    async def scenario():
        runtime = await _booted(empty_config_dir)
        from custom_components.eltako import simulation

        await simulation.async_add_preset(runtime.hass, keys=['fam14'])
        await simulation.async_set_interval(runtime.hass, 0, '00-00-00-05', 1)
        await simulation.async_set_paused(runtime.hass, True)
        await runtime.async_stop()

        runtime = await _booted(empty_config_dir)

        assert simulation.get_overview(runtime.hass)['paused']
        assert not simulation.is_repeating(runtime.hass, 0, '00-00-00-05')
        await runtime.async_stop()
    run(scenario())


def test_both_teach_in_telegrams_can_be_sent(empty_config_dir):
    """The profile teach-in of a device and the Eltako teach-in of its sender are not the same."""
    async def scenario():
        runtime = await _booted(empty_config_dir)
        hass = runtime.hass
        from custom_components.eltako import simulation

        await simulation.async_add_preset(hass, keys=['fam14'])

        profile = await simulation.async_trigger(hass, 0, '00-00-00-01', kind='teach_in')
        eltako = await simulation.async_trigger(hass, 0, '00-00-00-01', kind='eltako_teach_in')

        assert profile['hex'] != eltako['hex']
        assert eltako['telegram_count'] == 1
        # the Eltako one carries the payload of the sender profile and comes from the sender
        assert eltako['hex'][0][8:16] == 'e0400d80'
        assert '00-00-B0-01' in eltako['telegram']
        assert 'sender' in eltako['teach_in_description'].lower()

        # a sensor profile without such a payload says so instead of sending something wrong
        from custom_components.eltako.simulation.core import SimulationError
        try:
            await simulation.async_trigger(hass, 0, '00-00-00-05', kind='eltako_teach_in')
            raise AssertionError("a profile without an Eltako payload must be refused")
        except SimulationError as error:
            assert 'A5-38-08' in str(error)

        await runtime.async_stop()
    run(scenario())


REAL_TRANSCEIVER_YAML = """
eltako:
  general_settings:
    enable_frontend: True
  gateway:
  - id: 7
    device_type: enocean-usb300
    base_id: FF-AA-80-00
    name: Real USB300
    auto_reconnect: False
    serial_path: /dev/tty.does-not-exist
"""


@pytest.fixture
def real_gateway_config_dir(tmp_path):
    """A config folder with a real wireless transceiver (whose port does not exist)."""
    (tmp_path / "configuration.yaml").write_text(REAL_TRANSCEIVER_YAML, encoding="utf-8")
    return str(tmp_path)


def test_a_simulated_device_can_sit_on_a_real_gateway(real_gateway_config_dir):
    """Its telegrams are then really transmitted, and its address derives from that base id.

    The port of that gateway does not exist, which is enough here: what matters is that the
    telegram leaves *through that gateway* instead of being injected into a simulation.
    """
    async def scenario():
        runtime = await _booted(real_gateway_config_dir)
        hass = runtime.hass
        from homeassistant.helpers.dispatcher import async_dispatcher_connect
        from custom_components.eltako import simulation
        from custom_components.eltako.const import ELTAKO_GLOBAL_EVENT_BUS_ID

        device = await simulation.async_add_device(hass, 7, {
            'platform': 'binary_sensor', 'eep': 'F6-02-01', 'name': 'Simulated wall switch'})

        # the address comes from the base id of that real gateway, not from the FF-C0 range of
        # the simulation - a transceiver only transmits senders of its own base id range
        assert device['address'].startswith('FF-AA-80-'), device['address']

        overview = simulation.get_overview(hass)
        gateway = next(entry for entry in overview['gateways'] if entry['id'] == 7)
        assert gateway['simulated'] is False        # a real gateway, hosting a virtual device
        assert gateway['base_id'] == 'FF-AA-80-00'

        seen = []
        async_dispatcher_connect(hass, ELTAKO_GLOBAL_EVENT_BUS_ID,
                                 lambda data: seen.append(data))

        await simulation.async_trigger(hass, 7, device['address'],
                                       {'rocker_first_action': 3, 'energy_bow': 1})
        await _settled(hass, 0.3)

        # it was really sent through that gateway (not injected as a received telegram)
        sent = [entry for entry in seen
                if getattr(entry.get('esp2_msg'), 'address', None) ==
                bytes.fromhex(device['address'].replace('-', ''))]
        assert sent, seen
        assert getattr(sent[0]['gateway'], 'dev_id', None) == 7
        assert getattr(sent[0]['gateway'], 'is_simulated', False) is False

        await runtime.async_stop()
    run(scenario())


def test_deactivating_takes_the_simulation_out_of_home_assistant(empty_config_dir):
    """Deactivated: no entity, no device, no gateway entry - but nothing is lost."""
    async def scenario():
        runtime = await _booted(empty_config_dir)
        hass = runtime.hass
        from custom_components.eltako import simulation
        from custom_components.eltako.config.device_config import _describe_devices
        from custom_components.eltako.tools import plug_and_play

        await simulation.async_add_preset(hass, keys=['fam14'])
        await plug_and_play.async_run(hass)
        await _settled(hass)
        assert len(_describe_devices(hass)) == len(simulation.core.DEVICE_PRESETS)
        assert hass.states.get('sensor.eltako_gw_0_00_00_00_05_temperature') is not None

        result = await simulation.async_set_active(hass, False)
        await _settled(hass, 0.5)

        assert result['active'] is False
        assert result['devices'] == len(simulation.core.DEVICE_PRESETS)
        assert result['gateways'] == 1
        # gone from Home Assistant: no configured device, no entity, no gateway
        assert _describe_devices(hass) == []
        assert hass.states.get('sensor.eltako_gw_0_00_00_00_05_temperature') is None
        assert simulation.get_gateway(hass, 0) is None
        # but the simulation itself is complete and still editable
        overview = simulation.get_overview(hass)
        assert overview['active'] is False
        assert overview['device_count'] == len(simulation.core.DEVICE_PRESETS)
        assert overview['gateways'][0]['set_up'] is False
        changed = await simulation.async_update_device(hass, 0, '00-00-00-05',
                                                       {'state': {'temperature': 18}})
        assert changed['state']['temperature'] == 18
        added = await simulation.async_add_device(hass, 0, {
            'platform': 'sensor', 'eep': 'A5-04-02', 'name': 'While off'})
        assert await simulation.async_remove_device(hass, 0, added['address'])

        # ... and it cannot be used while it is off
        try:
            await simulation.async_trigger(hass, 0, '00-00-00-05')
            raise AssertionError("a deactivated simulation must not send anything")
        except simulation.core.SimulationError as error:
            assert 'not set up' in str(error)

        result = await simulation.async_set_active(hass, True)
        await _settled(hass, 1.0)

        assert result['active'] is True
        assert result['gateways'] == 1
        assert result['devices'] == len(simulation.core.DEVICE_PRESETS)
        assert len(_describe_devices(hass)) == len(simulation.core.DEVICE_PRESETS)
        assert hass.states.get('sensor.eltako_gw_0_00_00_00_05_temperature') is not None

        await runtime.async_stop()
    run(scenario())


def test_a_deactivated_simulation_stays_out_after_a_restart(empty_config_dir):
    async def scenario():
        runtime = await _booted(empty_config_dir)
        from custom_components.eltako import simulation

        await simulation.async_add_preset(runtime.hass, keys=['fam14'])
        await simulation.async_set_active(runtime.hass, False)
        await runtime.async_stop()

        runtime = await _booted(empty_config_dir)

        # the runtime must not set the gateway up again just because it is configured
        assert simulation.get_gateway(runtime.hass, 0) is None
        overview = simulation.get_overview(runtime.hass)
        assert overview['active'] is False
        assert overview['gateways'][0]['set_up'] is False
        assert overview['device_count'] == len(simulation.core.DEVICE_PRESETS)

        await runtime.async_stop()
    run(scenario())


def test_the_websocket_commands_are_registered(empty_config_dir):
    async def scenario():
        runtime = await _booted(empty_config_dir)
        from homeassistant.components.websocket_api import get_commands

        commands = get_commands(runtime.hass)
        for command in ('eltako/simulator/form', 'eltako/simulator/preset',
                        'eltako/simulator/gateway_add', 'eltako/simulator/gateway_remove',
                        'eltako/simulator/device_add', 'eltako/simulator/device_update',
                        'eltako/simulator/device_remove', 'eltako/simulator/trigger',
                        'eltako/simulator/base_id', 'eltako/simulator/teach_in',
                        'eltako/simulator/activate'):
            assert command in commands

        await runtime.async_stop()
    run(scenario())
