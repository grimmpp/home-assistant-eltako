"""Websocket api of the simulation - what the simulation page of the web ui calls.

Thin on purpose: every command validates its arguments and hands over to `service.py`, so the
web ui and the command line do exactly the same thing.
"""

from __future__ import annotations

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from ..const import (WS_SIMULATOR_BASE_ID, WS_SIMULATOR_DEVICE_ADD, WS_SIMULATOR_DEVICE_REMOVE,
                     WS_SIMULATOR_DEVICE_UPDATE, WS_SIMULATOR_FORM, WS_SIMULATOR_GATEWAY_ADD,
                     WS_SIMULATOR_GATEWAY_REMOVE, WS_SIMULATOR_ACTIVATE, WS_SIMULATOR_PRESET,
                     WS_SIMULATOR_TEACH_IN, WS_SIMULATOR_TRIGGER)
from . import service
from .core import SimulationError


def register_websocket_commands(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, ws_simulator_form)
    websocket_api.async_register_command(hass, ws_simulator_preset)
    websocket_api.async_register_command(hass, ws_simulator_gateway_add)
    websocket_api.async_register_command(hass, ws_simulator_gateway_remove)
    websocket_api.async_register_command(hass, ws_simulator_base_id)
    websocket_api.async_register_command(hass, ws_simulator_device_add)
    websocket_api.async_register_command(hass, ws_simulator_device_update)
    websocket_api.async_register_command(hass, ws_simulator_device_remove)
    websocket_api.async_register_command(hass, ws_simulator_trigger)
    websocket_api.async_register_command(hass, ws_simulator_teach_in)
    websocket_api.async_register_command(hass, ws_simulator_activate)


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required('type'): WS_SIMULATOR_FORM})
@callback
def ws_simulator_form(hass: HomeAssistant, connection, msg) -> None:
    """Everything the simulation page shows: gateways, devices, presets, profiles."""
    connection.send_result(msg['id'], service.get_overview(hass))


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required('type'): WS_SIMULATOR_PRESET,
    vol.Optional('keys'): vol.Any([str], None),
    vol.Optional('with_devices', default=True): bool,
    # given: add the example devices to THIS gateway instead of creating gateways
    vol.Optional('gateway_id'): vol.Any(vol.Coerce(int), None),
    vol.Optional('device_keys'): vol.Any([str], None),
})
@websocket_api.async_response
async def ws_simulator_preset(hass: HomeAssistant, connection, msg) -> None:
    """The starter set: gateways with example devices, or example devices for one gateway."""
    try:
        if msg.get('gateway_id') is not None:
            devices = await service.async_add_preset_devices(hass, msg['gateway_id'],
                                                             msg.get('device_keys'))
            connection.send_result(msg['id'], {'devices': devices, 'device_count': len(devices)})
            return
        result = await service.async_add_preset(hass, msg.get('keys'),
                                                msg.get('with_devices', True))
    except (SimulationError, vol.Invalid) as e:
        connection.send_error(msg['id'], 'preset_failed', str(e))
        return
    connection.send_result(msg['id'], result)


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required('type'): WS_SIMULATOR_GATEWAY_ADD,
    vol.Optional('device_type'): vol.Any(str, None),
    vol.Optional('name'): vol.Any(str, None),
    vol.Optional('with_devices', default=False): bool,
})
@websocket_api.async_response
async def ws_simulator_gateway_add(hass: HomeAssistant, connection, msg) -> None:
    try:
        result = await service.async_add_gateway(hass, msg.get('device_type'), msg.get('name'))
        if msg.get('with_devices'):
            devices = await service.async_add_preset_devices(hass, result['gateway_id'])
            result['devices'] = [device['address'] for device in devices]
    except (SimulationError, vol.Invalid) as e:
        connection.send_error(msg['id'], 'invalid_gateway', str(e))
        return
    connection.send_result(msg['id'], result)


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required('type'): WS_SIMULATOR_GATEWAY_REMOVE,
    vol.Required('gateway_id'): vol.Coerce(int),
})
@websocket_api.async_response
async def ws_simulator_gateway_remove(hass: HomeAssistant, connection, msg) -> None:
    try:
        result = await service.async_remove_gateway(hass, msg['gateway_id'])
    except (SimulationError, vol.Invalid) as e:
        connection.send_error(msg['id'], 'invalid_gateway', str(e))
        return
    connection.send_result(msg['id'], result)


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required('type'): WS_SIMULATOR_BASE_ID,
    vol.Required('gateway_id'): vol.Coerce(int),
})
@websocket_api.async_response
async def ws_simulator_base_id(hass: HomeAssistant, connection, msg) -> None:
    """Let a simulated gateway report its base id - the answer a real one gives when asked."""
    try:
        result = await service.async_send_base_id(hass, msg['gateway_id'])
    except (SimulationError, vol.Invalid) as e:
        connection.send_error(msg['id'], 'base_id_failed', str(e))
        return
    connection.send_result(msg['id'], result)


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required('type'): WS_SIMULATOR_DEVICE_ADD,
    vol.Required('gateway_id'): vol.Coerce(int),
    vol.Required('device'): dict,
})
@websocket_api.async_response
async def ws_simulator_device_add(hass: HomeAssistant, connection, msg) -> None:
    try:
        device = await service.async_add_device(hass, msg['gateway_id'], msg['device'])
    except (SimulationError, vol.Invalid) as e:
        connection.send_error(msg['id'], 'invalid_device', str(e))
        return
    connection.send_result(msg['id'], {'device': device})


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required('type'): WS_SIMULATOR_DEVICE_UPDATE,
    vol.Required('gateway_id'): vol.Coerce(int),
    vol.Required('address'): str,
    vol.Required('device'): dict,
})
@websocket_api.async_response
async def ws_simulator_device_update(hass: HomeAssistant, connection, msg) -> None:
    try:
        device = await service.async_update_device(hass, msg['gateway_id'], msg['address'],
                                                   msg['device'])
    except (SimulationError, vol.Invalid) as e:
        connection.send_error(msg['id'], 'invalid_device', str(e))
        return
    connection.send_result(msg['id'], {'device': device})


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required('type'): WS_SIMULATOR_DEVICE_REMOVE,
    vol.Required('gateway_id'): vol.Coerce(int),
    vol.Required('address'): str,
})
@websocket_api.async_response
async def ws_simulator_device_remove(hass: HomeAssistant, connection, msg) -> None:
    try:
        removed = await service.async_remove_device(hass, msg['gateway_id'], msg['address'])
    except (SimulationError, vol.Invalid) as e:
        connection.send_error(msg['id'], 'invalid_device', str(e))
        return
    connection.send_result(msg['id'], {'removed': removed})


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required('type'): WS_SIMULATOR_TRIGGER,
    vol.Required('gateway_id'): vol.Coerce(int),
    vol.Required('address'): str,
    vol.Optional('state'): vol.Any(dict, None),
    vol.Optional('kind', default='state'): vol.In(['state', 'teach_in', 'eltako_teach_in']),
})
@websocket_api.async_response
async def ws_simulator_trigger(hass: HomeAssistant, connection, msg) -> None:
    """Let a simulated device send its telegram now."""
    try:
        result = await service.async_trigger(hass, msg['gateway_id'], msg['address'],
                                             msg.get('state'), msg.get('kind', 'state'))
    except (SimulationError, vol.Invalid) as e:
        connection.send_error(msg['id'], 'trigger_failed', str(e))
        return
    except Exception as e:  # noqa: BLE001 - the message of the library explains the problem
        connection.send_error(msg['id'], 'trigger_failed', str(e))
        return
    connection.send_result(msg['id'], result)


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required('type'): WS_SIMULATOR_TEACH_IN,
    vol.Required('gateway_id'): vol.Coerce(int),
    vol.Required('address'): str,
    vol.Required('sender_id'): str,
    vol.Optional('sender_eep'): vol.Any(str, None),
    vol.Optional('name'): vol.Any(str, None),
    # given: remove that sender from the memory of the device instead of adding it
    vol.Optional('remove', default=False): bool,
})
@websocket_api.async_response
async def ws_simulator_teach_in(hass: HomeAssistant, connection, msg) -> None:
    """Teach a sender into a simulated actuator, or remove it again.

    The sender may be anything which sends telegrams - a real wall switch, a simulated one or
    another automation system.
    """
    try:
        if msg.get('remove'):
            result = await service.async_forget_sender(hass, msg['gateway_id'], msg['address'],
                                                      msg['sender_id'])
        else:
            result = await service.async_teach_in(hass, msg['gateway_id'], msg['address'],
                                                 msg['sender_id'], msg.get('sender_eep'),
                                                 msg.get('name'))
    except (SimulationError, vol.Invalid) as e:
        connection.send_error(msg['id'], 'teach_in_failed', str(e))
        return
    connection.send_result(msg['id'], result)


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required('type'): WS_SIMULATOR_ACTIVATE,
    vol.Required('active'): bool,
})
@websocket_api.async_response
async def ws_simulator_activate(hass: HomeAssistant, connection, msg) -> None:
    """Switch the whole simulation on or off.

    Deactivating takes every simulated device out of Home Assistant (its entities and its device
    disappear) and removes the config entries of the simulated gateways; the simulation itself is
    kept and can still be edited. Activating puts everything back.
    """
    try:
        result = await service.async_set_active(hass, msg['active'])
    except (SimulationError, vol.Invalid) as e:
        connection.send_error(msg['id'], 'activate_failed', str(e))
        return
    connection.send_result(msg['id'], result)
