"""Where the simulation is kept: the Home Assistant storage.

The model of `core` holds the simulated gateways and their devices; this module loads it, saves
it and keeps it in sync with the gateway configuration - because a simulated gateway is stored
where every other gateway is stored (configuration.yaml or the ui gateway store, see
config/gateway_config.py). The model only needs to know the *type* and the *base id* of a
gateway, since both decide which addresses its devices get.
"""

from __future__ import annotations

from homeassistant.const import CONF_ID, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from ..const import (CONF_BASE_ID, CONF_DEVICE_TYPE, CONF_GATEWAY, CONF_SIMULATED, DATA_ELTAKO,
                     DATA_SIMULATOR, DOMAIN, ELTAKO_CONFIG, LOGGER)
from . import core

LOG_PREFIX_SIM = "Simulator"

STORAGE_KEY = f"{DOMAIN}_simulator"
STORAGE_VERSION = 1


### ---------------------------------------------------------------------------
### which gateways of the configuration are simulated
### ---------------------------------------------------------------------------

def is_simulated_config(gateway: dict) -> bool:
    """True if this gateway configuration describes a gateway without hardware."""
    return bool((gateway or {}).get(CONF_SIMULATED, False))


def get_simulated_gateway_configs(hass: HomeAssistant) -> list[dict]:
    """Configuration of every simulated gateway (from the yaml and from the web ui)."""
    config = (getattr(hass, 'data', None) or {}).get(DATA_ELTAKO, {}).get(ELTAKO_CONFIG, {}) or {}
    return [gateway for gateway in (config.get(CONF_GATEWAY) or []) if is_simulated_config(gateway)]


def get_simulated_gateway_ids(hass: HomeAssistant) -> set[int]:
    """Ids of all simulated gateways - used to mark simulated devices in every list."""
    ids = set()
    for gateway in get_simulated_gateway_configs(hass):
        try:
            ids.add(int(gateway[CONF_ID]))
        except (KeyError, TypeError, ValueError):
            continue
    return ids


def is_simulated_gateway(hass: HomeAssistant, gateway_id) -> bool:
    try:
        return int(gateway_id) in get_simulated_gateway_ids(hass)
    except (TypeError, ValueError):
        return False


def get_gateway_configs(hass: HomeAssistant) -> dict[int, dict]:
    """Every configured gateway by its id - simulated ones and real ones.

    A virtual device can also sit behind a **real** gateway: its telegrams are then really
    transmitted (a wireless transceiver sends them over the air), which is how a simulated wall
    switch can switch a real actuator. Therefore not only the simulated gateways are of interest
    here.
    """
    config = (getattr(hass, 'data', None) or {}).get(DATA_ELTAKO, {}).get(ELTAKO_CONFIG, {}) or {}
    result = {}
    for gateway in (config.get(CONF_GATEWAY) or []):
        try:
            result[int(gateway[CONF_ID])] = gateway
        except (KeyError, TypeError, ValueError):
            continue
    return result


def can_host_simulated_devices(hass: HomeAssistant, gateway_id) -> bool:
    """A device can be simulated behind every configured gateway."""
    try:
        return int(gateway_id) in get_gateway_configs(hass)
    except (TypeError, ValueError):
        return False


def base_id_of(hass: HomeAssistant, gateway_id: int, config: dict = None) -> str:
    """The base id a simulated device of this gateway derives its address from.

    A real gateway reports its base id after connecting, so the live gateway knows it best; the
    configuration is the fallback, and a simulated gateway always has one.
    """
    from ..config import config_helpers

    live = (getattr(hass, 'data', None) or {}).get(DATA_ELTAKO, {}).get(f"gateway_{int(gateway_id)}")
    base_id = getattr(live, 'base_id', None)
    try:
        if base_id is not None and int.from_bytes(base_id[0], 'big') != 0:
            return config_helpers.b2s(base_id[0])
    except Exception:       # noqa: BLE001 - a gateway which is not fully set up yet
        pass

    configured = str((config or get_gateway_configs(hass).get(int(gateway_id), {})).get(CONF_BASE_ID)
                     or '')
    if configured and not configured.startswith('00-00-00-00'):
        return configured
    return core.default_base_id(gateway_id)


### ---------------------------------------------------------------------------
### the registry
### ---------------------------------------------------------------------------

class SimulatorRegistry:
    """The simulation model plus persistence and the sync with the configuration."""

    def __init__(self, hass: HomeAssistant):
        self.hass = hass
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self.model = core.SimulationModel()

    ### ------------------------------------------------------------- persistence

    async def async_load(self) -> None:
        stored = await self._store.async_load()
        self.model = core.SimulationModel.from_dict(
            stored or {}, on_error=lambda message: LOGGER.warning(f"[{LOG_PREFIX_SIM}] {message}"))
        devices = len(self.model.get_devices())
        if devices:
            LOGGER.info(f"[{LOG_PREFIX_SIM}] {devices} simulated device(s) on "
                        f"{len(self.model.get_gateway_ids())} simulated gateway(s) restored.")

    async def async_save(self) -> None:
        await self._store.async_save(self.model.to_dict())

    ### --------------------------------------------------- sync with the config

    def sync_with_config(self) -> None:
        """Take over the simulated gateways of the configuration - they are the truth.

        A gateway which is not configured anymore takes its virtual devices with it. Nothing
        happens as long as the configuration was not read yet: it must not look like all
        gateways were removed.
        """
        domain_data = (getattr(self.hass, 'data', None) or {}).get(DATA_ELTAKO, {})
        if ELTAKO_CONFIG not in domain_data:
            return

        all_gateways = get_gateway_configs(self.hass)
        simulated = {gateway_id for gateway_id, config in all_gateways.items()
                     if is_simulated_config(config)}
        # a real gateway is only of interest while it hosts simulated devices
        hosting = {gateway.id for gateway in self.model.get_gateways() if gateway.devices}
        relevant = {gateway_id for gateway_id in all_gateways
                    if gateway_id in simulated or gateway_id in hosting}

        for gateway_id in sorted(relevant):
            config = all_gateways[gateway_id]
            device_type = str(config.get(CONF_DEVICE_TYPE) or '')
            base_id = base_id_of(self.hass, gateway_id, config)
            name = config.get(CONF_NAME) or core.SIMULATOR_DEFAULT_NAME
            existing = self.model.get_gateway(gateway_id)
            if existing is None:
                self.model.add_gateway(gateway_id, device_type, name, base_id)
                LOGGER.debug(f"[{LOG_PREFIX_SIM}] Gateway {gateway_id} ({device_type}) taken over "
                             f"from the configuration.")
            else:
                existing.device_type = device_type
                existing.name = name
                # the base id of a real gateway only becomes known when it reports it, and every
                # address of its simulated devices derives from it
                existing.base_id = core.normalize_address(base_id)
                existing.simulated = gateway_id in simulated

        for gateway_id in self.model.get_gateway_ids():
            if gateway_id not in relevant:
                removed = self.model.remove_gateway(gateway_id)
                LOGGER.info(f"[{LOG_PREFIX_SIM}] Gateway {gateway_id} is not configured anymore - "
                            f"dropped it and {removed} simulated device(s).")

        for gateway_id in simulated:
            gateway = self.model.get_gateway(gateway_id)
            if gateway is not None:
                gateway.simulated = True

    ### ------------------------------------------------------------------- query

    def get_devices(self, gateway_id: int = None) -> list:
        return self.model.get_devices(gateway_id)

    def find(self, gateway_id: int, address):
        return self.model.find(gateway_id, address)

    def find_by_sender(self, gateway_id: int, sender_id):
        return self.model.find_by_sender(gateway_id, sender_id)

    def find_all_by_sender(self, gateway_id: int, sender_id) -> list:
        """Every simulated actuator of this gateway which knows that sender address."""
        return self.model.find_all_by_sender(gateway_id, sender_id)

    @property
    def active(self) -> bool:
        """False while the simulation is switched off - nothing of it is in Home Assistant."""
        return bool(self.model.active)

    @property
    def paused(self) -> bool:
        """True while nothing of the simulation runs (it is deactivated)."""
        return bool(self.model.paused)

    ### ------------------------------------------------------------------ change

    async def async_add_device(self, gateway_id: int, device):
        added = self.model.add_device(gateway_id, device)
        await self.async_save()
        LOGGER.info(f"[{LOG_PREFIX_SIM}] Gateway {gateway_id} simulates {added.platform} "
                    f"{added.address} ({added.eep}).")
        return added

    async def async_update_device(self, gateway_id: int, address, changes: dict):
        updated = self.model.update_device(gateway_id, address, changes or {})
        await self.async_save()
        return updated

    async def async_remove_device(self, gateway_id: int, address) -> bool:
        removed = self.model.remove_device(gateway_id, address)
        if removed:
            await self.async_save()
            LOGGER.info(f"[{LOG_PREFIX_SIM}] Removed simulated device {address} of "
                        f"gateway {gateway_id}.")
        return removed

    async def async_remove_gateway(self, gateway_id: int) -> int:
        removed = self.model.remove_gateway(gateway_id)
        await self.async_save()
        return removed

    async def async_teach_in(self, gateway_id: int, address, sender_id, eep: str = None,
                             name: str = None) -> dict:
        entry = self.model.teach_in(gateway_id, address, sender_id, eep, name)
        await self.async_save()
        LOGGER.info(f"[{LOG_PREFIX_SIM}] {entry['id']} ({entry.get('eep') or 'unknown profile'}) "
                    f"was taught into {address} of gateway {gateway_id}.")
        return entry

    async def async_forget_sender(self, gateway_id: int, address, sender_id) -> bool:
        removed = self.model.forget_sender(gateway_id, address, sender_id)
        if removed:
            await self.async_save()
            LOGGER.info(f"[{LOG_PREFIX_SIM}] {sender_id} does not control {address} of gateway "
                        f"{gateway_id} anymore.")
        return removed

    async def async_set_active(self, active: bool) -> bool:
        """Switch the whole simulation on or off. Returns the new state."""
        self.model.active = bool(active)
        await self.async_save()
        return self.model.active

    async def async_set_paused(self, paused: bool) -> bool:
        """Kept for callers which say 'pause' - deactivating is what it does."""
        return not await self.async_set_active(not paused)

    async def async_note_sent(self, gateway_id: int, address):
        device = self.model.require(gateway_id, address)
        device.note_sent()
        await self.async_save()
        return device


def get_registry(hass: HomeAssistant) -> SimulatorRegistry | None:
    """The registry, or None if the integration was not set up (yet)."""
    data = getattr(hass, 'data', None)
    if not isinstance(data, dict):
        return None
    return data.get(DATA_ELTAKO, {}).get(DATA_SIMULATOR)


async def async_setup_registry(hass: HomeAssistant) -> SimulatorRegistry:
    """Load the virtual devices and take over the configured gateways.

    Called during the setup of the integration (after the configuration was read) and by every
    action, so the registry is always available - in Home Assistant, in the standalone runtime
    and in a script alike.
    """
    registry = get_registry(hass)
    if registry is None:
        registry = SimulatorRegistry(hass)
        await registry.async_load()
        hass.data.setdefault(DATA_ELTAKO, {})[DATA_SIMULATOR] = registry

    registry.sync_with_config()
    return registry
