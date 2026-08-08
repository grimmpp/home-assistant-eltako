"""What can be done with the simulation - one function per action.

Every entry point of the simulation goes through here: the websocket api of the web ui
(`websocket.py`), the command line (`python -m eltako_standalone simulate ...`) and the tests.
So a simulated gateway created in the browser is identical to one created in a terminal.

The actions do the Home Assistant part - create the config entry of a gateway, store the
devices, hand a telegram to the live gateway - and leave every rule to `core`.
"""

from __future__ import annotations

import voluptuous as vol

from homeassistant.const import CONF_ID, CONF_NAME
from homeassistant.core import HomeAssistant

from ..config import config_helpers
from ..const import (CONF_AREA, CONF_BASE_ID, CONF_DEVICE_TYPE, CONF_EEP,
                     CONF_GATEWAY_DESCRIPTION, CONF_SENDER, CONF_SERIAL_PATH, CONF_SIMULATED,
                     DATA_ELTAKO, DOMAIN, ELTAKO_CONFIG, LOGGER, SOURCE_UI_GATEWAY,
                     GatewayDeviceType)
from . import core
from . import scheduler
from .runtime import get_gateway
from .store import (async_setup_registry, base_id_of, can_host_simulated_devices,
                    get_gateway_configs, get_registry, get_simulated_gateway_configs,
                    get_simulated_gateway_ids, is_simulated_config, is_simulated_gateway)

LOG_PREFIX_SIM = "Simulator"


### ---------------------------------------------------------------------------
### gateways
### ---------------------------------------------------------------------------

async def async_add_gateway(hass: HomeAssistant, device_type: str = None, name: str = None,
                            gateway_id: int = None, base_id: str = None) -> dict:
    """Create a simulated gateway incl. its config entry, so it is live right away.

    `device_type` is a normal gateway type of the integration (default: a FAM14 - a bus gateway
    shows the most: local addresses, senders, channels).
    """
    from ..config import gateway_config

    device_type = str(device_type or GatewayDeviceType.GatewayEltakoFAM14.value)
    if GatewayDeviceType.find(device_type) is None:
        raise core.SimulationError(f"'{device_type}' is not a supported gateway type.")

    config = hass.data.get(DATA_ELTAKO, {}).get(ELTAKO_CONFIG, {}) or {}
    if gateway_id is None:
        gateway_id = gateway_config.get_next_free_id(hass, config)

    gateway = {
        CONF_ID: int(gateway_id),
        CONF_DEVICE_TYPE: device_type,
        CONF_BASE_ID: base_id or core.default_base_id(gateway_id),
        CONF_NAME: name or core.SIMULATOR_DEFAULT_NAME,
        CONF_SIMULATED: True,
    }
    try:
        validated = await gateway_config.async_add_gateway(hass, gateway)
    except vol.Invalid as e:
        raise core.SimulationError(str(e)) from e

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={'source': SOURCE_UI_GATEWAY},
        data={CONF_GATEWAY_DESCRIPTION: gateway_config.get_description(validated),
              CONF_SERIAL_PATH: gateway_config.get_serial_path(validated)},
    )

    registry = await async_setup_registry(hass)
    LOGGER.info(f"[{LOG_PREFIX_SIM}] Created simulated {device_type} with id {gateway_id} "
                f"(base id {validated[CONF_BASE_ID]}).")
    return {'gateway_id': int(validated[CONF_ID]),
            'device_type': device_type,
            'base_id': validated[CONF_BASE_ID],
            'name': validated.get(CONF_NAME),
            'bus_gateway': registry.model.is_bus_gateway(gateway_id),
            'config_entry_created': result.get('type') == 'create_entry'}


async def async_remove_gateway(hass: HomeAssistant, gateway_id: int) -> dict:
    """Remove a simulated gateway, its config entry and all its virtual devices."""
    from ..config import gateway_config

    if not is_simulated_gateway(hass, gateway_id):
        raise core.SimulationError(f"Gateway {gateway_id} is not simulated.")

    registry = await async_setup_registry(hass)
    for device in registry.get_devices(gateway_id):
        scheduler.cancel(hass, gateway_id, device.address)
    removed_devices = await registry.async_remove_gateway(gateway_id)

    removed_entries = 0
    for entry in list(hass.config_entries.async_entries(DOMAIN)):
        try:
            entry_id = config_helpers.get_id_from_gateway_name(entry.data[CONF_GATEWAY_DESCRIPTION])
        except Exception:   # noqa: BLE001 - an entry without a gateway description
            continue
        if entry_id == int(gateway_id):
            await hass.config_entries.async_remove(entry.entry_id)
            removed_entries += 1

    removed = await gateway_config.async_remove_gateway(hass, gateway_id)
    return {'removed': removed, 'removed_config_entries': removed_entries,
            'removed_devices': removed_devices}


### ---------------------------------------------------------------------------
### devices
### ---------------------------------------------------------------------------

def validate_profiles(platform: str, eep: str, sender_eep: str = None) -> None:
    """Refuse a profile combination the configuration of that platform would not accept.

    Without this check a simulated device can be created which the detection then refuses ("value
    must be one of ...") - the device would sit on the simulation page and never appear under
    *Devices*. The rule is the same one the device configuration uses, so what can be simulated
    can always be configured.
    """
    supported = get_supported_eeps(platform)
    if supported and str(eep).upper() not in supported:
        raise core.SimulationError(
            f"A {platform} cannot use the profile {str(eep).upper()}. Home Assistant supports "
            f"{', '.join(supported)} for it - for a device which only sends, pick the kind "
            f"'sensor' or 'binary sensor' instead.")

    sender_supported = get_supported_sender_eeps(platform)
    if sender_eep and sender_supported and str(sender_eep).upper() not in sender_supported:
        raise core.SimulationError(
            f"A {platform} cannot be controlled with {str(sender_eep).upper()}. Home Assistant "
            f"supports {', '.join(sender_supported)} for it.")


async def async_add_device(hass: HomeAssistant, gateway_id: int, device: dict) -> dict:
    """Add a virtual device to a simulated gateway. What is not given is derived."""
    registry = await async_setup_registry(hass)
    if not can_host_simulated_devices(hass, gateway_id):
        raise core.SimulationError(f"There is no gateway {gateway_id} in the configuration.")
    if registry.model.get_gateway(gateway_id) is None:
        # a real gateway is taken into the model as soon as it hosts the first virtual device
        config = get_gateway_configs(hass).get(int(gateway_id), {})
        registry.model.add_gateway(gateway_id, str(config.get(CONF_DEVICE_TYPE) or ''),
                                   config.get(CONF_NAME), base_id_of(hass, gateway_id, config),
                                   simulated=False)

    device = dict(device or {})
    platform = str(device.get('platform') or '')
    if not device.get('eep'):
        raise core.SimulationError("A simulated device needs an EEP, e.g. A5-04-02.")

    gateway_model = registry.model.require_gateway(gateway_id)
    if not gateway_model.simulated:
        # a chosen address has to be one the real hardware can transmit: a wireless transceiver
        # only sends inside its base id range, a bus gateway addresses freely. The derived
        # addresses follow the gateway anyway, so only what the caller chose is checked.
        for key in ('address', 'sender_id'):
            if device.get(key):
                device[key] = core.validate_hosted_address(gateway_model.base_id, device[key],
                                                           gateway_model.is_bus_gateway)

    suggested = registry.model.suggest_device(gateway_id, platform, device['eep'],
                                             device.get('sender_eep'), device.get('name'),
                                             device.get('hw_type'))
    merged = {**suggested, **{key: value for key, value in device.items()
                              if value not in (None, "")}}
    merged['state'] = {**(suggested.get('state') or {}), **(device.get('state') or {})}
    validate_profiles(platform, merged['eep'], merged.get('sender_eep'))

    added = await registry.async_add_device(gateway_id, merged)
    scheduler.apply(hass, gateway_id, added)        # a device may be created with an interval
    return _described(hass, gateway_id, added)


async def async_update_device(hass: HomeAssistant, gateway_id: int, address: str,
                              changes: dict) -> dict:
    """Change a virtual device: its name, its profile, its interval or the values it reports."""
    registry = await async_setup_registry(hass)
    existing = registry.model.require(gateway_id, address)
    changes = changes or {}
    if 'eep' in changes or 'platform' in changes or 'sender_eep' in changes:
        validate_profiles(str(changes.get('platform') or existing.platform),
                          str(changes.get('eep') or existing.eep),
                          changes.get('sender_eep') or existing.sender_eep)

    updated = await registry.async_update_device(gateway_id, address, changes)
    # the interval decides whether this device sends on its own - apply it right away
    scheduler.apply(hass, gateway_id, updated)
    return _described(hass, gateway_id, updated)


async def async_set_interval(hass: HomeAssistant, gateway_id: int, address: str,
                             seconds: int) -> dict:
    """Let a device send its telegram every `seconds` seconds (0 switches it off)."""
    return await async_update_device(hass, gateway_id, address, {'interval': seconds})


def eltako_teach_in_of(device) -> dict | None:
    """The Eltako teach-in telegram of a device, or None if its profile has none.

    Two different telegrams are called 'teach-in', and they run in opposite directions:

    * the **profile teach-in** (`core.encode_teach_in_telegram`) is what a *sensor* sends to
      announce what it is - 4BS variation 2 with function, type and manufacturer.
    * the **Eltako teach-in** (this one) is what a *sender* sends so that an Eltako actuator takes
      it into its memory. Its four data bytes depend on the sender profile (A5-38-08 →
      `E0 40 0D 80`, A5-10-06 → `40 30 0D 85`, H5-3F-7F → `FF F8 0D 80`) and it is sent from the
      **sender** address, not from the address of the device. It is the telegram the teach-in
      button of a device in Home Assistant produces.

    Returns `{'address', 'eep', 'payload'}` - the address it is sent from, the sender profile it
    belongs to and its data bytes.
    """
    from ..catalog.teach_in import get_teach_in_payload

    # an actuator is taught in with the profile Home Assistant controls it with, and that
    # telegram carries its sender address; for a sensor its own profile and address are used
    eep = device.sender_eep if device.is_actuator else device.eep
    address = device.sender_id if device.is_actuator else device.address
    payload = get_teach_in_payload(eep)
    if not payload or not address:
        return None
    return {'address': address, 'eep': str(eep).upper(), 'payload': bytes(payload).hex()}


def _described(hass: HomeAssistant, gateway_id: int, device) -> dict:
    """One device for the ui, incl. whether its timer is running right now."""
    eltako = eltako_teach_in_of(device)
    return {**device.describe(),
            'repeating': scheduler.is_running(hass, gateway_id, device.address),
            # the second teach-in telegram, if this profile has one
            'eltako_teach_in': eltako}


async def async_remove_device(hass: HomeAssistant, gateway_id: int, address: str) -> bool:
    registry = await async_setup_registry(hass)
    scheduler.cancel(hass, gateway_id, address)
    return await registry.async_remove_device(gateway_id, address)


ELTAKO_TEACH_IN_DESCRIPTION = (
    "The ELTAKO teach-in telegram of the sender profile - the one the teach-in button of a device "
    "in Home Assistant sends, so that an actuator takes that sender into its memory. It is sent "
    "from the sender address and is a different telegram than the profile teach-in of a sensor.")


# A gateway is re-created whenever its devices change (adding a device stores it in the options
# of the config entry, which reloads the entry). A telegram triggered right in that window would
# find no gateway, so it is waited for shortly instead of failing.
GATEWAY_WAIT_SECONDS = 10.0
GATEWAY_WAIT_INTERVAL = 0.1


def get_any_gateway(hass: HomeAssistant, gateway_id: int):
    """The live gateway with this id - simulated or real."""
    from ..core.websocket import get_gateways

    return next((gateway for gateway in get_gateways(hass)
                 if int(getattr(gateway, 'dev_id', -1)) == int(gateway_id)), None)


async def async_wait_for_gateway(hass: HomeAssistant, gateway_id: int,
                                 timeout: float = GATEWAY_WAIT_SECONDS,
                                 any_gateway: bool = False):
    """The live gateway, waiting for a reload which is still running."""
    import asyncio

    look_up = get_any_gateway if any_gateway else get_gateway
    gateway = look_up(hass, gateway_id)
    waited = 0.0
    while gateway is None and waited < timeout:
        await asyncio.sleep(GATEWAY_WAIT_INTERVAL)
        waited += GATEWAY_WAIT_INTERVAL
        gateway = look_up(hass, gateway_id)
    if gateway is not None and waited:
        LOGGER.debug(f"[{LOG_PREFIX_SIM}] Waited {waited:.1f}s for gateway {gateway_id} "
                     f"to be set up again.")
    return gateway


async def async_trigger(hass: HomeAssistant, gateway_id: int, address: str,
                        state: dict = None, kind: str = 'state') -> dict:
    """Send the telegram of a simulated device. `kind` is 'state' or 'teach_in'.

    A state which is given is stored first, so the device keeps reporting the same values until
    they are changed again - like a real sensor which repeats its measurement.
    """
    registry = await async_setup_registry(hass)
    device = registry.model.require(gateway_id, address)
    if state:
        device = await registry.async_update_device(gateway_id, address, {'state': state})

    gateway = await async_wait_for_gateway(hass, gateway_id, any_gateway=True)
    if gateway is None:
        raise core.SimulationError(f"Gateway {gateway_id} is not set up - no telegram can be sent "
                                   f"through it. Reload the integration.")

    # a teach-in can be more than one telegram: RPS has none, so a press and its release are
    # sent - which is exactly what teaching in such a device does
    if kind == 'eltako_teach_in':
        eltako = eltako_teach_in_of(device)
        if eltako is None:
            raise core.SimulationError(
                f"{device.address} has no ELTAKO teach-in telegram: the profile "
                f"{device.sender_eep or device.eep} has no payload for it. Known are "
                f"A5-38-08, A5-10-06, A5-10-12 and H5-3F-7F.")
        telegrams = [core.encode_eltako_teach_in_telegram(eltako['address'],
                                                          bytes.fromhex(eltako['payload']))]
    else:
        telegrams = device.telegrams(kind)

    simulated_gateway = hasattr(gateway, 'simulate_incoming')
    for telegram in telegrams:
        if simulated_gateway:
            # the gateway itself is simulated: the telegram is injected where a real one would
            # have been read from the port
            gateway.simulate_incoming(telegram)
        else:
            # a real gateway: the telegram is really transmitted, so a real actuator receives it.
            # That is why the addresses of such a device derive from the base id of that
            # gateway - a wireless transceiver only sends its own senders.
            gateway.send_message(telegram)
    device = await registry.async_note_sent(gateway_id, address)

    LOGGER.info(f"[{LOG_PREFIX_SIM}] Gateway {gateway_id}: {device.address} sent {len(telegrams)} "
                f"{ {'teach_in': 'profile teach-in', 'eltako_teach_in': 'ELTAKO teach-in'}.get(kind, device.eep) } "
                f"telegram(s).")
    return {'sent': True, 'kind': kind, 'address': device.address,
            'telegram': ' + '.join(str(telegram) for telegram in telegrams),
            'hex': [telegram.serialize().hex() for telegram in telegrams],
            'telegram_count': len(telegrams),
            'teach_in_kind': device.teach_in_kind,
            'teach_in_description': (device.teach_in_description if kind == 'teach_in' else
                                     ELTAKO_TEACH_IN_DESCRIPTION if kind == 'eltako_teach_in'
                                     else ""),
            'state': device.public_state(), 'last_sent': device.last_sent,
            'sent_count': device.sent_count, 'interval': device.interval,
            'repeating': scheduler.is_running(hass, gateway_id, address)}


async def async_teach_in(hass: HomeAssistant, gateway_id: int, address: str, sender_id: str,
                         sender_eep: str = None, name: str = None) -> dict:
    """Teach a sender into a simulated actuator - its memory, like a real device has one.

    The sender can be anything which sends telegrams: a **real** wall switch (its telegrams
    arrive through a real gateway and are seen on the global telegram bus), a simulated one, or
    the sender of another automation system. From then on the actuator reacts to it.
    """
    registry = await async_setup_registry(hass)
    device = registry.model.require(gateway_id, address)
    if not device.is_actuator:
        raise core.SimulationError(f"{device.address} is a {device.platform} - it is not "
                                   f"controlled by anybody, so nothing can be taught into it.")

    # without a profile the one of the automation system is assumed; a wall switch usually
    # speaks a different one, so it is worth naming it
    entry = await registry.async_teach_in(gateway_id, address, sender_id, sender_eep, name)
    if not core.can_be_controlled(device.eep):
        LOGGER.warning(f"[{LOG_PREFIX_SIM}] {device.address} ({device.eep}) cannot be controlled "
                       f"by the simulation - the sender is stored, but nothing will answer.")
    return {'device': _described(hass, gateway_id, registry.model.require(gateway_id, address)),
            'sender': entry,
            'understood': (entry.get('eep') or device.sender_eep) in core.SENDER_DECODERS}


async def async_forget_sender(hass: HomeAssistant, gateway_id: int, address: str,
                              sender_id: str) -> dict:
    """Remove a taught-in sender from a simulated actuator."""
    registry = await async_setup_registry(hass)
    removed = await registry.async_forget_sender(gateway_id, address, sender_id)
    return {'removed': removed,
            'device': _described(hass, gateway_id, registry.model.require(gateway_id, address))}


async def async_set_active(hass: HomeAssistant, active: bool) -> dict:
    """Switch the whole simulation on or off.

    **Deactivated** means: nothing of the simulation exists in Home Assistant anymore. Every
    simulated device is removed from the configuration, so its entities and its device disappear,
    and the config entries of the simulated gateways are removed as well - a deactivated
    simulation cannot be used, not by an automation and not by accident.

    What stays is the simulation itself: the integration remembers every gateway and every device
    with all its values, they are still listed on the simulation page and can be created, changed
    and removed there. **Activating** puts everything back: the gateways are set up again and
    their devices are taken over into the configuration, exactly as the detection would do it.
    """
    registry = await async_setup_registry(hass)
    await registry.async_set_active(active)

    if not active:
        removed = await async_remove_from_home_assistant(hass)
        scheduler.apply_all(hass)       # cancels every timer
        LOGGER.info(f"[{LOG_PREFIX_SIM}] The simulation is deactivated: {removed['devices']} "
                    f"device(s) and {removed['gateways']} gateway entry/entries were removed from "
                    f"Home Assistant. Nothing of it is lost - it is put back when it is activated.")
        return {'active': False, 'paused': True, **removed,
                'repeating_count': 0,
                'devices_with_interval': len([device for device in registry.get_devices()
                                              if device.is_repeating])}

    restored = await async_restore_in_home_assistant(hass)
    running = scheduler.apply_all(hass)
    LOGGER.info(f"[{LOG_PREFIX_SIM}] The simulation is active again: {restored['gateways']} "
                f"gateway(s) and {restored['devices']} device(s) are back in Home Assistant.")
    return {'active': True, 'paused': False, **restored, 'repeating_count': running,
            'devices_with_interval': len([device for device in registry.get_devices()
                                          if device.is_repeating])}


# kept for callers which still say 'pause' - deactivating is what it does
async def async_set_paused(hass: HomeAssistant, paused: bool) -> dict:
    return await async_set_active(hass, not paused)


async def async_remove_gateway_entries(hass: HomeAssistant) -> int:
    """Remove the config entries of the simulated gateways.

    Their devices go with them (a device created in the web ui lives in the options of the entry
    of its gateway), so this is what makes a deactivated simulation disappear from Home Assistant
    completely. Runs on every setup as long as the simulation is off - otherwise an entry which
    was restored from disk would bring the whole simulation back.
    """
    removed = 0
    for gateway_id in sorted(get_simulated_gateway_ids(hass)):
        for entry in list(_entries_of_gateway(hass, gateway_id)):
            await hass.config_entries.async_remove(entry.entry_id)
            removed += 1
    return removed


async def async_remove_from_home_assistant(hass: HomeAssistant) -> dict:
    """Take everything of the simulation out of Home Assistant (the simulation itself stays).

    The devices are removed from the configuration first - their entities and their device entries
    disappear with them - and then the config entries of the simulated gateways, so no gateway
    without hardware is left over either. Devices which sit on a *real* gateway are removed as
    well; that gateway itself of course stays.
    """
    from ..config import device_config

    registry = await async_setup_registry(hass)
    simulated_addresses = {(gateway.id, device.address.upper())
                           for gateway in registry.model.get_gateways()
                           for device in gateway.devices}

    removed_devices = 0
    for configured in device_config._describe_devices(hass):
        key = (configured.get('gateway_id'), str(configured.get('address') or '').upper())
        if key not in simulated_addresses or configured.get('source') != 'ui':
            continue        # a device of the yaml is not ours to remove
        entry = device_config._find_gateway_entry(hass, configured['gateway_id'])
        if entry is None:
            continue
        try:
            await device_config.async_remove_ui_device(hass, entry, configured['platform'],
                                                       configured['address'])
            removed_devices += 1
        except Exception as e:  # noqa: BLE001 - one device must not stop the others
            LOGGER.warning(f"[{LOG_PREFIX_SIM}] Cannot remove {configured['address']}: {e}")

    removed_gateways = await async_remove_gateway_entries(hass)
    return {'devices': removed_devices, 'gateways': removed_gateways}


async def async_restore_in_home_assistant(hass: HomeAssistant) -> dict:
    """Put the simulation back into Home Assistant: its gateways and its devices."""
    from ..config import device_config, gateway_config

    await async_setup_registry(hass)

    created_gateways = 0
    for gateway in get_simulated_gateway_configs(hass):
        gateway_id = int(gateway[CONF_ID])
        if any(True for _entry in _entries_of_gateway(hass, gateway_id)):
            continue
        await hass.config_entries.flow.async_init(
            DOMAIN, context={'source': SOURCE_UI_GATEWAY},
            data={CONF_GATEWAY_DESCRIPTION: gateway_config.get_description(gateway),
                  CONF_SERIAL_PATH: gateway_config.get_serial_path(gateway)})
        created_gateways += 1

    # and the devices, exactly like the detection takes them over
    configured = device_config.get_configured_addresses(hass)
    candidates = derive_candidates(hass, configured)['candidates']
    by_gateway: dict[int, list] = {}
    for candidate in candidates:
        by_gateway.setdefault(candidate['gateway_id'], []).append(candidate)

    created_devices = 0
    for gateway_id, group in by_gateway.items():
        entry = device_config._find_gateway_entry(hass, gateway_id)
        if entry is None:
            LOGGER.warning(f"[{LOG_PREFIX_SIM}] Gateway {gateway_id} is not set up - "
                           f"{len(group)} simulated device(s) stay out of Home Assistant.")
            continue
        result = await device_config.async_add_ui_devices(
            hass, entry, [(candidate['platform'], candidate['device']) for candidate in group])
        created_devices += len(result['added'])
        for platform, address, message in result['errors']:
            LOGGER.warning(f"[{LOG_PREFIX_SIM}] {platform} {address}: {message}")

    return {'gateways': created_gateways, 'devices': created_devices}


async def async_send_base_id(hass: HomeAssistant, gateway_id: int) -> dict:
    """Let a simulated gateway report its base id, like a real one does after connecting.

    Only a simulated gateway can do that - a real one reports its own base id, and nothing may
    fake that for it.
    """
    if not is_simulated_gateway(hass, gateway_id):
        raise core.SimulationError(f"Gateway {gateway_id} is not simulated - a real gateway "
                                   f"reports its base id itself.")

    gateway = await async_wait_for_gateway(hass, gateway_id)
    if gateway is None:
        raise core.SimulationError(f"The simulated gateway {gateway_id} is not set up - it cannot "
                                   f"report anything. Reload the integration.")

    telegram = gateway.simulate_base_id_telegram()
    base_id = config_helpers.b2s(gateway.base_id[0]) if gateway.base_id is not None else None
    LOGGER.info(f"[{LOG_PREFIX_SIM}] Simulated gateway {gateway_id} reported its base id "
                f"{base_id}.")
    return {'sent': True, 'gateway_id': int(gateway_id), 'base_id': base_id,
            'telegram': str(telegram), 'hex': telegram.serialize().hex()}


### ---------------------------------------------------------------------------
### the starter set
### ---------------------------------------------------------------------------

async def async_add_preset(hass: HomeAssistant, keys: list[str] = None,
                           with_devices: bool = True) -> dict:
    """Create the starter set: a LAN gateway, a USB ESP3 gateway and a FAM14.

    Each of them gets the example devices of `core.DEVICE_PRESETS`: actuators for light,
    dimming, covers and heating/cooling plus sensors for temperature and humidity, motion, a
    4-way wall switch and a window contact. A preset whose gateway type is already simulated is
    skipped, so the call can be repeated.
    """
    await async_setup_registry(hass)
    wanted = [core.find_gateway_preset(key) for key in keys] if keys else list(core.GATEWAY_PRESETS)
    existing_types = {str(gateway.get(CONF_DEVICE_TYPE))
                      for gateway in get_simulated_gateway_configs(hass)}

    created = []
    skipped = []
    for preset in wanted:
        if preset['device_type'] in existing_types:
            skipped.append({'key': preset['key'], 'device_type': preset['device_type'],
                            'reason': "A simulated gateway of this type already exists."})
            continue
        gateway = await async_add_gateway(hass, preset['device_type'], preset['name'])
        devices = await async_add_preset_devices(hass, gateway['gateway_id']) if with_devices else []
        created.append({**gateway, 'preset': preset['key'],
                        'devices': [device['address'] for device in devices]})

    if not created:
        LOGGER.info(f"[{LOG_PREFIX_SIM}] Nothing to create - every preset gateway exists already.")
    return {'created': created, 'skipped': skipped,
            'device_count': sum(len(gateway['devices']) for gateway in created)}


async def async_add_preset_devices(hass: HomeAssistant, gateway_id: int,
                                   keys: list[str] = None) -> list[dict]:
    """Add the example devices to an existing simulated gateway."""
    registry = await async_setup_registry(hass)
    if not can_host_simulated_devices(hass, gateway_id):
        raise core.SimulationError(f"There is no gateway {gateway_id} in the configuration.")

    gateway = registry.model.require_gateway(gateway_id)
    added = []
    for preset in core.DEVICE_PRESETS:
        if keys is not None and preset['key'] not in keys:
            continue
        try:
            device = core.preset_device(gateway, preset)
        except core.SimulationError as e:
            LOGGER.warning(f"[{LOG_PREFIX_SIM}] Cannot build the example device "
                           f"'{preset['key']}': {e}")
            continue
        try:
            created = await registry.async_add_device(gateway_id, device)
            added.append(_described(hass, gateway_id, created))
        except core.SimulationError as e:
            LOGGER.warning(f"[{LOG_PREFIX_SIM}] Cannot add the example device "
                           f"'{preset['key']}': {e}")
    return added


### ---------------------------------------------------------------------------
### descriptors for the web ui and the command line
### ---------------------------------------------------------------------------

def get_device_templates(platform: str) -> list[dict]:
    """Known devices of the catalog which can be simulated for this platform.

    Filtered by what the *schema* of that platform accepts - a template whose profile the
    configuration would reject must not be offered: the simulated device could be created, but
    the detection would refuse to take it over, and it would never become an entity. (The device
    form of the web ui filters the same way, see config/device_config.py.)
    """
    from ..catalog.device_catalog import get_device_templates as catalog_templates

    # a switch is an actuator, so it uses the same devices as a light (a relay shown as a switch)
    templates = catalog_templates('light' if platform == 'switch' else platform,
                                  supported_eeps=get_supported_eeps(platform),
                                  supported_sender_eeps=get_supported_sender_eeps(platform) or None)
    return [{'value': template['value'], 'label': template['label'], 'eep': template['eep'],
             'hw_type': template['hw_type'], 'sender_eep': template.get('sender_eep')}
            for template in templates]


def get_supported_eeps(platform: str) -> list[str]:
    """EEPs the schema of this platform accepts - a simulated device has to fit it."""
    from ..config.schema import (CONF_EEP_SUPPORTED_BINARY_SENSOR, ClimateSchema, CoverSchema,
                                 LightSchema, SensorSchema, SwitchSchema)

    return {
        'binary_sensor': list(CONF_EEP_SUPPORTED_BINARY_SENSOR),
        'sensor': list(SensorSchema.CONF_EEP_SUPPORTED),
        'light': list(LightSchema.CONF_EEP_SUPPORTED),
        'switch': list(SwitchSchema.CONF_EEP_SUPPORTED),
        'cover': list(CoverSchema.CONF_EEP_SUPPORTED),
        'climate': list(ClimateSchema.CONF_CLIMATE_EEP),
    }.get(platform, [])


def get_supported_sender_eeps(platform: str) -> list[str]:
    """EEPs Home Assistant may control a device of this platform with."""
    from ..config.schema import ClimateSchema, CoverSchema, LightSchema, SwitchSchema

    return {
        'light': list(LightSchema.CONF_SENDER_EEP_SUPPORTED),
        'switch': list(SwitchSchema.CONF_SENDER_EEP_SUPPORTED),
        'cover': list(CoverSchema.CONF_SENDER_EEP_SUPPORTED),
        'climate': list(ClimateSchema.CONF_CLIMATE_SENDER_EEP),
    }.get(platform, [])


# What a kind is, in the words of the thing on the wall. "Switch" is the platform of Home
# Assistant for an actuator (a socket, a pump) - a wall switch is a binary sensor, and that is
# worth saying in the form: the two are easy to mix up.
PLATFORM_HELP = {
    'sensor': "Only sends: temperature, humidity, brightness, meter readings. One profile is "
              "enough - nothing is ever sent to it.",
    'binary_sensor': "Only sends: wall switch (rocker), window/door contact, motion. This is the "
                     "kind for a switch on the wall - one profile is enough.",
    'light': "An actuator Home Assistant switches or dims (relay, dimmer). It also needs the "
             "profile it is controlled with.",
    'switch': "An actuator Home Assistant switches, shown as a switch instead of a light "
              "(socket, pump, relay). It also needs the profile it is controlled with - a wall "
              "switch is NOT this kind, that is a binary sensor.",
    'cover': "An actuator for shutters and blinds. It also needs the profile it is controlled "
             "with.",
    'climate': "A heating/cooling actuator. It also needs the profile it is controlled with.",
}


def describe_platforms() -> list[dict]:
    """Everything a ui needs to offer a new virtual device, per platform."""
    from ..config.device_config import describe_eep

    result = []
    for platform, info in core.SIMULATED_PLATFORMS.items():
        eeps = []
        for eep in get_supported_eeps(platform):
            try:
                fields = core.eep_fields(eep)
                defaults = core.default_state(eep)
            except core.SimulationError:
                continue        # an EEP without a class in the library cannot be simulated
            description = describe_eep(eep)
            eeps.append({'value': eep, 'label': f"{eep} - {description}" if description else eep,
                         'fields': fields, 'defaults': defaults,
                         'teach_in': core.has_teach_in_telegram(eep),
                         'controllable': core.can_be_controlled(eep)})
        result.append({'platform': platform, 'label': info['label'],
                       'actuator': info['actuator'], 'eeps': eeps,
                       'help': PLATFORM_HELP.get(platform, ""),
                       'sender_eeps': get_supported_sender_eeps(platform),
                       'device_types': get_device_templates(platform)})
    return result


def describe_gateway(hass: HomeAssistant, gateway_config: dict) -> dict:
    """One simulated gateway with its virtual devices - for the web ui and the cli."""
    registry = get_registry(hass)
    gateway_id = int(gateway_config[CONF_ID])
    live = get_gateway(hass, gateway_id)
    device_type = str(gateway_config.get(CONF_DEVICE_TYPE) or '')
    model = registry.model.get_gateway(gateway_id) if registry else None

    return {
        'id': gateway_id,
        'name': gateway_config.get(CONF_NAME) or core.SIMULATOR_DEFAULT_NAME,
        'device_type': device_type,
        # False for a real gateway which only hosts simulated devices
        'simulated': bool(gateway_config.get(CONF_SIMULATED, False)),
        'bus_gateway': core.is_bus_gateway_type(device_type),
        'base_id': gateway_config.get(CONF_BASE_ID) or core.default_base_id(gateway_id),
        'description': config_helpers.get_gateway_name(gateway_config.get(CONF_NAME),
                                                       device_type, gateway_id),
        'serial_path': (gateway_config.get(CONF_SERIAL_PATH)
                        or config_helpers.simulator_serial_path(gateway_id)),
        'source': 'ui' if gateway_id in _ui_gateway_ids(hass) else 'yaml',
        'set_up': any(True for _entry in _entries_of_gateway(hass, gateway_id)),
        'live': live is not None,
        'connected': bool(live is not None and live._bus.is_active()),
        'devices': [_described(hass, gateway_id, device)
                    for device in (model.devices if model else [])],
    }


def _ui_gateway_ids(hass: HomeAssistant) -> set[int]:
    from ..config import gateway_config as gateway_config_module

    ids = set()
    for gateway in gateway_config_module.get_ui_gateways(hass):
        try:
            ids.add(int(gateway[CONF_ID]))
        except (KeyError, TypeError, ValueError):
            continue
    return ids


def _entries_of_gateway(hass: HomeAssistant, gateway_id: int):
    try:
        entries = hass.config_entries.async_entries(DOMAIN)
    except Exception:       # noqa: BLE001 - no config entries (e.g. in a unit test)
        return
    for entry in entries:
        try:
            if config_helpers.get_id_from_gateway_name(
                    entry.data[CONF_GATEWAY_DESCRIPTION]) == int(gateway_id):
                yield entry
        except Exception:   # noqa: BLE001 - an entry without a gateway description
            continue


def get_seen_addresses(hass: HomeAssistant, limit: int = 40) -> list[dict]:
    """Addresses which reported lately, newest first - candidates for a teach-in.

    Read from the device activity tracker, which is on by default (independent of the telegram
    recording). So a real wall switch which was pressed once can be picked from a list instead of
    being typed off its housing.
    """
    from ..observation.device_activity import get_activity_tracker

    tracker = get_activity_tracker(hass)
    if tracker is None:
        return []
    try:
        entries = tracker.get_all()
    except Exception:       # noqa: BLE001 - the tracker is a convenience, never a requirement
        return []

    registry = get_registry(hass)
    simulated = {device.address for device in (registry.get_devices() if registry else [])}
    # the activity tracker stores the *external* address, so a device of a simulated bus appears
    # as FF-C0-xx-xx while its own address is the local one - both belong to the simulation
    prefix = f"{core.SIMULATOR_BASE_ID_PREFIX}-"

    result = []
    for entry in entries:
        address = str(entry.get('address') or '').upper()
        if not address:
            continue
        result.append({'address': address, 'count': entry.get('count'),
                       'last_seen': entry.get('last_seen'),
                       'simulated': address in simulated or address.startswith(prefix)})
    result.sort(key=lambda item: str(item.get('last_seen') or ''), reverse=True)
    return result[:limit]


def get_hosting_gateway_configs(hass: HomeAssistant) -> list[dict]:
    """Every gateway the simulation page shows: simulated ones, and real ones with virtual devices.

    A real gateway only appears while it hosts at least one simulated device - then its telegrams
    are really transmitted and it belongs on that page.
    """
    registry = get_registry(hass)
    hosting = {gateway.id for gateway in (registry.model.get_gateways() if registry else [])
               if gateway.devices}
    configs = get_gateway_configs(hass)

    result = []
    for gateway_id in sorted(configs):
        config = configs[gateway_id]
        if is_simulated_config(config) or gateway_id in hosting:
            result.append(config)
    return result


def get_overview(hass: HomeAssistant) -> dict:
    """State of the whole simulation: the payload of the simulation page and of `simulate list`."""
    gateways = [describe_gateway(hass, gateway) for gateway in get_hosting_gateway_configs(hass)]
    existing_types = {gateway['device_type'] for gateway in gateways}
    return {
        'gateways': sorted(gateways, key=lambda gateway: gateway['id']),
        'device_count': sum(len(gateway['devices']) for gateway in gateways),
        'active': bool(registry.active) if (registry := get_registry(hass)) is not None else True,
        'paused': not (get_registry(hass).active if get_registry(hass) is not None else True),
        'repeating_count': len(scheduler.get_running(hass)),
        # addresses which sent telegrams lately - offered as suggestions when teaching in a
        # sender, so a real wall switch can be picked instead of being typed
        'seen_addresses': get_seen_addresses(hass),
        'sender_eeps': sorted({eep for eep in core.SENDER_DECODERS}),
        'interval_suggestions': list(core.INTERVAL_SUGGESTIONS),
        'interval_range': [core.MIN_INTERVAL_SECONDS, core.MAX_INTERVAL_SECONDS],
        'platforms': describe_platforms(),
        'presets': core.describe_gateway_presets(existing_types),
        'device_presets': core.describe_device_presets(),
        'gateway_types': sorted({device_type.value for device_type in GatewayDeviceType}),
        # real gateways a virtual device can be put on: its telegrams are then really
        # transmitted, and its addresses derive from the base id of that gateway
        'real_gateways': [{'id': gateway_id,
                           'name': config.get(CONF_NAME) or f"Gateway {gateway_id}",
                           'device_type': str(config.get(CONF_DEVICE_TYPE) or ''),
                           'bus_gateway': core.is_bus_gateway_type(
                               str(config.get(CONF_DEVICE_TYPE) or '')),
                           'base_id': base_id_of(hass, gateway_id, config),
                           'hosting': any(entry['id'] == gateway_id and not entry['simulated']
                                          for entry in gateways)}
                          for gateway_id, config in sorted(get_gateway_configs(hass).items())
                          if not is_simulated_config(config)],
        'hint': "A simulated gateway needs no hardware: it is a normal gateway of this "
                "integration whose devices are simulated in this process. Define the values a "
                "device reports and trigger its telegram - nothing behind the gateway can tell "
                "it apart from a real one. 'Search devices' on the device page takes every "
                "simulated device over into the configuration.",
    }


### ---------------------------------------------------------------------------
### plug & play: the simulated devices are found like real ones
### ---------------------------------------------------------------------------

def device_config_of(device) -> dict:
    """The configuration entry a simulated device gets when the detection takes it over."""
    entry = {CONF_ID: device.address, CONF_EEP: device.eep,
             CONF_NAME: device.name or f"Simulated {device.platform}"}
    if device.area:
        entry[CONF_AREA] = device.area
    if device.sender_id and device.sender_eep:
        entry[CONF_SENDER] = {CONF_ID: device.sender_id, CONF_EEP: device.sender_eep}
    return entry


def derive_candidates(hass: HomeAssistant, configured: dict) -> dict:
    """Devices of all simulated gateways which are not configured yet.

    Same result shape as the other sources of tools/plug_and_play.py, so a simulated device is
    treated exactly like a device found on a real bus. It states its platform, its EEP and (for
    an actuator) its sender - nothing is left to guess, so nothing is skipped.
    """
    registry = get_registry(hass)
    if registry is None:
        return {'candidates': [], 'skipped': []}

    known_by_gateway = (configured or {}).get('by_gateway') or {}
    candidates = []
    skipped = []

    for gateway_id in sorted(get_simulated_gateway_ids(hass)):
        known = {str(address).upper() for address in known_by_gateway.get(gateway_id, set())}
        for device in registry.get_devices(gateway_id):
            if device.address.upper() in known:
                continue
            if device.is_actuator and not device.sender_eep:
                skipped.append({'gateway_id': gateway_id, 'address': device.address,
                                'reason': "The simulated actuator has no sender EEP - it cannot "
                                          "be controlled."})
                continue
            candidates.append({'gateway_id': gateway_id, 'platform': device.platform,
                               'source': 'simulator', 'simulated': True,
                               'device_class': device.hw_type,
                               'device': device_config_of(device)})

    return {'candidates': candidates, 'skipped': skipped}
