"""Signal dispatcher mirroring homeassistant.helpers.dispatcher.

dispatcher_send() is thread-safe: called from the serial reader thread of
eltakobus it marshals every target into the event loop; called from the loop it
invokes the targets directly (same behaviour the integration relies on in HA).
"""

from __future__ import annotations

from typing import Callable

DATA_DISPATCHER = "dispatcher"


def _signals(hass) -> dict:
    return hass.data.setdefault(DATA_DISPATCHER, {})


def async_dispatcher_connect(hass, signal: str, target) -> Callable[[], None]:
    _signals(hass).setdefault(signal, []).append(target)

    def remove():
        try:
            _signals(hass).get(signal, []).remove(target)
        except ValueError:
            pass
    return remove


# the sync variant behaves identically here
dispatcher_connect = async_dispatcher_connect


def async_dispatcher_send(hass, signal: str, *args) -> None:
    for target in list(_signals(hass).get(signal, [])):
        hass.invoke_listener(target, *args)


def dispatcher_send(hass, signal: str, *args) -> None:
    """Thread-safe send."""
    hass.run_in_loop(async_dispatcher_send, hass, signal, *args)
