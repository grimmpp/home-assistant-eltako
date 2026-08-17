"""Boots the Eltako integration without Home Assistant.

The integration code in custom_components/eltako runs completely unchanged: the
`homeassistant` package is provided by the shim in hass_shim/ (activated via
sys.path, see install_shim). This module wires everything together:

    install_shim()                      # must run before anything imports homeassistant
    runtime = EltakoRuntime(config_dir)
    await runtime.async_start()
    ...
    await runtime.async_stop()

The config folder works like the Home Assistant one:
    <config_dir>/configuration.yaml     # the same `eltako:` section as in HA
    <config_dir>/.storage/              # settings/gateways/devices created in the web ui
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys

LOGGER = logging.getLogger("eltako_standalone")

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SHIM_DIR = os.path.join(_REPO_ROOT, "eltako_standalone", "hass_shim")
DEFAULT_STORAGE_DIR = os.path.join(_REPO_ROOT, "standalone_configurations")

ENTRY_STORE_KEY = "eltako_standalone.config_entries"
ENTRY_STORE_VERSION = 1


def _silence_third_party_warnings() -> None:
    """The enocean library parses its EEP.xml with the html parser of
    BeautifulSoup, which prints a scary XMLParsedAsHTMLWarning on every start.
    Nothing we can fix here - suppress it before the library is imported."""
    try:
        import warnings

        from bs4 import XMLParsedAsHTMLWarning
        warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
    except ImportError:
        pass


def install_shim() -> None:
    """Make `import homeassistant` resolve to the shim. Must run first."""
    _silence_third_party_warnings()
    if "homeassistant" in sys.modules:
        module = sys.modules["homeassistant"]
        if _SHIM_DIR not in str(getattr(module, "__file__", "")):
            raise RuntimeError(
                "The real homeassistant package is already imported in this process - "
                "the standalone runtime must run in its own process.")
        return
    if _SHIM_DIR not in sys.path:
        sys.path.insert(0, _SHIM_DIR)
    if _REPO_ROOT not in sys.path:
        sys.path.insert(1, _REPO_ROOT)


class EltakoRuntime:
    def __init__(self, config_dir: str):
        self.config_dir = os.path.abspath(os.path.expanduser(config_dir))
        self.workspace_dir = self.config_dir
        self._storage_settings_path = os.path.join(self.config_dir, ".storage",
                                                   "eltako_standalone_settings.json")
        self.storage_dir = self._read_storage_dir()
        self.active_name = "default"
        self.hass = None
        self._integration = None
        self._entry_store = None
        self.seeded_settings = {}

    def _read_storage_dir(self) -> str:
        """Return the configured browser folder, defaulting to the repository workspace."""
        try:
            with open(self._storage_settings_path, encoding="utf-8") as handle:
                configured = json.load(handle).get("storage_dir")
            if configured:
                return os.path.abspath(os.path.expanduser(configured))
        except (OSError, ValueError, TypeError):
            pass
        return os.path.abspath(DEFAULT_STORAGE_DIR)

    def set_storage_dir(self, path: str) -> str:
        """Select and create the folder used by the standalone configuration browser."""
        selected = os.path.abspath(os.path.expanduser(path))
        os.makedirs(selected, exist_ok=True)
        self.storage_dir = selected
        os.makedirs(os.path.dirname(self._storage_settings_path), exist_ok=True)
        with open(self._storage_settings_path, "w", encoding="utf-8") as handle:
            json.dump({"storage_dir": selected}, handle, indent=2)
        return selected

    # ------------------------------------------------------------------ boot
    async def async_start(self) -> None:
        install_shim()
        os.makedirs(self.config_dir, exist_ok=True)

        from homeassistant.core import HomeAssistant
        from homeassistant.config_entries import ConfigEntries, ConfigEntry, ConfigEntryState
        from homeassistant.components.http import HomeAssistantHTTP
        from homeassistant.helpers.storage import Store
        from homeassistant.helpers import restore_state

        import custom_components.eltako.core.integration as integration
        self._integration = integration

        hass = HomeAssistant(self.config_dir, loop=asyncio.get_event_loop())
        hass.http = HomeAssistantHTTP()
        hass.config_entries = ConfigEntries(
            hass,
            setup_entry=integration.async_setup_entry,
            unload_entry=integration.async_unload_entry,
            forward_setup=self._async_forward_setup,
            forward_unload=self._async_forward_unload,
            on_change=self._async_persist_entries,
        )
        self.hass = hass
        hass.data.setdefault("eltako_standalone", {})["runtime"] = self

        # last known entity states (RestoreEntity)
        await restore_state.async_load_restore_state(hass)

        # config entries of the previous run (they carry the web ui devices in options)
        self._entry_store = Store(hass, ENTRY_STORE_VERSION, ENTRY_STORE_KEY)
        stored = await self._entry_store.async_load()
        for item in (stored or {}).get("entries", []):
            try:
                await hass.config_entries.async_add(ConfigEntry.from_dict(item), setup=False)
            except Exception:  # noqa: BLE001 - a broken persisted entry is not fatal
                LOGGER.exception("Cannot restore config entry %s", item)

        # On the very first start of a config folder: record telegrams and export them into
        # InfluxDB by default (see defaults.py). Must run before the integration reads the
        # settings store.
        from eltako_standalone.defaults import async_seed_settings
        self.seeded_settings = await async_seed_settings(hass)

        # the integration itself (config, websocket commands, telegram logger, panel)
        LOGGER.info("Setting up the Eltako integration (config folder: %s)", self.config_dir)
        await integration.async_setup(hass, {})

        # standalone extras: entity list/control commands and the functional
        # device tests of the EnOcean Device Manager (burst test, cover test)
        # device tests are registered by the integration itself now
        from eltako_standalone import entity_api
        entity_api.register_websocket_commands(hass)
        from eltako_standalone import configurations
        configurations.register_websocket_commands(hass)

        # one config entry per configured gateway (Home Assistant needs a manual step
        # here - standalone creates them automatically)
        await self._async_create_missing_gateway_entries()

        for entry in hass.config_entries.async_entries():
            if entry.state is not ConfigEntryState.LOADED:
                await hass.config_entries.async_setup(entry.entry_id)

        hass.bus.async_fire("homeassistant_started", {})
        LOGGER.info("Eltako standalone runtime is up (%d gateway entries).",
                    len(hass.config_entries.async_entries()))

    async def _async_create_missing_gateway_entries(self) -> None:
        from custom_components.eltako.const import (
            DATA_ELTAKO, ELTAKO_CONFIG, CONF_GATEWAY, CONF_GATEWAY_DESCRIPTION,
            CONF_SERIAL_PATH, DOMAIN)
        from homeassistant.const import CONF_ID, CONF_NAME
        from custom_components.eltako.config import gateway_config
        from homeassistant.config_entries import ConfigEntry

        config = self.hass.data.get(DATA_ELTAKO, {}).get(ELTAKO_CONFIG, {}) or {}
        existing = {entry.data.get(CONF_GATEWAY_DESCRIPTION)
                    for entry in self.hass.config_entries.async_entries(DOMAIN)}

        # a deactivated simulation stays out of the runtime: its gateways must not be set up
        # again on the next start (see custom_components/eltako/simulation)
        from custom_components.eltako import simulation

        simulation_off = not simulation.get_registry(self.hass).active \
            if simulation.get_registry(self.hass) is not None else False

        for gateway in config.get(CONF_GATEWAY, []) or []:
            if simulation_off and simulation.is_simulated_config(gateway):
                LOGGER.debug("Simulation is deactivated - gateway '%s' is not set up.",
                             gateway.get(CONF_NAME) or gateway.get(CONF_ID))
                continue
            try:
                description = gateway_config.get_description(gateway)
            except Exception:  # noqa: BLE001 - one malformed gateway must not stop the rest
                LOGGER.exception("Cannot build the description of gateway %s", gateway)
                continue
            if description in existing:
                continue
            entry = ConfigEntry(domain=DOMAIN, title=description, data={
                CONF_GATEWAY_DESCRIPTION: description,
                CONF_SERIAL_PATH: gateway_config.get_serial_path(gateway),
            })
            await self.hass.config_entries.async_add(entry, setup=False)
            LOGGER.info("Created config entry for gateway '%s'.", description)

    # ------------------------------------------------------------- platforms
    async def _async_forward_setup(self, entry, platforms) -> None:
        import importlib

        from homeassistant.helpers.entity_platform import EntityPlatform, register_platform
        from custom_components.eltako.const import DOMAIN

        for platform_name in platforms:
            platform_name = str(platform_name)
            module = importlib.import_module(f"custom_components.eltako.{platform_name}")
            platform = EntityPlatform(self.hass, domain=platform_name,
                                      platform_name=DOMAIN, config_entry=entry)
            register_platform(self.hass, platform)
            entry.platforms[platform_name] = platform
            try:
                await module.async_setup_entry(self.hass, entry, platform.async_add_entities)
            except Exception:  # noqa: BLE001 - one platform must not stop the others
                LOGGER.exception("Setup of platform %s failed", platform_name)

    async def _async_forward_unload(self, entry, platforms) -> bool:
        from homeassistant.helpers.entity_platform import unregister_platform

        for platform_name in list(entry.platforms):
            platform = entry.platforms.pop(platform_name)
            await platform.async_destroy()
            unregister_platform(self.hass, platform)
        return True

    # ------------------------------------------------------------ persistence
    async def _async_persist_entries(self) -> None:
        if self._entry_store is None:
            return
        entries = [entry.as_dict() for entry in self.hass.config_entries.async_entries()]
        await self._entry_store.async_save({"entries": entries})

    # ------------------------------------------------------------------ stop
    async def _async_stop_gateway_buses(self, join_timeout: float = 3.0) -> None:
        """Stop the serial threads of all gateways WITHOUT blocking the event loop.

        gateway.unload() calls `self._bus.join()` without a timeout. A bus whose
        port is gone sits in the 10s reconnect sleep of eltakobus (time.sleep, it
        does not observe the stop flag), so that join would freeze the loop for
        up to 10s per gateway - Ctrl+C then looks like it does not work. The
        threads are stopped here in the executor with a bounded join; a thread
        which is still stuck afterwards gets a no-op join so that the unload of
        the integration cannot block on it (the process exit reaps it).
        """
        from custom_components.eltako.const import DATA_ELTAKO
        from custom_components.eltako.core.gateway import EnOceanGateway

        gateways = [value for value in (self.hass.data.get(DATA_ELTAKO, {}) or {}).values()
                    if isinstance(value, EnOceanGateway)]

        def stop_bus(gateway) -> None:
            bus = getattr(gateway, "_bus", None)
            if bus is None:
                return
            try:
                bus.stop()
                if bus.is_alive():
                    bus.join(join_timeout)
                if bus.is_alive():
                    LOGGER.warning("Serial thread of gateway %s is stuck in its reconnect "
                                   "sleep - not waiting for it.", gateway.dev_id)
                    bus.join = lambda timeout=None: None
            except Exception:  # noqa: BLE001
                LOGGER.debug("Cannot stop the bus of gateway %s", gateway.dev_id, exc_info=True)

        await asyncio.gather(*(self.hass.async_add_executor_job(stop_bus, gateway)
                               for gateway in gateways))

    async def async_stop(self) -> None:
        if self.hass is None:
            return
        from homeassistant.helpers import restore_state

        LOGGER.info("Shutting down ...")
        # persist the states BEFORE the entities are removed by the unload
        try:
            await restore_state.async_save_restore_state(self.hass)
        except Exception:  # noqa: BLE001
            LOGGER.exception("Cannot persist the entity states")
        await self._async_stop_gateway_buses()
        for entry in self.hass.config_entries.async_entries():
            try:
                await self.hass.config_entries.async_unload(entry.entry_id)
            except Exception:  # noqa: BLE001
                LOGGER.exception("Cannot unload entry '%s'", entry.title)
        await self.hass.async_stop()
        LOGGER.info("Bye.")

    async def async_switch_configuration(self, name: str) -> None:
        """Stop the current installation and start another profile in this process."""
        from eltako_standalone.configurations import _profile_dir

        target = _profile_dir(self, name)
        if not target.is_dir():
            raise ValueError(f"Unknown configuration '{name}'")
        if os.path.abspath(self.config_dir) == os.path.abspath(str(target)):
            return
        await self.async_stop()
        self.config_dir = os.path.abspath(str(target))
        self.active_name = name
        await self.async_start()

    async def async_reload_configuration(self) -> None:
        """Restart after loading YAML and discard entities from the previous UI configuration.

        Standalone stores UI-created gateways and devices in Home Assistant config entries. If
        those entries were restored after loading another YAML file, the old entities would be
        merged into the new configuration again. Loading a file is therefore a clean replacement:
        stop the old runtime, clear its persisted UI entries, and let the new YAML create only the
        gateways and entities it declares.
        """
        current = self.config_dir
        active_name = self.active_name
        await self.async_stop()
        # ``async_stop`` unloads the entries but deliberately keeps them in the in-memory
        # ConfigEntries manager. Remove them as well; otherwise the next start can reuse the
        # gateways from the previous setup even though the persisted store is empty.
        for entry in list(self.hass.config_entries.async_entries()):
            await self.hass.config_entries.async_remove(entry.entry_id)
        await self._async_clear_persisted_ui_configuration()
        self.config_dir = current
        self.active_name = active_name
        await self.async_start()

    async def _async_clear_persisted_ui_configuration(self) -> None:
        """Remove standalone UI gateways/devices before a YAML configuration replacement."""
        if self._entry_store is not None:
            await self._entry_store.async_save({"entries": []})

        # Gateways created in the UI have their own store; UI devices live in the options of
        # the config entries above. Clearing both stores is what makes loading a configuration
        # a replacement instead of an additive merge.
        from custom_components.eltako.config.gateway_config import STORAGE_KEY, STORAGE_VERSION
        from custom_components.eltako.config.device_config import UNKNOWN_STORAGE_KEY, UNKNOWN_STORAGE_VERSION
        from homeassistant.helpers.storage import Store

        await Store(self.hass, STORAGE_VERSION, STORAGE_KEY).async_save({"gateways": []})
        await Store(self.hass, UNKNOWN_STORAGE_VERSION, UNKNOWN_STORAGE_KEY).async_save({"devices": []})
        LOGGER.info("Cleared persisted standalone UI gateways and devices before configuration reload.")
