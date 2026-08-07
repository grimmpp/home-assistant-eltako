"""The one error of the simulation."""

from __future__ import annotations


class SimulationError(ValueError):
    """Something cannot be simulated.

    Unknown EEP, malformed address, an address which is already in use, a device or gateway
    which does not exist. A ValueError on purpose: the core of the simulation must not force a
    caller to know voluptuous or Home Assistant.
    """
