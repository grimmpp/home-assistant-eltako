"""Support for Eltako devices."""
import os

from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.dispatcher import dispatcher_connect
from homeassistant.helpers.reload import async_reload_integration_platforms
from homeassistant.components.frontend import async_register_built_in_panel
from homeassistant.components.http import StaticPathConfig
from homeassistant.components import panel_custom, websocket_api
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er, device_registry as dr, entity_platform as pl
from importlib.resources import files


from .const import *
from .virtual_network_gateway import VirtualNetworkGateway, VIRT_GW_PORT
from .schema import CONFIG_SCHEMA
from . import config_helpers
from .gateway import *
from .frontend.info_page_view import InfoPageView
from .websocket import register_websockets
from .enocean_logger import async_setup_telegram_logger, is_telegram_logging_enabled

import home_assistant_eltako_frontend as eltako_frontend

LOG_PREFIX_INIT = "Eltako Integration Setup"

async def async_setup(hass: HomeAssistant, config_type: ConfigType) -> bool:
    """Set up the Eltako component."""
    LOGGER.info(f"[{LOG_PREFIX_INIT}] Initialize Home Assistant Eltako Integration: https://github.com/grimmpp/home-assistant-eltako")

    if DATA_ELTAKO not in hass.data:
        hass.data[DATA_ELTAKO] = {}

    # Migrage existing gateway configs / ESP2 was removed in the name
    migrate_old_gateway_descriptions(hass)

    # Read the config
    LOGGER.debug(f"[{LOG_PREFIX_INIT}] Load Config")
    config = await config_helpers.async_get_home_assistant_config(hass, CONFIG_SCHEMA)
    LOGGER.debug(f"[{LOG_PREFIX_INIT}] Config: {config}")
    hass.data[DATA_ELTAKO] = hass.data.setdefault(DATA_ELTAKO, {})
    hass.data[DATA_ELTAKO][ELTAKO_CONFIG] = config
    general_settings = config_helpers.get_general_settings_from_configuration(hass)

    LOGGER.info("f[{LOG_PREFIX_INIT}] Register websocket extension.")
    await register_websockets(hass, config_type)

    # Recording, statistics and live view of all EnOcean telegrams
    await async_setup_telegram_logger(hass, general_settings)
    await async_register_telegram_log_panel(hass, general_settings)

    # hass.http.register_static_path(
    #     "/eltako",
    #     # hass.config.path("custom_components/eltako/frontend/index.html"),
    #     os.path.join(os.path.dirname(__file__), "frontend"),
    #     cache_headers=False,
    # )

    # hass.http.register_view(InfoPageView())

    # # Register the sidebar panel
    # hass.components.frontend.async_register_built_in_panel(
    #     component_name="iframe",  # Use "iframe" to embed the custom view
    #     sidebar_title="Eltako",  # Title shown in the sidebar
    #     sidebar_icon="mdi:bus-electric",  # Icon for the sidebar
    #     frontend_url_path="",  # URL path for the sidebar
    #     config={
    #         "url": "/eltako"  # Path to your custom view
    #     },
    #     require_admin=True  # Whether the panel requires admin privileges
    # )
    
    if general_settings[CONF_ENABLE_FRONTEND]:
        LOGGER.debug(f"[{LOG_PREFIX_INIT}] Enable and register frontend.")

        if len(general_settings[CONF_FRONTEND_DEV_URL]) > 0:
            LOGGER.debug(f"[{LOG_PREFIX_INIT}] Link frontend of dev server: {general_settings[CONF_FRONTEND_DEV_URL]}")

            # Use separately running dev server
            hass.components.frontend.async_register_built_in_panel(
                component_name="iframe",  # Use iframe to embed the view
                sidebar_title="Eltako",  # Title in the sidebar
                sidebar_icon="mdi:bus-electric", # mdi:view-dashboard",  # Icon for the sidebar
                frontend_url_path="eltako",  # URL in the sidebar
                
                config={
                    # "url": "http://localhost:5173"  # URL served by the view
                    "url": general_settings[CONF_FRONTEND_DEV_URL]  # URL served by the view
                },
                require_admin=True,
            )

        else:
            LOGGER.debug(f"[{LOG_PREFIX_INIT}] Register frontend and load from package 'home-assistant-eltako-frontend'.")

            static_path = str(files("home_assistant_eltako_frontend") / "static")
            LOGGER.debug(f"[{LOG_PREFIX_INIT}] Load static path from resource_filename: {static_path}")

            # Include frontend from library
            await hass.http.async_register_static_paths([
                StaticPathConfig(
                    "/eltako",
                    path=static_path,
                    cache_headers=False
                )])
            
            LOGGER.debug(f"[{LOG_PREFIX_INIT}] Register webcomponent '{eltako_frontend.webcomponent_name}' under '/eltako' with js module '{eltako_frontend.module_url}'")

            await panel_custom.async_register_panel(
                hass=hass,
                frontend_url_path="eltako",
                webcomponent_name=eltako_frontend.webcomponent_name,
                sidebar_title="eltako",
                sidebar_icon="mdi:bus-electric",
                module_url=eltako_frontend.module_url, 
                config={
                    "url": "/eltako"  # Path to your custom view
                },
                embed_iframe=False,
                require_admin=True,
                # config_panel_domain=DOMAIN,
            )

    LOGGER.info(f"[{LOG_PREFIX_INIT}] Eltako Integration initiallized. ... loading device configuration")

    return True

async def async_register_telegram_log_panel(hass: HomeAssistant, general_settings: dict) -> None:
    """Register the web ui which shows device statistics and a live view of all telegrams.

    The panel is part of this integration (no build step, no additional package) and is
    only registered if telegram recording and the web ui are enabled.
    """
    if not general_settings.get(CONF_ENABLE_TELEGRAM_WEB_UI, True):
        LOGGER.debug(f"[{LOG_PREFIX_INIT}] EnOcean telegram web ui is disabled.")
        return

    if not is_telegram_logging_enabled(general_settings):
        LOGGER.debug(f"[{LOG_PREFIX_INIT}] EnOcean telegram web ui not registered because telegram "
                     f"recording is disabled. (Enable it with '{CONF_LOG_ENOCEAN_TELEGRAMS}: True'.)")
        return

    try:
        # only the panel itself is served as static file (not the whole frontend folder)
        js_file_path = os.path.join(os.path.dirname(__file__), "frontend", TELEGRAM_PANEL_JS_FILE)
        await hass.http.async_register_static_paths([
            StaticPathConfig(
                TELEGRAM_PANEL_JS_URL,
                path=js_file_path,
                cache_headers=False,
            )])

        await panel_custom.async_register_panel(
            hass=hass,
            frontend_url_path=TELEGRAM_PANEL_URL_PATH,
            webcomponent_name=TELEGRAM_PANEL_WEBCOMPONENT,
            sidebar_title=TELEGRAM_PANEL_TITLE,
            sidebar_icon=TELEGRAM_PANEL_ICON,
            module_url=TELEGRAM_PANEL_JS_URL,
            embed_iframe=False,
            require_admin=True,
        )

        LOGGER.info(f"[{LOG_PREFIX_INIT}] Registered EnOcean telegram web ui under '/{TELEGRAM_PANEL_URL_PATH}'.")

    except Exception as e:
        LOGGER.error(f"[{LOG_PREFIX_INIT}] Cannot register EnOcean telegram web ui: {e}", exc_info=True)


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
    return config_helpers.get_device_config(hass.data[DATA_ELTAKO][ELTAKO_CONFIG], gateway.dev_id)


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up an Eltako gateway for the given entry."""
    LOGGER.info(f"[{LOG_PREFIX_INIT}] Start gateway setup.")
    print_config_entry(hass, config_entry)

    # Check domain
    if config_entry.domain != DOMAIN:
        LOGGER.warning(f"[{LOG_PREFIX_INIT}] Ooops, received configuration entry of wrong domain '%s' (expected: '')!", config_entry.domain, DOMAIN)
        return

    
    # Read the config
    config = await config_helpers.async_get_home_assistant_config(hass, CONFIG_SCHEMA)

    # Check if gateway ids are unique
    if not config_helpers.config_check_gateway(config):
        raise Exception(f"[{LOG_PREFIX_INIT}] Gateway Ids are not unique.")


    # set config for global access
    eltako_data = hass.data.setdefault(DATA_ELTAKO, {})
    eltako_data[ELTAKO_CONFIG] = config
    # print whole eltako configuration
    LOGGER.debug(f"[{LOG_PREFIX_INIT}] config: {config}\n")

    
    general_settings = config_helpers.get_general_settings_from_configuration(hass)
    # Initialise the gateway
    # get base_id from user input
    if CONF_GATEWAY_DESCRIPTION not in config_entry.data.keys():
        LOGGER.warning("[{LOG_PREFIX}] Ooops, device information for gateway is not available. Try to delete and recreate the gateway.")
        return
    gateway_description = config_entry.data[CONF_GATEWAY_DESCRIPTION]    # from user input

    if not ('(' in gateway_description and ')' in gateway_description):
        LOGGER.warning("[{LOG_PREFIX}] Ooops, no base id of gateway available. Try to delete and recreate the gateway.")
        return
    
    gateway_id = config_helpers.get_id_from_gateway_name(gateway_description)

    # get home assistant configuration section matching base_id
    gateway_config = await config_helpers.async_find_gateway_config_by_id(gateway_id, hass, CONFIG_SCHEMA)
    if not gateway_config:
        LOGGER.warning(f"[{LOG_PREFIX_INIT}] Ooops, no gateway configuration found in '/homeassistant/configuration.yaml'.")
        return
    
    # get serial path info
    if CONF_SERIAL_PATH not in config_entry.data.keys():
        LOGGER.warning("[{LOG_PREFIX}] Ooops, no information about serial path available for gateway.")
        return
    gateway_serial_path = config_entry.data[CONF_SERIAL_PATH]

    # only transceiver can send teach-in telegrams
    gateway_device_type = GatewayDeviceType.find(gateway_config[CONF_DEVICE_TYPE])    # from configuration
    if gateway_device_type is None:
        LOGGER.error(f"[{LOG_PREFIX_INIT}] USB device {gateway_config[CONF_DEVICE_TYPE]} is not supported!!!")
        return False
    if GatewayDeviceType.is_lan_gateway(gateway_device_type):
        if gateway_config.get(CONF_GATEWAY_ADDRESS, None) is None:
            raise Exception(f"[{LOG_PREFIX_INIT}] Missing field '{CONF_GATEWAY_ADDRESS}' for LAN Gateway (id: {gateway_id})")

    general_settings[CONF_ENABLE_TEACH_IN_BUTTONS] = True # GatewayDeviceType.is_transceiver(gateway_device_type) # should only be disabled for decentral gateways

    LOGGER.info(f"[{LOG_PREFIX_INIT}] Initializes Gateway Device '{gateway_description}'")
    gateway_name = gateway_config.get(CONF_NAME, None)  # from configuration
    baud_rate= BAUD_RATE_DEVICE_TYPE_MAPPING[gateway_device_type]
    port = gateway_config.get(CONF_GATEWAY_PORT, VIRT_GW_PORT if gateway_device_type == GatewayDeviceType.VirtualNetworkAdapter else 5100)
    auto_reconnect = gateway_config.get(CONF_GATEWAY_AUTO_RECONNECT, True)
    gateway_base_id = AddressExpression.parse(gateway_config[CONF_BASE_ID])
    message_delay = gateway_config.get(CONF_GATEWAY_MESSAGE_DELAY, None)
    LOGGER.debug(f"[{LOG_PREFIX_INIT}] id: {gateway_id}, device type: {gateway_device_type}, serial path: {gateway_serial_path}, baud rate: {baud_rate}, base id: {gateway_base_id}")
    
    if gateway_device_type == GatewayDeviceType.VirtualNetworkAdapter:
        gateway = VirtualNetworkGateway(general_settings, hass, gateway_id, port, config_entry)
    else:
        gateway = EnOceanGateway(general_settings, hass, gateway_id, gateway_device_type, gateway_serial_path, baud_rate, port, gateway_base_id, gateway_name, auto_reconnect, message_delay, config_entry)

    
    await gateway.async_setup()
    set_gateway_to_hass(hass, gateway)

    hass.data[DATA_ELTAKO][DATA_ENTITIES] = {}
    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)


    return True



async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Unload Eltako config entry."""

    unload_gateway(hass, config_entry)

    return True
