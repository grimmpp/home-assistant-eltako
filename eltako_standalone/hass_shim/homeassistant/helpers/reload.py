"""Config loading mirroring homeassistant.helpers.reload.

async_integration_yaml_config() reads <config_dir>/configuration.yaml, validates
the section of the requested domain with the CONFIG_SCHEMA of the integration and
returns {domain: validated_config} - the same contract the integration relies on
in Home Assistant.
"""

from __future__ import annotations

import logging
import os

LOGGER = logging.getLogger("homeassistant.shim.reload")

CONFIGURATION_FILE = "configuration.yaml"


def _load_yaml(path: str) -> dict | None:
    import yaml

    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


async def async_integration_yaml_config(hass, domain: str):
    path = hass.config.path(CONFIGURATION_FILE)
    raw = await hass.async_add_executor_job(_load_yaml, path)
    if raw is None:
        LOGGER.debug("No %s found in %s", CONFIGURATION_FILE, hass.config.config_dir)
        return None
    if domain not in raw:
        return {}

    if domain == "eltako":
        # validate with the schema of the integration - same as Home Assistant does
        from custom_components.eltako.schema import CONFIG_SCHEMA
        return CONFIG_SCHEMA({domain: raw.get(domain) or {}})

    return {domain: raw.get(domain)}


async def async_reload_integration_platforms(hass, domain: str, platforms) -> None:
    LOGGER.debug("async_reload_integration_platforms(%s) is a no-op in standalone mode", domain)
