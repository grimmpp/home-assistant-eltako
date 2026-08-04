"""Event helpers mirroring homeassistant.helpers.event."""

from __future__ import annotations

from ..core import Event


def async_track_state_change_event(hass, entity_ids, action):
    """Call `action` with an Event carrying entity_id/old_state/new_state."""
    if isinstance(entity_ids, str):
        entity_ids = [entity_ids]
    wanted = {str(entity_id) for entity_id in entity_ids}

    def listener(entity_id, old_state, new_state):
        if entity_id not in wanted:
            return
        event = Event("state_changed", {
            "entity_id": entity_id, "old_state": old_state, "new_state": new_state})
        hass.invoke_listener(action, event)

    return hass.states.add_listener(listener)
