"""Tests: importing configurations (.eodm of the EnOcean Device Manager / yaml)."""

import asyncio
import os

from eltako_standalone.runtime import EltakoRuntime

EXAMPLE_EODM = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "examples", "demo.eodm")


def _example_content() -> str:
    with open(EXAMPLE_EODM, encoding="utf-8") as handle:
        return handle.read()


def test_parse_demo_eodm():
    from custom_components.eltako.config_import import parse_eodm, eodm_to_config

    data = parse_eodm(_example_content())
    gateways, warnings = eodm_to_config(data)

    by_type = {gateway["device_type"]: gateway for gateway in gateways}
    assert "fam14" in by_type

    fam14 = by_type["fam14"]
    assert fam14["base_id"] == "FF-CD-60-80"

    lights = fam14["devices"]["light"]
    fmz14 = next(device for device in lights if device["id"] == "00-00-00-01")
    assert fmz14["eep"] == "M5-38-08"
    # sender of a bus gateway: 00-00-B0-00 offset + last byte
    assert fmz14["sender"]["id"] == "00-00-B0-01"
    assert fmz14["sender"]["eep"] == "A5-38-08"

    covers = fam14["devices"]["cover"]
    assert any(device.get("time_closes") == 25 for device in covers)

    # wireless buttons keep their external id
    all_binary = [device for gateway in gateways
                  for device in gateway["devices"].get("binary_sensor", [])]
    assert any(device["id"] == "FE-DB-0A-1B" for device in all_binary)


def test_yaml_import_parsing():
    from custom_components.eltako.config_import import parse_import

    content = """
eltako:
  gateway:
  - id: 7
    device_type: fgw14usb
    base_id: FF-AA-80-00
    serial_path: /dev/ttyUSB7
    devices:
      light:
      - id: 00-00-00-01
        eep: M5-38-08
        sender: {id: 00-00-B0-01, eep: A5-38-08}
"""
    gateways, warnings, detected = parse_import(content)
    assert detected == "yaml"
    assert gateways[0]["serial_path"] == "/dev/ttyUSB7"
    assert len(gateways[0]["devices"]["light"]) == 1


def test_apply_import_creates_entities_and_is_idempotent(empty_config_dir):
    async def scenario():
        runtime = EltakoRuntime(empty_config_dir)
        await runtime.async_start()

        from custom_components.eltako.config_import import async_import
        from eltako_standalone.entity_api import list_entities

        content = _example_content()
        result = await async_import(runtime.hass, content, dry_run=False,
                                    gateway_overrides={"auto_reconnect": False})
        # ALL gateways of the file are imported - including the FGW14-USB which sits on
        # the same bus as the FAM14 (same base id). Several gateways on one bus are a
        # supported setup, commands are idempotent.
        assert result["created_gateways"] == 4
        assert result["skipped_gateways"] == 0
        assert result["created_devices"] >= 10
        await runtime.hass.async_block_till_done()

        entities = {entity["entity_id"] for entity in list_entities(runtime.hass)}
        assert any(entity.startswith("cover.") for entity in entities)
        assert any(entity.startswith("light.") for entity in entities)

        # importing the same file again must not duplicate anything: all gateways are
        # recognized (type + base id + name) and every device already exists
        again = await async_import(runtime.hass, content, dry_run=False,
                                   gateway_overrides={"auto_reconnect": False})
        assert again["created_gateways"] == 0
        assert again["created_devices"] == 0
        assert again["skipped_gateways"] == result["created_gateways"]
        assert again["skipped_devices"] == result["created_devices"]

        await runtime.async_stop()
    asyncio.run(scenario())


def test_reimport_merges_new_devices_onto_the_existing_gateway(empty_config_dir):
    """An extended file adds exactly the new parts - nothing is lost, nothing duplicated."""
    async def scenario():
        runtime = EltakoRuntime(empty_config_dir)
        await runtime.async_start()

        from custom_components.eltako.config_import import async_import

        first = """
eltako:
  gateway:
  - id: 1
    device_type: fgw14usb
    base_id: FF-AA-80-00
    name: Bus
    serial_path: /dev/ttyUSB9
    devices:
      light:
      - id: 00-00-00-01
        eep: M5-38-08
        sender: {id: 00-00-B0-01, eep: A5-38-08}
"""
        extended = first + """
      - id: 00-00-00-02
        eep: M5-38-08
        sender: {id: 00-00-B0-02, eep: A5-38-08}
"""
        result = await async_import(runtime.hass, first, dry_run=False,
                                    gateway_overrides={"auto_reconnect": False})
        assert result["created_gateways"] == 1
        assert result["created_devices"] == 1

        merged = await async_import(runtime.hass, extended, dry_run=False,
                                    gateway_overrides={"auto_reconnect": False})
        assert merged["created_gateways"] == 0
        assert merged["skipped_gateways"] == 1
        assert merged["created_devices"] == 1       # only the new light
        assert merged["skipped_devices"] == 1       # the existing one is untouched

        await runtime.async_stop()
    asyncio.run(scenario())


def test_dry_run_reports_plan(empty_config_dir):
    async def scenario():
        runtime = EltakoRuntime(empty_config_dir)
        await runtime.async_start()

        from custom_components.eltako.config_import import async_import

        preview = await async_import(runtime.hass, _example_content(), dry_run=True)
        assert preview["dry_run"] is True
        assert preview["format"] == "eodm"
        assert len(preview["gateways"]) >= 2
        assert sum(gateway["device_count"] for gateway in preview["gateways"]) >= 10

        await runtime.async_stop()
    asyncio.run(scenario())


def test_test_runner_suites():
    from eltako_standalone.test_runner import get_suites

    suites = {suite["id"]: suite for suite in get_suites()}
    assert suites["integration"]["available"]
    assert suites["standalone"]["available"]
    assert "device-manager" in suites
