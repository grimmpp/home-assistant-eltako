"""Simulation: gateways and devices without any hardware.

Answers the question "does the integration work at all?" without a FAM14, a stick or a single
real device - and it does so with the *real* gateway types. A simulated gateway is a normal
gateway of this integration which carries `simulated: True` in its configuration: it has an id,
a base id, a config entry and entities; only its connection is not a serial port but the
simulation itself.

    simulated FAM14 (id 2, bus gateway -> local addresses)
      +- 00-00-00-01  light          M5-38-08   sender 00-00-B0-01 (A5-38-08)
      +- 00-00-00-05  sensor         A5-04-02   temperature=21.5 humidity=45
    simulated USB300 (id 3, wireless transceiver -> addresses of its base id range)
      +- FF-C0-03-01  binary_sensor  F6-02-01   4-way wall switch

Three things happen with it:

1. **Telegrams are injected** into the receive path of the gateway
   (`runtime.SimulatedGateway.simulate_incoming`) - exactly where a real gateway hands over what
   it read from its port. Everything behind it is untouched: entity states, telegram recording,
   statistics, device activity, the bus event and the timeseries export.
2. **Commands are answered.** A command Home Assistant sends to a simulated actuator (light,
   cover, heating) is decoded and the actuator reports its new state back - so switching a
   simulated light really turns the entity on.
3. **The devices are found.** A simulated device is a candidate of the plug & play detection
   (`service.derive_candidates`), so "search devices" takes it over into the configuration
   exactly like a device found on a real bus.
4. **They can send on their own.** A device with an interval repeats its telegram like a real
   sensor which reports every few minutes (`scheduler.py`), and its teach-in button announces its
   profile the way its profile family does it (4BS teach-in, 1BS learn telegram, RPS press).

Where things live:

    core/          the simulation itself - addresses, telegrams, actuator behaviour, model,
                   presets. No Home Assistant import: it can be moved into a library.
    store.py       the model in the Home Assistant storage, kept in sync with the config
    runtime.py     SimulatedGateway and SimulatorBus - the gateway of a simulation
    scheduler.py   the timers of the devices which send on their own (interval per device)
    service.py     the actions: create, change, trigger, presets, descriptors
    websocket.py   the eltako/simulator/* commands the web ui calls

The web ui is `frontend/pages/simulation.js`, the command line is
`python -m eltako_standalone simulate ...` - both only call `service.py`.
"""

from ..const import LOGGER                                                       # noqa: F401
from . import core                                                              # noqa: F401
from .core import (Command, SimulatedDevice, SimulationError, SimulationModel,  # noqa: F401
                   SimulatedGateway as SimulatedGatewayModel)
from .runtime import SimulatedGateway, SimulatorBus, create_gateway, get_gateway    # noqa: F401
from .scheduler import (apply_all as apply_intervals, async_setup_scheduler,     # noqa: F401
                        cancel_all as cancel_intervals, get_running as get_repeating_devices,
                        is_paused, is_running as is_repeating)
from .service import (async_add_device, async_add_gateway, async_add_preset,    # noqa: F401
                      async_remove_from_home_assistant, async_restore_in_home_assistant,
                      async_add_preset_devices, async_forget_sender, async_remove_device,
                      async_remove_gateway, async_send_base_id, async_set_interval,
                      async_set_active, async_set_paused, async_teach_in, async_trigger, async_update_device,
                      derive_candidates, describe_gateway, describe_platforms, get_overview,
                      get_seen_addresses)
from .store import (SimulatorRegistry, async_setup_registry, get_registry,      # noqa: F401
                    get_simulated_gateway_configs, get_simulated_gateway_ids,
                    is_simulated_config, is_simulated_gateway)
from .websocket import register_websocket_commands                              # noqa: F401


async def async_setup_simulation(hass) -> 'SimulatorRegistry':
    """Load the simulation and start the timers of the devices which send on their own.

    This is what the setup of the integration calls (see core/integration.py); the actions use
    `async_setup_registry` on their own.
    """
    registry = await async_setup_registry(hass)

    # A deactivated simulation must not come back by itself: an entry which was restored from
    # disk (or recreated by the standalone runtime) would bring its gateway and its devices along.
    if not registry.active:
        from .service import async_remove_gateway_entries

        removed = await async_remove_gateway_entries(hass)
        if removed:
            LOGGER.info(f"[Simulator] The simulation is deactivated - removed {removed} left over "
                        f"gateway entry/entries. Its devices are kept and can be edited.")

    await async_setup_scheduler(hass)
    return registry
