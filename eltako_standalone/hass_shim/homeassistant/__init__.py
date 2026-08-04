"""Minimal Home Assistant API shim for the Eltako standalone runtime.

This package mimics exactly the subset of the `homeassistant` package which
`custom_components/eltako` imports, so the integration code runs unchanged
without a Home Assistant installation. It is activated by putting the parent
directory (`eltako_standalone/hass_shim`) at the FRONT of sys.path before
anything imports `homeassistant` (see eltako_standalone.runtime.install_shim).

It is NOT a general purpose Home Assistant replacement.
"""

from . import config_entries  # noqa: F401 - `from homeassistant import config_entries`

__version__ = "0.0-eltako-standalone"
