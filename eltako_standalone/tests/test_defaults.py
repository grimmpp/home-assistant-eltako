"""The standalone runtime records telegrams and exports them to InfluxDB by default.

Home Assistant is a general purpose system where recording every telegram is opt-in. The
standalone runtime is a test/analysis tool, so it defaults the other way round - but only by
SEEDING the settings store once. Whatever the user changes afterwards must survive.
"""

import asyncio
import json
import os

from eltako_standalone.runtime import EltakoRuntime


def read_settings(config_dir: str) -> dict:
    path = os.path.join(config_dir, ".storage", "eltako_general_settings")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as handle:
        return json.load(handle).get("data", {}).get("overrides", {})


def effective_settings(runtime) -> dict:
    from custom_components.eltako.config_helpers import get_general_settings_from_configuration

    return get_general_settings_from_configuration(runtime.hass)


def test_defaults_are_seeded_on_a_fresh_config_folder(empty_config_dir):
    async def scenario():
        runtime = EltakoRuntime(empty_config_dir)
        await runtime.async_start()

        settings = effective_settings(runtime)
        assert settings["log_enocean_telegrams"] is True
        assert settings["telegram_log_filename"] == "enocean_telegrams.jsonl"
        assert settings["timeseries_enabled"] is True
        assert settings["timeseries_url"] == "http://localhost:8086"
        assert settings["timeseries_bucket"] == "eltako"
        assert settings["grafana_url"] == "http://localhost:3000"
        assert settings["enable_frontend"] is True

        # persisted, so they are visible and editable in the web ui
        assert read_settings(empty_config_dir)["timeseries_enabled"] is True

        await runtime.async_stop()
    asyncio.run(scenario())


def test_user_changes_are_not_overwritten_on_the_next_start(empty_config_dir):
    """The seed runs once. Turning the export off must stay off."""
    async def scenario():
        runtime = EltakoRuntime(empty_config_dir)
        await runtime.async_start()
        assert runtime.seeded_settings, "first start must seed"

        from custom_components.eltako import general_settings
        await general_settings.async_set_overrides(
            runtime.hass, {"timeseries_enabled": False, "grafana_url": ""})
        await runtime.async_stop()

        again = EltakoRuntime(empty_config_dir)
        await again.async_start()

        assert again.seeded_settings == {}, "second start must not seed again"
        settings = effective_settings(again)
        assert settings["timeseries_enabled"] is False
        assert settings["grafana_url"] == ""
        # untouched defaults of the first seed are still there
        assert settings["log_enocean_telegrams"] is True
        await again.async_stop()
    asyncio.run(scenario())


def test_configuration_yaml_is_not_shadowed(empty_config_dir):
    """Seeded values are ui overrides, which win over the yaml by design. A value the user
    explicitly wrote into configuration.yaml must therefore not be seeded at all."""
    with open(os.path.join(empty_config_dir, "configuration.yaml"), "w", encoding="utf-8") as handle:
        handle.write("eltako:\n"
                     "  general_settings:\n"
                     "    log_enocean_telegrams: False\n"
                     "    timeseries_enabled: False\n")

    async def scenario():
        runtime = EltakoRuntime(empty_config_dir)
        await runtime.async_start()

        assert "log_enocean_telegrams" not in runtime.seeded_settings
        assert "timeseries_enabled" not in runtime.seeded_settings
        settings = effective_settings(runtime)
        assert settings["log_enocean_telegrams"] is False
        assert settings["timeseries_enabled"] is False
        # everything not mentioned in the yaml is still seeded
        assert settings["grafana_url"] == "http://localhost:3000"

        await runtime.async_stop()
    asyncio.run(scenario())


def test_influx_defaults_can_be_overridden_by_environment(empty_config_dir, monkeypatch):
    monkeypatch.setenv("ELTAKO_INFLUX_URL", "http://influx.local:8086")
    monkeypatch.setenv("ELTAKO_GRAFANA_URL", "http://grafana.local:3000")
    import importlib

    from eltako_standalone import defaults
    importlib.reload(defaults)
    try:
        values = defaults.standalone_defaults()
        assert values["timeseries_url"] == "http://influx.local:8086"
        assert values["grafana_url"] == "http://grafana.local:3000"
    finally:
        monkeypatch.undo()
        importlib.reload(defaults)


def test_grafana_url_is_reported_to_the_web_ui(empty_config_dir):
    """The web ui builds the dashboard link from this field (pages/telegrams.js)."""
    async def scenario():
        runtime = EltakoRuntime(empty_config_dir)
        await runtime.async_start()

        from custom_components.eltako.enocean_logger import get_telegram_logger
        info = get_telegram_logger(runtime.hass).get_info()

        assert info["grafana_url"] == "http://localhost:3000"
        assert info["timeseries_enabled"] is True
        await runtime.async_stop()
    asyncio.run(scenario())
