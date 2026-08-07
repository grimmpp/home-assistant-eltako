"""Config flows for the Eltako integration."""
# https://developers.home-assistant.io/docs/config_entries_config_flow_handler

import voluptuous as vol

import ipaddress

from homeassistant import config_entries
from homeassistant.const import CONF_ID, CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.selector import selector

from .core import gateway
from .config import config_helpers
from .config import gateway_config
from .config import general_settings
from .const import *
from .config.schema import CONFIG_SCHEMA

LOGGER_PREFIX_CONFIG_FLOW = "config_flow"
LOGGER_PREFIX_OPTIONS_FLOW = "options_flow"

class EltakoFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the Eltako config flows."""

    VERSION = 1
    MINOR_VERSION = 1
    MANUAL_PATH_VALUE = "Custom path"

    def __init__(self) -> None:
        """Initialize the Eltako config flow."""

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        """The 'Configure' button on the Home Assistant integration page."""
        return EltakoOptionsFlowHandler()

    def is_input_available(self, user_input) -> bool:
        LOGGER.debug("[%s] Check available data", LOGGER_PREFIX_CONFIG_FLOW)
        if user_input is not None:
            if CONF_SERIAL_PATH in user_input and user_input[CONF_SERIAL_PATH] is not None:
                if CONF_GATEWAY_DESCRIPTION in user_input and user_input[CONF_GATEWAY_DESCRIPTION] is not None:
                    return True
        return False

    async def async_step_user(self, user_input=None):
        """Entry point. Nothing has to be entered here, and nothing is asked.

        Home Assistant does not load a custom integration which has no config entry and no
        `eltako:` section in the yaml - so copying the files and restarting cannot bring the
        web ui into the sidebar, whatever the integration does. Adding the integration is what
        loads it, and that is the whole reason this step exists: it must therefore be over as
        fast as it can be. So the first time it runs it asks nothing at all and sets the
        integration up as it is (`async_step_auto`) - the panel appears, the detection runs,
        and everything else is done in the web ui.

        There is deliberately no menu entry for "set up automatically" anymore: it is not a
        choice, it is what installing means, so it happens without being asked for. Only once
        the integration is there does this step become a menu, and then it is about *gateways*:
        picking up one which is declared in the configuration but not set up in Home Assistant
        yet, or defining a new one by hand. Both are also on the overview page of the web ui.
        """
        LOGGER.debug("[%s] config_flow user step started.", LOGGER_PREFIX_CONFIG_FLOW)

        if not self._core_entry_exists():
            return await self.async_step_auto()

        menu_options = {}
        if await self._async_get_available_gateways():
            menu_options["detect"] = "Set up a gateway of my configuration"
        menu_options["new_gateway"] = "Add a gateway by hand"

        if list(menu_options) == ["new_gateway"]:
            # nothing to pick up - only the wizard is left
            return await self.async_step_new_gateway()

        return self.async_show_menu(step_id="user", menu_options=menu_options)

    def _core_entry_exists(self) -> bool:
        """True if the integration itself is already set up (the gateway-less entry)."""
        return any(entry.data.get(CONF_CORE_ENTRY)
                   for entry in self.hass.config_entries.async_entries(DOMAIN))

    async def async_step_auto(self, user_input=None):
        """Set the integration up without any input and let it look for the gateways itself.

        The entry created here carries no gateway: it is the integration, which brings the web
        ui and the detection with it. Every gateway which is found gets its own entry through
        `async_step_ui_gateway`, exactly like one created in the web ui - so nothing here has
        to know about serial ports.

        The detection itself is not run here but requested with a flag which
        `async_setup_entry` picks up: at this point the component may not even be set up yet,
        and probing the ports takes seconds while reading a bus takes minutes - a config flow
        which blocks that long looks broken. The overview page of the web ui draws the run
        live. The flag is consumed once, so a restart does not lock the bus again.
        """
        LOGGER.debug("[%s] Setting up the integration and requesting the initial detection.",
                     LOGGER_PREFIX_CONFIG_FLOW)

        await self.async_set_unique_id(CORE_UNIQUE_ID)
        self._abort_if_unique_id_configured()

        self.hass.data.setdefault(DATA_ELTAKO, {})[DATA_INITIAL_DETECTION] = True

        return self.async_create_entry(title=CORE_TITLE, data={CONF_CORE_ENTRY: True})

    async def async_step_ui_gateway(self, data: dict):
        """A gateway was created in the web ui - create its config entry directly."""
        LOGGER.debug("[%s] Creating entry for gateway created in the web ui: %s",
                     LOGGER_PREFIX_CONFIG_FLOW, data.get(CONF_GATEWAY_DESCRIPTION))
        await self.async_set_unique_id(str(data.get(CONF_GATEWAY_DESCRIPTION)))
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=data[CONF_GATEWAY_DESCRIPTION], data=data)

    async def _async_get_available_gateways(self) -> list[str]:
        """Gateway descriptions which are configured but not set up in Home Assistant yet."""
        g_list_dict = await config_helpers.async_get_list_of_gateway_descriptions(self.hass, CONFIG_SCHEMA)
        self.hass.data.setdefault(DATA_ELTAKO, {})
        return [description for description in g_list_dict.values()
                if description not in self.hass.data[DATA_ELTAKO]
                and 'gateway_' + str(config_helpers.get_id_from_gateway_name(description)) not in self.hass.data[DATA_ELTAKO]]

    async def async_step_new_gateway(self, user_input=None):
        """Define a completely new gateway. This does not need configuration.yaml at all."""
        errors = {}
        config = await config_helpers.async_get_home_assistant_config(self.hass, CONFIG_SCHEMA)

        if user_input is not None:
            gateway_data = {
                CONF_ID: int(user_input[CONF_ID]),
                CONF_DEVICE_TYPE: user_input[CONF_DEVICE_TYPE],
                CONF_NAME: user_input.get(CONF_NAME) or "",
                CONF_BASE_ID: user_input.get(CONF_BASE_ID) or '00-00-00-00',
            }
            connection = (user_input.get(CONF_SERIAL_PATH) or "").strip()
            device_type = gateway.GatewayDeviceType.find(user_input[CONF_DEVICE_TYPE])
            if device_type is not None and gateway.GatewayDeviceType.is_lan_gateway(device_type) \
                    and device_type != gateway.GatewayDeviceType.VirtualNetworkAdapter:
                gateway_data[CONF_GATEWAY_ADDRESS] = connection
            else:
                gateway_data[CONF_SERIAL_PATH] = connection

            try:
                validated = await gateway_config.async_add_gateway(self.hass, gateway_data)
            except vol.Invalid as e:
                LOGGER.warning("[%s] Cannot add gateway: %s", LOGGER_PREFIX_CONFIG_FLOW, e)
                errors['base'] = 'invalid_gateway'
                self.context['last_error'] = str(e)
            else:
                description = gateway_config.get_description(validated)
                await self.async_set_unique_id(description)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=description, data={
                    CONF_GATEWAY_DESCRIPTION: description,
                    CONF_SERIAL_PATH: gateway_config.get_serial_path(validated),
                })

        # suggest the free serial ports of the scan, but allow any input
        from .tools.gateway_scan import scan_serial_ports
        ports = await self.hass.async_add_executor_job(scan_serial_ports)
        port_hints = ", ".join(port['device'] for port in ports) or "no serial port found"

        return self.async_show_form(
            step_id="new_gateway",
            data_schema=vol.Schema({
                vol.Required(CONF_DEVICE_TYPE, default=gateway.GatewayDeviceType.GatewayEltakoFGW14USB.value):
                    vol.In(sorted({t.value for t in gateway.GatewayDeviceType})),
                vol.Required(CONF_SERIAL_PATH, description={'suggested_value': ports[0]['device'] if ports else ''}): str,
                vol.Required(CONF_ID, default=gateway_config.get_next_free_id(self.hass, config)): int,
                vol.Optional(CONF_NAME, default=""): str,
                vol.Optional(CONF_BASE_ID, default='00-00-00-00'): str,
            }),
            errors=errors,
            description_placeholders={
                'ports': port_hints,
                'error': self.context.get('last_error', ''),
            },
        )

    async def async_step_detect(self, user_input=None):

        """Propose a list of gateways which are configured but not set up yet."""
        LOGGER.debug("[%s] config_flow detect step started.", LOGGER_PREFIX_CONFIG_FLOW)
        return await self.manual_selection_routine(user_input)
        
    async def async_step_manual(self, user_input=None):
        """Request manual USB gateway path."""
        LOGGER.debug("[%s] config_flow manual step started.", LOGGER_PREFIX_CONFIG_FLOW)
        return await self.manual_selection_routine(user_input, manual_setp=True)
    
    async def manual_selection_routine(self, user_input=None, manual_setp:bool=False):
        LOGGER.debug("[%s] Add new gateway", LOGGER_PREFIX_CONFIG_FLOW)
        errors = {}

        if DATA_ELTAKO in self.hass.data:
            LOGGER.debug("[%s] Available Eltako Objects", LOGGER_PREFIX_CONFIG_FLOW)
            for g in self.hass.data[DATA_ELTAKO]:
                LOGGER.debug(g)

        # get configuration for debug purpose
        config = await config_helpers.async_get_home_assistant_config(self.hass, CONFIG_SCHEMA)
        LOGGER.debug(f"[%s] Config: {config}\n")

        # ensure data entry is set
        if DATA_ELTAKO not in self.hass.data:
            LOGGER.debug("[%s] No configuration available.", LOGGER_PREFIX_CONFIG_FLOW)
            self.hass.data.setdefault(DATA_ELTAKO, {})

        # goes recursively ...
        # check if values were set in the step before
        if user_input is not None:
            if self.is_input_available(user_input):
                if await self.validate_eltako_conf(user_input):
                    return self.create_eltako_entry(user_input)
            
                errors = {CONF_SERIAL_PATH: ERROR_INVALID_GATEWAY_PATH}

        LOGGER.debug("[%s] Get data for gateway selection", LOGGER_PREFIX_CONFIG_FLOW)

        # find all existing serial paths
        serial_paths = await self.hass.async_add_executor_job(gateway.detect)
        
        # get available (not registered) gateways
        g_list_dict = (await config_helpers.async_get_list_of_gateway_descriptions(self.hass, CONFIG_SCHEMA)) 
        # filter out registered gateways. all registered gateways are listen in data section
        g_list = list([g for g in g_list_dict.values() if g not in self.hass.data[DATA_ELTAKO] and 'gateway_'+str(config_helpers.get_id_from_gateway_name(g)) not in self.hass.data[DATA_ELTAKO]])
        LOGGER.debug("[%s] Available gateways to be added: %s", LOGGER_PREFIX_CONFIG_FLOW, g_list)
        if len(g_list) == 0:
            LOGGER.debug("[%s] No gateways are configured in the 'configuration.yaml'.", LOGGER_PREFIX_CONFIG_FLOW)
            errors = {CONF_GATEWAY_DESCRIPTION: ERROR_NO_GATEWAY_CONFIGURATION_AVAILABLE}

        # add manually added serial paths and ip addresses from configuration
        for g_id in g_list_dict.keys():
            #only for available gw
            if g_list_dict[g_id] in g_list:
                g_c = config_helpers.find_gateway_config_by_id(config, g_id)
                if CONF_SERIAL_PATH in g_c:
                    serial_paths.append(g_c[CONF_SERIAL_PATH])
                if CONF_GATEWAY_ADDRESS in g_c:
                    address = g_c[CONF_GATEWAY_ADDRESS]
                    serial_paths.append(address)

        # get all serial paths which are not taken by existing gateways
        device_registry = dr.async_get(self.hass)
        serial_paths_of_registered_gateways = await gateway.async_get_serial_path_of_registered_gateway(device_registry)
        serial_paths = list(set([sp for sp in serial_paths if sp not in serial_paths_of_registered_gateways]))
        LOGGER.debug("[%s] Available serial paths/IP addresses: %s", LOGGER_PREFIX_CONFIG_FLOW, serial_paths)

        if manual_setp or len(serial_paths) == 0:
            LOGGER.debug("[%s] No usb port or any manually configured address available.", LOGGER_PREFIX_CONFIG_FLOW)
            errors = {CONF_SERIAL_PATH: ERROR_NO_SERIAL_PATH_AVAILABLE}
                
            return self.async_show_form(
                step_id="manual",
                data_schema=vol.Schema({
                    vol.Required(CONF_GATEWAY_DESCRIPTION, msg="EnOcean Gateway", description="Gateway to be initialized."): vol.In(g_list),
                    vol.Required(CONF_SERIAL_PATH, msg="Serial Port/IP Address", description="Serial path/IP address for selected gateway."): str
                }),
                errors=errors,
            )


        # show form in which gateways and serial paths are displayed so that a mapping can be selected.
        return self.async_show_form(
            step_id="detect",
            data_schema=vol.Schema({
                vol.Required(CONF_GATEWAY_DESCRIPTION, msg="EnOcean Gateway", description="Gateway to be initialized."): vol.In(g_list),
                vol.Required(CONF_SERIAL_PATH, msg="Serial Port/IP Address", description="Serial path/IP address for selected gateway."): vol.In(serial_paths),
            }),
            errors=errors,
        )

    async def validate_eltako_conf(self, user_input) -> bool:
        """Return True if the user_input contains a valid gateway path."""
        serial_path: str = user_input[CONF_SERIAL_PATH]
        baud_rate: int = -1
        gateway_selection: str = user_input[CONF_GATEWAY_DESCRIPTION]

        LOGGER.debug("[%s] Start serial path validation for '%s' and address '%s'", LOGGER_PREFIX_CONFIG_FLOW, gateway_selection, serial_path)

        for gdc in gateway.GatewayDeviceType:
            if gdc in gateway_selection:
                baud_rate = gateway.BAUD_RATE_DEVICE_TYPE_MAPPING[gdc]

        is_network_gw = False
        for gdc in GatewayDeviceType:
            if GatewayDeviceType.is_lan_gateway(gdc) and gdc in gateway_selection:
                is_network_gw = True
                break
        
        # check ip address for esp2/3 over tcp
        if GatewayDeviceType.VirtualNetworkAdapter.value in gateway_selection:
            return True
        elif is_network_gw:
            try:
                ip = ipaddress.ip_address(serial_path)
                LOGGER.debug("[%s] Found valid IP Address %s.", serial_path)
                return True
            except Exception:
                LOGGER.debug("[%s] serial_path: %s is no valid IP Address", serial_path)
                return False
        # check serial ports / usb
        else:
            path_is_valid = await self.hass.async_add_executor_job(
                gateway.validate_path, serial_path, baud_rate
            )
            LOGGER.debug("[%s] serial_path: %s, validated with baud rate %d is %s", LOGGER_PREFIX_CONFIG_FLOW, serial_path, baud_rate, path_is_valid)

        return path_is_valid

    def create_eltako_entry(self, user_input):
        """Create an entry for the provided configuration."""
        LOGGER.debug("[%s] Create Gateway Entry", LOGGER_PREFIX_CONFIG_FLOW)
        return self.async_create_entry(title=user_input[CONF_GATEWAY_DESCRIPTION], data=user_input)


### ---------------------------------------------------------------------------
### options flow: the general settings, editable from the integration page
### ---------------------------------------------------------------------------

def _editable_descriptors(group_id: str) -> list[dict]:
    """The settings of one group which may be changed from here.

    Locked settings (currently only 'enable_frontend') are left out on purpose: a Home
    Assistant form has no read-only field, and offering a switch which silently does nothing
    is worse than not offering it. They stay visible in the web ui and in configuration.yaml.
    """
    return [descriptor for descriptor in general_settings.SETTING_DESCRIPTORS
            if descriptor['group'] == group_id and not descriptor.get('locked')]


def _selector_for(descriptor: dict):
    """Turn one setting descriptor into the matching Home Assistant form field."""
    kind = descriptor.get('type')
    if kind == 'boolean':
        return selector({'boolean': {}})
    if kind == 'number':
        number = {'mode': 'box', 'step': 'any'}
        if 'min' in descriptor:
            number['min'] = descriptor['min']
        if 'max' in descriptor:
            number['max'] = descriptor['max']
        return selector({'number': number})
    if kind == 'select':
        return selector({'select': {'options': [str(option) for option in descriptor['options']],
                                    'mode': 'dropdown'}})
    return selector({'text': {}})


def _schema_for(descriptors: list[dict], values: dict) -> vol.Schema:
    """Form for one group of settings, pre-filled with the values which are in effect.

    The field keys are the *labels* of the settings, not their names. This integration ships no
    translations, and Home Assistant falls back to the raw key for a field it cannot translate -
    'Record EnOcean telegrams' reads better there than 'log_enocean_telegrams', and it keeps the
    labels of the web ui and of this form the same text.
    """
    fields = {}
    for descriptor in descriptors:
        value = values.get(descriptor['name'])
        if value is None:
            value = '' if descriptor.get('type') == 'text' else vol.UNDEFINED
        fields[vol.Optional(descriptor['label'], default=value)] = _selector_for(descriptor)
    return vol.Schema(fields)


def _help_for(group_id: str, descriptors: list[dict]) -> str:
    """Markdown shown above the form: what the group is about and what each setting does."""
    group_help = next((help_text for identifier, _label, help_text in SETTING_GROUPS
                       if identifier == group_id), '')
    lines = [group_help] if group_help else []
    lines += [f"- **{descriptor['label']}**: {descriptor['help']}"
              for descriptor in descriptors if descriptor.get('help')]
    return "\n".join(lines)


class EltakoOptionsFlowHandler(config_entries.OptionsFlow):
    """Change the general settings of the integration from the Home Assistant ui.

    Same settings, same storage and same precedence as the 'Settings' page of the web ui (see
    config/general_settings.py): whatever is changed here is stored as an override and takes
    effect right away. They belong to the integration as a whole, not to one gateway, so every
    entry of this integration offers the same form.

    Only values which actually differ from the ones currently in effect are stored. Saving a
    form therefore does not turn every setting of that group into an override, which would
    silently detach them from `configuration.yaml`.
    """

    async def async_step_init(self, user_input=None):
        return self.async_show_menu(
            step_id='init',
            menu_options={group_id: label for group_id, label, _help in SETTING_GROUPS},
        )

    async def _async_group_step(self, group_id: str, user_input=None):
        descriptors = _editable_descriptors(group_id)
        effective = config_helpers.get_general_settings_from_configuration(self.hass)
        errors = {}

        if user_input is not None:
            by_label = {descriptor['label']: descriptor['name'] for descriptor in descriptors}
            validated = {}
            for label, value in user_input.items():
                name = by_label.get(label)
                if name is None:
                    continue        # not part of this group - cannot happen through the ui
                try:
                    validated[name] = general_settings.validate_setting(name, value)
                except vol.Invalid as e:
                    LOGGER.warning("[%s] Invalid value for '%s': %s",
                                   LOGGER_PREFIX_OPTIONS_FLOW, name, e)
                    errors[label] = 'invalid_setting'

            if not errors:
                changed = {name: value for name, value in validated.items()
                           if value != effective.get(name)}
                if changed:
                    LOGGER.info("[%s] Changed on the integration page: %s",
                                LOGGER_PREFIX_OPTIONS_FLOW,
                                ', '.join(f'{name}={value!r}' for name, value in changed.items()))
                    await general_settings.async_set_overrides(self.hass, changed)
                    await general_settings.async_apply_settings(self.hass)
                # the settings are not part of the entry options - keep those as they are
                return self.async_create_entry(title='', data=dict(self.config_entry.options))

            effective = {**effective, **{by_label[label]: value
                                         for label, value in user_input.items()
                                         if label in by_label}}

        return self.async_show_form(
            step_id=group_id,
            data_schema=_schema_for(descriptors, effective),
            errors=errors,
            description_placeholders={'help': _help_for(group_id, descriptors)},
        )


def _group_step(group_id: str):
    """One `async_step_<group>` method - the menu above jumps to them by name."""
    async def step(self, user_input=None):
        return await self._async_group_step(group_id, user_input)

    step.__name__ = f'async_step_{group_id}'
    return step


# Built from SETTING_GROUPS so that a new group appears in this form as well, instead of being
# reachable in the web ui only.
for _group_id, _label, _help in SETTING_GROUPS:
    setattr(EltakoOptionsFlowHandler, f'async_step_{_group_id}', _group_step(_group_id))
