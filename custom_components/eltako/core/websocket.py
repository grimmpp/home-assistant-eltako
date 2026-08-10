"""Websocket api of the Eltako integration. It is used by the web ui (folder 'frontend')."""

import inspect
import json
import os
import re

import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.components import websocket_api
from homeassistant.const import __version__ as HA_VERSION
from homeassistant.helpers import area_registry as ar, device_registry as dr, entity_registry as er

from eltakobus.util import b2s

from ..const import (DATA_ELTAKO, DOMAIN, INTEGRATION_DIR, LOGGER, WS_ACTIVITY, WS_HELP_CATALOG,
                     WS_INTEGRATION_INFO, WS_SEND_TELEGRAM, WS_SEND_TELEGRAM_FORM, is_prerelease)
from .gateway import detect, EnOceanGateway


async def register_websockets(hass: HomeAssistant, config: ConfigEntry):
    websocket_api.async_register_command(hass, ws_info)
    websocket_api.async_register_command(hass, ws_usb_ports)
    websocket_api.async_register_command(hass, ws_configured_gateways)
    websocket_api.async_register_command(hass, ws_integration_info)
    websocket_api.async_register_command(hass, ws_activity)
    websocket_api.async_register_command(hass, ws_help_catalog)
    websocket_api.async_register_command(hass, ws_send_telegram_form)
    websocket_api.async_register_command(hass, ws_send_telegram)


def _get_manifest_info():
    try:
        with open(os.path.join(INTEGRATION_DIR, "manifest.json"), "r") as file:
            response = json.load(file)
            # LOGGER.info(f"info response: {response}")
    except Exception:   # noqa: BLE001 - an unreadable manifest must not break the api
        LOGGER.error("Cannot read manifest.json", exc_info=True, stack_info=True)
        response = {}

    return response

def get_gateways(hass: HomeAssistant) -> list[EnOceanGateway]:
    """All gateway objects of the integration.

    The gateways are stored as "gateway_<id>" in hass.data, but other data lives there too,
    so the type is checked instead of guessing by the name of the key.
    """
    return [value for value in (hass.data.get(DATA_ELTAKO, {}) or {}).values()
            if isinstance(value, EnOceanGateway)]


def _get_configured_gateways(hass: HomeAssistant):
    result = []
    for gw in get_gateways(hass):
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
            "ha_device_id": _get_gateway_ha_device_id(hass, gw),
            # a gateway without hardware: its devices are simulated in this process. Every list
            # of the web ui marks it (see simulation/).
            "simulated": bool(getattr(gw, 'is_simulated', False)),
        })
    return sorted(result, key=lambda gateway: gateway["id"])


def _get_gateways_without_entry(hass: HomeAssistant) -> list[dict]:
    """Stored gateways Home Assistant never set up. Never fails the whole info response."""
    try:
        from ..config.gateway_config import get_gateways_without_entry

        return get_gateways_without_entry(hass)
    except Exception as e:      # noqa: BLE001 - an extra list is not worth the overview page
        LOGGER.debug(f"Cannot determine the gateways without a config entry: {e}")
        return []


def _gateway_type(gateway: EnOceanGateway) -> str:
    dev_type = gateway.dev_type
    return getattr(dev_type, 'value', str(dev_type))


def _get_gateway_ha_device_id(hass: HomeAssistant, gateway: EnOceanGateway) -> str | None:
    """Device id of the gateway in the Home Assistant device registry.

    Gateways register their device with identifiers={(DOMAIN, serial_path)}, see
    gateway._register_device().
    """
    try:
        device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, gateway.serial_path)})
        return device.id if device else None
    except Exception:   # noqa: BLE001 - registry not available (e.g. in tests)
        return None


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


### sending arbitrary telegrams ------------------------------------------------------------

def _is_sendable(eep: str, defaults: dict) -> bool:
    """Whether a telegram of this profile can be built at all.

    Not every EEP of the library can be encoded - a few are decode-only (`A5-09-0C`, the air
    quality profile of the FLGTF, raises "NOT IMPLEMENTED"). A form which can only fail is
    worse than none, so the web ui leaves those out instead of offering a send button.
    """
    try:
        build_eep_telegram('FF-AA-80-01', eep, defaults)
        return True
    except Exception:   # noqa: BLE001 - whatever the library complains about: it cannot be sent
        return False


def get_eep_descriptors() -> list[dict]:
    """All EEPs of the eltakobus library with the fields of their constructor.

    The web ui builds the input fields of the send form from this list - the free form on the
    telegram page as well as the send fields of every device on the control page. `defaults`
    holds a usable start value per field (the same ones a simulated device starts with), so an
    opened form is filled with a telegram which can be sent as it is instead of a row of zeros
    - and 0 is not a valid state for every profile.
    """
    from eltakobus.eep import EEP

    from ..config.device_config import describe_eep
    from ..simulation.core import conditional_fields, default_state, describe_fields

    result = []
    def walk(cls):
        for sub in cls.__subclasses__():
            eep_string = getattr(sub, 'eep_string', None)
            if eep_string:
                fields = CENTRAL_COMMAND_FIELDS if eep_string == 'A5-38-08' else \
                    [param.name for param in inspect.signature(sub.__init__).parameters.values()
                     if param.name != 'self' and param.kind == param.POSITIONAL_OR_KEYWORD]
                defaults = default_state(eep_string)
                result.append({'eep': eep_string, 'fields': list(fields),
                               'defaults': defaults,
                               # what the values mean: named options, units, ranges - the form
                               # offers a dropdown instead of a number nobody can guess
                               'field_info': describe_fields(eep_string, list(fields), sub),
                               'conditional': conditional_fields(eep_string),
                               'sendable': _is_sendable(eep_string, defaults),
                               'description': describe_eep(eep_string)})
            walk(sub)
    walk(EEP)
    return sorted(result, key=lambda descriptor: descriptor['eep'])


# A5-38-08 (central command) takes nested objects in its constructor - the form offers the
# flat fields of both variants instead: command 1 switches, command 2 dims. The list lives in
# the simulation core, which encodes those telegrams (see build_eep_telegram below).
from ..simulation.core import CENTRAL_COMMAND_FIELDS      # noqa: E402,F401


def parse_raw_esp2(raw: str):
    """An arbitrary ESP2 telegram from a hex string.

    Accepts the 11 body bytes or the full 14 byte frame (a5 5a + body + checksum, the
    checksum is validated then). Whitespace and separators are ignored.
    """
    from eltakobus.message import ESP2Message

    data = bytes.fromhex(re.sub(r'[^0-9A-Fa-f]', '', raw or ''))
    if len(data) == 14:
        return ESP2Message.parse(data)
    if len(data) == 11:
        return ESP2Message(data)
    raise ValueError(f"An ESP2 telegram has 11 body bytes or 14 frame bytes "
                     f"(A5 5A + body + checksum) - got {len(data)} bytes.")


def build_eep_telegram(sender_id: str, eep: str, fields: dict):
    """A telegram built from an EEP and its field values (like the send_message service).

    The encoder itself lives in the simulation core (`simulation/core/telegrams.py`): a hand
    written telegram of this form and a telegram of a simulated device are then built by exactly
    the same code, so what the form sends is what the simulation would send.
    """
    from ..simulation.core import encode_eep_telegram

    return encode_eep_telegram(sender_id, eep, fields)


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required('type'): WS_SEND_TELEGRAM_FORM})
@websocket_api.async_response
async def ws_send_telegram_form(hass: HomeAssistant, connection, msg):
    connection.send_result(msg['id'], {
        'gateways': _get_configured_gateways(hass),
        'eeps': get_eep_descriptors(),
    })


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required('type'): WS_SEND_TELEGRAM,
    vol.Required('gateway_id'): vol.Coerce(int),
    vol.Optional('raw'): str,
    vol.Optional('sender_id'): str,
    vol.Optional('eep'): str,
    vol.Optional('fields'): dict,
})
@websocket_api.async_response
async def ws_send_telegram(hass: HomeAssistant, connection, msg):
    """Send an arbitrary EnOcean telegram through one of the gateways.

    Either as raw ESP2 hex (completely arbitrary) or built from an EEP with its field
    values - the same way the send_message service of the gateways works.
    """
    gateway = next((gw for gw in get_gateways(hass) if gw.dev_id == msg['gateway_id']), None)
    if gateway is None:
        connection.send_error(msg['id'], 'unknown_gateway', f"No gateway with id {msg['gateway_id']}")
        return

    try:
        if msg.get('raw'):
            telegram = parse_raw_esp2(msg['raw'])
        elif msg.get('eep') and msg.get('sender_id'):
            telegram = build_eep_telegram(msg['sender_id'], msg['eep'], msg.get('fields'))
        else:
            raise ValueError("Either 'raw' or 'sender_id' + 'eep' must be given.")
        gateway.send_message(telegram)
    except Exception as e:  # noqa: BLE001 - the message of the library explains the problem
        connection.send_error(msg['id'], 'send_failed', str(e))
        return

    LOGGER.info(f"[Websocket] Sent telegram via gateway {gateway.dev_id}: {telegram}")
    connection.send_result(msg['id'], {'sent': True, 'telegram': str(telegram),
                                       'hex': telegram.serialize().hex()})


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required('type'): WS_HELP_CATALOG})
@websocket_api.async_response
async def ws_help_catalog(hass: HomeAssistant, connection, msg):
    """Everything the help page lists: devices, EEPs, gateways, platforms, documentation.

    Compiled from the catalog, the schemas and the docs directory - see help_catalog.py. The
    docs part touches the filesystem, so the whole build runs in the executor.
    """
    from ..catalog import help_catalog

    catalog = await hass.async_add_executor_job(help_catalog.build_catalog)
    connection.send_result(msg['id'], catalog)


### ---------------------------------------------------------------------------
### what runs right now
### ---------------------------------------------------------------------------

def get_activity(hass: HomeAssistant) -> dict:
    """Everything the integration is busy with right now, in one answer.

    The long operations of this integration are not instant and not invisible: reading the
    memory of a bus takes minutes and locks the bus while it runs, so the devices on it do not
    react and every other bus operation is refused. Without a single place which says what is
    running, a user presses a button, nothing happens, and there is no way to tell a slow
    operation from a broken one.

    So the web ui polls this on **every** page and shows it as a banner. Deliberately cheap:
    no io and no locks, only the state which is kept anyway (the plug & play state, the bus
    lock of every gateway and the counters of the running scans).

    Returns `{'busy': bool, 'jobs': [...]}`; a job carries what it is (`kind`), how far it is
    (`progress`) and what it blocks (`blocks`), the wording is up to the web ui.
    """
    from ..observation import bus_members
    from ..tools import plug_and_play

    jobs = []

    detection = plug_and_play.get_state(hass)
    if detection.get('running'):
        jobs.append({
            'kind': 'detection',
            'step': detection.get('step'),
            'stage': detection.get('stage'),
            'started_at': detection.get('started_at'),
            # devices are added while the scan runs, not at its end - so this counter grows
            # during the run and is what makes the progress tangible
            'added': len(((detection.get('last_report') or {}).get('devices_added')) or []),
            # a second detection is refused, and it reads the buses itself
            'blocks': ['detection', 'bus'],
        })

    progress = {int(entry['gateway_id']): entry for entry in bus_members.get_scan_progress()
                if entry.get('gateway_id') is not None}
    for gateway in get_gateways(hass):
        try:
            if not gateway.is_bus_busy:
                continue
            reason = gateway.bus_busy_reason
        except Exception:   # noqa: BLE001 - a gateway which is not initialized is not busy
            continue
        scan = progress.get(gateway.dev_id)
        jobs.append({
            'kind': 'bus',
            'gateway_id': gateway.dev_id,
            'gateway_name': gateway.dev_name,
            # 'bus scan', 'teach in', 'base id request', ... - what took the bus
            'reason': reason,
            'progress': scan,
            'started_at': (scan or {}).get('started_at'),
            'blocks': ['bus', f"gateway:{gateway.dev_id}"],
        })

    return {'busy': bool(jobs), 'jobs': jobs}


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required('type'): WS_ACTIVITY})
@websocket_api.async_response
async def ws_activity(hass: HomeAssistant, connection, msg):
    """What is running right now - polled by the web ui on every page."""
    connection.send_result(msg['id'], get_activity(hass))


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required('type'): WS_INTEGRATION_INFO})
@websocket_api.async_response
async def ws_integration_info(hass: HomeAssistant, connection, msg):
    """Everything the 'about' and 'overview' pages of the web ui need."""
    from ..config import config_helpers
    from ..observation.enocean_logger import is_telegram_logging_enabled

    manifest = await hass.async_add_executor_job(_get_manifest_info)
    general_settings = config_helpers.get_general_settings_from_configuration(hass)

    response = {
        "domain": DOMAIN,
        "name": manifest.get("name", "Eltako"),
        "version": manifest.get("version"),
        # a release candidate / beta must be recognizable inside the running
        # integration, not only in the release notes on github
        "prerelease": is_prerelease(manifest.get("version")),
        "documentation": manifest.get("documentation"),
        "issue_tracker": manifest.get("issue_tracker"),
        "codeowners": manifest.get("codeowners", []),
        "iot_class": manifest.get("iot_class"),
        "requirements": manifest.get("requirements", []),
        "home_assistant_version": HA_VERSION,
        "general_settings": {str(k): v for k, v in general_settings.items()},
        "telegram_logging_enabled": is_telegram_logging_enabled(general_settings),
        "gateways": _get_configured_gateways(hass),
        # configured in the web ui but without a config entry, so Home Assistant never built
        # them - they are in no other list and would be invisible without this one
        "gateways_not_set_up": _get_gateways_without_entry(hass),
        "entities": _get_entity_summary(hass),
    }

    connection.send_result(msg['id'], response)
