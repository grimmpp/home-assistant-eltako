"""JSON storage mirroring homeassistant.helpers.storage.Store.

Files live in <config_dir>/.storage/<key> and use the same envelope as Home
Assistant ({"version": ..., "key": ..., "data": ...}), so a standalone
installation pointed at a Home Assistant config folder reads the same stores
(settings overrides, ui gateways, ui devices, ...) and vice versa.
"""

from __future__ import annotations

import json
import logging
import os
import uuid

LOGGER = logging.getLogger("homeassistant.shim.storage")


class Store:
    def __init__(self, hass, version: int, key: str, *, private: bool = False,
                 atomic_writes: bool = True, encoder=None, minor_version: int = 1):
        self.hass = hass
        self.version = version
        self.minor_version = minor_version
        self.key = key

    @property
    def path(self) -> str:
        return self.hass.config.path(".storage", self.key)

    async def async_load(self):
        return await self.hass.async_add_executor_job(self._load)

    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as handle:
                envelope = json.load(handle)
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as e:
            LOGGER.warning("Cannot read store %s: %s", self.key, e)
            return None
        return envelope.get("data")

    async def async_save(self, data) -> None:
        await self.hass.async_add_executor_job(self._save, data)

    def async_delay_save(self, data_func, delay: float = 0) -> None:
        data = data_func() if callable(data_func) else data_func
        self.hass.async_create_task(self.async_save(data))

    def _save(self, data) -> None:
        envelope = {"version": self.version, "minor_version": self.minor_version,
                    "key": self.key, "data": data}
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        # unique temp name: concurrent saves of the same store (e.g. an import
        # creating many devices) must not steal each other's temp file
        tmp_path = f"{self.path}.{uuid.uuid4().hex}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(envelope, handle, ensure_ascii=False, indent=2, default=str)
        os.replace(tmp_path, self.path)

    async def async_remove(self) -> None:
        def _remove():
            try:
                os.remove(self.path)
            except FileNotFoundError:
                pass
        await self.hass.async_add_executor_job(_remove)
