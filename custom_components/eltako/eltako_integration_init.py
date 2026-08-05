"""Support for Eltako devices."""
import os

from homeassistant.components.http import HomeAssistantView, StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ID, CONF_NAME
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.dispatcher import dispatcher_connect
from homeassistant.helpers.reload import async_reload_integration_platforms
from homeassistant.components.frontend import async_register_built_in_panel
from homeassistant.components.http import StaticPathConfig
from homeassistant.components import panel_custom, websocket_api
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er, device_registry as dr, entity_platform as pl


from .const import *
from .virtual_network_gateway import VirtualNetworkGateway, VIRT_GW_PORT
from .schema import CONFIG_SCHEMA
from . import config_helpers
from .gateway import *
from .websocket import register_websockets
from .enocean_logger import async_setup_telegram_logger, is_telegram_logging_enabled
from . import device_config
from . import device_activity
from . import general_settings
from . import gateway_scan
from . import gateway_config
from . import config_import
from . import bus_members
from . import device_tests
from . import plug_and_play

LOG_PREFIX_INIT = "Eltako Integration Setup"

async def async_setup(hass: HomeAssistant, config_type: ConfigType) -> bool:
    """Set up the Eltako component."""
    LOGGER.info(f"[{LOG_PREFIX_INIT}] Initialize Home Assistant Eltako Integration: https://github.com/grimmpp/home-assistant-eltako")

    if DATA_ELTAKO not in hass.data:
        hass.data[DATA_ELTAKO] = {}

    # Migrage existing gateway configs / ESP2 was removed in the name
    migrate_old_gateway_descriptions(hass)

    # Gateways which were created in the web ui. Must be loaded before the configuration is
    # read, because they are merged into it.
    await gateway_config.async_load_ui_gateways(hass)

    # Read the config
    LOGGER.debug(f"[{LOG_PREFIX_INIT}] Load Config")
    config = await config_helpers.async_get_home_assistant_config(hass, CONFIG_SCHEMA)
    LOGGER.debug(f"[{LOG_PREFIX_INIT}] Config: {config}")
    hass.data[DATA_ELTAKO] = hass.data.setdefault(DATA_ELTAKO, {})
    hass.data[DATA_ELTAKO][ELTAKO_CONFIG] = config

    # Settings which were changed in the web ui. Must be loaded before the settings are read.
    await general_settings.async_load_overrides(hass)

    general_settings_values = config_helpers.get_general_settings_from_configuration(hass)
    config_helpers.log_deprecated_general_settings(general_settings_values)
    # the radio is a virtual bus with several gateways: a wireless device taught into more
    # than one gateway gets one entity, but its commands are repeated through all of them
    hass.data[DATA_ELTAKO][DATA_ADDITIONAL_SENDERS] = config_helpers.collect_additional_senders(config)
    config_helpers.remove_duplicate_devices(config)

    LOGGER.info("f[{LOG_PREFIX_INIT}] Register websocket extension.")
    await register_websockets(hass, config_type)
    device_config.register_websocket_commands(hass)
    general_settings.register_websocket_commands(hass)
    gateway_scan.register_websocket_commands(hass)
    gateway_config.register_websocket_commands(hass)
    config_import.register_websocket_commands(hass)
    # functional device tests (burst, cover travel times) - they run against the gateways
    # of this runtime, so they work in Home Assistant as well as standalone
    device_tests.register_websocket_commands(hass)

    # Devices on the RS485 bus, detected passively from the traffic. Restores the memory
    # images of the last scan, so the taught-in senders are known without locking the bus.
    await bus_members.async_setup_registry(hass)

    # Long term activity of all EnOcean addresses (independent of the telegram logging)
    await device_activity.async_setup_activity_tracker(hass)

    # Recording, statistics and live view of all EnOcean telegrams
    await async_setup_telegram_logger(hass, general_settings_values)

    # Plug & play: detects gateways which are plugged in, reads their bus and adds the devices
    # which can be identified without any doubt. Off by default (general setting 'plug_and_play').
    await plug_and_play.async_setup_detection(hass, general_settings_values)

    # Web ui of the integration incl. all its sub pages (overview, telegram log, about, ...)
    await async_register_frontend(hass, general_settings_values)

    LOGGER.info(f"[{LOG_PREFIX_INIT}] Eltako Integration initiallized. ... loading device configuration")

    return True

class EltakoFrontendView(HomeAssistantView):
    """Serves custom_components/eltako/frontend with an explicit no-cache header.

    The folder contains frontend code only (plain javascript modules, no build step), so it can
    be served completely. Requests are contained inside it - a path which escapes the folder
    (../) is rejected instead of read.
    """

    url = PANEL_STATIC_URL + "/{path:.*}"
    name = "eltako:frontend"
    requires_auth = False       # the browser loads the modules without the auth header

    def __init__(self, root: str):
        self._root = os.path.realpath(root)

    async def get(self, request, path: str):
        return self._serve(path)

    async def head(self, request, path: str):
        return self._serve(path)

    def _serve(self, path: str):
        from aiohttp import web

        target = os.path.realpath(os.path.join(self._root, path))
        if target != self._root and not target.startswith(self._root + os.sep):
            return web.Response(status=404)
        if not os.path.isfile(target):
            return web.Response(status=404)

        return web.FileResponse(target, headers={
            'Cache-Control': 'no-cache, must-revalidate',
        })


async def async_register_frontend(hass: HomeAssistant, general_settings: dict) -> None:
    """Register the web ui of this integration.

    The frontend is part of the integration (folder 'frontend', plain javascript modules,
    no build step and no additional package). It contains all sub pages: overview,
    EnOcean telegram log, device statistics, unknown devices and about.
    """
    if not config_helpers.is_frontend_enabled(general_settings):
        LOGGER.info(f"[{LOG_PREFIX_INIT}] Web ui is switched off by the configuration. "
                    f"(Remove '{CONF_ENABLE_FRONTEND}: False' from '{CONF_GERNERAL_SETTINGS}' "
                    f"to get it back - it is on by default.)")
        return

    try:
        # The folder contains frontend code only, therefore it can be served completely.
        static_path = os.path.join(os.path.dirname(__file__), "frontend")

        # Serve it through our own view instead of async_register_static_paths:
        # cache_headers=False only means "do not add long lived cache headers", the response
        # then carries ETag/Last-Modified only. Browsers cache ES modules heuristically from
        # Last-Modified and do NOT revalidate, so an edited page of the web ui stays invisible
        # until a hard reload. The view sends an explicit no-cache instead.
        hass.http.register_view(EltakoFrontendView(static_path))

        await panel_custom.async_register_panel(
            hass=hass,
            frontend_url_path=PANEL_URL_PATH,
            webcomponent_name=PANEL_WEBCOMPONENT,
            sidebar_title=PANEL_TITLE,
            sidebar_icon=PANEL_ICON,
            module_url=f"{PANEL_STATIC_URL}/{PANEL_JS_FILE}",
            embed_iframe=False,
            require_admin=True,
        )

        LOGGER.info(f"[{LOG_PREFIX_INIT}] Registered web ui under '/{PANEL_URL_PATH}'.")

        if not is_telegram_logging_enabled(general_settings):
            LOGGER.info(f"[{LOG_PREFIX_INIT}] Telegram recording is disabled. The telegram pages of the "
                        f"web ui stay empty until '{CONF_LOG_ENOCEAN_TELEGRAMS}: True' is configured.")

    except Exception as e:
        LOGGER.error(f"[{LOG_PREFIX_INIT}] Cannot register web ui: {e}", exc_info=True)


def print_subfolders(folder: str):
    LOGGER.debug(f"[{LOG_PREFIX_INIT}] print subfolders of '{folder}':  \n  {os.listdir(folder)}")

def print_config_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    LOGGER.debug("ConfigEntry")
    LOGGER.debug("- tilte: %s", config_entry.title)
    LOGGER.debug("- domain: %s", config_entry.domain)
    LOGGER.debug("- unique_id: %s", config_entry.unique_id)
    LOGGER.debug("- version: %s", config_entry.version)
    LOGGER.debug("- entry_id: %s", config_entry.entry_id)
    LOGGER.debug("- state: %s", config_entry.state)
    for k in config_entry.data.keys():
        LOGGER.debug("- data %s - %s", k, config_entry.data.get(k, ''))

    if DATA_ELTAKO in hass.data:
        LOGGER.debug("Available Eltako Objects")
        for g in hass.data[DATA_ELTAKO]:
            LOGGER.debug(g)

# relevant for higher than v.1.3.4: removed 'ESP2' from GATEWAY_DEFAULT_NAME which is still in OLD_GATEWAY_DEFAULT_NAME
def migrate_old_gateway_descriptions(hass: HomeAssistant):
    LOGGER.debug(f"[{LOG_PREFIX_INIT}] Provide new and old gateway descriptions/id for smooth version upgrades.")
    migration_dict:dict = {}
    if DATA_ELTAKO in hass.data:
        for key in hass.data[DATA_ELTAKO].keys():
            # LOGGER.debug(f"[{LOG_PREFIX}] Check description: {key}")
            if GATEWAY_DEFAULT_NAME in key:
                old_key = key.replace(GATEWAY_DEFAULT_NAME, OLD_GATEWAY_DEFAULT_NAME)
                LOGGER.info(f"[{LOG_PREFIX_INIT}] Support downwards compatibility => from new gateway description '{key}' to old description '{old_key}'")
                migration_dict[old_key] = hass.data[DATA_ELTAKO][key]
                # del hass.data[DATA_ELTAKO][key]
            if OLD_GATEWAY_DEFAULT_NAME in key:
                new_key = key.replace(OLD_GATEWAY_DEFAULT_NAME, GATEWAY_DEFAULT_NAME)
                LOGGER.info(f"[{LOG_PREFIX_INIT}] Migrate gateway from old description '{key}' to new description '{new_key}'")
                migration_dict[new_key] = hass.data[DATA_ELTAKO][key]
        # prvide either new or old key in parallel
        for key in migration_dict:
            hass.data[DATA_ELTAKO][key] = migration_dict[key]

    LOGGER.debug(f"[{LOG_PREFIX_INIT}] Migration routine completed.")


def get_gateway_from_hass(hass: HomeAssistant, config_entry: ConfigEntry) -> EnOceanGateway:

    g_id = "gateway_"+str(config_helpers.get_id_from_gateway_name(config_entry.data[CONF_GATEWAY_DESCRIPTION]))
    if g_id in hass.data[DATA_ELTAKO]:
        return hass.data[DATA_ELTAKO][g_id]
    else:
        return None


def set_gateway_to_hass(hass: HomeAssistant, gateway: EnOceanGateway) -> None:

    g_id = "gateway_"+str(gateway.dev_id)
    hass.data[DATA_ELTAKO][g_id] = gateway

def unload_gateway(hass: HomeAssistant, config_entry: ConfigEntry) -> None:

    gateway:EnOceanGateway = get_gateway_from_hass(hass, config_entry)
    if gateway is not None:

        LOGGER.info(f"[{LOG_PREFIX_INIT}] Unload {gateway.dev_name} and all its supported devices!")
        gateway.unload()
    
        gw_id = "gateway_"+str(gateway.dev_id)
        if gw_id in hass.data[DATA_ELTAKO]:
            del hass.data[DATA_ELTAKO][gw_id]
        # because of legacy
        if gateway.dev_name in hass.data[DATA_ELTAKO]:
            del hass.data[DATA_ELTAKO][gateway.dev_name]


def get_device_config_for_gateway(hass: HomeAssistant, config_entry: ConfigEntry, gateway: EnOceanGateway) -> ConfigType:
    """Devices of this gateway from 'configuration.yaml' and from the web ui.

    All platforms use this function, so both sources are always treated equally.
    """
    yaml_devices = config_helpers.get_device_config(hass.data[DATA_ELTAKO][ELTAKO_CONFIG], gateway.dev_id)
    return device_config.get_merged_device_config(hass, config_entry, yaml_devices)


async def async_setup_hub_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up the gateway-less entry of the integration itself.

    'Add integration' creates this one without asking for anything. It exists so that Home
    Assistant sets the component up at all - that is what brings the web ui into the sidebar
    and the websocket api behind it. From there gateways and devices are configured
    graphically, or in `configuration.yaml` for whoever prefers files.

    Right after it was added the detection runs once, so a gateway which is plugged in shows up
    on its own. The flag is set by the config flow and consumed here: repeating this on every
    restart would lock the RS485 bus for minutes every time. Afterwards the detection is
    controlled by the general setting `plug_and_play` and by the button on the overview page.
    """
    LOGGER.info(f"[{LOG_PREFIX_INIT}] Integration set up. The web ui is in the sidebar, "
                f"gateways and devices are configured there.")

    if hass.data.setdefault(DATA_ELTAKO, {}).pop(DATA_INITIAL_DETECTION, False):
        LOGGER.info(f"[{LOG_PREFIX_INIT}] Looking for gateways which are connected.")
        hass.async_create_task(plug_and_play.async_run(hass))

    return True


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up an Eltako gateway for the given entry."""
    LOGGER.info(f"[{LOG_PREFIX_INIT}] Start gateway setup.")
    print_config_entry(hass, config_entry)

    # Check domain
    if config_entry.domain != DOMAIN:
        LOGGER.warning(f"[{LOG_PREFIX_INIT}] Ooops, received configuration entry of wrong domain "
                       f"'{config_entry.domain}' (expected: '{DOMAIN}')!")
        return False

    # The entry of the integration itself: it carries no gateway. Everything it provides - the
    # web ui, the websocket api, the detection - was already set up in async_setup(), so there
    # is nothing to do here. Gateways get their own entries.
    if config_entry.data.get(CONF_HUB):
        return await async_setup_hub_entry(hass, config_entry)


    # Read the config
    config = await config_helpers.async_get_home_assistant_config(hass, CONFIG_SCHEMA)

    # Check if gateway ids are unique
    if not config_helpers.config_check_gateway(config):
        raise Exception(f"[{LOG_PREFIX_INIT}] Gateway Ids are not unique.")


    # devices which are declared for more than one gateway would result in entities with
    # duplicated unique ids. (Already reported during async_setup, therefore no logging here.)
    config_helpers.remove_duplicate_devices(config, log=False)

    # set config for global access
    eltako_data = hass.data.setdefault(DATA_ELTAKO, {})
    eltako_data[ELTAKO_CONFIG] = config
    # print whole eltako configuration
    LOGGER.debug(f"[{LOG_PREFIX_INIT}] config: {config}\n")

    
    general_settings_values = config_helpers.get_general_settings_from_configuration(hass)
    # Initialise the gateway
    # get base_id from user input
    if CONF_GATEWAY_DESCRIPTION not in config_entry.data.keys():
        LOGGER.warning(f"[{LOG_PREFIX_INIT}] Ooops, device information for gateway is not available. Try to delete and recreate the gateway.")
        return False
    gateway_description = config_entry.data[CONF_GATEWAY_DESCRIPTION]    # from user input

    if not ('(' in gateway_description and ')' in gateway_description):
        LOGGER.warning(f"[{LOG_PREFIX_INIT}] Ooops, no base id of gateway available. Try to delete and recreate the gateway.")
        return False
    
    gateway_id = config_helpers.get_id_from_gateway_name(gateway_description)

    # get home assistant configuration section matching base_id
    gateway_conf = await config_helpers.async_find_gateway_config_by_id(gateway_id, hass, CONFIG_SCHEMA)
    if not gateway_conf:
        LOGGER.warning(f"[{LOG_PREFIX_INIT}] Ooops, no gateway configuration found in '/homeassistant/configuration.yaml'.")
        return False
    
    # get serial path info
    if CONF_SERIAL_PATH not in config_entry.data.keys():
        LOGGER.warning(f"[{LOG_PREFIX_INIT}] Ooops, no information about serial path available for gateway.")
        return False
    gateway_serial_path = config_entry.data[CONF_SERIAL_PATH]

    # only transceiver can send teach-in telegrams
    gateway_device_type = GatewayDeviceType.find(gateway_conf[CONF_DEVICE_TYPE])    # from configuration
    if gateway_device_type is None:
        LOGGER.error(f"[{LOG_PREFIX_INIT}] USB device {gateway_conf[CONF_DEVICE_TYPE]} is not supported!!!")
        return False
    if GatewayDeviceType.is_lan_gateway(gateway_device_type):
        if gateway_conf.get(CONF_GATEWAY_ADDRESS, None) is None:
            raise Exception(f"[{LOG_PREFIX_INIT}] Missing field '{CONF_GATEWAY_ADDRESS}' for LAN Gateway (id: {gateway_id})")

    general_settings_values[CONF_ENABLE_TEACH_IN_BUTTONS] = True # GatewayDeviceType.is_transceiver(gateway_device_type) # should only be disabled for decentral gateways

    # The kernel renumbers /dev/ttyUSB* when sticks are re-plugged. If the configured port is
    # gone, follow the stick by its usb serial number so that reception does not silently die.
    if not GatewayDeviceType.is_lan_gateway(gateway_device_type):
        gateway_serial_path = await gateway_scan.async_resolve_serial_path(
            hass, gateway_id, gateway_device_type, gateway_serial_path)

    LOGGER.info(f"[{LOG_PREFIX_INIT}] Initializes Gateway Device '{gateway_description}'")
    gateway_name = gateway_conf.get(CONF_NAME, None)  # from configuration
    baud_rate= BAUD_RATE_DEVICE_TYPE_MAPPING[gateway_device_type]
    port = gateway_conf.get(CONF_GATEWAY_PORT, VIRT_GW_PORT if gateway_device_type == GatewayDeviceType.VirtualNetworkAdapter else 5100)
    auto_reconnect = gateway_conf.get(CONF_GATEWAY_AUTO_RECONNECT, True)
    gateway_base_id = AddressExpression.parse(gateway_conf[CONF_BASE_ID])
    message_delay = gateway_conf.get(CONF_GATEWAY_MESSAGE_DELAY, None)
    LOGGER.debug(f"[{LOG_PREFIX_INIT}] id: {gateway_id}, device type: {gateway_device_type}, serial path: {gateway_serial_path}, baud rate: {baud_rate}, base id: {gateway_base_id}")
    
    if gateway_device_type == GatewayDeviceType.VirtualNetworkAdapter:
        gateway = VirtualNetworkGateway(general_settings_values, hass, gateway_id, port, config_entry)
    else:
        gateway = EnOceanGateway(general_settings_values, hass, gateway_id, gateway_device_type, gateway_serial_path, baud_rate, port, gateway_base_id, gateway_name, auto_reconnect, message_delay, config_entry)

    
    # gateways query their base id from the hardware after the connection is up - persist
    # the answer for gateways created in the web ui, so nobody has to know the base id upfront
    async def _persist_reported_base_id(base_id):
        try:
            await gateway_config.async_update_gateway_base_id(hass, gateway.dev_id, b2s(base_id[0]))
        except Exception as e:  # noqa: BLE001 - persisting is a convenience, never break reception
            LOGGER.warning(f"[{LOG_PREFIX_INIT}] Cannot store the reported base id: {e}")
    gateway.add_base_id_change_handler(_persist_reported_base_id)

    await gateway.async_setup()
    set_gateway_to_hass(hass, gateway)

    hass.data[DATA_ELTAKO][DATA_ENTITIES] = {}
    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)

    # Devices created in the web ui are stored in the options of this entry. Reloading on
    # change makes them appear (or disappear) without restarting Home Assistant.
    config_entry.async_on_unload(config_entry.add_update_listener(async_reload_entry))

    return True


async def async_reload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Reload the gateway when its options (e.g. devices created in the web ui) changed."""
    LOGGER.debug(f"[{LOG_PREFIX_INIT}] Options of {config_entry.title} changed. Reload gateway.")
    await hass.config_entries.async_reload(config_entry.entry_id)


async def async_remove_config_entry_device(hass: HomeAssistant, config_entry: ConfigEntry,
                                           device_entry: dr.DeviceEntry) -> bool:
    """Allow deleting a device in the Home Assistant ui.

    Devices which were created in the web ui are removed from the configuration as well.
    Devices of 'configuration.yaml' cannot be deleted here - they would come back with the
    next reload, so the user is pointed to the yaml instead. Left over devices (their
    configuration is already gone) can always be removed.
    """
    addresses = {identifier for domain, identifier in device_entry.identifiers if domain == DOMAIN}

    # the entry of the integration itself owns no device - nothing here can belong to it
    if config_entry.data.get(CONF_HUB):
        return True

    yaml_devices = config_helpers.get_device_config(
        hass.data[DATA_ELTAKO][ELTAKO_CONFIG], config_helpers.get_id_from_gateway_name(
            config_entry.data[CONF_GATEWAY_DESCRIPTION]))
    for platform, devices in (yaml_devices or {}).items():
        for device in devices or []:
            if str(device.get(CONF_ID, '')).upper() in {a.upper() for a in addresses}:
                LOGGER.warning(f"[{LOG_PREFIX_INIT}] Device {addresses} is declared in configuration.yaml "
                               f"as {platform} and cannot be deleted here. Please remove it from the yaml.")
                return False

    ui_devices = device_config.get_ui_devices(config_entry)
    for platform, devices in ui_devices.items():
        for device in list(devices):
            if str(device.get(CONF_ID, '')).upper() in {a.upper() for a in addresses}:
                await device_config.async_remove_ui_device(hass, config_entry, platform, device[CONF_ID])
                LOGGER.info(f"[{LOG_PREFIX_INIT}] Removed device {addresses} from the web ui configuration.")
                return True

    LOGGER.info(f"[{LOG_PREFIX_INIT}] Removed left over device {addresses}.")
    return True


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Unload Eltako config entry."""

    # the entry of the integration itself has no gateway and no platforms
    if config_entry.data.get(CONF_HUB):
        return True

    # The platforms need to be unloaded as well, otherwise a reload would add all entities
    # a second time.
    unload_ok = await hass.config_entries.async_unload_platforms(config_entry, PLATFORMS)

    unload_gateway(hass, config_entry)

    return unload_ok
