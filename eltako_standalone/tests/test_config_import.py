"""Tests: importing configurations (.eodm of the EnOcean Device Manager / PCT14 export / yaml)."""

import asyncio
import os

from eltako_standalone.runtime import EltakoRuntime

EXAMPLES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples")
EXAMPLE_EODM = os.path.join(EXAMPLES, "demo.eodm")
EXAMPLE_PCT14 = os.path.join(EXAMPLES, "demo_pct14_export.xml")


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _example_content() -> str:
    return _read(EXAMPLE_EODM)


def _pct14_content() -> str:
    return _read(EXAMPLE_PCT14)


def test_parse_demo_eodm():
    from custom_components.eltako.config.config_import import parse_eodm, eodm_to_config

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


def test_export_includes_persisted_unknown_devices():
    """Unknown metadata must be present in the YAML backup even when added after startup."""
    import yaml

    from custom_components.eltako.config.config_import import async_export
    from custom_components.eltako.const import DATA_ELTAKO, DATA_UNKNOWN_DEVICES, ELTAKO_CONFIG

    class Hass:
        data = {DATA_ELTAKO: {
            ELTAKO_CONFIG: {"general_settings": {}},
            DATA_UNKNOWN_DEVICES: [{"id": "FF-AA-80-01", "eep": "A5-04-02", "platform": "sensor"}],
        }}

    exported = asyncio.run(async_export(Hass()))
    config = yaml.safe_load(exported)
    assert config["eltako"]["unknown"] == [{
        "id": "FF-AA-80-01", "eep": "A5-04-02", "platform": "sensor"}]


def test_parse_pct14_export():
    """A PCT14 export becomes the FAM14 bus with its actuators and its taught-in senders."""
    from custom_components.eltako.config.config_import import parse_import

    gateways, warnings, detected = parse_import(_pct14_content())
    assert detected == "pct14"
    assert len(gateways) == 1

    fam14 = gateways[0]
    assert fam14["device_type"] == "fam14"
    assert fam14["base_id"] == "FF-A2-24-00"        # <baseid> of the <rootdevice>
    assert fam14["name"] == "Test Bus 1"            # <description> of the <rootdevice>

    # one device per channel, named after the descriptions the user typed into PCT14
    lights = {device["id"]: device for device in fam14["devices"]["light"]}
    assert lights["00-00-00-04"]["name"] == "FSR14-4x - Light Kitchen - Light 4"
    assert lights["00-00-00-04"]["eep"] == "M5-38-08"
    # sender of a bus device: offset of the local senders + its bus address
    assert lights["00-00-00-04"]["sender"] == {"id": "00-00-B0-04", "eep": "A5-38-08"}
    # the FMZ14 is switched with a rocker switch, not with a dimmer value
    assert lights["00-00-00-0A"]["sender"]["eep"] == "F6-02-01"

    # channels without their own description keep their number, so no two devices are alike
    covers = {device["id"]: device for device in fam14["devices"]["cover"]}
    assert covers["00-00-00-06"]["name"] == "FSB14 - 00-00-00-06 (1/2)"
    assert covers["00-00-00-06"]["device_class"] == "shutter"
    assert covers["00-00-00-06"]["time_closes"] == 25

    climate = {device["id"]: device for device in fam14["devices"]["climate"]}
    assert climate["00-00-00-08"]["name"] == "FAE14SSR - Heater 1 (1/2)"
    assert climate["00-00-00-08"]["min_target_temperature"] == 16

    # the senders taught into the actuators: wireless pushbuttons and FTS14EM inputs
    binary = {device["id"]: device for device in fam14["devices"]["binary_sensor"]}
    assert binary["FE-DB-DA-04"] == {"id": "FE-DB-DA-04", "eep": "F6-02-01",
                                     "name": "Button FE-DB-DA-04"}
    assert binary["00-00-10-10"]["name"] == "FTS14EM input 00-00-10-10"
    # ... and the sensors whose EEP the key function of the teach-in reveals
    sensors = {device["id"]: device for device in fam14["devices"]["sensor"]}
    assert sensors["FF-E2-35-92"]["eep"] == "A5-10-12"

    # the virtual senders of home assistant itself (00-00-B*) are no devices
    assert not any(address.startswith("00-00-B") for address in binary)
    assert not any(address.startswith("00-00-B") for address in sensors)

    # an address can only be one device: a taught-in sender which is a bus position of the
    # export (an actuator used for a central function) is not imported a second time
    per_address: dict[str, list[str]] = {}
    for platform, devices in fam14["devices"].items():
        for device in devices:
            per_address.setdefault(device["id"], []).append(platform)
    assert not [address for address, platforms in per_address.items() if len(platforms) > 1]

    # the FGW14 of the same rack is no second gateway of this import
    assert any("FGW14" in warning for warning in warnings)


def test_pct14_detection_and_broken_xml():
    import voluptuous as vol
    from custom_components.eltako.config.config_import import is_pct14, parse_import

    assert is_pct14(_pct14_content())
    assert not is_pct14(_example_content())

    try:
        parse_import("<exchange><rootdevice></exchange>")
    except vol.Invalid as e:
        assert "xml" in str(e).lower()
    else:
        raise AssertionError("a broken PCT14 export must be reported as an invalid file")

    try:
        parse_import("<exchange version='5.0'><rootdevice/></exchange>")
    except vol.Invalid as e:
        assert "FAM14" not in str(e) or "rootdevice" in str(e)


def test_apply_pct14_import_creates_entities(empty_config_dir):
    async def scenario():
        runtime = EltakoRuntime(empty_config_dir)
        await runtime.async_start()

        from custom_components.eltako.config.config_import import async_import
        from eltako_standalone.entity_api import list_entities

        result = await async_import(runtime.hass, _pct14_content(), dry_run=False,
                                    gateway_overrides={"auto_reconnect": False})
        assert result["created_gateways"] == 1
        assert result["created_devices"] >= 20
        await runtime.hass.async_block_till_done()

        entities = {entity["entity_id"] for entity in list_entities(runtime.hass)}
        for domain in ("light.", "cover.", "climate.", "binary_sensor.", "sensor."):
            assert any(entity.startswith(domain) for entity in entities), domain

        # importing the same export again changes nothing
        again = await async_import(runtime.hass, _pct14_content(), dry_run=False,
                                   gateway_overrides={"auto_reconnect": False})
        assert again["created_gateways"] == 0
        assert again["created_devices"] == 0
        assert again["skipped_devices"] == result["created_devices"]

        await runtime.async_stop()
    asyncio.run(scenario())


def test_yaml_import_parsing():
    from custom_components.eltako.config.config_import import parse_import

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

        from custom_components.eltako.config.config_import import async_import
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

        from custom_components.eltako.config.config_import import async_import

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

        from custom_components.eltako.config.config_import import async_import

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
