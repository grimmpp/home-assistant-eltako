"""Devices which send on their own: one timer per virtual device.

A real sensor is not triggered by anybody - it reports every few minutes, whether anything
changed or not. That is what makes the telegram rate, the statistics, the activity tracker
("has this device reported lately?") and an automation which reacts on a value testable at all.
So a simulated device can carry an interval (`SimulatedDevice.interval`, in seconds) and then
repeats its telegram until it is switched off again.

One timer per device, cancelled and rebuilt whenever the interval changes. The timers live in
`hass.data` next to the registry, so a gateway which is reloaded (adding a device does that) does
not lose them; a tick which finds no gateway simply skips - the next one will find it again.
"""

from __future__ import annotations

from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval

from ..const import DATA_ELTAKO, LOGGER
from . import core
from .store import get_registry, get_simulated_gateway_ids

LOG_PREFIX_SIM = "Simulator"

# where the cancel callbacks of the running timers are kept: {(gateway id, address): cancel}
DATA_SIMULATOR_TIMERS = "simulator_timers"


def _timers(hass: HomeAssistant) -> dict:
    return hass.data.setdefault(DATA_ELTAKO, {}).setdefault(DATA_SIMULATOR_TIMERS, {})


def get_running(hass: HomeAssistant) -> list[tuple[int, str]]:
    """(gateway id, address) of every device which is sending on its own right now."""
    return sorted(_timers(hass))


def is_running(hass: HomeAssistant, gateway_id: int, address: str) -> bool:
    return (int(gateway_id), str(address).upper()) in _timers(hass)


def cancel(hass: HomeAssistant, gateway_id: int, address: str) -> bool:
    """Stop the timer of one device. True if there was one."""
    key = (int(gateway_id), str(address).upper())
    stop = _timers(hass).pop(key, None)
    if stop is None:
        return False
    stop()
    LOGGER.debug(f"[{LOG_PREFIX_SIM}] {address} of gateway {gateway_id} stopped sending on its own.")
    return True


def cancel_all(hass: HomeAssistant) -> int:
    """Stop every timer (used when the integration goes down)."""
    timers = _timers(hass)
    for stop in list(timers.values()):
        stop()
    count = len(timers)
    timers.clear()
    return count


def is_paused(hass: HomeAssistant) -> bool:
    """True while the simulation is deactivated - then nothing is sent on its own."""
    registry = get_registry(hass)
    return bool(registry is not None and not registry.active)


def apply(hass: HomeAssistant, gateway_id: int, device) -> bool:
    """Start, restart or stop the timer of one device according to its interval.

    Returns True if the device is sending on its own afterwards. A paused simulation starts
    nothing: the interval stays stored, it simply does not run.
    """
    from .service import async_trigger

    cancel(hass, gateway_id, device.address)
    if not device.is_repeating or is_paused(hass):
        return False

    address = device.address
    interval = int(device.interval)

    async def _tick(now=None) -> None:
        registry = get_registry(hass)
        if registry is None:
            return
        if not registry.active:
            return          # deactivated: the timer keeps running, it just sends nothing
        current = registry.find(gateway_id, address)
        if current is None or not current.is_repeating:
            cancel(hass, gateway_id, address)       # the device is gone or was switched off
            return
        try:
            await async_trigger(hass, gateway_id, address)
        except core.SimulationError as e:
            # e.g. the gateway is being reloaded right now - the next tick tries again
            LOGGER.debug(f"[{LOG_PREFIX_SIM}] {address} of gateway {gateway_id} could not send: {e}")
        except Exception as e:      # noqa: BLE001 - a failing tick must not kill the timer
            LOGGER.warning(f"[{LOG_PREFIX_SIM}] {address} of gateway {gateway_id} could not "
                           f"send: {e}")

    _timers(hass)[(int(gateway_id), address.upper())] = async_track_time_interval(
        hass, _tick, timedelta(seconds=interval),
        name=f"eltako simulator {gateway_id}/{address}")
    LOGGER.info(f"[{LOG_PREFIX_SIM}] {address} of gateway {gateway_id} sends its telegram every "
                f"{interval} s.")
    return True


def apply_all(hass: HomeAssistant) -> int:
    """(Re)build the timers of every simulated device. Returns how many are sending.

    Called after the simulation was loaded (so an interval survives a restart), after a gateway
    was removed (so no timer of a gateway which is gone stays behind) and when the simulation is
    paused or continued.
    """
    registry = get_registry(hass)
    if registry is None:
        return 0

    if not registry.active:
        cancelled = cancel_all(hass)
        if cancelled:
            LOGGER.info(f"[{LOG_PREFIX_SIM}] The simulation is deactivated - stopped "
                        f"{cancelled} timer(s).")
        return 0

    known = get_simulated_gateway_ids(hass)
    for gateway_id, address in get_running(hass):
        if gateway_id not in known or registry.find(gateway_id, address) is None:
            cancel(hass, gateway_id, address)

    running = 0
    for gateway_id in sorted(known):
        for device in registry.get_devices(gateway_id):
            if apply(hass, gateway_id, device):
                running += 1
    return running


async def async_setup_scheduler(hass: HomeAssistant) -> int:
    """Start the timers of the stored intervals and stop them when Home Assistant does.

    Runs during the setup of the integration (after the simulation was loaded).
    """
    from homeassistant.const import EVENT_HOMEASSISTANT_STOP

    running = apply_all(hass)
    if running:
        LOGGER.info(f"[{LOG_PREFIX_SIM}] {running} simulated device(s) send on their own.")

    def _stop(event=None) -> None:
        cancel_all(hass)

    try:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _stop)
    except Exception as e:      # noqa: BLE001 - without the hook the timers die with the process
        LOGGER.debug(f"[{LOG_PREFIX_SIM}] Cannot register the shutdown hook: {e}")
    return running
