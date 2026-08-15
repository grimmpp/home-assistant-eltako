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

from ..const import (CONF_AREA, CONF_BASE_ID, CONF_CORE_ENTRY, CONF_DEVICE_TYPE, CONF_EEP, CONF_GATEWAY,
                     CONF_GATEWAY_DESCRIPTION, CONF_INVERT_SIGNAL, CONF_MAX_TARGET_TEMPERATURE,
                     CONF_METER_TARIFFS, CONF_MIN_TARGET_TEMPERATURE, CONF_OFF_TEMPERATURE, CONF_ROOM_SENSOR,
                     CONF_ROOM_THERMOSTAT, CONF_SENDER, CONF_SIMULATED, CONF_TIME_CLOSES, CONF_TIME_OPENS,
                     CONF_TIME_TILTS, CONF_UI_DEVICES, DATA_ELTAKO, DOMAIN, ELTAKO_CONFIG, LOGGER,
                     WS_DEVICE_ADD, WS_DEVICE_FORM, WS_DEVICE_LIST, WS_DEVICE_REMOVE, WS_DEVICE_REMOVE_ALL,
                     WS_DEVICE_TEACH_IN, WS_DEVICE_UPDATE)
from . import config_helpers
from ..catalog.device_catalog import get_device_templates
from .schema import (
    BinarySensorSchema,
    ClimateSchema,
    CoverSchema,
    FanSchema,
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
    Platform.FAN.value: FanSchema,
}

# fields which are offered per platform in the web ui. The EEP lists are taken from the
# schemas so that they cannot drift apart from the supported EEPs.
FIELD_ID = {'name': CONF_ID, 'label': 'Address', 'type': 'address', 'required': True,
            'help': "EnOcean address, e.g. FF-AA-80-01. Bus devices use their local address, e.g. 00-00-00-01."}
FIELD_NAME = {'name': CONF_NAME, 'label': 'Name', 'type': 'text', 'required': False}
# combo: text input with suggestions. The options (the areas known to Home Assistant) are
# injected by ws_device_form - a new area can still be typed, it is created automatically.
FIELD_AREA = {'name': CONF_AREA, 'label': 'Area', 'type': 'combo', 'required': False,
              'help': "Area of the device in Home Assistant. Pick one of the existing areas "
                      "or type a new one - it is created if it does not exist."}


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
    'M5-38-08': "ELTAKO relay, e.g. FSR14, FSR61",
    'G5-3F-7F': "ELTAKO cover actuator, e.g. FSB14, FSB61",
    'H5-3F-7F': "ELTAKO cover command",
}


def describe_eep(eep: str) -> str:
    """Readable description of an EEP: docstring of the library plus the typical device."""
    from eltakobus.eep import EEP

    from ..catalog.device_catalog import as_display_text

    description = ""
    try:
        docstring = as_display_text(EEP.find(eep).__doc__).strip()
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
    """Describe all platforms and their fields so that the web ui can render the forms.

    Besides the fields every platform carries `device_types`: the known devices of the
    central catalog (device_catalog.py). Selecting one in the form prefills its EEP and
    sender EEP as template - like the device list of the EnOcean Device Manager. The
    templates are filtered against the EEPs the platform schema supports, so the form
    can never offer a combination the validation would reject.
    """
    return {
        'platforms': [
            {
                'platform': Platform.BINARY_SENSOR.value,
                'label': 'Binary sensor',
                'help': "Rocker switches, window/door contacts, occupancy sensors, ...",
                'device_types': get_device_templates(
                    Platform.BINARY_SENSOR.value,
                    supported_eeps=BinarySensorSchema.ENTITY_SCHEMA.validators[0].schema[vol.Required(CONF_EEP)].container),
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
                'device_types': get_device_templates(
                    Platform.SENSOR.value, supported_eeps=SensorSchema.CONF_EEP_SUPPORTED),
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
                'help': "ELTAKO relays (M5-38-08) and dimmers (A5-38-08)",
                'device_types': get_device_templates(
                    Platform.LIGHT.value, supported_eeps=LightSchema.CONF_EEP_SUPPORTED,
                    supported_sender_eeps=LightSchema.CONF_SENDER_EEP_SUPPORTED),
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
                'device_types': get_device_templates(
                    'light',        # switches use the same actuators as lights
                    supported_eeps=SwitchSchema.CONF_EEP_SUPPORTED,
                    supported_sender_eeps=SwitchSchema.CONF_SENDER_EEP_SUPPORTED),
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
                'device_types': get_device_templates(
                    Platform.COVER.value, supported_eeps=CoverSchema.CONF_EEP_SUPPORTED,
                    supported_sender_eeps=CoverSchema.CONF_SENDER_EEP_SUPPORTED),
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
                'device_types': get_device_templates(
                    Platform.CLIMATE.value, supported_eeps=ClimateSchema.CONF_CLIMATE_EEP,
                    supported_sender_eeps=ClimateSchema.CONF_CLIMATE_SENDER_EEP),
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
            {
                'platform': Platform.FAN.value,
                'label': 'Fan',
                'help': "Ventilation fans (FUD14, FSR14, ...)",
                'device_types': get_device_templates(
                    Platform.FAN.value, supported_eeps=FanSchema.CONF_EEP_SUPPORTED,
                    supported_sender_eeps=FanSchema.CONF_SENDER_EEP_SUPPORTED),
                'fields': [
                    FIELD_ID,
                    _eep_field(FanSchema.CONF_EEP_SUPPORTED),
                    _sender_field(FanSchema.CONF_SENDER_EEP_SUPPORTED, required=True),
                    FIELD_NAME, FIELD_AREA,
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


def _prepare_ui_device(hass: HomeAssistant, config_entry: ConfigEntry, devices: dict,
                       platform: str, device: dict) -> tuple[dict, dict]:
    """Validate one new device against the schema and the devices which already exist.

    Returns (entry to store, validated device). Raises vol.Invalid.
    """
    validated = validate_device(platform, device)
    address = normalize_address(str(device.get(CONF_ID)))

    if find_device(devices, platform, address) is not None:
        raise vol.Invalid(f"Device '{address}' is already configured as {platform} in the web ui.")

    # a device which is declared in the yaml must not be shadowed
    yaml_devices = _get_yaml_devices_of_gateway(hass, config_entry)
    if find_device(yaml_devices, platform, address) is not None:
        raise vol.Invalid(f"Device '{address}' is already declared as {platform} in your "
                          f"configuration.yaml. Please edit it there.")

    entry = dict(device)
    entry[CONF_ID] = address
    return entry, validated


async def async_add_ui_device(hass: HomeAssistant, config_entry: ConfigEntry, platform: str,
                              device: dict) -> dict:
    """Validate and store a new device. Returns the validated device."""
    devices = get_ui_devices(config_entry)
    entry, validated = _prepare_ui_device(hass, config_entry, devices, platform, device)

    devices.setdefault(platform, []).append(entry)
    await async_save_ui_devices(hass, config_entry, devices)

    LOGGER.info(f"[{LOG_PREFIX_DEVICE_CONFIG}] Added {platform} '{entry[CONF_ID]}' via web ui.")
    return validated


async def async_add_ui_devices(hass: HomeAssistant, config_entry: ConfigEntry,
                               candidates: list[tuple[str, dict]]) -> dict:
    """Store several devices of one gateway with ONE write of the config entry.

    Every write of the options reloads the gateway, which rebuilds its connection and all its
    entities. Adding devices one by one - an automatic detection can find dozens at once -
    would therefore reload the gateway dozens of times in a row. So all devices are validated
    first and stored together; a single invalid device is reported and skipped instead of
    stopping the others.

    `candidates` is a list of (platform, device). Returns
    `{'added': [(platform, device)], 'existing': [...], 'errors': [(platform, address, message)]}`.
    """
    devices = get_ui_devices(config_entry)
    result = {'added': [], 'existing': [], 'errors': []}

    for platform, device in candidates:
        try:
            entry, _validated = _prepare_ui_device(hass, config_entry, devices, platform, device)
        except vol.Invalid as e:
            address = str(device.get(CONF_ID, '?'))
            # "already configured/declared" is the merge working as intended, not an error
            target = 'existing' if 'already' in str(e) else 'errors'
            result[target].append((platform, address, str(e)) if target == 'errors'
                                  else (platform, address))
            continue
        devices.setdefault(platform, []).append(entry)
        result['added'].append((platform, entry))

    if result['added']:
        await async_save_ui_devices(hass, config_entry, devices)
        LOGGER.info(f"[{LOG_PREFIX_DEVICE_CONFIG}] Added {len(result['added'])} device(s) in one "
                    f"go: {', '.join(f'{platform} {entry[CONF_ID]}' for platform, entry in result['added'])}")
    return result


def get_form_field_names(platform: str) -> set[str]:
    """Names of the fields the web ui offers for a platform (groups count as one field)."""
    for descriptor in get_form_descriptor()['platforms']:
        if descriptor['platform'] == platform:
            return {field['name'] for field in descriptor['fields']}
    return set()


def _keep_fields_the_form_does_not_offer(platform: str, existing: dict, device: dict) -> dict:
    """Carry over settings which the form of the web ui cannot show.

    The schemas support more than the form offers (e.g. `cooling_mode` of a climate device,
    `voc_type_indexes` and `language` of a sensor). The ui sends exactly the fields it
    rendered, so saving a device which was imported or hand written would silently drop
    everything else. Such a field is therefore taken from the stored device; a field which the
    form does offer is always taken from the ui - leaving it empty has to be able to clear it.
    """
    offered = get_form_field_names(platform)
    preserved = {key: value for key, value in (existing or {}).items()
                 if key not in offered and key not in device and key != CONF_ID}
    if preserved:
        LOGGER.debug(f"[{LOG_PREFIX_DEVICE_CONFIG}] Keeping {', '.join(preserved)} of "
                     f"{platform} '{existing.get(CONF_ID)}' - the web ui form does not offer it.")
    return {**preserved, **device}


async def async_update_ui_device(hass: HomeAssistant, config_entry: ConfigEntry, platform: str,
                                 address: str, device: dict) -> dict:
    """Change an existing ui device. Returns the validated device."""
    address = normalize_address(address)

    devices = get_ui_devices(config_entry)
    existing = find_device(devices, platform, address)
    if existing is None:
        raise vol.Invalid(f"Device '{address}' is not configured as {platform} in the web ui.")

    entry = _keep_fields_the_form_does_not_offer(platform, existing, device)
    validated = validate_device(platform, entry)
    entry[CONF_ID] = normalize_address(str(entry.get(CONF_ID, address)))

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


async def async_remove_all_ui_devices(hass: HomeAssistant, gateway_id: int = None) -> dict:
    """Remove every device which was created in the web ui. Returns what was removed.

    The counterpart of a fresh detection: everything plug & play added (and everything added
    by hand) is dropped, so the next run starts from an empty configuration instead of
    skipping what already exists.

    Two things are deliberately **not** touched:

    * devices declared in `configuration.yaml` - they are not ours to delete, and the merge
      keeps them anyway (see `_get_yaml_devices_of_gateway`)
    * the gateways themselves and the stored bus memory images - re-reading a bus locks it for
      minutes, so a device reset must not silently throw that away. `plug_and_play.async_run`
      decides whether the bus is read again (`rescan_bus`).

    Each gateway is written **once**, so the entities are rebuilt in one reload per gateway
    instead of one per device.
    """
    entries = ([_find_gateway_entry(hass, gateway_id)] if gateway_id is not None
               else _get_gateway_entries(hass))

    removed: list[dict] = []
    for config_entry in entries:
        if config_entry is None:
            raise vol.Invalid(f"No gateway with id {gateway_id}")
        devices = get_ui_devices(config_entry)
        if not devices:
            continue
        for platform, entries_of_platform in devices.items():
            removed.extend({'platform': platform, 'address': device.get(CONF_ID)}
                           for device in entries_of_platform)
        await async_save_ui_devices(hass, config_entry, {})

    LOGGER.info(f"[{LOG_PREFIX_DEVICE_CONFIG}] Removed all {len(removed)} device(s) created in "
                f"the web ui{'' if gateway_id is None else f' of gateway {gateway_id}'}.")
    return {'removed': len(removed), 'devices': removed}


### ---------------------------------------------------------------------------
### merging
### ---------------------------------------------------------------------------

def _get_yaml_devices_of_gateway(hass: HomeAssistant, config_entry: ConfigEntry) -> dict[str, list[dict]]:
    """Devices of this gateway which are declared in configuration.yaml."""
    from ..core.integration import get_gateway_from_hass

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


def get_devices_of_gateway(hass: HomeAssistant, gateway_id: int) -> dict[str, list[dict]]:
    """Devices of one gateway from both sources, without having its config entry at hand.

    The platform setups get the entry handed over (get_merged_device_config), everything which
    only knows the gateway id - device tests, the configuration check, the command line - uses
    this one. Reading only the yaml would silently ignore every device created in the web ui.
    """
    config = (getattr(hass, 'data', None) or {}).get(DATA_ELTAKO, {}).get(ELTAKO_CONFIG, {}) or {}
    yaml_devices = config_helpers.get_device_config(config, int(gateway_id)) or {}
    try:
        entry = _find_gateway_entry(hass, int(gateway_id))
    except Exception:   # noqa: BLE001 - no config entries (e.g. in a unit test)
        entry = None
    return merge_device_config(yaml_devices, get_ui_devices(entry) if entry else {})


### ---------------------------------------------------------------------------
### websocket api
### ---------------------------------------------------------------------------

def _get_gateway_entries(hass: HomeAssistant) -> list[ConfigEntry]:
    """The config entries which carry a gateway.

    The entry of the integration itself carries none (see CONF_CORE_ENTRY) and is skipped here:
    everything below reads the gateway description out of an entry, and an installation which
    has only that one - a fresh one, or one whose gateways were removed - would otherwise make
    the device form and the device list fail instead of showing an empty list.
    """
    return [entry for entry in hass.config_entries.async_entries(DOMAIN)
            if not entry.data.get(CONF_CORE_ENTRY) and CONF_GATEWAY_DESCRIPTION in entry.data]


def _find_gateway_entry(hass: HomeAssistant, gateway_id: int) -> ConfigEntry | None:
    for entry in _get_gateway_entries(hass):
        try:
            if config_helpers.get_id_from_gateway_name(entry.data[CONF_GATEWAY_DESCRIPTION]) == gateway_id:
                return entry
        except Exception:   # noqa: BLE001
            continue
    return None


def _get_entity_ids_by_address(hass: HomeAssistant) -> dict[str, list[str]]:
    """EnOcean address -> entity ids of the live entities of this integration.

    Read from the entity platforms, where every entity states which addresses it listens to
    (device.py: `listen_to_addresses`). That works without the telegram logger - the simple
    device page of the web ui shows the state of a device even when recording is switched off
    - and in the standalone runtime alike.
    """
    try:
        from homeassistant.helpers.entity_platform import DATA_ENTITY_PLATFORM

        result: dict[str, list[str]] = {}
        platforms = (getattr(hass, 'data', None) or {}).get(DATA_ENTITY_PLATFORM, {}) or {}
        for entity_platform in platforms.get(DOMAIN, []):
            for entity in list(getattr(entity_platform, 'entities', {}).values()):
                entity_id = getattr(entity, 'entity_id', None)
                # info fields (event id, address, ...) describe the device instead of
                # reporting a value - they are of no use in the simple device view
                if not entity_id or getattr(entity, 'is_info_field', False):
                    continue
                for raw_address in getattr(entity, 'listen_to_addresses', []) or []:
                    try:
                        key = config_helpers.b2s(raw_address).upper()
                    except Exception:   # noqa: BLE001
                        continue
                    if entity_id not in result.setdefault(key, []):
                        result[key].append(entity_id)
        return result
    except Exception:   # noqa: BLE001 - no entity platforms (e.g. in a unit test)
        return {}


def _sender_taught_in(hass: HomeAssistant, gateway_id, address: str, sender) -> bool | None:
    """Whether the sender of a device is taught into it - as far as that can be known."""
    sender_id = (sender or {}).get(CONF_ID) if isinstance(sender, dict) else None
    if not sender_id:
        return None
    try:
        from ..observation.bus_members import sender_is_taught_in

        return sender_is_taught_in(hass, gateway_id, address, str(sender_id))
    except Exception:   # noqa: BLE001 - no registry (e.g. in a unit test)
        return None


def _describe_devices(hass: HomeAssistant) -> list[dict]:
    """All configured devices of all gateways incl. their source (yaml or web ui).

    Iterates the *configuration* (yaml plus ui gateways), not the config entries: devices of
    a gateway which is not set up in Home Assistant yet must stay visible - otherwise the
    whole list goes blank when gateways are re-created.
    """
    from ..observation.device_activity import get_activity_tracker
    from ..observation.bus_members import _get_ha_device_ids

    activity_tracker = get_activity_tracker(hass)
    ha_devices = _get_ha_device_ids(hass)
    entity_ids_by_address = _get_entity_ids_by_address(hass)
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
        # devices of a gateway without hardware are simulated - every list marks them, so a
        # simulated device is never mistaken for a real one (see simulation/)
        simulated = bool(gateway_config.get(CONF_SIMULATED, False))
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
                        'simulated': simulated,
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
                        # the entities of this device, so the web ui can show their state
                        'entity_ids': (entity_ids_by_address.get(str(external_address or '').upper())
                                       or entity_ids_by_address.get(address.upper()) or []),
                        'name': device.get(CONF_NAME),
                        'eep': device.get(CONF_EEP),
                        'area': device.get(CONF_AREA),
                        'sender': device.get(CONF_SENDER),
                        # is the sender of Home Assistant in the memory of the actuator? None
                        # when it cannot be told (no bus device, or its memory was never read)
                        'sender_taught_in': _sender_taught_in(hass, gateway_id, address,
                                                              device.get(CONF_SENDER)),
                        'config': {str(k): _plain(v) for k, v in device.items()},
                    })
    return result


def get_configured_addresses(hass: HomeAssistant) -> dict:
    """Every address which is in use, from configuration.yaml and from the web ui.

    Returns `{'by_gateway': {gateway id: {addresses}}, 'all': {addresses}}`. A local bus
    address (00-00-00-xx) only identifies a device together with its gateway - every bus has
    its own position 1 - therefore the addresses are additionally grouped per gateway. Sender
    ids and external addresses are included, so an automatic detection can neither add a
    device twice nor hand out a sender id which is already used.
    """
    result = {'by_gateway': {}, 'all': set()}
    for device in _describe_devices(hass):
        gateway_id = device.get('gateway_id')
        addresses = {device.get('address'), device.get('external_address'),
                     (device.get('sender') or {}).get(CONF_ID) if isinstance(device.get('sender'), dict) else None}
        addresses = {str(address).upper() for address in addresses if address}
        result['all'].update(addresses)
        result['by_gateway'].setdefault(gateway_id, set()).update(addresses)
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
    websocket_api.async_register_command(hass, ws_device_remove_all)
    websocket_api.async_register_command(hass, ws_device_teach_in)
    # which gateway switches an actuator - imported here because that module builds on the
    # device configuration of this one (and would be a circular import at module level)
    from .sender_gateway import register_websocket_commands as register_sender_gateway
    register_sender_gateway(hass)


def _get_area_names(hass: HomeAssistant) -> list[str]:
    """All areas known to Home Assistant, offered as suggestions for the area field."""
    try:
        from homeassistant.helpers import area_registry as ar

        return sorted((area.name for area in ar.async_get(hass).async_list_areas()),
                      key=str.casefold)
    except Exception:   # noqa: BLE001 - registry not available (e.g. in tests)
        return []


def _inject_area_options(descriptor: dict, areas: list[str]) -> None:
    """Fill the suggestions of every area field (incl. fields nested in groups).

    Replaces the field dicts instead of mutating them - FIELD_AREA is a shared module
    level constant and must not accumulate state between websocket calls.
    """
    def walk(fields: list[dict]) -> None:
        for index, field in enumerate(fields):
            if field.get('name') == CONF_AREA:
                fields[index] = {**field, 'options': areas}
            elif field.get('fields'):
                field['fields'] = list(field['fields'])
                walk(field['fields'])

    for platform in descriptor.get('platforms', []):
        platform['fields'] = list(platform.get('fields', []))
        walk(platform['fields'])


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required('type'): WS_DEVICE_FORM})
@callback
def ws_device_form(hass: HomeAssistant, connection, msg) -> None:
    """Descriptor of all platforms and their fields, used to render the forms in the web ui."""
    from ..core.integration import get_gateway_from_hass

    descriptor = get_form_descriptor()
    descriptor['areas'] = _get_area_names(hass)
    _inject_area_options(descriptor, descriptor['areas'])
    descriptor['gateways'] = [{
        'id': getattr(get_gateway_from_hass(hass, entry), 'dev_id', None),
        'name': getattr(get_gateway_from_hass(hass, entry), 'dev_name', entry.title),
        'base_id': config_helpers.b2s(getattr(get_gateway_from_hass(hass, entry), 'base_id', b'\0\0\0\0')),
        'config_entry_id': entry.entry_id,
    } for entry in _get_gateway_entries(hass)]
    connection.send_result(msg['id'], descriptor)


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required('type'): WS_DEVICE_TEACH_IN,
    vol.Required('gateway_id'): vol.Coerce(int),
    vol.Required('address'): str,
})
@websocket_api.async_response
async def ws_device_teach_in(hass: HomeAssistant, connection, msg) -> None:
    """Teach the sender of Home Assistant into this device - the way its kind needs it.

    A device on the RS485 bus has a memory, and the sender is written into it (the standard
    procedure of the EnOcean Device Manager, `ensure_programmed`) - that works without touching
    the device. A wireless actuator has to be put into its teach-in mode by hand, and then it
    takes the sender from the telegram which is sent here.
    """
    from ..catalog.teach_in import get_teach_in_payload, supports_teach_in_button
    from ..core.integration import get_gateway_from_hass
    from ..observation import bus_members

    entry = _find_gateway_entry(hass, msg['gateway_id'])
    gateway = get_gateway_from_hass(hass, entry) if entry else None
    if gateway is None:
        connection.send_error(msg['id'], 'unknown_gateway',
                              f"No gateway with id {msg['gateway_id']}")
        return

    address = normalize_address(msg['address'])
    devices = get_devices_of_gateway(hass, msg['gateway_id'])
    device = next((entry_device for entries in devices.values() for entry_device in entries or []
                   if normalize_address(str(entry_device.get(CONF_ID, ''))) == address), None)
    if device is None:
        connection.send_error(msg['id'], 'unknown_device',
                              f"Gateway {msg['gateway_id']} has no device {address}")
        return

    sender = device.get(CONF_SENDER) or {}
    sender_id, sender_eep = sender.get(CONF_ID), sender.get(CONF_EEP)
    if not sender_id or not sender_eep:
        connection.send_error(msg['id'], 'no_sender',
                              f"{address} has no sender - only an actuator is taught in, and it "
                              f"needs the address Home Assistant switches it with.")
        return

    # a bus device: write the sender into its memory
    if address.startswith('00-00-00-'):
        try:
            results = await bus_members.async_teach_in_senders(hass, gateway, address)
        except Exception as e:  # noqa: BLE001
            connection.send_error(msg['id'], 'teach_in_failed', str(e))
            return
        connection.send_result(msg['id'], {'kind': 'bus_memory', 'sender_id': sender_id,
                                           'results': results})
        return

    # a wireless actuator: send the teach-in telegram of the sender profile
    if not supports_teach_in_button(sender_eep):
        connection.send_error(msg['id'], 'no_teach_in_telegram',
                              f"There is no teach-in telegram for {sender_eep}. Teach the "
                              f"sender {sender_id} in at the device itself.")
        return
    try:
        from eltakobus.message import Regular4BSMessage
        from eltakobus.util import AddressExpression

        payload = get_teach_in_payload(sender_eep)
        telegram = Regular4BSMessage(AddressExpression.parse(sender_id)[0], 0x80, payload, True)
        gateway.send_message(telegram)
    except Exception as e:  # noqa: BLE001
        connection.send_error(msg['id'], 'teach_in_failed', str(e))
        return

    connection.send_result(msg['id'], {'kind': 'telegram', 'sender_id': sender_id,
                                       'eep': str(sender_eep), 'telegram': str(telegram)})


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


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required('type'): WS_DEVICE_REMOVE_ALL,
    vol.Optional('gateway_id'): vol.Coerce(int),
})
@websocket_api.async_response
async def ws_device_remove_all(hass: HomeAssistant, connection, msg) -> None:
    """Remove every device created in the web ui - of one gateway or of all of them.

    Destructive, so the caller confirms it: the web ui asks before it sends this.
    """
    try:
        result = await async_remove_all_ui_devices(hass, msg.get('gateway_id'))
    except vol.Invalid as e:
        connection.send_error(msg['id'], 'unknown_gateway', str(e))
        return
    connection.send_result(msg['id'], result)
