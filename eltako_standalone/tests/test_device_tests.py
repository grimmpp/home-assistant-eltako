"""Tests: the functional device tests of the EnOcean Device Manager (burst, cover)."""

import asyncio
from unittest import mock

import pytest

from eltako_standalone.runtime import EltakoRuntime

TWO_GATEWAY_CONFIG = """
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
      cover:
      - id: 00-00-00-06
        eep: G5-3F-7F
        name: Rollladen
        sender: {id: 00-00-B0-06, eep: H5-3F-7F}
        time_closes: 24
        time_opens: 25
  - id: 2
    device_type: fgw14usb
    base_id: FF-BC-00-00
    auto_reconnect: False
    serial_path: /dev/tty.test-gw2
"""
# Both gateways sit on the RS485 bus on purpose: the burst test sends with the fixed addresses
# FF-00-00-01.., which lie outside every base id range, so a wireless transceiver would neither
# transmit nor hear them. device_tests.is_wired() rejects one - see
# tests/test_device_tests_wired_gateways.py. Gateway 2 used to be a fam-usb here, which no real
# burst test could have used.


@pytest.fixture
def two_gateway_config_dir(tmp_path):
    (tmp_path / "configuration.yaml").write_text(TWO_GATEWAY_CONFIG, encoding="utf-8")
    return str(tmp_path)


async def _booted(config_dir):
    runtime = EltakoRuntime(config_dir)
    await runtime.async_start()
    await runtime.hass.async_block_till_done()
    return runtime


def _fake_bus(gateway, on_send=None):
    """Replace the serial bus of a gateway: active, sends go to on_send."""
    bus = mock.Mock()
    bus.is_active.return_value = True

    async def send(msg):
        if on_send is not None:
            on_send(msg)
    bus.send = send
    gateway._bus = bus


def _gateway(runtime, gateway_id):
    from custom_components.eltako.core.websocket import get_gateways
    return next(gw for gw in get_gateways(runtime.hass) if gw.dev_id == gateway_id)


class TestResolveCovers:
    """The cover test takes the actuator addresses AND the sender addresses as arrays, so an
    actuator can be calibrated before it is configured."""

    def _resolve(self, config_dir, addresses, senders):
        async def scenario():
            runtime = await _booted(config_dir)
            from custom_components.eltako.tools.device_tests import resolve_covers
            try:
                return resolve_covers(runtime.hass, 1, addresses, senders)
            finally:
                await runtime.async_stop()
        return asyncio.run(scenario())

    def test_without_arrays_every_configured_cover(self, two_gateway_config_dir):
        covers = self._resolve(two_gateway_config_dir, None, None)

        assert [cover["id"] for cover in covers] == ["00-00-00-06"]
        assert covers[0]["sender_id"] == "00-00-B0-06"
        assert covers[0]["time_opens"] == 25

    def test_addresses_only_filter_the_configured_covers(self, two_gateway_config_dir):
        assert self._resolve(two_gateway_config_dir, ["00-00-00-06"], None)[0]["id"] == "00-00-00-06"
        # an address which is not configured has no sender - the test refuses it later
        unknown = self._resolve(two_gateway_config_dir, ["00-00-00-09"], None)
        assert unknown[0]["sender_id"] == ""

    def test_explicit_pairs_work_for_unconfigured_actuators(self, two_gateway_config_dir):
        covers = self._resolve(two_gateway_config_dir,
                               ["00-00-00-09", "00-00-00-0A"], ["00-00-B0-09", "00-00-B0-0A"])

        assert [(c["id"], c["sender_id"]) for c in covers] == [
            ("00-00-00-09", "00-00-B0-09"), ("00-00-00-0A", "00-00-B0-0A")]
        assert "not configured" in covers[0]["name"]

    def test_one_sender_for_all_actuators(self, two_gateway_config_dir):
        covers = self._resolve(two_gateway_config_dir,
                               ["00-00-00-09", "00-00-00-0A"], ["00-00-B0-09"])

        assert {c["sender_id"] for c in covers} == {"00-00-B0-09"}

    def test_explicit_sender_overrides_the_configured_one(self, two_gateway_config_dir):
        covers = self._resolve(two_gateway_config_dir, ["00-00-00-06"], ["00-00-B0-99"])

        assert covers[0]["sender_id"] == "00-00-B0-99"
        assert covers[0]["time_opens"] == 25        # configured data is kept
        assert "not configured" not in covers[0]["name"]

    def test_addresses_are_normalized_and_blanks_ignored(self, two_gateway_config_dir):
        covers = self._resolve(two_gateway_config_dir,
                               [" 00-00-00-06 ", ""], ["00-00-b0-06"])

        assert [(c["id"], c["sender_id"]) for c in covers] == [("00-00-00-06", "00-00-B0-06")]

    def test_mismatching_array_lengths_are_rejected(self, two_gateway_config_dir):
        with pytest.raises(ValueError, match="sender"):
            self._resolve(two_gateway_config_dir,
                          ["00-00-00-06", "00-00-00-07", "00-00-00-08"],
                          ["00-00-B0-06", "00-00-B0-07"])

    def test_senders_without_addresses_are_rejected(self, two_gateway_config_dir):
        with pytest.raises(ValueError, match="without actuator addresses"):
            self._resolve(two_gateway_config_dir, None, ["00-00-B0-06"])


def test_cover_test_runs_with_explicit_addresses(two_gateway_config_dir):
    """End to end: an actuator which is not in the configuration is driven."""
    async def scenario():
        runtime = await _booted(two_gateway_config_dir)
        from custom_components.eltako.tools.device_tests import run_cover_test

        sent = []
        _fake_bus(_gateway(runtime, 1), on_send=sent.append)
        result = await run_cover_test(
            runtime.hass,
            {"gateway": 1, "covers": ["00-00-00-09"], "senders": ["00-00-B0-09"],
             "sequence": "up:0.2,pause:0.1,down:0.2", "runs": 1},
            lambda line, style="info": None, asyncio.Event())

        assert result["covers"] == ["00-00-00-09"]
        assert result["senders"] == ["00-00-B0-09"]
        assert sent, "commands must be sent with the given sender"
        await runtime.async_stop()
    asyncio.run(scenario())


def test_parse_sequence_and_default():
    from custom_components.eltako.tools.device_tests import _parse_sequence, default_cover_sequence

    assert _parse_sequence("up:25, pause:2, down:25, stop") == \
        [("up", 25.0), ("pause", 2.0), ("down", 25.0), ("stop", 0.0)]
    assert default_cover_sequence([{"time_opens": 25, "time_closes": 24}]) == \
        "up:28,pause:2,down:27"
    with pytest.raises(ValueError):
        _parse_sequence("sideways:5")
    with pytest.raises(ValueError):
        _parse_sequence("up")          # missing duration


def test_burst_test_all_messages_received(two_gateway_config_dir):
    async def scenario():
        runtime = await _booted(two_gateway_config_dir)
        from custom_components.eltako.tools.device_tests import run_burst_test

        gw1, gw2 = _gateway(runtime, 1), _gateway(runtime, 2)
        # everything gateway 1 sends is "heard" by gateway 2 (radio link)
        _fake_bus(gw1, on_send=gw2._callback_receive_message_from_serial_bus)
        _fake_bus(gw2)

        logs = []
        result = await run_burst_test(
            runtime.hass, {"gateway1": 1, "gateway2": 2, "count": 5, "delay": 0,
                           "runs": 2, "settle": 0.3},
            lambda line, style="info": logs.append(line), asyncio.Event())

        assert result["success"] is True
        assert len(result["runs"]) == 2
        assert all(run["received"] == 5 and run["missing"] == 0 for run in result["runs"])
        await runtime.async_stop()
    asyncio.run(scenario())


def test_burst_test_reports_missing_messages(two_gateway_config_dir):
    async def scenario():
        runtime = await _booted(two_gateway_config_dir)
        from custom_components.eltako.tools.device_tests import run_burst_test

        gw1, gw2 = _gateway(runtime, 1), _gateway(runtime, 2)
        dropped = {"count": 0}

        def lossy_link(msg):
            dropped["count"] += 1
            if dropped["count"] != 2:      # drop the second telegram
                gw2._callback_receive_message_from_serial_bus(msg)
        _fake_bus(gw1, on_send=lossy_link)
        _fake_bus(gw2)

        result = await run_burst_test(
            runtime.hass, {"gateway1": 1, "gateway2": 2, "count": 4, "delay": 0,
                           "runs": 1, "settle": 0.3},
            lambda line, style="info": None, asyncio.Event())

        assert result["success"] is False
        assert result["runs"][0]["missing"] == 1
        assert result["runs"][0]["missing_addresses"] == ["FF-00-00-02"]
        await runtime.async_stop()
    asyncio.run(scenario())


def test_cover_test_measures_travel_times(two_gateway_config_dir):
    async def scenario():
        runtime = await _booted(two_gateway_config_dir)
        from custom_components.eltako.tools.device_tests import run_cover_test
        from eltakobus.eep import G5_3F_7F, H5_3F_7F

        gw1 = _gateway(runtime, 1)
        actuator = b"\x00\x00\x00\x06"

        def fsb14(msg):
            """Simulated FSB14: announces the movement and reports the travel time."""
            try:
                command = H5_3F_7F.decode_message(msg)
            except Exception:  # noqa: BLE001
                return
            if command.command not in (0x01, 0x02):
                return

            async def respond():
                await asyncio.sleep(0.05)
                start = G5_3F_7F(state=command.command).encode_message(actuator)
                gw1._callback_receive_message_from_serial_bus(start)
                await asyncio.sleep(0.1)
                report = G5_3F_7F(time=2, direction=command.command).encode_message(actuator)
                gw1._callback_receive_message_from_serial_bus(report)
            runtime.hass.async_create_task(respond())
        _fake_bus(gw1, on_send=fsb14)

        logs = []
        result = await run_cover_test(
            runtime.hass, {"gateway": 1, "sequence": "up:0.4,pause:0.2,down:0.4",
                           "runs": 1, "settle": 0.3, "delay": 0},
            lambda line, style="info": logs.append(line), asyncio.Event())

        assert result["success"] is True, logs
        assert len(result["movements"]) == 2       # one up, one down movement
        for movement in result["movements"]:
            assert movement["reported_s"] == 0.2   # the actuator reported 2 x 100ms
            assert not movement["problems"]
        assert result["recommendations"][0]["cover"] == "00-00-00-06"
        await runtime.async_stop()
    asyncio.run(scenario())


def test_cover_test_detects_missing_reaction(two_gateway_config_dir):
    async def scenario():
        runtime = await _booted(two_gateway_config_dir)
        from custom_components.eltako.tools.device_tests import run_cover_test

        _fake_bus(_gateway(runtime, 1))    # the actuator never answers

        result = await run_cover_test(
            runtime.hass, {"gateway": 1, "sequence": "up:0.2", "runs": 1,
                           "settle": 0.1, "delay": 0},
            lambda line, style="info": None, asyncio.Event())

        assert result["success"] is False
        assert result["movements"][0]["problems"] == ["no reaction"]
        await runtime.async_stop()
    asyncio.run(scenario())


def test_manager_and_websocket_flow(two_gateway_config_dir):
    async def scenario():
        runtime = await _booted(two_gateway_config_dir)
        from homeassistant.components.websocket_api import ActiveConnection, async_handle_message
        from custom_components.eltako.tools.device_tests import get_manager

        gw1, gw2 = _gateway(runtime, 1), _gateway(runtime, 2)
        _fake_bus(gw1, on_send=gw2._callback_receive_message_from_serial_bus)
        _fake_bus(gw2)

        messages = []
        connection = ActiveConnection(runtime.hass, messages.append)

        await async_handle_message(runtime.hass, connection,
                                   {"id": 1, "type": "eltako/device_tests/info"})
        info = messages[-1]["result"]
        # every test the backend can run is offered (order = TEST_DESCRIPTORS)
        from custom_components.eltako.tools.device_tests import TEST_DESCRIPTORS
        assert [test["id"] for test in info["tests"]] == \
            [descriptor["id"] for descriptor in TEST_DESCRIPTORS]
        assert {"burst", "cover"} <= {test["id"] for test in info["tests"]}
        assert len(info["gateways"]) == 2
        assert "1" in info["covers"]        # the configured cover of gateway 1

        await async_handle_message(runtime.hass, connection,
                                   {"id": 2, "type": "eltako/device_tests/subscribe"})
        await async_handle_message(runtime.hass, connection, {
            "id": 3, "type": "eltako/device_tests/start", "test": "burst",
            "params": {"gateway1": 1, "gateway2": 2, "count": 3, "delay": 0,
                       "runs": 1, "settle": 0.2}})
        assert messages[-1]["success"]

        # a second start while the test runs is rejected
        await async_handle_message(runtime.hass, connection, {
            "id": 4, "type": "eltako/device_tests/start", "test": "burst", "params": {}})
        assert messages[-1]["success"] is False

        while get_manager(runtime.hass).is_running:
            await asyncio.sleep(0.05)
        await runtime.hass.async_block_till_done()

        events = [m["event"] for m in messages if m.get("type") == "event"]
        assert any(event["kind"] == "log" for event in events)
        result_event = next(event for event in events if event["kind"] == "result")
        assert result_event["result"]["success"] is True
        await runtime.async_stop()
    asyncio.run(scenario())
