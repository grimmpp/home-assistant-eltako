"""Tests: booting the integration on the shim, entity creation, state flow."""

import asyncio
from unittest import mock

from eltako_standalone.runtime import EltakoRuntime


def run(coro):
    return asyncio.run(coro)


async def _booted(config_dir):
    runtime = EltakoRuntime(config_dir)
    await runtime.async_start()
    await runtime.hass.async_block_till_done()
    return runtime


def test_boot_without_gateways(empty_config_dir):
    async def scenario():
        runtime = await _booted(empty_config_dir)
        from homeassistant.components.websocket_api import get_commands

        commands = get_commands(runtime.hass)
        assert "eltako/integration_info" in commands
        assert "eltako/telegram_log/subscribe" in commands
        assert "eltako/entities/list" in commands
        assert len(commands) >= 30
        await runtime.async_stop()
    run(scenario())


def test_boot_creates_entities(config_dir):
    async def scenario():
        runtime = await _booted(config_dir)
        from eltako_standalone.entity_api import list_entities

        entities = {entity["entity_id"]: entity for entity in list_entities(runtime.hass)}
        assert "light.eltako_gw_1_00_00_00_01" in entities
        assert "binary_sensor.eltako_ff_bb_0a_1b" in entities
        light = entities["light.eltako_gw_1_00_00_00_01"]
        assert light["name"] == "Testlampe"
        assert light["area"] == "Kitchen"
        assert light["eep"] == "M5-38-08"
        assert "turn_on" in light["actions"]
        await runtime.async_stop()
    run(scenario())


def test_incoming_telegram_updates_state(config_dir):
    async def scenario():
        runtime = await _booted(config_dir)
        from eltakobus.message import RPSMessage
        from custom_components.eltako.core.websocket import get_gateways

        gateway = get_gateways(runtime.hass)[0]
        # rocker switch FF-BB-0A-1B presses top-right (0x70)
        gateway._handle_received_message(RPSMessage(b"\xff\xbb\x0a\x1b", 0x30, b"\x70"))
        await runtime.hass.async_block_till_done()

        state = runtime.hass.states.get("binary_sensor.eltako_ff_bb_0a_1b")
        assert state is not None
        assert state.state == "on"
        await runtime.async_stop()
    run(scenario())


def test_control_light_sends_telegram(config_dir):
    async def scenario():
        runtime = await _booted(config_dir)
        from eltako_standalone.entity_api import async_call_entity
        from custom_components.eltako.core.websocket import get_gateways

        gateway = get_gateways(runtime.hass)[0]
        sent = []

        async def fake_send(msg):
            sent.append(msg)
        gateway._bus = mock.Mock()
        gateway._bus.is_active.return_value = True
        gateway._bus.send = fake_send

        await async_call_entity(runtime.hass, "light.eltako_gw_1_00_00_00_01", "turn_on", {})
        await runtime.hass.async_block_till_done()

        assert len(sent) == 1
        assert sent[0].address == b"\x00\x00\xb0\x01"      # the configured sender id
        await runtime.async_stop()
    run(scenario())


def test_state_restore_across_restart(config_dir):
    async def first_run():
        runtime = await _booted(config_dir)
        from eltakobus.message import RPSMessage
        from custom_components.eltako.core.websocket import get_gateways

        gateway = get_gateways(runtime.hass)[0]
        gateway._handle_received_message(RPSMessage(b"\xff\xbb\x0a\x1b", 0x30, b"\x70"))
        await runtime.hass.async_block_till_done()
        assert runtime.hass.states.get("binary_sensor.eltako_ff_bb_0a_1b").state == "on"
        await runtime.async_stop()      # persists the states

    async def second_run():
        runtime = await _booted(config_dir)
        state = runtime.hass.states.get("binary_sensor.eltako_ff_bb_0a_1b")
        assert state is not None
        assert state.state == "on"      # restored via RestoreEntity
        await runtime.async_stop()

    run(first_run())
    run(second_run())


def test_ui_device_add_creates_entity_after_reload(config_dir):
    async def scenario():
        runtime = await _booted(config_dir)
        from homeassistant.components.websocket_api import ActiveConnection, async_handle_message

        messages = []
        connection = ActiveConnection(runtime.hass, messages.append)
        await async_handle_message(runtime.hass, connection, {
            "id": 1, "type": "eltako/devices/add", "gateway_id": 1, "platform": "switch",
            "device": {"id": "00-00-00-05", "eep": "M5-38-08", "name": "UI Steckdose",
                       "sender": {"id": "00-00-B0-05", "eep": "A5-38-08"}},
        })
        assert messages and messages[-1]["success"], messages
        # updating the entry options triggers the reload listener asynchronously
        await runtime.hass.async_block_till_done()

        from eltako_standalone.entity_api import list_entities
        entities = {entity["entity_id"] for entity in list_entities(runtime.hass)}
        assert "switch.eltako_gw_1_00_00_00_05" in entities
        await runtime.async_stop()
    run(scenario())
