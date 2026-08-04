"""Config entries mirroring homeassistant.config_entries for the standalone runtime.

A ConfigEntry represents one gateway (exactly like in Home Assistant). The manager
persists the entries (incl. their options, which hold the devices created in the
web ui) in the .storage folder, so everything survives restarts.
"""

from __future__ import annotations

import logging
import uuid
from enum import Enum
from typing import Callable

LOGGER = logging.getLogger("homeassistant.shim.config_entries")

SOURCE_USER = "user"
STORAGE_KEY = "eltako_standalone.config_entries"
STORAGE_VERSION = 1


class ConfigEntryState(Enum):
    NOT_LOADED = "not_loaded"
    LOADED = "loaded"
    SETUP_ERROR = "setup_error"


class ConfigEntry:
    def __init__(self, *, domain: str, title: str = "", data: dict | None = None,
                 options: dict | None = None, entry_id: str | None = None,
                 unique_id: str | None = None, version: int = 1, source: str = SOURCE_USER):
        self.entry_id = entry_id or uuid.uuid4().hex
        self.domain = domain
        self.title = title
        self.data = dict(data or {})
        self.options = dict(options or {})
        self.unique_id = unique_id
        self.version = version
        self.source = source
        self.state = ConfigEntryState.NOT_LOADED
        self.update_listeners: list[Callable] = []
        self._on_unload: list[Callable] = []
        # entity platforms created for this entry (see ConfigEntries.async_forward_entry_setups)
        self.platforms: dict[str, object] = {}

    def add_update_listener(self, listener) -> Callable[[], None]:
        self.update_listeners.append(listener)

        def remove():
            try:
                self.update_listeners.remove(listener)
            except ValueError:
                pass
        return remove

    def async_on_unload(self, func) -> None:
        if func is not None:
            self._on_unload.append(func)

    def as_dict(self) -> dict:
        return {"entry_id": self.entry_id, "domain": self.domain, "title": self.title,
                "data": self.data, "options": self.options, "unique_id": self.unique_id,
                "version": self.version, "source": self.source}

    @classmethod
    def from_dict(cls, data: dict) -> "ConfigEntry":
        return cls(domain=data["domain"], title=data.get("title", ""), data=data.get("data"),
                   options=data.get("options"), entry_id=data.get("entry_id"),
                   unique_id=data.get("unique_id"), version=data.get("version", 1),
                   source=data.get("source", SOURCE_USER))


class _FlowManager:
    """Replaces the config flow: creating a flow directly creates and sets up the entry."""

    def __init__(self, manager: "ConfigEntries", title_key: str | None = None):
        self._manager = manager
        # the entry title is taken from this data field if present
        self._title_key = title_key or "gateway_description"

    async def async_init(self, domain: str, *, context: dict | None = None,
                         data: dict | None = None) -> dict:
        data = dict(data or {})
        title = str(data.get(self._title_key) or domain)

        for entry in self._manager.async_entries(domain):
            if entry.data.get(self._title_key) == data.get(self._title_key):
                return {"type": "abort", "reason": "already_configured"}

        entry = ConfigEntry(domain=domain, title=title, data=data,
                            source=(context or {}).get("source", SOURCE_USER))
        await self._manager.async_add(entry)
        return {"type": "create_entry", "result": entry, "title": title}


class ConfigEntries:
    """Manager, created by the runtime with the integration's setup/unload functions."""

    def __init__(self, hass, *, setup_entry=None, unload_entry=None, forward_setup=None,
                 forward_unload=None, on_change=None):
        self.hass = hass
        self._entries: list[ConfigEntry] = []
        self._setup_entry = setup_entry            # async (hass, entry) -> bool
        self._unload_entry = unload_entry          # async (hass, entry) -> bool
        self._forward_setup = forward_setup        # async (entry, platforms) -> None
        self._forward_unload = forward_unload      # async (entry, platforms) -> bool
        self._on_change = on_change                # async () -> None  (persistence hook)
        self.flow = _FlowManager(self)

    # ------------------------------------------------------------------ query
    def async_entries(self, domain: str | None = None) -> list[ConfigEntry]:
        if domain is None:
            return list(self._entries)
        return [entry for entry in self._entries if entry.domain == domain]

    def async_get_entry(self, entry_id: str) -> ConfigEntry | None:
        return next((entry for entry in self._entries if entry.entry_id == entry_id), None)

    # ----------------------------------------------------------------- manage
    async def async_add(self, entry: ConfigEntry, setup: bool = True) -> None:
        self._entries.append(entry)
        await self._notify_change()
        if setup:
            await self.async_setup(entry.entry_id)

    async def async_setup(self, entry_id: str) -> bool:
        entry = self.async_get_entry(entry_id)
        if entry is None or self._setup_entry is None:
            return False
        try:
            ok = await self._setup_entry(self.hass, entry)
        except Exception:  # noqa: BLE001 - a failing gateway must not kill the runtime
            LOGGER.exception("Setup of entry '%s' failed", entry.title)
            entry.state = ConfigEntryState.SETUP_ERROR
            return False
        entry.state = ConfigEntryState.LOADED if ok else ConfigEntryState.SETUP_ERROR
        return bool(ok)

    async def async_unload(self, entry_id: str) -> bool:
        entry = self.async_get_entry(entry_id)
        if entry is None:
            return False
        ok = True
        if self._unload_entry is not None and entry.state == ConfigEntryState.LOADED:
            try:
                ok = await self._unload_entry(self.hass, entry)
            except Exception:  # noqa: BLE001
                LOGGER.exception("Unload of entry '%s' failed", entry.title)
                ok = False
        for func in entry._on_unload:
            try:
                func()
            except Exception:  # noqa: BLE001
                LOGGER.exception("on_unload callback of '%s' failed", entry.title)
        entry._on_unload.clear()
        entry.state = ConfigEntryState.NOT_LOADED
        return ok

    async def async_reload(self, entry_id: str) -> bool:
        await self.async_unload(entry_id)
        return await self.async_setup(entry_id)

    async def async_remove(self, entry_id: str) -> dict:
        entry = self.async_get_entry(entry_id)
        if entry is None:
            return {"require_restart": False}
        await self.async_unload(entry_id)
        self._entries.remove(entry)
        await self._notify_change()
        return {"require_restart": False}

    def async_update_entry(self, entry: ConfigEntry, *, data: dict | None = None,
                           options: dict | None = None, title: str | None = None) -> bool:
        changed = False
        if data is not None and data != entry.data:
            entry.data = dict(data)
            changed = True
        if options is not None and options != entry.options:
            entry.options = dict(options)
            changed = True
        if title is not None and title != entry.title:
            entry.title = title
            changed = True
        if changed:
            self.hass.async_create_task(self._notify_change())
            for listener in list(entry.update_listeners):
                self.hass.async_create_task(listener(self.hass, entry))
        return changed

    # -------------------------------------------------------------- platforms
    async def async_forward_entry_setups(self, entry: ConfigEntry, platforms) -> None:
        if self._forward_setup is not None:
            await self._forward_setup(entry, platforms)

    async def async_unload_platforms(self, entry: ConfigEntry, platforms) -> bool:
        if self._forward_unload is not None:
            return await self._forward_unload(entry, platforms)
        return True

    # ------------------------------------------------------------ persistence
    async def _notify_change(self) -> None:
        if self._on_change is not None:
            await self._on_change()
