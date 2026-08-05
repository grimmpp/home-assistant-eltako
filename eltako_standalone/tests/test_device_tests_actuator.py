"""End to end: the actuator / teach-in test and the configuration check on a booted runtime.

The actuator test is the answer to "Home Assistant sends but nothing happens": it switches the
actuator and waits for its status telegram. Here the bus is faked - an actuator which answers,
one which stays silent - so both outcomes are covered without hardware.
"""

import asyncio
from unittest import mock

import pytest

from eltako_standalone.runtime import EltakoRuntime

CONFIG = """
eltako:
  general_settings:
    enable_frontend: True
  gateway:
  - id: 1
    device_type: fgw14usb
    base_id: FF-AA-80-00
    auto_reconnect: False
    serial_path: /dev/tty.test-gw1
    devices:
      switch:
      - id: 00-00-00-01
        eep: M5-38-08
        name: Relay
        sender: {id: 00-00-B0-01, eep: A5-38-08}
      light:
      - id: 00-00-00-02
        eep: M5-38-08
        name: Lamp
        sender: {id: 00-00-B0-02, eep: A5-38-08}
      cover:
      - id: 00-00-00-06
        eep: G5-3F-7F
        name: Cover
        sender: {id: 00-00-B0-06, eep: H5-3F-7F}
        time_closes: 24
        time_opens: 25
"""


@pytest.fixture
def config_dir(tmp_path):
    (tmp_path / "configuration.yaml").write_text(CONFIG, encoding="utf-8")
    return str(tmp_path)


async def _booted(config_dir):
    runtime = EltakoRuntime(config_dir)
    await runtime.async_start()
    await runtime.hass.async_block_till_done()
    return runtime


def _gateway(runtime, gateway_id):
    from custom_components.eltako.websocket import get_gateways
    return next(gw for gw in get_gateways(runtime.hass) if gw.dev_id == gateway_id)


def _answering_bus(gateway, answering: set[str]):
    """Fake bus: an actuator of `answering` replies with its status telegram.

    The reply is a 4BS telegram from the address of the actuator - exactly what an FSR14 puts
    on the bus after it switched. Every sent command is recorded.
    """
    from eltakobus.message import Regular4BSMessage

    sent = []
    bus = mock.Mock()
    bus.is_active.return_value = True

    # which sender belongs to which actuator (the answer has to come from the actuator)
    device_of_sender = {"00-00-B0-01": b"\x00\x00\x00\x01", "00-00-B0-02": b"\x00\x00\x00\x02"}

    async def send(msg):
        sent.append(msg)
        from eltakobus.util import b2s
        sender = b2s(msg.body[-5:-1])
        address = device_of_sender.get(sender)
        if address is None or b2s(address) not in answering:
            return
        gateway._callback_receive_message_from_serial_bus(
            Regular4BSMessage(address, 0x00, b"\x70\x00\x00\x09", True))

    bus.send = send
    gateway._bus = bus
    return sent


def _run(config_dir, params, answering):
    async def scenario():
        runtime = await _booted(config_dir)
        from custom_components.eltako.device_tests import run_actuator_test

        gateway = _gateway(runtime, 1)
        sent = _answering_bus(gateway, answering)
        # send_message dispatches into the event loop and the fake bus answers from there
        logs = []
        try:
            result = await run_actuator_test(
                runtime.hass, params,
                lambda line, style="info": logs.append((style, line)), asyncio.Event())
        finally:
            await runtime.async_stop()
        return result, logs, sent
    return asyncio.run(scenario())


def test_every_actuator_answers(config_dir):
    result, logs, sent = _run(config_dir, {"gateway": 1, "settle": 0, "timeout": 2},
                              {"00-00-00-01", "00-00-00-02"})

    assert result["success"] is True
    assert result["answered"] == result["total"] == 4      # two devices, ON and OFF each
    assert [step["command"] for step in result["steps"]] == ["ON", "OFF", "ON", "OFF"]
    assert all(step["response_s"] is not None for step in result["steps"])
    assert len(sent) == 4


def test_a_silent_actuator_is_reported_with_the_teach_in_hint(config_dir):
    result, logs, _sent = _run(config_dir, {"gateway": 1, "settle": 0, "timeout": 0.4},
                               {"00-00-00-01"})

    assert result["success"] is False
    assert result["answered"] == 2                          # only the relay answered
    silent = [step for step in result["steps"] if not step["answered"]]
    assert {step["device"] for step in silent} == {"00-00-00-02"}
    assert "taught" in silent[0]["problems"][0]
    assert any("NO ANSWER" in line for _style, line in logs)
    assert any("teach it in" in line for _style, line in logs)


def test_a_single_command_switches_once(config_dir):
    result, _logs, sent = _run(config_dir, {"gateway": 1, "command": "on", "settle": 0},
                               {"00-00-00-01", "00-00-00-02"})

    assert [step["command"] for step in result["steps"]] == ["ON", "ON"]
    assert len(sent) == 2


def test_only_the_selected_device(config_dir):
    result, _logs, sent = _run(config_dir,
                               {"gateway": 1, "devices": ["00-00-00-02"], "settle": 0},
                               {"00-00-00-02"})

    assert {step["device"] for step in result["steps"]} == {"00-00-00-02"}
    assert result["devices"] == ["00-00-00-02"]
    assert len(sent) == 2


def test_an_unknown_command_is_refused(config_dir):
    with pytest.raises(ValueError, match="on_off"):
        _run(config_dir, {"gateway": 1, "command": "blink"}, set())


def test_a_gateway_which_is_not_connected_is_refused(tmp_path):
    """No fake bus: the real one cannot open /dev/tty.test-gw1."""
    (tmp_path / "configuration.yaml").write_text(CONFIG, encoding="utf-8")

    async def scenario():
        runtime = await _booted(str(tmp_path))
        from custom_components.eltako.device_tests import run_actuator_test
        try:
            with pytest.raises(ValueError, match="not connected"):
                await run_actuator_test(runtime.hass, {"gateway": 1},
                                        lambda line, style="info": None, asyncio.Event())
        finally:
            await runtime.async_stop()
    asyncio.run(scenario())


def test_the_configuration_check_sees_the_devices_of_the_runtime(config_dir):
    """The check runs against the same configuration the runtime booted with."""
    async def scenario():
        runtime = await _booted(config_dir)
        from custom_components.eltako.config_check import check_configuration
        try:
            return check_configuration(runtime.hass)
        finally:
            await runtime.async_stop()

    result = asyncio.run(scenario())

    assert result["gateway_count"] == 1
    assert result["device_count"] == 3
    # the configuration is healthy, only hints are allowed
    assert result["counts"]["error"] == 0
    assert result["counts"]["warning"] == 0
