import re

from homeassistant.helpers.reload import async_integration_yaml_config
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from homeassistant.const import CONF_DEVICES, CONF_NAME, CONF_ID

from eltakobus.util import AddressExpression, b2s
from eltakobus.message import EltakoMessage
from eltakobus.eep import EEP

from ..const import (CONF_AREA, CONF_BASE_ID, CONF_DEPRECATED_ENABLE_FRONTEND,
                     CONF_DEPRECATED_ENABLE_TELEGRAM_WEB_UI, CONF_DEPRECATED_FRONTEND_DEV_URL,
                     CONF_DEVICE_TYPE, CONF_EEP, CONF_ENABLE_FRONTEND, CONF_ENABLE_TEACH_IN_BUTTONS,
                     CONF_ENABLE_TEST_PAGE, CONF_FAST_STATUS_CHANGE, CONF_GATEWAY, CONF_GATEWAY_ID,
                     CONF_GERNERAL_SETTINGS, CONF_GRAFANA_TOKEN, CONF_GRAFANA_URL,
                     CONF_LOG_ENOCEAN_TELEGRAMS, CONF_LOG_LEVEL_BUS_MESSAGES, CONF_LOG_LEVEL_DECODE_ERRORS,
                     CONF_LOG_LEVEL_INCOMING, CONF_LOG_LEVEL_OUTGOING, CONF_LOG_LEVEL_POLLING,
                     CONF_LOG_LEVEL_UNKNOWN_DEVICES, CONF_PLUG_AND_PLAY, CONF_PLUG_AND_PLAY_INTERVAL,
                     CONF_SENDER, CONF_SERIAL_PATH, CONF_SHOW_DEV_ID_IN_DEV_NAME, CONF_SHOW_PANEL_IN_SIDEBAR,
                     CONF_TELEGRAM_LOG_BACKUP_COUNT, CONF_TELEGRAM_LOG_BUFFER_SIZE,
                     CONF_TELEGRAM_LOG_DECODE_EEP, CONF_TELEGRAM_LOG_FILENAME, CONF_TELEGRAM_LOG_FORMAT,
                     CONF_TELEGRAM_LOG_INCLUDE_POLLING, CONF_TELEGRAM_LOG_MAX_FILE_SIZE_MB,
                     CONF_TELEGRAM_LOG_ROTATE_DAYS, CONF_TIMESERIES_BUCKET, CONF_TIMESERIES_ENABLED,
                     CONF_TIMESERIES_MEASUREMENT, CONF_TIMESERIES_ORG, CONF_TIMESERIES_TOKEN,
                     CONF_TIMESERIES_URL, DATA_ELTAKO, DATA_SETTINGS_OVERRIDES, DATA_UI_GATEWAYS, DOMAIN,
                     ELTAKO_CONFIG, GATEWAY_DEFAULT_NAME, LOGGER, TelegramLogFormat, TelegramLogLevel)

# default settings from configuration
DEFAULT_GENERAL_SETTINGS = {
    CONF_FAST_STATUS_CHANGE: False,
    CONF_SHOW_DEV_ID_IN_DEV_NAME: False,
    CONF_PLUG_AND_PLAY: False,
    CONF_PLUG_AND_PLAY_INTERVAL: 1440,      # once a day
    CONF_ENABLE_TEACH_IN_BUTTONS: False,
    # the web ui is where everything is configured - it must be reachable without any yaml
    CONF_ENABLE_FRONTEND: True,
    # ... and it is found by everybody when it sits in the sidebar
    CONF_SHOW_PANEL_IN_SIDEBAR: True,
    # default True while the test page is under development - switch the default
    # to False for a release
    CONF_ENABLE_TEST_PAGE: True,
    CONF_LOG_ENOCEAN_TELEGRAMS: False,
    CONF_TELEGRAM_LOG_FILENAME: "",
    CONF_TELEGRAM_LOG_FORMAT: TelegramLogFormat.JSONL.value,
    CONF_TELEGRAM_LOG_MAX_FILE_SIZE_MB: 10,
    CONF_TELEGRAM_LOG_ROTATE_DAYS: 7,
    CONF_TELEGRAM_LOG_BACKUP_COUNT: 3,
    CONF_TIMESERIES_ENABLED: False,
    CONF_TIMESERIES_URL: "",
    CONF_TIMESERIES_TOKEN: "",
    CONF_TIMESERIES_ORG: "",
    CONF_TIMESERIES_BUCKET: "eltako",
    CONF_TIMESERIES_MEASUREMENT: "eltako_telegram",
    CONF_GRAFANA_URL: "",
    CONF_GRAFANA_TOKEN: "",
    CONF_TELEGRAM_LOG_INCLUDE_POLLING: False,
    CONF_TELEGRAM_LOG_DECODE_EEP: True,
    CONF_TELEGRAM_LOG_BUFFER_SIZE: 500,
    CONF_LOG_LEVEL_INCOMING: TelegramLogLevel.OFF.value,
    CONF_LOG_LEVEL_OUTGOING: TelegramLogLevel.OFF.value,
    CONF_LOG_LEVEL_UNKNOWN_DEVICES: TelegramLogLevel.OFF.value,
    CONF_LOG_LEVEL_BUS_MESSAGES: TelegramLogLevel.OFF.value,
    CONF_LOG_LEVEL_POLLING: TelegramLogLevel.OFF.value,
    CONF_LOG_LEVEL_DECODE_ERRORS: TelegramLogLevel.OFF.value,
}

# deprecated option -> replacement (None means the option is not needed anymore)
DEPRECATED_GENERAL_SETTINGS = {
    CONF_DEPRECATED_ENABLE_FRONTEND: CONF_ENABLE_FRONTEND,
    CONF_DEPRECATED_FRONTEND_DEV_URL: None,
    CONF_DEPRECATED_ENABLE_TELEGRAM_WEB_UI: CONF_ENABLE_FRONTEND,
}

class DeviceConf(dict):
    """Object representation of config."""
    def __init__(self, config: ConfigType, extra_keys:list[str]=[]):
        # merge everything into dict
        self.update(config)

        # additionally add attributes
        self.id = config.get(CONF_ID, None)
        if self.id is not None and isinstance(self.id, str):
            self.id = AddressExpression.parse(self.id)
        self[CONF_ID] = self.id

        self.eep = config.get(CONF_EEP, None)
        if self.eep is not None:
            self.eep = EEP.find(self.eep)
        self[CONF_EEP] = self.eep

        self.name = config.get(CONF_NAME, None)
        self[CONF_NAME] = self.name

        self.area = config.get(CONF_AREA, None)
        self[CONF_AREA] = self.area

        self.base_id = config.get(CONF_BASE_ID, None)
        if self.base_id is not None:
            self.base_id = AddressExpression.parse(self.base_id)
        self[CONF_BASE_ID] = self.base_id

        self.device_type = config.get(CONF_DEVICE_TYPE, None)
        self[CONF_DEVICE_TYPE] = self.device_type

        self.gateway_id = config.get(CONF_GATEWAY_ID, None)
        self[CONF_GATEWAY_ID] = self.gateway_id

        # add extra fields
        for ek in extra_keys:
            if ek in config:
                setattr(self, ek, config.get(ek))

    def get(self, key: str, default = None):
        return super().get(key, default)

def get_device_conf(config: ConfigType, key: str, extra_keys:list[str]=[]) -> DeviceConf:
    if config is not None:
        if key in config.keys():
            return DeviceConf(config.get(key), extra_keys)
    return None

def get_general_settings_from_configuration(hass: HomeAssistant) -> dict:
    # start with a copy of the defaults so that missing options are always available
    # and the module level defaults cannot be modified by accident.
    settings = dict(DEFAULT_GENERAL_SETTINGS)
    if hass and CONF_GERNERAL_SETTINGS in hass.data[DATA_ELTAKO][ELTAKO_CONFIG]:
        settings.update( hass.data[DATA_ELTAKO][ELTAKO_CONFIG][CONF_GERNERAL_SETTINGS] )

    # Settings which were changed in the web ui override the yaml on purpose, so that the
    # integration can be configured without writing yaml. (See general_settings.py)
    if hass:
        overrides = (hass.data.get(DATA_ELTAKO, {}) or {}).get(DATA_SETTINGS_OVERRIDES, {}) or {}
        settings.update(overrides)

    # LOGGER.debug(f"General Settings: {settings}")

    return settings


def is_frontend_enabled(general_settings: dict) -> bool:
    """Return True if the web ui of the integration (incl. all its sub pages) is enabled.

    Enabled unless it was switched off explicitly - a settings dict which does not mention the
    option at all describes an installation without any configuration, and that is exactly the
    one which needs the web ui.
    """
    if general_settings.get(CONF_ENABLE_FRONTEND, DEFAULT_GENERAL_SETTINGS[CONF_ENABLE_FRONTEND]):
        return True
    # backwards compatibility for the former option name 'enable-frontend'
    return bool(general_settings.get(CONF_DEPRECATED_ENABLE_FRONTEND, False))


def is_panel_in_sidebar(general_settings: dict) -> bool:
    """Return True if the web ui gets an entry in the Home Assistant sidebar.

    Only the navigation entry - a hidden panel is still served and still reachable, e.g.
    through the 'Web UI' button on the integration page or by typing its url.
    """
    return bool(general_settings.get(CONF_SHOW_PANEL_IN_SIDEBAR,
                                     DEFAULT_GENERAL_SETTINGS[CONF_SHOW_PANEL_IN_SIDEBAR]))


def log_deprecated_general_settings(general_settings: dict) -> list[str]:
    """Log a warning for every deprecated general setting and return the ones which were found."""
    found = []
    for deprecated, replacement in DEPRECATED_GENERAL_SETTINGS.items():
        if deprecated not in general_settings:
            continue
        found.append(deprecated)
        if replacement:
            LOGGER.warning(f"General setting '{deprecated}' is deprecated. Please use '{replacement}' instead.")
        else:
            LOGGER.warning(f"General setting '{deprecated}' is deprecated and has no effect anymore. "
                           f"Please remove it from your configuration.")
    return found


async def async_get_gateway_config(hass: HomeAssistant, CONFIG_SCHEMA: dict, get_integration_config=async_integration_yaml_config) -> dict:
    config = await async_get_home_assistant_config(hass, CONFIG_SCHEMA, get_integration_config)
    # LOGGER.debug(f"config: {config}")
    if CONF_GATEWAY in config:
        if isinstance(config[CONF_GATEWAY], dict) and CONF_DEVICE_TYPE in config[CONF_GATEWAY]:
            return config[CONF_GATEWAY]
        elif len(config[CONF_GATEWAY]) > 0 and CONF_DEVICE_TYPE in config[CONF_GATEWAY][0]:
            return config[CONF_GATEWAY][0]
    return None

async def async_find_gateway_config_by_base_id(base_id: AddressExpression, hass: HomeAssistant, CONFIG_SCHEMA: dict, get_integration_config=async_integration_yaml_config) -> dict:
    config = await async_get_home_assistant_config(hass, CONFIG_SCHEMA, get_integration_config)
    if CONF_GATEWAY in config:
        for g in config[CONF_GATEWAY]:
            if g[CONF_BASE_ID].upper() == b2s(base_id):
                return g
    return None

async def async_find_gateway_config_by_id(id: int, hass: HomeAssistant, CONFIG_SCHEMA: dict, get_integration_config=async_integration_yaml_config) -> dict:
    config = await async_get_home_assistant_config(hass, CONFIG_SCHEMA, get_integration_config)
    return find_gateway_config_by_id(config, id)

def find_gateway_config_by_id(config: dict, id: int) -> dict:
    if CONF_GATEWAY in config:
        for g in config[CONF_GATEWAY]:
            if g[CONF_ID] == id:
                return g
    return None

async def async_get_gateway_config_serial_port(hass: HomeAssistant, CONFIG_SCHEMA: dict, get_integration_config=async_integration_yaml_config) -> dict:
    gateway_config = await async_get_gateway_config(hass, CONFIG_SCHEMA, get_integration_config)
    if gateway_config is not None and CONF_SERIAL_PATH in gateway_config:
        return gateway_config[CONF_SERIAL_PATH]
    return None

async def async_get_home_assistant_config(hass: HomeAssistant, CONFIG_SCHEMA: dict, get_integration_config=async_integration_yaml_config) -> dict:
    """Configuration of the integration: 'configuration.yaml' plus gateways created in the ui.

    Every consumer (config flow, gateway setup, device lookup, web ui) uses this function, so
    all of them see the same complete picture. Gateways of the yaml win, see gateway_config.py.
    """
    _conf = await get_integration_config(hass, DOMAIN)
    if not _conf or DOMAIN not in _conf:
        # no eltako section at all - the integration can be configured completely in the ui
        LOGGER.debug("No `eltako:` key found in configuration.yaml. Using defaults.")
        config = CONFIG_SCHEMA({DOMAIN: {}})[DOMAIN]
    else:
        config = _conf[DOMAIN]

    return add_ui_gateways_to_config(hass, config)


def add_ui_gateways_to_config(hass: HomeAssistant, config: dict) -> dict:
    """Merge the gateways which were created in the user interface into the configuration."""
    if hass is None:
        return config

    ui_gateways = (getattr(hass, 'data', None) or {}).get(DATA_ELTAKO, {}).get(DATA_UI_GATEWAYS, [])
    if not ui_gateways:
        return config

    from .gateway_config import merge_gateways

    merged = dict(config)
    merged[CONF_GATEWAY] = merge_gateways(config.get(CONF_GATEWAY, []) or [], ui_gateways)
    return merged

def get_device_config(config: dict, id: int) -> dict:
    # a configuration without any gateway is valid (everything can be created in the web ui),
    # so the key can be missing entirely
    gateways = (config or {}).get(CONF_GATEWAY) or []
    for g in gateways:
        if g[CONF_ID] == id:
            if CONF_DEVICES in g:
                return g[CONF_DEVICES]
            else:
                return {}
    return {}

async def async_get_list_of_gateway_descriptions(hass: HomeAssistant, CONFIG_SCHEMA: dict, get_integration_config=async_integration_yaml_config, filter_out: list[str]=[]) -> dict:
    config = await async_get_home_assistant_config(hass, CONFIG_SCHEMA, get_integration_config)
    return get_list_of_gateway_descriptions(config, filter_out)

def get_list_of_gateway_descriptions(config: dict, filter_out: list[str]=[]) -> dict:
    """Compiles a list of all gateways in config."""
    result = {}
    if CONF_GATEWAY in config:
        for g in config[CONF_GATEWAY]:
            g_id = g[CONF_ID]
            g_name = g.get(CONF_NAME, None)
            g_device_type = g[CONF_DEVICE_TYPE]
            if g_id not in filter_out:
                result[g_id] = get_gateway_name(g_name, g_device_type, g_id)
    return result

def config_check_gateway(config: dict) -> bool:
    #ids in gateway config are unique
    g_ids = []
    if CONF_GATEWAY in config:
        for g in config[CONF_GATEWAY]:
            if g[CONF_ID] in g_ids:
                return False
            g_ids.append(g[CONF_ID])

    if len(g_ids) == 0:
        return True

    return True

def parse_number_state(state: str):
    """Parse a state string of the state machine back into a number.

    Home Assistant stores states as strings, so a restored counter or measurement can
    contain a decimal point ('36231.4') even if it was written as int. Returns an int if
    the value has no fractional part (so that counters keep their type), a float if it
    has, and None if the state is not a number at all (e.g. 'open' of a window handle).
    """
    if state is None:
        return None

    try:
        value = float(str(state).strip().replace(',', '.'))
    except (TypeError, ValueError):
        return None

    if value.is_integer():
        return int(value)
    return value


def compare_enocean_ids(id1: bytes, id2: bytes, len=3) -> bool:
    """Compares two bytes arrays. len specifies the length to be checked."""
    for i in range(0,len):
        if id1[i] != id2[i]:
            return False
    return True

def simulator_serial_path(gateway_id: int) -> str:
    """'Serial port' of a simulated gateway, e.g. 'simulator-2'.

    A simulated gateway has no hardware, but a gateway is identified by its serial path
    everywhere (config entry, device registry, unique id). So it gets a stable synthetic one
    which cannot collide with a real device file. The rule itself lives in the hardware
    independent core of the simulation (simulation/core/addressing.py).
    """
    from ..simulation.core import serial_path

    return serial_path(gateway_id)


def is_simulator_serial_path(path: str) -> bool:
    from ..simulation.core import is_simulator_serial_path as is_simulated

    return is_simulated(path)


def get_gateway_name(dev_name:str, dev_type:str, dev_id: int) -> str:
    if not dev_name or len(dev_name) == 0:
        dev_name = GATEWAY_DEFAULT_NAME

    return f"{dev_name} - {dev_type} (Id: {dev_id})"


def get_device_name(dev_name: str, dev_id: AddressExpression, general_config: dict) -> str:
    if general_config[CONF_SHOW_DEV_ID_IN_DEV_NAME]:
        return f"{dev_name} ({b2s(dev_id)})"
    else:
        return dev_name

def get_id_from_gateway_name(dev_name: str) -> AddressExpression:
    return int(dev_name.split('(Id: ')[1].split(')')[0])


def get_identifier(gateway_id: int, dev_id: AddressExpression | bytes, event_id:str=None, description_key:str=None) -> str:
    id = f"{DOMAIN}_"

    ## add gateway id only for local addresses
    _dev_id = dev_id
    if dev_id is not None and isinstance(_dev_id, AddressExpression):
        _dev_id = _dev_id[0]
    if dev_id is not None and _dev_id[0:2] == b'\x00\x00':
        id += f"gw_{gateway_id}_"

    if event_id is not None:
        if not id.endswith('_'): id += '_'
        id += f"{event_id}"

    # if dev_id = 00-00-00-00 leave it away because entitiy belongs then to gateway
    if dev_id is not None and int.from_bytes(_dev_id, 'big') > 0:
        if not id.endswith('_'): id += '_'
        id += f"{b2s(dev_id, '_')}"

    if description_key is not None and description_key != '':
        if not id.endswith('_'): id += '_'
        id += f"{description_key.replace(' ', "_").replace('-', '_')}"

    return id.lower()


def sanitize_object_id(id: str) -> str:
    """Make an identifier usable as object id of an entity id.

    Home Assistant does not accept leading/trailing or repeated underscores.
    """
    result = re.sub('_+', '_', id).strip('_')
    return result if result else DOMAIN


def collect_additional_senders(config: dict) -> dict[tuple[str, str], list[dict]]:
    """Senders of wireless devices which are declared for more than one gateway.

    The radio is a virtual bus with several gateways (and repeaters) attached to it. A
    wireless device therefore gets ONE entity (see remove_duplicate_devices), but it can be
    taught into several gateways - each declaration carries the sender of its gateway.
    This collects the senders of the second and later declarations, keyed by
    (platform, device address), so that the entity can repeat every command through all
    of its gateways (commands are idempotent, telegrams arriving twice are fine).

    Must run BEFORE remove_duplicate_devices - it reads the declarations which are
    removed there.
    """
    result: dict[tuple[str, str], list[dict]] = {}
    seen: set[tuple[str, str]] = set()

    for gateway_config in config.get(CONF_GATEWAY, []) or []:
        gateway_id = gateway_config.get(CONF_ID)
        for platform, devices in (gateway_config.get(CONF_DEVICES, {}) or {}).items():
            for device in devices or []:
                dev_id = str(device.get(CONF_ID, '')).upper().split(' ')[0]
                if not dev_id or dev_id.startswith('00-00-'):
                    continue        # bus devices get one entity per gateway instead
                key = (str(platform), dev_id)
                if key not in seen:
                    seen.add(key)   # the first declaration becomes the entity
                    continue
                sender = device.get(CONF_SENDER)
                if isinstance(sender, dict) and sender.get(CONF_ID):
                    result.setdefault(key, []).append({
                        CONF_ID: str(sender[CONF_ID]),
                        CONF_EEP: sender.get(CONF_EEP),
                        CONF_GATEWAY_ID: gateway_id,
                    })
    return result


def remove_duplicate_devices(config: dict, log: bool = True) -> dict[str, list[str]]:
    """Remove device configurations which collide and report them.

    Several gateways on one bus and devices taught into more than one gateway are a
    supported setup: telegrams arriving through several gateways are fine and all commands
    are idempotent. Therefore **bus devices** (local 00-00-.. addresses) may be declared
    for more than one gateway - their unique id contains the gateway id, every declaration
    becomes its own working entity.

    Only two real collisions are removed (first declaration wins):
    * the same device declared twice for the **same** gateway
    * a **wireless** device declared for more than one gateway: its unique id carries no
      gateway id (the entity listens to the telegrams of all gateways anyway), so a second
      declaration would be rejected by Home Assistant with 'Platform eltako does not
      generate unique IDs'.
    """
    occurrences: dict[str, list[str]] = {}

    for gateway_config in config.get(CONF_GATEWAY, []) or []:
        gateway_id = gateway_config.get(CONF_ID)
        for platform, devices in (gateway_config.get(CONF_DEVICES, {}) or {}).items():
            if not devices:
                continue
            for device in list(devices):
                dev_id = device.get(CONF_ID)
                if not dev_id:
                    continue
                dev_id = str(dev_id).upper()
                # local bus addresses get one entity per gateway (unique id contains the
                # gateway id) - they only collide within the same gateway
                is_bus_device = dev_id.startswith('00-00-')
                key = f"{platform}/{dev_id}" + (f"@gw{gateway_id}" if is_bus_device else "")
                if key in occurrences:
                    devices.remove(device)      # keep the first declaration only
                occurrences.setdefault(key, []).append(f"gateway {gateway_id}")

    duplicates = {key: sources for key, sources in occurrences.items() if len(sources) > 1}
    if log:
        for key, sources in duplicates.items():
            platform, dev_id = key.split('/', 1)
            if '@gw' in dev_id:
                dev_id = dev_id.split('@gw', 1)[0]
                LOGGER.warning(f"Device '{dev_id}' is configured {len(sources)} times as {platform} "
                               f"on the same gateway ({sources[0]}). Only the first declaration "
                               f"is used, please remove the duplicates.")
            else:
                LOGGER.info(f"Wireless device '{dev_id}' is configured {len(sources)} times as "
                            f"{platform} ({', '.join(sources)}). The radio is one virtual bus, so "
                            f"one entity is created (declaration of {sources[0]}) - it receives "
                            f"through all gateways and repeats its commands through every gateway "
                            f"with a declared sender.")
    return duplicates


def get_bus_event_type(gateway_id: int, function_id: str, source_id: AddressExpression | bytes=None, description_key:str=None) -> str:
    return get_identifier(gateway_id, source_id, function_id, description_key)

def get_device_id(gateway_id:int, dev_id: AddressExpression | bytes, description_key:str=None) -> str:
    return get_identifier(gateway_id, dev_id, event_id=None, description_key=description_key)

def convert_button_pos_from_hex_to_str(pos: int) -> str:
    if pos == 0x10:
        return "LB"
    if pos == 0x30:
        return "LT"
    if pos == 0x70:
        return "RT"
    if pos == 0x50:
        return "RB"
    return None

def convert_button_abbreviation(buttons:list[str]) -> list[str]:
    result = []
    for b in buttons:
        if b.upper() == "LB":
            result.append("Left Bottom")
        elif b.upper() == "LT":
            result.append("Left Top")
        elif b.upper() == "RB":
            result.append("Right Bottom")
        elif b.upper() == "RT":
            result.append("Right Top")
    return result

def button_abbreviation_to_str(buttons:list[str]) -> list[str]:
    return ', '.join(convert_button_abbreviation(buttons))

def address_to_str(value) -> str | int | None:
    """Convert an address like field of a telegram into a string.

    Bus messages (discovery, memory, polling) report the position on the bus as int instead of
    an EnOcean address. b2s() cannot handle that and raises a TypeError, so every field which
    can be either has to go through this function.
    """
    if value is None:
        return None
    if isinstance(value, (bytes, bytearray, AddressExpression)):
        return b2s(value)
    if isinstance(value, int):
        return value
    return str(value)


def telegram2json(telegram: EltakoMessage, local_telegram: EltakoMessage = None) -> dict:
    result = {}
    result['msg_type'] = telegram.__class__.__name__
    if hasattr(telegram, 'address'):
        if isinstance(telegram.address, int): result['address'] = telegram.address
        else: result['address'] = b2s(telegram.address)
    if hasattr(telegram, 'org'): result['org'] = telegram.org
    if hasattr(telegram, 'is_request'): result['is_request'] = telegram.is_request
    if hasattr(telegram, 'data'): result['data'] = address_to_str(telegram.data)
    if hasattr(telegram, 'payload'): result['payload'] = address_to_str(telegram.payload)
    # Bus messages report the position on the bus as int instead of an EnOcean address.
    # b2s() would raise a TypeError for those, which used to kill the serial reader thread.
    if hasattr(telegram, 'reported_address'): result['reported_address'] = address_to_str(telegram.reported_address)
    if hasattr(telegram, 'reported_size'): result['reported_size'] = telegram.reported_size
    if hasattr(telegram, 'memory_size'): result['memory_size'] = telegram.memory_size
    if hasattr(telegram, 'model'): result['model'] = address_to_str(telegram.model)
    if hasattr(telegram, 'is_fam'): result['is_fam'] = telegram.is_fam
    if hasattr(telegram, 'row'): result['row'] = telegram.row

    if local_telegram and hasattr(local_telegram, 'address'):
        if isinstance(local_telegram.address, int): result['local_address'] = local_telegram.address
        else: result['local_address'] = b2s(local_telegram.address)

    return result
