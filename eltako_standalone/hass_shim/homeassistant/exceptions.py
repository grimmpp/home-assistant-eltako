"""The Home Assistant exceptions the integration raises.

Only the ones which appear in `custom_components/eltako` are here - the shim mimics the
subset which is really used, see the package docstring.
"""


class HomeAssistantError(Exception):
    """General Home Assistant error. Its text reaches the user in the frontend."""


class ServiceValidationError(HomeAssistantError):
    """A service was called with values which cannot be used."""
