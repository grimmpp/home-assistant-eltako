"""Support for Eltako devices."""
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.dispatcher import dispatcher_connect
from homeassistant.helpers.reload import async_reload_integration_platforms
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er, device_registry as dr, entity_platform as pl


from .const import *
from .virtual_network_gateway import create_central_virtual_network_gateway, stop_central_virtual_network_gateway, VirtualNetworkGateway
from .schema import CONFIG_SCHEMA
from . import config_helpers
from .gateway import *

LOG_PREFIX_INIT = "Eltako Integration Setup"

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Eltako component."""
    return True

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


def get_gateway_from_hass(hass: HomeAssistant, config_entry: ConfigEntry) -> EnOceanGateway:

    # Migrage existing gateway configs / ESP2 was removed in the name
    migrate_old_gateway_descriptions(hass)

    g_id = "gateway_"+str(config_helpers.get_id_from_gateway_name(config_entry.data[CONF_GATEWAY_DESCRIPTION]))
    return hass.data[DATA_ELTAKO][g_id]


def set_gateway_to_hass(hass: HomeAssistant, gateway: EnOceanGateway) -> None:

    # Migrage existing gateway configs / ESP2 was removed in the name
    migrate_old_gateway_descriptions(hass)
    g_id = "gateway_"+str(gateway.dev_id)
    hass.data[DATA_ELTAKO][g_id] = gateway

def unload_gateway_from_hass(hass: HomeAssistant, gateway: EnOceanGateway) -> None:
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

    # Migrage existing gateway configs / ESP2 was removed in the name
    migrate_old_gateway_descriptions(hass)

    general_settings = config_helpers.get_general_settings_from_configuration(hass)
    # Initialise the gateway
    # get base_id from user input
    if CONF_GATEWAY_DESCRIPTION not in config_entry.data.keys():
        LOGGER.warning("[{LOG_PREFIX}] Ooops, device information for gateway is not available. Try to delete and recreate the gateway.")
        return
    gateway_description = config_entry.data[CONF_GATEWAY_DESCRIPTION]    # from user input
    if CONF_VIRTUAL_NETWORK_GATEWAY in gateway_description:
        LOGGER.info(f"[{LOG_PREFIX_INIT}] Create Virtual ESP2 Reverse Network Bridge")
        virt_gw = VirtualNetworkGateway(hass)
        virt_gw.restart_tcp_server()
        hass.data[DATA_ELTAKO][CONF_VIRTUAL_NETWORK_GATEWAY] = virt_gw
        return True
    elif not ('(' in gateway_description and ')' in gateway_description):
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
    if gateway_device_type == GatewayDeviceType.LAN:
        if gateway_config.get(CONF_GATEWAY_ADDRESS, None) is None:
            raise Exception(f"[{LOG_PREFIX_INIT}] Missing field '{CONF_GATEWAY_ADDRESS}' for LAN Gateway (id: {gateway_id})")

    general_settings[CONF_ENABLE_TEACH_IN_BUTTONS] = True # GatewayDeviceType.is_transceiver(gateway_device_type) # should only be disabled for decentral gateways

    LOGGER.info(f"[{LOG_PREFIX_INIT}] Initializes Gateway Device '{gateway_description}'")
    gateway_name = gateway_config.get(CONF_NAME, None)  # from configuration
    baud_rate= BAUD_RATE_DEVICE_TYPE_MAPPING[gateway_device_type]
    port = gateway_config.get(CONF_GATEWAY_PORT, 5100)
    auto_reconnect = gateway_config.get(CONF_GATEWAY_AUTO_RECONNECT, True)
    gateway_base_id = AddressExpression.parse(gateway_config[CONF_BASE_ID])
    message_delay = gateway_config.get(CONF_GATEWAY_MESSAGE_DELAY, None)
    LOGGER.debug(f"[{LOG_PREFIX_INIT}] id: {gateway_id}, device type: {gateway_device_type}, serial path: {gateway_serial_path}, baud rate: {baud_rate}, base id: {gateway_base_id}")
    gateway = EnOceanGateway(general_settings, hass, gateway_id, gateway_device_type, gateway_serial_path, baud_rate, port, gateway_base_id, gateway_name, auto_reconnect, message_delay, v_gw, config_entry)

    
    await gateway.async_setup()
    set_gateway_to_hass(hass, gateway)

    hass.data[DATA_ELTAKO][DATA_ENTITIES] = {}
    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)

    return True



async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Unload Eltako config entry."""

    gateway = get_gateway_from_hass(hass, config_entry)

    LOGGER.info(f"[{LOG_PREFIX_INIT}] Unload {gateway.dev_name} and all its supported devices!")
    gateway.unload()
    unload_gateway_from_hass(hass, gateway)
    

    return True
