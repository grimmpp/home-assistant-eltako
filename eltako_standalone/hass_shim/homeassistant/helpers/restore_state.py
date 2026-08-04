"""State restoration mirroring homeassistant.helpers.restore_state.

The runtime persists all entity states into .storage/eltako_standalone.restore_state
on shutdown (and periodically). RestoreEntity.async_get_last_state() serves the
value from that snapshot - same contract as in Home Assistant.
"""

from __future__ import annotations

from ..core import State
from .entity import Entity

DATA_RESTORE_STATE = "restore_state"
STORAGE_KEY = "eltako_standalone.restore_state"
STORAGE_VERSION = 1


def get_last_states(hass) -> dict[str, State]:
    return hass.data.setdefault(DATA_RESTORE_STATE, {})


async def async_load_restore_state(hass) -> None:
    """Called by the runtime before entities are added."""
    from .storage import Store

    stored = await Store(hass, STORAGE_VERSION, STORAGE_KEY).async_load()
    states: dict[str, State] = {}
    for item in (stored or {}).get("states", []):
        try:
            state = State.from_dict(item)
            states[state.entity_id] = state
        except Exception:  # noqa: BLE001 - a broken snapshot entry is not fatal
            continue
    hass.data[DATA_RESTORE_STATE] = states


async def async_save_restore_state(hass) -> None:
    """Called by the runtime on shutdown."""
    from .storage import Store

    snapshot = [state.as_dict() for state in hass.states.all()]
    await Store(hass, STORAGE_VERSION, STORAGE_KEY).async_save({"states": snapshot})


class RestoreEntity(Entity):
    async def async_get_last_state(self) -> State | None:
        if self.hass is None or self.entity_id is None:
            return None
        return get_last_states(self.hass).get(self.entity_id)

    async def async_internal_added_to_hass(self) -> None:
        pass
