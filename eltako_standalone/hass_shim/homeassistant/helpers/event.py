"""Event helpers mirroring homeassistant.helpers.event."""

from __future__ import annotations

import asyncio
import inspect

from ..core import Event


def async_track_time_interval(hass, action, interval, name: str = None, cancel_on_shutdown=None):
    """Call `action` every `interval`. Returns a function which cancels the timer.

    Mirrors the signature of Home Assistant. `action` is called with the current time in
    Home Assistant; the shim has no clock of its own, so it is called with None.
    """
    seconds = interval.total_seconds() if hasattr(interval, 'total_seconds') else float(interval)

    async def runner():
        while True:
            await asyncio.sleep(seconds)
            try:
                result = action(None)
                if inspect.isawaitable(result):
                    await result
            except asyncio.CancelledError:
                raise
            except Exception:   # noqa: BLE001 - a failing tick must not stop the timer
                pass

    task = asyncio.get_event_loop().create_task(runner())

    def cancel():
        task.cancel()

    return cancel


def async_call_later(hass, delay, action):
    """Call `action` once after `delay` seconds. Returns a function which cancels it."""
    seconds = delay.total_seconds() if hasattr(delay, 'total_seconds') else float(delay)

    async def runner():
        await asyncio.sleep(seconds)
        result = action(None)
        if inspect.isawaitable(result):
            await result

    task = asyncio.get_event_loop().create_task(runner())

    def cancel():
        task.cancel()

    return cancel


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
