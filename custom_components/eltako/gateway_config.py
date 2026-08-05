"""Gateways which are created in the user interface instead of `configuration.yaml`.

Until now a gateway had to be declared in `configuration.yaml` *and* be created as a config
entry in Home Assistant - the config flow only offered gateways which were already in the yaml.
This module removes that requirement: a gateway can be created completely in the user
interface, either in the panel of the integration or in the normal Home Assistant dialog
"Add integration".

Gateways created here are stored in the Home Assistant storage and are merged into the
configuration by `config_helpers.async_get_home_assistant_config()`, so every consumer
(config flow, gateway setup, device lookup, web ui) sees one single, complete picture.
A gateway declared in the yaml always wins - same rule as for devices.
"""

from __future__ import annotations

import voluptuous as vol

from homeassistant.const import CONF_DEVICES, CONF_ID, CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.components import websocket_api
from homeassistant.helpers.storage import Store

from .const import *
from . import config_helpers

LOG_PREFIX_GATEWAY_CONFIG = "Gateway Config"

STORAGE_KEY = f"{DOMAIN}_gateways"
STORAGE_VERSION = 1

# fields which are relevant for the different gateway families
FIELDS_SERIAL = [CONF_SERIAL_PATH]
FIELDS_LAN = [CONF_GATEWAY_ADDRESS, CONF_GATEWAY_PORT]


def _store(hass: HomeAssistant) -> Store:
    domain_data = hass.data.setdefault(DATA_ELTAKO, {})
    store = domain_data.get(DATA_GATEWAY_STORE)
    if store is None:
        store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        domain_data[DATA_GATEWAY_STORE] = store
    return store


def get_ui_gateways(hass: HomeAssistant) -> list[dict]:
    """Gateways which were created in the user interface."""
    data = getattr(hass, 'data', None)
    if not isinstance(data, dict):
        return []
    return list(data.get(DATA_ELTAKO, {}).get(DATA_UI_GATEWAYS, []) or [])


async def async_load_ui_gateways(hass: HomeAssistant) -> list[dict]:
    """Load the gateways of the user interface. Must run before the configuration is read."""
    stored = await _store(hass).async_load()
    gateways = []
    if stored and isinstance(stored.get('gateways'), list):
        for gateway in stored['gateways']:
            try:
                gateways.append(validate_gateway(gateway))
            except vol.Invalid as e:
                LOGGER.warning(f"[{LOG_PREFIX_GATEWAY_CONFIG}] Ignoring stored gateway {gateway}: {e}")

    hass.data.setdefault(DATA_ELTAKO, {})[DATA_UI_GATEWAYS] = gateways
    if gateways:
        LOGGER.info(f"[{LOG_PREFIX_GATEWAY_CONFIG}] {len(gateways)} gateway(s) from the user interface: "
                    f"{', '.join(str(gateway[CONF_ID]) for gateway in gateways)}")
    return gateways


async def _async_save(hass: HomeAssistant, gateways: list[dict]) -> None:
    hass.data.setdefault(DATA_ELTAKO, {})[DATA_UI_GATEWAYS] = gateways
    await _store(hass).async_save({'gateways': gateways})
    await async_refresh_config(hass)


async def async_refresh_config(hass: HomeAssistant) -> dict:
    """Re-read the configuration so that the cached one matches the ui gateways again.

    The configuration in hass.data already contains the merged ui gateways, so it cannot be
    patched incrementally - reading it again is the only way to stay consistent.
    """
    from .schema import CONFIG_SCHEMA

    try:
        config = await config_helpers.async_get_home_assistant_config(hass, CONFIG_SCHEMA)
    except Exception as e:  # noqa: BLE001
        LOGGER.warning(f"[{LOG_PREFIX_GATEWAY_CONFIG}] Cannot re-read the configuration: {e}")
        return hass.data.get(DATA_ELTAKO, {}).get(ELTAKO_CONFIG, {})

    config_helpers.remove_duplicate_devices(config, log=False)
    hass.data.setdefault(DATA_ELTAKO, {})[ELTAKO_CONFIG] = config
    return config


def validate_gateway(gateway: dict) -> dict:
    """Validate a gateway with the same schema as the yaml. Raises vol.Invalid."""
    from .schema import GatewaySchema

    cleaned = {key: value for key, value in (gateway or {}).items()
               if value is not None and value != ""}
    cleaned.pop(CONF_DEVICES, None)     # devices are managed separately (device_config.py)

    validated = dict(GatewaySchema.get_schema()(cleaned))

    device_type = GatewayDeviceType.find(str(validated[CONF_DEVICE_TYPE]))
    if device_type is None:
        raise vol.Invalid(f"'{validated[CONF_DEVICE_TYPE]}' is not a supported gateway type.")

    if GatewayDeviceType.is_lan_gateway(device_type) and device_type != GatewayDeviceType.VirtualNetworkAdapter:
        if not validated.get(CONF_GATEWAY_ADDRESS):
            raise vol.Invalid(f"A LAN gateway needs the field '{CONF_GATEWAY_ADDRESS}' (host name or ip address).")
    elif not validated.get(CONF_SERIAL_PATH):
        raise vol.Invalid(f"A serial gateway needs the field '{CONF_SERIAL_PATH}' (e.g. /dev/ttyUSB0).")

    return validated


def get_serial_path(gateway: dict) -> str:
    """The 'serial path' a config entry is created with. LAN gateways use their address."""
    if gateway.get(CONF_SERIAL_PATH):
        return str(gateway[CONF_SERIAL_PATH])
    return str(gateway.get(CONF_GATEWAY_ADDRESS) or "")


def get_description(gateway: dict) -> str:
    """The description a config entry is identified by, e.g. 'FAM14 - fam14 (Id: 1)'."""
    return config_helpers.get_gateway_name(gateway.get(CONF_NAME), str(gateway[CONF_DEVICE_TYPE]),
                                           gateway[CONF_ID])


def get_next_free_id(hass: HomeAssistant, config: dict = None) -> int:
    """Smallest gateway id which is not used yet."""
    used = set()
    for gateway in (config or {}).get(CONF_GATEWAY, []) or []:
        try:
            used.add(int(gateway[CONF_ID]))
        except (KeyError, TypeError, ValueError):
            continue
    for gateway in get_ui_gateways(hass):
        used.add(int(gateway[CONF_ID]))

    candidate = 0
    while candidate in used:
        candidate += 1
    return candidate


def merge_gateways(yaml_gateways: list[dict], ui_gateways: list[dict]) -> list[dict]:
    """Merge both sources. A gateway of the yaml wins over one with the same id."""
    merged = list(yaml_gateways or [])
    declared = {str(gateway.get(CONF_ID)) for gateway in merged}

    for gateway in ui_gateways or []:
        if str(gateway.get(CONF_ID)) in declared:
            LOGGER.warning(f"[{LOG_PREFIX_GATEWAY_CONFIG}] Gateway id {gateway.get(CONF_ID)} exists in "
                           f"configuration.yaml and in the user interface. The yaml declaration is used.")
            continue
        merged.append(gateway)
        declared.add(str(gateway.get(CONF_ID)))

    return merged


async def async_add_gateway(hass: HomeAssistant, gateway: dict) -> dict:
    """Validate and store a new gateway. Returns the validated gateway."""
    validated = validate_gateway(gateway)

    config = hass.data.get(DATA_ELTAKO, {}).get(ELTAKO_CONFIG, {}) or {}
    for existing in (config.get(CONF_GATEWAY, []) or []):
        if str(existing.get(CONF_ID)) == str(validated[CONF_ID]):
            raise vol.Invalid(f"Gateway id {validated[CONF_ID]} is already used. "
                              f"Please choose a different id.")

    gateways = get_ui_gateways(hass)
    gateways.append(validated)
    await _async_save(hass, gateways)

    LOGGER.info(f"[{LOG_PREFIX_GATEWAY_CONFIG}] Added gateway '{get_description(validated)}' "
                f"({get_serial_path(validated)}) via user interface.")
    return validated


async def async_update_gateway_base_id(hass: HomeAssistant, gateway_id: int, base_id: str) -> bool:
    """Persist the base id a gateway reported about itself.

    Gateways query their base id from the hardware right after the connection is
    established (gateway.query_for_base_id_and_version). For gateways created in the user
    interface that value is written back into the store, so nobody has to know the base id
    upfront when adding a gateway.
    """
    if not base_id or base_id.upper() in ('00-00-00-00', 'FF-FF-FF-FF'):
        return False        # nothing was reported (yet)

    gateways = get_ui_gateways(hass)
    for gateway in gateways:
        if int(gateway.get(CONF_ID, -1)) != int(gateway_id):
            continue
        if str(gateway.get(CONF_BASE_ID) or '').upper() == base_id.upper():
            return False
        gateway[CONF_BASE_ID] = base_id.upper()
        await _async_save(hass, gateways)
        LOGGER.info(f"[{LOG_PREFIX_GATEWAY_CONFIG}] Gateway {gateway_id} reported base id {base_id} - "
                    f"stored in its configuration.")
        return True
    return False


### fields a gateway of the user interface can be edited with. The id is missing on purpose:
### it is part of the description a config entry is identified by and of every entity id of
### the gateway, so changing it would orphan all devices and entities of that gateway.
EDITABLE_FIELDS = [CONF_NAME, CONF_DEVICE_TYPE, CONF_BASE_ID, CONF_SERIAL_PATH,
                   CONF_GATEWAY_ADDRESS, CONF_GATEWAY_PORT, CONF_GATEWAY_AUTO_RECONNECT,
                   CONF_GATEWAY_MESSAGE_DELAY]


async def async_update_gateway(hass: HomeAssistant, gateway_id: int, changes: dict) -> dict:
    """Change the attributes of a gateway which was created in the user interface.

    Only the fields of EDITABLE_FIELDS are taken over, everything else keeps its stored
    value. A gateway declared in `configuration.yaml` is not editable here - it wins over the
    ui anyway, so an override would silently do nothing.

    Returns the validated gateway. The caller (`ws_gateway_update`) keeps the config entry in
    sync and reloads it, so the change is live without a restart.
    """
    gateways = get_ui_gateways(hass)
    index = next((i for i, gateway in enumerate(gateways)
                  if int(gateway.get(CONF_ID, -1)) == int(gateway_id)), None)
    if index is None:
        config = hass.data.get(DATA_ELTAKO, {}).get(ELTAKO_CONFIG, {}) or {}
        if any(str(gateway.get(CONF_ID)) == str(gateway_id) for gateway in (config.get(CONF_GATEWAY) or [])):
            raise vol.Invalid(f"Gateway {gateway_id} is declared in your configuration.yaml. "
                              f"Please edit it there.")
        raise vol.Invalid(f"No gateway with id {gateway_id} was created in the user interface.")

    updated = dict(gateways[index])
    for field in EDITABLE_FIELDS:
        if field in changes:
            updated[field] = changes[field]

    # a serial gateway has no address and a LAN gateway no serial port - the fields of the
    # other family are dropped so that a type change cannot leave a stale connection behind
    device_type = GatewayDeviceType.find(str(updated.get(CONF_DEVICE_TYPE, '')))
    if device_type is not None and GatewayDeviceType.is_lan_gateway(device_type):
        updated.pop(CONF_SERIAL_PATH, None)
    else:
        updated.pop(CONF_GATEWAY_ADDRESS, None)

    updated[CONF_ID] = int(gateway_id)
    validated = validate_gateway(updated)

    gateways[index] = validated
    await _async_save(hass, gateways)

    LOGGER.info(f"[{LOG_PREFIX_GATEWAY_CONFIG}] Updated gateway '{get_description(validated)}' "
                f"({get_serial_path(validated)}) via user interface.")
    return validated


def find_config_entry(hass: HomeAssistant, gateway_id: int):
    """Config entry of a gateway, identified by the id inside its description."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        try:
            if config_helpers.get_id_from_gateway_name(entry.data[CONF_GATEWAY_DESCRIPTION]) == int(gateway_id):
                return entry
        except Exception:   # noqa: BLE001 - an entry without a usable description
            continue
    return None


async def async_apply_to_config_entry(hass: HomeAssistant, gateway: dict) -> dict:
    """Write description and connection of a changed gateway into its config entry.

    The entry carries the description and the serial path (see async_setup_entry), so a
    renamed or re-plugged gateway has to be updated there as well. Updating the entry
    triggers the update listener which reloads the gateway; if nothing in the entry changed,
    the reload is requested explicitly - the rest of the configuration lives in the store and
    is only read while setting up.
    """
    entry = find_config_entry(hass, int(gateway[CONF_ID]))
    if entry is None:
        return {'config_entry_updated': False, 'reloaded': False}

    data = dict(entry.data)
    data[CONF_GATEWAY_DESCRIPTION] = get_description(gateway)
    data[CONF_SERIAL_PATH] = get_serial_path(gateway)

    if data != dict(entry.data):
        hass.config_entries.async_update_entry(entry, data=data)
        return {'config_entry_updated': True, 'reloaded': True}

    await hass.config_entries.async_reload(entry.entry_id)
    return {'config_entry_updated': False, 'reloaded': True}


async def async_remove_gateway(hass: HomeAssistant, gateway_id: int) -> bool:
    """Remove a gateway of the user interface (its config entry has to be removed separately)."""
    gateways = get_ui_gateways(hass)
    remaining = [gateway for gateway in gateways if int(gateway[CONF_ID]) != int(gateway_id)]
    if len(remaining) == len(gateways):
        return False

    await _async_save(hass, remaining)
    LOGGER.info(f"[{LOG_PREFIX_GATEWAY_CONFIG}] Removed gateway {gateway_id} from the user interface.")
    return True


### ---------------------------------------------------------------------------
### descriptor for the web ui / config flow
### ---------------------------------------------------------------------------

def get_gateway_type_descriptors() -> list[dict]:
    """All supported gateway types incl. the fields they need."""
    from .const import BAUD_RATE_DEVICE_TYPE_MAPPING

    seen = {}
    for device_type in GatewayDeviceType:
        if device_type.value in seen:
            continue
        is_lan = GatewayDeviceType.is_lan_gateway(device_type)
        baud_rate = BAUD_RATE_DEVICE_TYPE_MAPPING.get(device_type, -1)
        seen[device_type.value] = {
            'device_type': device_type.value,
            'protocol': 'ESP2' if GatewayDeviceType.is_esp2_gateway(device_type) else 'ESP3',
            'is_lan': is_lan,
            'is_bus_gateway': GatewayDeviceType.is_bus_gateway(device_type),
            'is_transceiver': GatewayDeviceType.is_transceiver(device_type),
            'baud_rate': baud_rate if baud_rate > 0 else None,
            'fields': FIELDS_LAN if is_lan else FIELDS_SERIAL,
        }
    return list(seen.values())


def get_form_descriptor(hass: HomeAssistant) -> dict:
    """Everything the web ui needs to render the 'add gateway' wizard."""
    # the full scan knows which port is already used by a gateway ('free' flag)
    from .gateway_scan import scan as scan_ports

    config = hass.data.get(DATA_ELTAKO, {}).get(ELTAKO_CONFIG, {}) or {}
    ui_ids = {int(gateway[CONF_ID]) for gateway in get_ui_gateways(hass)}

    gateways = []
    for gateway in (config.get(CONF_GATEWAY, []) or []):
        from_ui = int(gateway.get(CONF_ID, -1)) in ui_ids
        gateways.append({
            'id': gateway.get(CONF_ID),
            'name': gateway.get(CONF_NAME) or "",
            'device_type': str(gateway.get(CONF_DEVICE_TYPE)),
            'base_id': gateway.get(CONF_BASE_ID),
            'serial_path': gateway.get(CONF_SERIAL_PATH),
            'address': gateway.get(CONF_GATEWAY_ADDRESS),
            'port': gateway.get(CONF_GATEWAY_PORT),
            'auto_reconnect': gateway.get(CONF_GATEWAY_AUTO_RECONNECT, True),
            'message_delay': gateway.get(CONF_GATEWAY_MESSAGE_DELAY),
            'source': 'ui' if from_ui else 'yaml',
            # only a gateway of the user interface can be changed here, see async_update_gateway
            'editable': from_ui,
            'description': get_description(gateway) if gateway.get(CONF_DEVICE_TYPE) else None,
        })

    return {
        'gateways': gateways,
        'types': get_gateway_type_descriptors(),
        'next_free_id': get_next_free_id(hass, config),
        'ports': [{'device': port['device'], 'name': port.get('name'),
                   'free': port.get('free', True), 'by_id': port.get('by_id'),
                   'suggested_device_types': port.get('suggested_device_types', [])}
                  for port in scan_ports(hass)['ports']],
        'default_base_id': '00-00-00-00',
        'editable_fields': list(EDITABLE_FIELDS),
        'hint': "A FAM14 and ESP3 gateways (e.g. USB300) report their base id automatically after "
                "connecting - simply leave 00-00-00-00, it is stored here as soon as it is known. "
                "For a FAM-USB enter the base id printed on the device, for a FGW14-USB the base "
                "id of its FAM14.",
    }


### ---------------------------------------------------------------------------
### websocket api
### ---------------------------------------------------------------------------

def register_websocket_commands(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, ws_gateway_form)
    websocket_api.async_register_command(hass, ws_gateway_add)
    websocket_api.async_register_command(hass, ws_gateway_update)
    websocket_api.async_register_command(hass, ws_gateway_remove)


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required('type'): WS_GATEWAY_FORM})
@websocket_api.async_response
async def ws_gateway_form(hass: HomeAssistant, connection, msg) -> None:
    descriptor = await hass.async_add_executor_job(get_form_descriptor, hass)
    connection.send_result(msg['id'], descriptor)


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required('type'): WS_GATEWAY_ADD,
    vol.Required('gateway'): dict,
})
@websocket_api.async_response
async def ws_gateway_add(hass: HomeAssistant, connection, msg) -> None:
    """Store the gateway and create its config entry, so it is set up right away."""
    try:
        validated = await async_add_gateway(hass, msg['gateway'])
    except vol.Invalid as e:
        connection.send_error(msg['id'], 'invalid_gateway', str(e))
        return

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={'source': SOURCE_UI_GATEWAY},
        data={
            CONF_GATEWAY_DESCRIPTION: get_description(validated),
            CONF_SERIAL_PATH: get_serial_path(validated),
        },
    )

    connection.send_result(msg['id'], {
        'gateway': {str(key): str(value) for key, value in validated.items()},
        'config_entry_created': result.get('type') == 'create_entry',
        'flow_result': result.get('type'),
        'reason': result.get('reason'),
    })


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required('type'): WS_GATEWAY_UPDATE,
    vol.Required('gateway_id'): vol.Coerce(int),
    vol.Required('gateway'): dict,
})
@websocket_api.async_response
async def ws_gateway_update(hass: HomeAssistant, connection, msg) -> None:
    """Change the attributes of a gateway of the user interface and apply them live."""
    try:
        validated = await async_update_gateway(hass, msg['gateway_id'], msg['gateway'])
    except vol.Invalid as e:
        connection.send_error(msg['id'], 'invalid_gateway', str(e))
        return

    applied = await async_apply_to_config_entry(hass, validated)
    connection.send_result(msg['id'], {
        'gateway': {str(key): str(value) for key, value in validated.items()},
        **applied,
    })


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required('type'): WS_GATEWAY_REMOVE,
    vol.Required('gateway_id'): vol.Coerce(int),
})
@websocket_api.async_response
async def ws_gateway_remove(hass: HomeAssistant, connection, msg) -> None:
    """Remove the gateway and its config entry."""
    gateway_id = msg['gateway_id']

    removed_entries = 0
    for entry in list(hass.config_entries.async_entries(DOMAIN)):
        try:
            entry_id = config_helpers.get_id_from_gateway_name(entry.data[CONF_GATEWAY_DESCRIPTION])
        except Exception:   # noqa: BLE001
            continue
        if entry_id == gateway_id:
            await hass.config_entries.async_remove(entry.entry_id)
            removed_entries += 1

    removed = await async_remove_gateway(hass, gateway_id)
    connection.send_result(msg['id'], {'removed': removed, 'removed_config_entries': removed_entries})
