"""Default settings of the standalone runtime.

Home Assistant is a general purpose home automation system - there, recording every telegram
is opt-in. The standalone runtime exists for testing, analysis and calibration, so the
opposite default makes sense: record everything, persist it and export it into a timeseries
database that Grafana can read.

The defaults are written into the settings store of the integration **once**, on the very
first start of a config folder (exactly like the seed of the dev container). From then on the
values belong to the user: whatever is changed in the web ui is kept, and re-running the
runtime never overwrites it. Delete `<config>/.storage/eltako_general_settings` to get the
defaults back.

`configuration.yaml` still wins over nothing here - these are stored ui overrides, which by
design take precedence over the yaml (see general_settings.py). Therefore a value that is
explicitly set in the yaml is NOT seeded, otherwise the seed would silently shadow it.
"""

from __future__ import annotations

import logging
import os

LOGGER = logging.getLogger(__name__)

# InfluxDB/Grafana of the analytics stack (dev/docker-compose.yml, profile 'analytics').
# Overridable via environment so a different instance can be used without editing code.
DEFAULT_INFLUX_URL = os.environ.get("ELTAKO_INFLUX_URL", "http://localhost:8086")
DEFAULT_INFLUX_TOKEN = os.environ.get("ELTAKO_INFLUX_TOKEN", "eltako-dev-token")
DEFAULT_INFLUX_ORG = os.environ.get("ELTAKO_INFLUX_ORG", "home")
DEFAULT_INFLUX_BUCKET = os.environ.get("ELTAKO_INFLUX_BUCKET", "eltako")
DEFAULT_GRAFANA_URL = os.environ.get("ELTAKO_GRAFANA_URL", "http://localhost:3000")

TELEGRAM_LOG_FILENAME = "enocean_telegrams.jsonl"


def standalone_defaults() -> dict:
    """Setting name -> value. Imported lazily so the shim is installed first."""
    from custom_components.eltako.const import (
        CONF_ENABLE_FRONTEND,
        CONF_GRAFANA_URL,
        CONF_LOG_ENOCEAN_TELEGRAMS,
        CONF_TELEGRAM_LOG_FILENAME,
        CONF_TIMESERIES_BUCKET,
        CONF_TIMESERIES_ENABLED,
        CONF_TIMESERIES_ORG,
        CONF_TIMESERIES_TOKEN,
        CONF_TIMESERIES_URL,
    )

    return {
        # the web ui is the point of the standalone runtime
        CONF_ENABLE_FRONTEND: True,
        # record and persist every telegram - this is a test and analysis tool
        CONF_LOG_ENOCEAN_TELEGRAMS: True,
        CONF_TELEGRAM_LOG_FILENAME: TELEGRAM_LOG_FILENAME,
        # export into InfluxDB so the history can be analysed in Grafana. If no InfluxDB is
        # running the exporter reports the connection error in the web ui and keeps retrying -
        # recording itself is not affected.
        CONF_TIMESERIES_ENABLED: True,
        CONF_TIMESERIES_URL: DEFAULT_INFLUX_URL,
        CONF_TIMESERIES_TOKEN: DEFAULT_INFLUX_TOKEN,
        CONF_TIMESERIES_ORG: DEFAULT_INFLUX_ORG,
        CONF_TIMESERIES_BUCKET: DEFAULT_INFLUX_BUCKET,
        CONF_GRAFANA_URL: DEFAULT_GRAFANA_URL,
    }


async def async_seed_settings(hass) -> dict:
    """Write the standalone defaults into the settings store if it is still empty.

    Returns the settings which were seeded (empty dict if nothing was written). Must run
    BEFORE the integration is set up, because the store is read there.
    """
    from custom_components.eltako.const import CONF_GERNERAL_SETTINGS, DOMAIN
    from custom_components.eltako.config.general_settings import STORAGE_KEY, STORAGE_VERSION
    from homeassistant.helpers.storage import Store

    store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
    try:
        stored = await store.async_load()
    except Exception as e:  # noqa: BLE001 - a broken store must not prevent the start
        LOGGER.warning("Cannot read the settings store, defaults are not seeded: %s", e)
        return {}

    if stored is not None:
        return {}       # the user owns the settings from now on

    # values which are explicitly configured in configuration.yaml must not be shadowed
    yaml_settings = _yaml_general_settings(hass, DOMAIN, CONF_GERNERAL_SETTINGS)
    seeded = {name: value for name, value in standalone_defaults().items()
              if name not in yaml_settings}

    if not seeded:
        return {}

    await store.async_save({'overrides': seeded})
    LOGGER.info("Standalone defaults applied (telegram recording and InfluxDB export are on): "
                "%s. Change them in the web ui under About -> Active configuration.",
                ", ".join(sorted(seeded)))
    return seeded


def _yaml_general_settings(hass, domain: str, settings_key: str) -> dict:
    """The `eltako: general_settings:` section of configuration.yaml, unvalidated."""
    path = os.path.join(hass.config.config_dir, "configuration.yaml")
    if not os.path.exists(path):
        return {}
    try:
        import yaml

        with open(path, encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}
        section = ((raw.get(domain) or {}).get(settings_key) or {})
        return section if isinstance(section, dict) else {}
    except Exception as e:  # noqa: BLE001 - the integration reports a broken yaml itself
        LOGGER.debug("Cannot read the general settings of configuration.yaml: %s", e)
        return {}
