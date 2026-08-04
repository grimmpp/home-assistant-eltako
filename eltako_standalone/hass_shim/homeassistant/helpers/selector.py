"""Selector helper mirroring homeassistant.helpers.selector (validation only)."""


def selector(config: dict):
    """Return a permissive validator - selectors are ui sugar in Home Assistant."""
    def validate(value):
        return value
    validate.config = config
    return validate
