"""General settings which can be edited in the web ui.

The `general_settings` section of `configuration.yaml` stays fully supported. In addition
every setting can be overridden in the web ui, so the integration can be configured without
writing yaml at all.

Precedence (last one wins):

    1. defaults of the integration (DEFAULT_GENERAL_SETTINGS)
    2. `general_settings` of configuration.yaml
    3. overrides made in the web ui  <- documented as "override" on purpose

This is the opposite of the device configuration, where the yaml always wins. The reason is
the intention: devices in the yaml are version controlled and must not be shadowed silently,
while a setting is deliberately changed by the user in the ui and should take effect.
Every override can be reset again, which falls back to the yaml/default value.
"""

from __future__ import annotations

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store

from ..const import *
from . import config_helpers
from .config_helpers import DEFAULT_GENERAL_SETTINGS
from .schema import GeneralSettings

LOG_PREFIX_SETTINGS = "General Settings"

STORAGE_KEY = f"{DOMAIN}_general_settings"
STORAGE_VERSION = 1


### ---------------------------------------------------------------------------
### descriptor for the web ui
### ---------------------------------------------------------------------------

LOG_LEVEL_OPTIONS = [level.value for level in TelegramLogLevel]

# group, type, label, help and whether a restart is needed. The defaults come from
# DEFAULT_GENERAL_SETTINGS so that they cannot drift apart.
SETTING_DESCRIPTORS = [
    {'group': 'general', 'name': CONF_FAST_STATUS_CHANGE, 'type': 'boolean', 'label': 'Fast status change',
     'help': "Changes the state in Home Assistant immediately without waiting for the answer of "
             "the actuator. Feels faster but can show a state which was not confirmed."},
    {'group': 'general', 'name': CONF_SHOW_DEV_ID_IN_DEV_NAME, 'type': 'boolean', 'label': 'Show device id in device name',
     'help': "Appends the EnOcean address to the device name. Helpful while setting up."},
    {'group': 'plug_and_play', 'name': CONF_PLUG_AND_PLAY, 'type': 'boolean', 'label': 'Plug & play enabled',
     'help': "Checks regularly whether a gateway was plugged in, creates it, reads its bus and adds "
             "every device which is identified without any doubt (bus position with a known model, "
             "sender found in a device memory, teach-in telegram). Ambiguous devices are only listed - "
             "they stay a manual decision. The bus of a gateway is only read once; use the button on "
             "the overview page to read it again."},
    {'group': 'plug_and_play', 'name': CONF_PLUG_AND_PLAY_INTERVAL, 'type': 'number',
     'label': 'Check every (minutes)', 'min': 0, 'max': 10080,
     'help': "How often the serial ports are checked for a new gateway. Default is 1440 - once a "
             "day, which is often enough: a gateway is plugged in rarely and the check opens every "
             "free serial port. 60 = hourly, 0 = only when the button on the overview page is "
             "pressed. Every run additionally happens a minute after Home Assistant started."},
    # Shown, but not switchable from here: turning it off would remove the very page the
    # switch is on, and the yaml cannot undo it (an override stored here wins over the yaml).
    # Recovery would mean deleting '.storage/eltako_general_settings' by hand. It stays
    # configurable in configuration.yaml, where switching it back on works.
    {'group': 'web_ui', 'name': CONF_ENABLE_FRONTEND, 'type': 'boolean', 'label': 'Web ui enabled',
     'help': "This web ui. On by default. It can only be switched off in your "
             "configuration.yaml ('general_settings: enable_frontend: false'), not here: this "
             "page would disappear with it and an override stored here would win over the yaml, "
             "so there would be no way back short of deleting '.storage/eltako_general_settings'.",
     'locked': True,
     'restart_required': True},
    # Switchable from everywhere (web ui, configuration.yaml and the Home Assistant integration
    # page): it only takes the entry out of the sidebar, this page stays reachable.
    {'group': 'web_ui', 'name': CONF_SHOW_PANEL_IN_SIDEBAR, 'type': 'boolean', 'label': 'Show in sidebar',
     'help': "Shows the web ui in the navigation of Home Assistant. Switched off it disappears "
             "from the sidebar but stays reachable under '/" + PANEL_URL_PATH + "' - bookmark that "
             "url before hiding it. Switching it back on works here and on the Home Assistant "
             "integration page ('Configure')."},
    {'group': 'web_ui', 'name': CONF_ENABLE_TEST_PAGE, 'type': 'boolean', 'label': 'Test page enabled',
     'help': "Shows the 'Tests' page which runs the test suites of the project (integration, "
             "standalone runtime, EnOcean Device Manager). Only useful on a development "
             "machine - the suites run in the standalone runtime, not inside Home Assistant."},
    {'group': 'telegram_log', 'name': CONF_LOG_ENOCEAN_TELEGRAMS, 'type': 'boolean', 'label': 'Record EnOcean telegrams',
     'help': "Enables the live view, the statistics and the detection of unknown devices."},
    {'group': 'telegram_log', 'name': CONF_TELEGRAM_LOG_FILENAME, 'type': 'text', 'label': 'Telegram log file',
     'help': "If set, all telegrams are written into this file. Relative paths are located in the "
             "Home Assistant configuration folder. Setting a filename also enables the recording."},
    {'group': 'telegram_log', 'name': CONF_TELEGRAM_LOG_FORMAT, 'type': 'select', 'label': 'Telegram log format',
     'options': [f.value for f in TelegramLogFormat],
     'help': "jsonl: one json object per line (best for analysis). csv: spreadsheet friendly."},
    {'group': 'telegram_log', 'name': CONF_TELEGRAM_LOG_MAX_FILE_SIZE_MB, 'type': 'number', 'label': 'Max. log file size (MB)',
     'min': 0.1, 'max': 1024, 'help': "The log file is rotated when it grows beyond this size."},
    {'group': 'telegram_log', 'name': CONF_TELEGRAM_LOG_ROTATE_DAYS, 'type': 'number', 'label': 'Rotate after (days)',
     'min': 0, 'max': 3650, 'help': "The log file is also rotated when its oldest telegram is older than "
                                    "this. 0 disables the time based rotation - the file then only rotates "
                                    "by size."},
    {'group': 'telegram_log', 'name': CONF_TELEGRAM_LOG_BACKUP_COUNT, 'type': 'number', 'label': 'Rotated log files kept',
     'min': 0, 'max': 100},
    {'group': 'telegram_log', 'name': CONF_TELEGRAM_LOG_INCLUDE_POLLING, 'type': 'boolean', 'label': 'Include bus polling telegrams',
     'help': "Bus gateways (FAM14) poll their actuators permanently. Those telegrams are dropped by "
             "default because they would flood the log."},
    {'group': 'telegram_log', 'name': CONF_TELEGRAM_LOG_DECODE_EEP, 'type': 'boolean', 'label': 'Decode telegrams of known devices',
     'help': "Decodes telegrams with the configured EEP and stores the values (temperature, button, ...)."},
    {'group': 'telegram_log', 'name': CONF_TELEGRAM_LOG_BUFFER_SIZE, 'type': 'number', 'label': 'Live buffer size',
     'min': 0, 'max': 100000, 'help': "Number of telegrams kept in memory for the live view."},

    # timeseries export (InfluxDB / Grafana)
    {'group': 'timeseries', 'name': CONF_TIMESERIES_ENABLED, 'type': 'boolean', 'label': 'Export telegrams to InfluxDB',
     'help': "Requires the telegram recording to be enabled. The full history of the log files can be "
             "imported once with the service 'eltako.export_telegram_log_to_timeseries'."},
    {'group': 'timeseries', 'name': CONF_TIMESERIES_URL, 'type': 'text', 'label': 'InfluxDB URL',
     'help': "e.g. http://localhost:8086"},
    {'group': 'timeseries', 'name': CONF_TIMESERIES_TOKEN, 'type': 'text', 'label': 'API token',
     'help': "InfluxDB 2.x: an api token with write access to the bucket. "
             "InfluxDB 1.8: 'username:password'."},
    {'group': 'timeseries', 'name': CONF_TIMESERIES_ORG, 'type': 'text', 'label': 'Organization',
     'help': "InfluxDB 2.x organization. Leave empty for InfluxDB 1.8."},
    {'group': 'timeseries', 'name': CONF_TIMESERIES_BUCKET, 'type': 'text', 'label': 'Bucket',
     'help': "InfluxDB 2.x: bucket name. InfluxDB 1.8: 'database/retention_policy'."},
    {'group': 'timeseries', 'name': CONF_TIMESERIES_MEASUREMENT, 'type': 'text', 'label': 'Measurement',
     'help': "Name of the measurement the telegrams are written into."},
    {'group': 'timeseries', 'name': CONF_GRAFANA_URL, 'type': 'text', 'label': 'Grafana URL',
     'help': "e.g. http://localhost:3000 - used for the link to the dashboards in this web ui "
             "and by the 'Sync dashboards' button. Leave empty to hide both."},
    {'group': 'timeseries', 'name': CONF_GRAFANA_TOKEN, 'type': 'text', 'label': 'Grafana API token',
     'help': "Service account token with the role 'Editor' (Grafana: Administration -> Users and "
             "access -> Service accounts). Only needed for the 'Sync dashboards' button. "
             "'user:password' is accepted as well (basic auth, e.g. admin:admin for a test setup)."},

    # one log level per telegram category
    {'group': 'log_levels', 'name': CONF_LOG_LEVEL_INCOMING, 'type': 'select', 'label': 'Incoming telegrams',
     'options': LOG_LEVEL_OPTIONS,
     'help': "Telegrams of configured devices which were received."},
    {'group': 'log_levels', 'name': CONF_LOG_LEVEL_OUTGOING, 'type': 'select', 'label': 'Outgoing commands',
     'options': LOG_LEVEL_OPTIONS,
     'help': "Telegrams Home Assistant sends to actuators. Use it to check whether a command really "
             "goes onto the bus."},
    {'group': 'log_levels', 'name': CONF_LOG_LEVEL_UNKNOWN_DEVICES, 'type': 'select', 'label': 'Unknown devices',
     'options': LOG_LEVEL_OPTIONS,
     'help': "Telegrams of addresses which are not configured. 'warning' makes new devices "
             "(e.g. a button you press) stand out in the log."},
    {'group': 'log_levels', 'name': CONF_LOG_LEVEL_BUS_MESSAGES, 'type': 'select', 'label': 'Bus messages',
     'options': LOG_LEVEL_OPTIONS,
     'help': "Discovery, memory and other messages of the RS485 bus (no EnOcean address)."},
    {'group': 'log_levels', 'name': CONF_LOG_LEVEL_POLLING, 'type': 'select', 'label': 'Bus polling',
     'options': LOG_LEVEL_OPTIONS,
     'help': "The FAM14 polls its actuators permanently - this can be hundreds of telegrams per "
             "minute. Only switch it on for a short analysis."},
    {'group': 'log_levels', 'name': CONF_LOG_LEVEL_DECODE_ERRORS, 'type': 'select', 'label': 'Decode errors',
     'options': LOG_LEVEL_OPTIONS,
     'help': "A telegram of a known device which cannot be decoded with its configured EEP - "
             "the strongest hint for a wrong EEP."},
]

# these settings are not configurable, they are derived at runtime
READ_ONLY_SETTINGS = [CONF_ENABLE_TEACH_IN_BUTTONS]


def get_form_descriptor(hass: HomeAssistant) -> dict:
    """Descriptor incl. current value, origin of the value and the fallback value."""
    yaml_settings = _get_yaml_settings(hass)
    overrides = get_overrides(hass)
    effective = config_helpers.get_general_settings_from_configuration(hass)

    settings = []
    for descriptor in SETTING_DESCRIPTORS:
        name = descriptor['name']
        if name in overrides:
            origin = 'ui'
        elif name in yaml_settings:
            origin = 'yaml'
        else:
            origin = 'default'

        fallback = yaml_settings.get(name, DEFAULT_GENERAL_SETTINGS.get(name))
        value = effective.get(name)
        extra_help = None

        # The deprecated option 'enable-frontend' still switches the web ui on. Without this the
        # page would show 'False' although the panel the user is looking at is enabled.
        if name == CONF_ENABLE_FRONTEND:
            value = config_helpers.is_frontend_enabled(effective)
            if not effective.get(name) and value:
                origin = 'yaml'
                fallback = True
                extra_help = (f"Currently enabled through the deprecated option "
                              f"'{CONF_DEPRECATED_ENABLE_FRONTEND}' in your configuration.yaml. "
                              f"Please rename it to '{CONF_ENABLE_FRONTEND}'.")

        settings.append({
            **descriptor,
            'help': f"{descriptor.get('help', '')} {extra_help}".strip() if extra_help else descriptor.get('help'),
            'value': value,
            'origin': origin,
            'fallback': fallback,
            'fallback_origin': 'yaml' if name in yaml_settings else 'default',
            'default': DEFAULT_GENERAL_SETTINGS.get(name),
        })

    return {
        'groups': [{'id': group_id, 'label': label, 'help': help_text}
                   for group_id, label, help_text in SETTING_GROUPS],
        'settings': settings,
        'read_only': {name: effective.get(name) for name in READ_ONLY_SETTINGS},
        'has_yaml_section': bool(yaml_settings),
        'telegram_logger_name': TELEGRAM_LOGGER_NAME,
    }


### ---------------------------------------------------------------------------
### storage
### ---------------------------------------------------------------------------

def _store(hass: HomeAssistant) -> Store:
    domain_data = hass.data.setdefault(DATA_ELTAKO, {})
    store = domain_data.get(DATA_SETTINGS_STORE)
    if store is None:
        store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        domain_data[DATA_SETTINGS_STORE] = store
    return store


def get_overrides(hass: HomeAssistant) -> dict:
    """Settings which were changed in the web ui."""
    data = getattr(hass, 'data', None)
    if not isinstance(data, dict):
        return {}
    return dict(data.get(DATA_ELTAKO, {}).get(DATA_SETTINGS_OVERRIDES, {}) or {})


def _get_yaml_settings(hass: HomeAssistant) -> dict:
    config = hass.data.get(DATA_ELTAKO, {}).get(ELTAKO_CONFIG, {}) or {}
    return dict(config.get(CONF_GERNERAL_SETTINGS, {}) or {})


def validate_setting(name: str, value) -> object:
    """Validate one setting with the schema of the general settings section."""
    known = {descriptor['name'] for descriptor in SETTING_DESCRIPTORS}
    if name not in known:
        raise vol.Invalid(f"'{name}' is not an editable general setting.")

    # the schema fills all other keys with their defaults, so validating one key is enough
    validated = GeneralSettings.ENTITY_SCHEMA({name: value})
    return validated[name]


LOCKED_SETTINGS = frozenset(
    descriptor['name'] for descriptor in SETTING_DESCRIPTORS if descriptor.get('locked'))


async def async_set_overrides(hass: HomeAssistant, changes: dict) -> dict:
    """Validate and store overrides. Returns the validated values.

    Locked settings are dropped instead of stored: the web ui sends every field back when the
    form is saved, so a locked one arrives on each save with its unchanged value. Storing it
    would be harmless but pointless, and refusing the whole call would make saving impossible.
    A real change to one is ignored and logged - the yaml is the place for those.
    """
    validated = {}
    for name, value in changes.items():
        if name in LOCKED_SETTINGS:
            current = config_helpers.get_general_settings_from_configuration(hass).get(name)
            if value != current:
                LOGGER.warning(f"[{LOG_PREFIX_SETTINGS}] '{name}' cannot be changed in the web ui "
                               f"(requested {value!r}, staying {current!r}). Use configuration.yaml.")
            continue
        validated[name] = validate_setting(name, value)

    overrides = get_overrides(hass)
    overrides.update(validated)
    await _async_save(hass, overrides)

    LOGGER.info(f"[{LOG_PREFIX_SETTINGS}] Changed in web ui: "
                f"{', '.join(f'{k}={v!r}' for k, v in validated.items())}")
    return validated


async def async_reset_overrides(hass: HomeAssistant, names: list[str]) -> list[str]:
    """Remove overrides so that the yaml/default value is used again.

    Locked settings are skipped. For `enable_frontend` that is a leftover which stays on
    purpose: resetting it falls back to the yaml, and a yaml which switched the web ui off
    would take this page away - the same one-way door the lock exists for. (The default itself
    is True nowadays, so a reset without any yaml is harmless.)
    """
    overrides = get_overrides(hass)
    removed = [name for name in names if name in overrides and name not in LOCKED_SETTINGS]
    skipped = [name for name in names if name in LOCKED_SETTINGS]
    if skipped:
        LOGGER.warning(f"[{LOG_PREFIX_SETTINGS}] Not resetting {', '.join(skipped)} - "
                       f"changeable in configuration.yaml only.")
    for name in removed:
        del overrides[name]
    if removed:
        await _async_save(hass, overrides)
        LOGGER.info(f"[{LOG_PREFIX_SETTINGS}] Reset in web ui: {', '.join(removed)}")
    return removed


async def _async_save(hass: HomeAssistant, overrides: dict) -> None:
    hass.data.setdefault(DATA_ELTAKO, {})[DATA_SETTINGS_OVERRIDES] = overrides
    await _store(hass).async_save({'overrides': overrides})


async def async_load_overrides(hass: HomeAssistant) -> dict:
    """Load the overrides. Must run before the settings are read the first time."""
    stored = await _store(hass).async_load()
    overrides = {}
    if stored and isinstance(stored.get('overrides'), dict):
        for name, value in stored['overrides'].items():
            try:
                overrides[name] = validate_setting(name, value)
            except vol.Invalid as e:
                LOGGER.warning(f"[{LOG_PREFIX_SETTINGS}] Ignoring stored setting '{name}': {e}")

    hass.data.setdefault(DATA_ELTAKO, {})[DATA_SETTINGS_OVERRIDES] = overrides
    if overrides:
        LOGGER.info(f"[{LOG_PREFIX_SETTINGS}] Applying {len(overrides)} setting(s) from the web ui: "
                    f"{', '.join(overrides.keys())}")
    return overrides


### ---------------------------------------------------------------------------
### applying changes at runtime
### ---------------------------------------------------------------------------

async def async_apply_settings(hass: HomeAssistant) -> dict:
    """Apply the current settings without restarting Home Assistant.

    The telegram logger is re-created directly. Everything which is evaluated while creating
    gateways and entities (e.g. the device name) is applied by reloading the config entries.
    """
    from ..core.integration import async_apply_panel_visibility
    from ..observation.enocean_logger import async_setup_telegram_logger
    from ..tools import plug_and_play

    settings = config_helpers.get_general_settings_from_configuration(hass)
    result = {'telegram_logger_restarted': False, 'reloaded_gateways': 0,
              'plug_and_play_enabled': bool(settings.get(CONF_PLUG_AND_PLAY, False)),
              'panel_in_sidebar': config_helpers.is_panel_in_sidebar(settings)}

    try:
        await async_setup_telegram_logger(hass, settings)
        result['telegram_logger_restarted'] = True
    except Exception as e:  # noqa: BLE001
        LOGGER.error(f"[{LOG_PREFIX_SETTINGS}] Cannot restart the telegram logger: {e}", exc_info=True)

    # switching plug & play on or off (or changing its interval) takes effect immediately
    try:
        plug_and_play.apply_settings(hass, settings)
    except Exception as e:  # noqa: BLE001
        LOGGER.error(f"[{LOG_PREFIX_SETTINGS}] Cannot apply the plug & play settings: {e}", exc_info=True)

    # showing/hiding the web ui in the sidebar is a re-registration of the panel - the browser
    # picks it up through the panel update event, without a restart and without a reload
    try:
        async_apply_panel_visibility(hass, settings)
    except Exception as e:  # noqa: BLE001
        LOGGER.error(f"[{LOG_PREFIX_SETTINGS}] Cannot apply the sidebar setting: {e}", exc_info=True)

    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.data.get(CONF_HUB):
            continue                # the entry of the integration itself has no gateway
        hass.async_create_task(hass.config_entries.async_reload(entry.entry_id))
        result['reloaded_gateways'] += 1

    LOGGER.debug(f"[{LOG_PREFIX_SETTINGS}] Applied settings: {result}")
    return result


### ---------------------------------------------------------------------------
### websocket api
### ---------------------------------------------------------------------------

def register_websocket_commands(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, ws_settings_get)
    websocket_api.async_register_command(hass, ws_settings_set)
    websocket_api.async_register_command(hass, ws_settings_reset)


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required('type'): WS_SETTINGS_GET})
@callback
def ws_settings_get(hass: HomeAssistant, connection, msg) -> None:
    connection.send_result(msg['id'], get_form_descriptor(hass))


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required('type'): WS_SETTINGS_SET,
    vol.Required('settings'): dict,
})
@websocket_api.async_response
async def ws_settings_set(hass: HomeAssistant, connection, msg) -> None:
    try:
        validated = await async_set_overrides(hass, msg['settings'])
    except vol.Invalid as e:
        connection.send_error(msg['id'], 'invalid_setting', str(e))
        return

    applied = await async_apply_settings(hass)
    connection.send_result(msg['id'], {
        'settings': {str(k): v for k, v in validated.items()},
        'applied': applied,
        'form': get_form_descriptor(hass),
    })


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required('type'): WS_SETTINGS_RESET,
    vol.Required('names'): [str],
})
@websocket_api.async_response
async def ws_settings_reset(hass: HomeAssistant, connection, msg) -> None:
    removed = await async_reset_overrides(hass, msg['names'])
    applied = await async_apply_settings(hass) if removed else {}
    connection.send_result(msg['id'], {
        'reset': removed,
        'applied': applied,
        'form': get_form_descriptor(hass),
    })
