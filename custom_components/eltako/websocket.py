"""Websocket api of the Eltako integration. It is used by the web ui (folder 'frontend')."""

import json
import os

import voluptuous as vol

from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.components import websocket_api
from homeassistant.const import __version__ as HA_VERSION
from homeassistant.helpers import area_registry as ar, device_registry as dr, entity_registry as er

from eltakobus.util import b2s

from .const import *
from .gateway import detect, EnOceanGateway


async def register_websockets(hass: HomeAssistant, config: ConfigEntry):
    websocket_api.async_register_command(hass, ws_info)
    websocket_api.async_register_command(hass, ws_usb_ports)
    websocket_api.async_register_command(hass, ws_configured_gateways)
    websocket_api.async_register_command(hass, ws_integration_info)


def _get_manifest_info():
    try:
        dir_path = os.path.dirname(__file__)
        with open(os.path.join(dir_path, "manifest.json"), "r") as file:
            response = json.load(file)
            # LOGGER.info(f"info response: {response}")
    except Exception as e:
        LOGGER.error("Cannot read manifest.json", exc_info=True, stack_info=True)
        response = {}

    return response

def _get_configured_gateways(hass: HomeAssistant):
    result = []
    for k in hass.data[DATA_ELTAKO]:
        if k.startswith('gateway'):
            gw:EnOceanGateway = hass.data[DATA_ELTAKO][k]
            result.append({
                "name": gw.dev_name,
                "id": gw.dev_id,
                "type": _gateway_type(gw),
                "config_entry_id": gw.config_entry_id,
                "unique_id": gw.unique_id,
                "baud_rate": gw.baud_rate,
                "serial_path": gw.serial_path,
                "base_id": b2s(gw.base_id),
                "model": gw.model,
                "auto_reconnect": gw.is_auto_reconnect_enabled,
                "message_delay": gw.message_delay,
                "native_protocol": gw.native_protocol,
                "connected": _is_gateway_connected(gw),
            })
    return result


def _gateway_type(gateway: EnOceanGateway) -> str:
    dev_type = gateway.dev_type
    return getattr(dev_type, 'value', str(dev_type))


def _is_gateway_connected(gateway: EnOceanGateway) -> bool | None:
    """Connection state of the serial/tcp connection of the gateway."""
    try:
        return bool(gateway._bus.is_active())
    except Exception:   # noqa: BLE001 - gateway might not be fully initialized
        return None


def _get_entity_summary(hass: HomeAssistant) -> dict:
    """Number of devices and entities of this integration grouped by platform."""
    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)
    area_registry = ar.async_get(hass)

    count_by_platform: dict[str, int] = {}
    areas: set[str] = set()
    entity_count = 0

    for entity in entity_registry.entities.values():
        if entity.platform != DOMAIN:
            continue
        entity_count += 1
        count_by_platform[entity.domain] = count_by_platform.get(entity.domain, 0) + 1

    device_count = 0
    for device in device_registry.devices.values():
        if not any(identifier[0] == DOMAIN for identifier in device.identifiers):
            continue
        device_count += 1
        if device.area_id:
            area = area_registry.async_get_area(device.area_id)
            if area:
                areas.add(area.name)

    return {
        "entity_count": entity_count,
        "device_count": device_count,
        "count_by_platform": dict(sorted(count_by_platform.items())),
        "areas": sorted(areas),
    }


@websocket_api.websocket_command({
    'type': 'eltako/info',
    'required': []
})
@websocket_api.async_response
async def ws_info(hass: HomeAssistant, connection, msg):

    # LOGGER.debug("Call WS eltako/info")

    response = await hass.async_add_executor_job(_get_manifest_info)

    # Send the response back
    connection.send_message(websocket_api.result_message(msg['id'], response))


@websocket_api.websocket_command({
    'type': 'eltako/potential_usb_ports',
    'required': []
})
@websocket_api.async_response
async def ws_usb_ports(hass: HomeAssistant, connection, msg):

    response = await hass.async_add_executor_job(detect)

    # Send the response back
    connection.send_message(websocket_api.result_message(msg['id'], response))


@websocket_api.websocket_command({
    'type': 'eltako/configured_gateways',
    'required': []
})
@websocket_api.async_response
async def ws_configured_gateways(hass: HomeAssistant, connection, msg):

    response = _get_configured_gateways(hass)

    # Send the response back
    connection.send_message(websocket_api.result_message(msg['id'], response))


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required('type'): WS_INTEGRATION_INFO})
@websocket_api.async_response
async def ws_integration_info(hass: HomeAssistant, connection, msg):
    """Everything the 'about' and 'overview' pages of the web ui need."""
    from . import config_helpers
    from .enocean_logger import is_telegram_logging_enabled

    manifest = await hass.async_add_executor_job(_get_manifest_info)
    general_settings = config_helpers.get_general_settings_from_configuration(hass)

    response = {
        "domain": DOMAIN,
        "name": manifest.get("name", "Eltako"),
        "version": manifest.get("version"),
        "documentation": manifest.get("documentation"),
        "issue_tracker": manifest.get("issue_tracker"),
        "codeowners": manifest.get("codeowners", []),
        "iot_class": manifest.get("iot_class"),
        "requirements": manifest.get("requirements", []),
        "home_assistant_version": HA_VERSION,
        "general_settings": {str(k): v for k, v in general_settings.items()},
        "telegram_logging_enabled": is_telegram_logging_enabled(general_settings),
        "gateways": _get_configured_gateways(hass),
        "entities": _get_entity_summary(hass),
    }

    connection.send_result(msg['id'], response)
