"""Device configuration from two sources: configuration.yaml and the web ui.

Devices can be declared in `configuration.yaml` (as before) and additionally be created
through the web ui. Devices created in the ui are stored in the options of the config entry
of their gateway, so they survive restarts and can be edited or removed again.

Both sources are validated with the **same** voluptuous schemas (schema.py) and are merged
by `get_merged_device_config()`. The yaml declaration always wins: it is the documented and
version-controlled source, and a ui device must never silently shadow it.

The module also derives the form descriptors for the ui from the schemas, so the fields
offered in the web ui stay in sync with what the integration actually supports.
"""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DEVICE_CLASS, CONF_DEVICES, CONF_ID, CONF_NAME, CONF_TEMPERATURE_UNIT, Platform, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.components import websocket_api

from eltakobus.util import AddressExpression

from .const import *
from . import config_helpers
from .schema import (
    BinarySensorSchema,
    ClimateSchema,
    CoverSchema,
    LightSchema,
    SensorSchema,
    SwitchSchema,
)

LOG_PREFIX_DEVICE_CONFIG = "Device Config"

# platforms for which devices can be created through the web ui
SUPPORTED_PLATFORMS: dict[str, type] = {
    Platform.BINARY_SENSOR.value: BinarySensorSchema,
    Platform.SENSOR.value: SensorSchema,
    Platform.LIGHT.value: LightSchema,
    Platform.SWITCH.value: SwitchSchema,
    Platform.COVER.value: CoverSchema,
    Platform.CLIMATE.value: ClimateSchema,
}

# fields which are offered per platform in the web ui. The EEP lists are taken from the
# schemas so that they cannot drift apart from the supported EEPs.
FIELD_ID = {'name': CONF_ID, 'label': 'Address', 'type': 'address', 'required': True,
            'help': "EnOcean address, e.g. FF-AA-80-01. Bus devices use their local address, e.g. 00-00-00-01."}
FIELD_NAME = {'name': CONF_NAME, 'label': 'Name', 'type': 'text', 'required': False}
FIELD_AREA = {'name': CONF_AREA, 'label': 'Area', 'type': 'text', 'required': False,
              'help': "Area of the device in Home Assistant. It is created if it does not exist."}


# Typical Eltako devices per EEP. The description itself comes from the docstring of the EEP
# class of the eltakobus library, this only adds which device usually speaks it.
EEP_DEVICE_HINTS = {
    'F6-01-01': "single button, e.g. FMH1W",
    'F6-02-01': "rocker switch (EU), also FTS14EM contacts",
    'F6-02-02': "rocker switch (US style)",
    'F6-10-00': "window handle / window and door contacts, e.g. FTKE, FFTE",
    'D5-00-01': "contact via FTS14EM, e.g. window contact",
    'A5-04-01': "temperature and humidity",
    'A5-04-02': "temperature and humidity, e.g. FLGTF, FLT58, FFT60",
    'A5-04-03': "temperature and humidity, e.g. FFT60",
    'A5-06-01': "brightness, e.g. weather station",
    'A5-07-01': "occupancy, e.g. FB55EB",
    'A5-08-01': "brightness, temperature and occupancy, e.g. FBH65",
    'A5-09-0C': "air quality / VOC, e.g. FLGTF",
    'A5-10-03': "thermostat, e.g. FTR78S",
    'A5-10-06': "heating and cooling actuator, e.g. FAE14, FHK14, FUTH",
    'A5-10-12': "thermostat with humidity, e.g. FUTH",
    'A5-12-01': "electricity meter, e.g. FWZ12, FSR14M-2x",
    'A5-12-02': "gas meter, e.g. F3Z14D",
    'A5-12-03': "water meter, e.g. F3Z14D",
    'A5-13-01': "weather station, e.g. FWG14",
    'A5-30-01': "digital input with battery status, e.g. FSM60B",
    'A5-30-03': "digital inputs",
    'A5-38-08': "central command - PREFERRED for lights and switches",
    'M5-38-08': "Eltako relay, e.g. FSR14, FSR61",
    'G5-3F-7F': "Eltako cover actuator, e.g. FSB14, FSB61",
    'H5-3F-7F': "Eltako cover command",
}


def describe_eep(eep: str) -> str:
    """Readable description of an EEP: docstring of the library plus the typical device."""
    from eltakobus.eep import EEP

    description = ""
    try:
        docstring = (EEP.find(eep).__doc__ or "").strip()
        description = docstring.split("\n")[0].strip()
        if len(description) > 58:
            description = description[:55].rstrip(" ,(") + "..."
    except Exception:   # noqa: BLE001 - an EEP without class must not break the form
        pass

    hint = EEP_DEVICE_HINTS.get(eep.upper())
    if description and hint:
        return f"{description} ({hint})"
    return description or hint or ""


def _eep_options(eeps: list[str]) -> list[dict]:
    """Options with a label, so the user does not have to know the EEP numbers."""
    options = []
    for eep in sorted(eeps):
        description = describe_eep(eep)
        options.append({'value': eep, 'label': f"{eep} - {description}" if description else eep})
    return options


def _eep_field(eeps: list[str], label: str = 'EEP', required: bool = True, help_text: str = "") -> dict:
    return {'name': CONF_EEP, 'label': label, 'type': 'select', 'required': required,
            'options': _eep_options(eeps), 'help': help_text}


def _sender_field(eeps: list[str], required: bool) -> dict:
    return {
        'name': CONF_SENDER, 'label': 'Sender', 'type': 'group', 'required': required,
        'help': "Address Home Assistant sends commands with. Must be a free address of the base id "
                "range of the gateway and must be registered in the actuator (e.g. with PCT14).",
        'fields': [
            {'name': CONF_ID, 'label': 'Sender address', 'type': 'address', 'required': True},
            _eep_field(eeps, 'Sender EEP'),
        ],
    }


def get_form_descriptor() -> dict:
    """Describe all platforms and their fields so that the web ui can render the forms."""
    return {
        'platforms': [
            {
                'platform': Platform.BINARY_SENSOR.value,
                'label': 'Binary sensor',
                'help': "Rocker switches, window/door contacts, occupancy sensors, ...",
                'fields': [
                    FIELD_ID,
                    _eep_field(BinarySensorSchema.ENTITY_SCHEMA.validators[0].schema[vol.Required(CONF_EEP)].container),
                    FIELD_NAME, FIELD_AREA,
                    {'name': CONF_DEVICE_CLASS, 'label': 'Device class', 'type': 'text', 'required': False,
                     'help': "e.g. window, door, motion, moisture. Changes icon and wording in Home Assistant."},
                    {'name': CONF_INVERT_SIGNAL, 'label': 'Invert signal', 'type': 'boolean', 'required': False,
                     'default': False},
                ],
            },
            {
                'platform': Platform.SENSOR.value,
                'label': 'Sensor',
                'help': "Temperature, humidity, weather station, meter readings, ...",
                'fields': [
                    FIELD_ID,
                    _eep_field(SensorSchema.CONF_EEP_SUPPORTED),
                    FIELD_NAME, FIELD_AREA,
                    {'name': CONF_METER_TARIFFS, 'label': 'Meter tariffs', 'type': 'int_list', 'required': False,
                     'help': "Only for meter readings (A5-12-xx): tariff registers to read, e.g. 1"},
                ],
            },
            {
                'platform': Platform.LIGHT.value,
                'label': 'Light',
                'help': "Eltako relays (M5-38-08) and dimmers (A5-38-08)",
                'fields': [
                    FIELD_ID,
                    _eep_field(LightSchema.CONF_EEP_SUPPORTED),
                    _sender_field(LightSchema.CONF_SENDER_EEP_SUPPORTED, required=True),
                    FIELD_NAME, FIELD_AREA,
                ],
            },
            {
                'platform': Platform.SWITCH.value,
                'label': 'Switch',
                'help': "Same actuators as light, but represented as switch (sockets, pumps, ...)",
                'fields': [
                    FIELD_ID,
                    _eep_field(SwitchSchema.CONF_EEP_SUPPORTED),
                    _sender_field(SwitchSchema.CONF_SENDER_EEP_SUPPORTED, required=True),
                    FIELD_NAME, FIELD_AREA,
                ],
            },
            {
                'platform': Platform.COVER.value,
                'label': 'Cover',
                'help': "Blind/shutter actuators (FSB14, FSB61, ...)",
                'fields': [
                    FIELD_ID,
                    _eep_field(CoverSchema.CONF_EEP_SUPPORTED),
                    _sender_field(CoverSchema.CONF_SENDER_EEP_SUPPORTED, required=True),
                    FIELD_NAME, FIELD_AREA,
                    {'name': CONF_DEVICE_CLASS, 'label': 'Device class', 'type': 'text', 'required': False,
                     'help': "shutter, blind, awning, curtain, ..."},
                    {'name': CONF_TIME_CLOSES, 'label': 'Time closes (s)', 'type': 'number', 'required': False,
                     'min': 1, 'max': 255, 'help': "Seconds for closing completely (from PCT14)"},
                    {'name': CONF_TIME_OPENS, 'label': 'Time opens (s)', 'type': 'number', 'required': False,
                     'min': 1, 'max': 255},
                    {'name': CONF_TIME_TILTS, 'label': 'Time tilts (0.1 s)', 'type': 'number', 'required': False,
                     'min': 1, 'max': 255, 'help': "Runtime of a complete tilt in tenths of a second"},
                ],
            },
            {
                'platform': Platform.CLIMATE.value,
                'label': 'Climate',
                'help': "Heating and cooling actuators (FAE14, FHK14, ...)",
                'fields': [
                    FIELD_ID,
                    _eep_field(ClimateSchema.CONF_CLIMATE_EEP),
                    _sender_field(ClimateSchema.CONF_CLIMATE_SENDER_EEP, required=True),
                    FIELD_NAME, FIELD_AREA,
                    {'name': CONF_TEMPERATURE_UNIT, 'label': 'Temperature unit', 'type': 'select', 'required': False,
                     'options': [u.value for u in UnitOfTemperature], 'default': '°C'},
                    {'name': CONF_MIN_TARGET_TEMPERATURE, 'label': 'Min. target temperature', 'type': 'number',
                     'required': False, 'default': 17},
                    {'name': CONF_MAX_TARGET_TEMPERATURE, 'label': 'Max. target temperature', 'type': 'number',
                     'required': False, 'default': 25},
                    {'name': CONF_ROOM_SENSOR, 'label': 'Room sensor entity', 'type': 'text', 'required': False,
                     'help': "entity_id of any Home Assistant sensor providing the current room temperature"},
                    {'name': CONF_OFF_TEMPERATURE, 'label': 'Off temperature', 'type': 'number', 'required': False,
                     'help': "Target temperature which is sent for hvac mode 'off' (anti-frost)"},
                    {'name': CONF_ROOM_THERMOSTAT, 'label': 'Physical thermostat', 'type': 'group', 'required': False,
                     'help': "Physical thermostat (e.g. FUTH) which is kept in sync",
                     'fields': [
                         {'name': CONF_ID, 'label': 'Thermostat address', 'type': 'address', 'required': True},
                         _eep_field(ClimateSchema.CONF_CLIMATE_SENDER_EEP, 'Thermostat EEP'),
                     ]},
                ],
            },
        ],
    }


### ---------------------------------------------------------------------------
### storage and validation
### ---------------------------------------------------------------------------

def get_ui_devices(config_entry: ConfigEntry) -> dict[str, list[dict]]:
    """Return the devices which were created through the web ui for this gateway."""
    if config_entry is None:
        return {}
    devices = (config_entry.options or {}).get(CONF_UI_DEVICES, {}) or {}
    # options are stored as plain json, make sure the structure is as expected
    return {str(platform): list(entries) for platform, entries in devices.items() if entries}


def validate_device(platform: str, device: dict) -> dict:
    """Validate one device with the schema of its platform. Raises vol.Invalid."""
    if platform not in SUPPORTED_PLATFORMS:
        raise vol.Invalid(f"Platform '{platform}' does not support devices.")

    # remove empty optional values so that the defaults of the schema are used
    cleaned = {key: value for key, value in device.items()
               if value is not None and value != "" and value != []}
    for key in (CONF_SENDER, CONF_ROOM_THERMOSTAT):
        group = cleaned.get(key)
        if isinstance(group, dict):
            group = {k: v for k, v in group.items() if v is not None and v != ""}
            if group:
                cleaned[key] = group
            else:
                del cleaned[key]

    return SUPPORTED_PLATFORMS[platform].ENTITY_SCHEMA(cleaned)


def normalize_address(address: str) -> str:
    """Uppercase representation of an EnOcean address, raises vol.Invalid if malformed."""
    try:
        return config_helpers.b2s(AddressExpression.parse(address)[0])
    except Exception as e:      # noqa: BLE001
        raise vol.Invalid(f"'{address}' is not a valid EnOcean address (e.g. FF-AA-80-01)") from e


def find_device(devices: dict[str, list[dict]], platform: str, address: str) -> dict | None:
    for device in devices.get(platform, []):
        if str(device.get(CONF_ID, '')).upper() == address.upper():
            return device
    return None


async def async_save_ui_devices(hass: HomeAssistant, config_entry: ConfigEntry,
                               devices: dict[str, list[dict]]) -> None:
    """Store the ui devices in the options of the config entry (triggers a reload)."""
    options = dict(config_entry.options or {})
    options[CONF_UI_DEVICES] = {platform: entries for platform, entries in devices.items() if entries}
    hass.config_entries.async_update_entry(config_entry, options=options)


async def async_add_ui_device(hass: HomeAssistant, config_entry: ConfigEntry, platform: str,
                              device: dict) -> dict:
    """Validate and store a new device. Returns the validated device."""
    validated = validate_device(platform, device)
    address = normalize_address(str(device.get(CONF_ID)))

    devices = get_ui_devices(config_entry)
    if find_device(devices, platform, address) is not None:
        raise vol.Invalid(f"Device '{address}' is already configured as {platform} in the web ui.")

    # a device which is declared in the yaml must not be shadowed
    yaml_devices = _get_yaml_devices_of_gateway(hass, config_entry)
    if find_device(yaml_devices, platform, address) is not None:
        raise vol.Invalid(f"Device '{address}' is already declared as {platform} in your "
                          f"configuration.yaml. Please edit it there.")

    entry = dict(device)
    entry[CONF_ID] = address
    devices.setdefault(platform, []).append(entry)
    await async_save_ui_devices(hass, config_entry, devices)

    LOGGER.info(f"[{LOG_PREFIX_DEVICE_CONFIG}] Added {platform} '{address}' via web ui.")
    return validated


async def async_update_ui_device(hass: HomeAssistant, config_entry: ConfigEntry, platform: str,
                                 address: str, device: dict) -> dict:
    """Replace an existing ui device."""
    validated = validate_device(platform, device)
    address = normalize_address(address)

    devices = get_ui_devices(config_entry)
    existing = find_device(devices, platform, address)
    if existing is None:
        raise vol.Invalid(f"Device '{address}' is not configured as {platform} in the web ui.")

    entry = dict(device)
    entry[CONF_ID] = normalize_address(str(device.get(CONF_ID, address)))
    devices[platform][devices[platform].index(existing)] = entry
    await async_save_ui_devices(hass, config_entry, devices)

    LOGGER.info(f"[{LOG_PREFIX_DEVICE_CONFIG}] Updated {platform} '{address}' via web ui.")
    return validated


async def async_remove_ui_device(hass: HomeAssistant, config_entry: ConfigEntry, platform: str,
                                 address: str) -> None:
    """Remove a ui device."""
    address = normalize_address(address)
    devices = get_ui_devices(config_entry)
    existing = find_device(devices, platform, address)
    if existing is None:
        raise vol.Invalid(f"Device '{address}' is not configured as {platform} in the web ui.")

    devices[platform].remove(existing)
    await async_save_ui_devices(hass, config_entry, devices)

    LOGGER.info(f"[{LOG_PREFIX_DEVICE_CONFIG}] Removed {platform} '{address}' via web ui.")


### ---------------------------------------------------------------------------
### merging
### ---------------------------------------------------------------------------

def _get_yaml_devices_of_gateway(hass: HomeAssistant, config_entry: ConfigEntry) -> dict[str, list[dict]]:
    """Devices of this gateway which are declared in configuration.yaml."""
    from . import get_gateway_from_hass

    config = hass.data.get(DATA_ELTAKO, {}).get(ELTAKO_CONFIG, {}) or {}
    gateway = get_gateway_from_hass(hass, config_entry)
    gateway_id = getattr(gateway, 'dev_id', None)
    if gateway_id is None:
        try:
            gateway_id = config_helpers.get_id_from_gateway_name(config_entry.data[CONF_GATEWAY_DESCRIPTION])
        except Exception:   # noqa: BLE001
            return {}

    return config_helpers.get_device_config(config, gateway_id) or {}


def merge_device_config(yaml_devices: dict, ui_devices: dict) -> dict:
    """Merge both sources. Devices of the yaml configuration win."""
    merged: dict[str, list[dict]] = {platform: list(entries or [])
                                     for platform, entries in (yaml_devices or {}).items()}

    for platform, entries in (ui_devices or {}).items():
        target = merged.setdefault(platform, [])
        declared = {str(entry.get(CONF_ID, '')).upper() for entry in target}
        for entry in entries or []:
            address = str(entry.get(CONF_ID, '')).upper()
            if address in declared:
                LOGGER.warning(f"[{LOG_PREFIX_DEVICE_CONFIG}] Device '{address}' ({platform}) is declared in "
                               f"configuration.yaml and in the web ui. The yaml declaration is used.")
                continue
            target.append(entry)
            declared.add(address)

    return merged


def get_merged_device_config(hass: HomeAssistant, config_entry: ConfigEntry,
                            yaml_devices: dict) -> dict:
    """Device configuration of one gateway from configuration.yaml and from the web ui."""
    return merge_device_config(yaml_devices, get_ui_devices(config_entry))


### ---------------------------------------------------------------------------
### websocket api
### ---------------------------------------------------------------------------

def _get_gateway_entries(hass: HomeAssistant) -> list[ConfigEntry]:
    return list(hass.config_entries.async_entries(DOMAIN))


def _find_gateway_entry(hass: HomeAssistant, gateway_id: int) -> ConfigEntry | None:
    for entry in _get_gateway_entries(hass):
        try:
            if config_helpers.get_id_from_gateway_name(entry.data[CONF_GATEWAY_DESCRIPTION]) == gateway_id:
                return entry
        except Exception:   # noqa: BLE001
            continue
    return None


def _describe_devices(hass: HomeAssistant) -> list[dict]:
    """All configured devices of all gateways incl. their source (yaml or web ui).

    Iterates the *configuration* (yaml plus ui gateways), not the config entries: devices of
    a gateway which is not set up in Home Assistant yet must stay visible - otherwise the
    whole list goes blank when gateways are re-created.
    """
    from .device_activity import get_activity_tracker
    from .bus_members import _get_ha_device_ids

    activity_tracker = get_activity_tracker(hass)
    ha_devices = _get_ha_device_ids(hass)
    config = hass.data.get(DATA_ELTAKO, {}).get(ELTAKO_CONFIG, {}) or {}

    entries_by_gateway_id = {}
    for entry in _get_gateway_entries(hass):
        try:
            entries_by_gateway_id[config_helpers.get_id_from_gateway_name(
                entry.data[CONF_GATEWAY_DESCRIPTION])] = entry
        except Exception:   # noqa: BLE001
            continue

    result = []
    for gateway_config in config.get(CONF_GATEWAY, []) or []:
        gateway_id = gateway_config.get(CONF_ID)
        entry = entries_by_gateway_id.get(gateway_id)
        gateway = hass.data.get(DATA_ELTAKO, {}).get(f"gateway_{gateway_id}")

        gateway_name = getattr(gateway, 'dev_name', None) or config_helpers.get_gateway_name(
            gateway_config.get(CONF_NAME), str(gateway_config.get(CONF_DEVICE_TYPE, '?')), gateway_id)
        base_id = getattr(gateway, 'base_id', None)
        if base_id is None and gateway_config.get(CONF_BASE_ID):
            try:
                base_id = AddressExpression.parse(str(gateway_config[CONF_BASE_ID]))
            except Exception:   # noqa: BLE001
                base_id = None

        yaml_devices = gateway_config.get(CONF_DEVICES, {}) or {}
        ui_devices = get_ui_devices(entry) if entry else {}

        for source, devices in (('yaml', yaml_devices), ('ui', ui_devices)):
            for platform, entries in (devices or {}).items():
                for device in entries or []:
                    address = str(device.get(CONF_ID, ''))
                    external_address = _external_address(address, base_id)

                    activity = None
                    sender_activity = None
                    if activity_tracker is not None:
                        activity = (activity_tracker.get_activity(external_address)
                                    or activity_tracker.get_activity(address.upper()))
                        sender = device.get(CONF_SENDER) or {}
                        sender_id = str(sender.get(CONF_ID, '')) if isinstance(sender, dict) else ''
                        if sender_id:
                            sender_activity = (activity_tracker.get_activity(_external_address(sender_id, base_id))
                                               or activity_tracker.get_activity(sender_id.upper()))

                    result.append({
                        'gateway_id': gateway_id,
                        'gateway_name': gateway_name,
                        'gateway_set_up': entry is not None,
                        'config_entry_id': entry.entry_id if entry else None,
                        'platform': str(platform),
                        'source': source,
                        'editable': source == 'ui' and entry is not None,
                        'address': address.upper(),
                        'external_address': external_address,
                        'activity': activity,
                        'sender_activity': sender_activity,
                        # link to the device page in home assistant (see device.py: entities
                        # register their device with identifiers={(DOMAIN, <address>)})
                        'ha_device_id': ha_devices.get(address.upper()) or ha_devices.get(external_address),
                        'name': device.get(CONF_NAME),
                        'eep': device.get(CONF_EEP),
                        'area': device.get(CONF_AREA),
                        'sender': device.get(CONF_SENDER),
                        'config': {str(k): _plain(v) for k, v in device.items()},
                    })
    return result


def _external_address(address: str, base_id) -> str | None:
    try:
        expression = AddressExpression.parse(address)
    except Exception:   # noqa: BLE001
        return None
    if expression.is_local_address() and base_id is not None and int.from_bytes(base_id[0], 'big') != 0:
        return config_helpers.b2s(expression.add(base_id))
    return config_helpers.b2s(expression)


def _plain(value):
    """Config values can contain AddressExpression/EEP objects when they come from the yaml."""
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, AddressExpression):
        return config_helpers.b2s(value)
    if isinstance(value, (bytes, bytearray)):
        return config_helpers.b2s(bytes(value))
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return getattr(value, 'eep_string', str(value))


def register_websocket_commands(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, ws_device_form)
    websocket_api.async_register_command(hass, ws_device_list)
    websocket_api.async_register_command(hass, ws_device_add)
    websocket_api.async_register_command(hass, ws_device_update)
    websocket_api.async_register_command(hass, ws_device_remove)


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required('type'): WS_DEVICE_FORM})
@callback
def ws_device_form(hass: HomeAssistant, connection, msg) -> None:
    """Descriptor of all platforms and their fields, used to render the forms in the web ui."""
    from . import get_gateway_from_hass

    descriptor = get_form_descriptor()
    descriptor['gateways'] = [{
        'id': getattr(get_gateway_from_hass(hass, entry), 'dev_id', None),
        'name': getattr(get_gateway_from_hass(hass, entry), 'dev_name', entry.title),
        'base_id': config_helpers.b2s(getattr(get_gateway_from_hass(hass, entry), 'base_id', b'\0\0\0\0')),
        'config_entry_id': entry.entry_id,
    } for entry in _get_gateway_entries(hass)]
    connection.send_result(msg['id'], descriptor)


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required('type'): WS_DEVICE_LIST})
@callback
def ws_device_list(hass: HomeAssistant, connection, msg) -> None:
    connection.send_result(msg['id'], {'devices': _describe_devices(hass)})


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required('type'): WS_DEVICE_ADD,
    vol.Required('gateway_id'): vol.Coerce(int),
    vol.Required('platform'): str,
    vol.Required('device'): dict,
})
@websocket_api.async_response
async def ws_device_add(hass: HomeAssistant, connection, msg) -> None:
    entry = _find_gateway_entry(hass, msg['gateway_id'])
    if entry is None:
        connection.send_error(msg['id'], 'unknown_gateway', f"No gateway with id {msg['gateway_id']}")
        return
    try:
        validated = await async_add_ui_device(hass, entry, msg['platform'], msg['device'])
    except vol.Invalid as e:
        connection.send_error(msg['id'], 'invalid_device', str(e))
        return
    connection.send_result(msg['id'], {'device': _plain(dict(validated))})


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required('type'): WS_DEVICE_UPDATE,
    vol.Required('gateway_id'): vol.Coerce(int),
    vol.Required('platform'): str,
    vol.Required('address'): str,
    vol.Required('device'): dict,
})
@websocket_api.async_response
async def ws_device_update(hass: HomeAssistant, connection, msg) -> None:
    entry = _find_gateway_entry(hass, msg['gateway_id'])
    if entry is None:
        connection.send_error(msg['id'], 'unknown_gateway', f"No gateway with id {msg['gateway_id']}")
        return
    try:
        validated = await async_update_ui_device(hass, entry, msg['platform'], msg['address'], msg['device'])
    except vol.Invalid as e:
        connection.send_error(msg['id'], 'invalid_device', str(e))
        return
    connection.send_result(msg['id'], {'device': _plain(dict(validated))})


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required('type'): WS_DEVICE_REMOVE,
    vol.Required('gateway_id'): vol.Coerce(int),
    vol.Required('platform'): str,
    vol.Required('address'): str,
})
@websocket_api.async_response
async def ws_device_remove(hass: HomeAssistant, connection, msg) -> None:
    entry = _find_gateway_entry(hass, msg['gateway_id'])
    if entry is None:
        connection.send_error(msg['id'], 'unknown_gateway', f"No gateway with id {msg['gateway_id']}")
        return
    try:
        await async_remove_ui_device(hass, entry, msg['platform'], msg['address'])
    except vol.Invalid as e:
        connection.send_error(msg['id'], 'invalid_device', str(e))
        return
    connection.send_result(msg['id'], {'removed': True})
