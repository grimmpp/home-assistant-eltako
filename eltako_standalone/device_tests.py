"""Functional device tests of the EnOcean Device Manager, running on the
standalone runtime.

Ported from eo_man (https://github.com/grimmpp/enocean-device-manager):

* **burst** (BusBurstTester): sends a burst of test telegrams through one
  gateway and verifies that a second gateway receives every single one -
  checks the reliability of the bus/radio link and the message delay.
* **cover** (CoverTravelTester): drives the configured covers with a sequence
  of movement commands, records every telegram and measures the real travel
  times - the base for configuring the runtime (time_closes/time_opens) of an
  FSB actuator.

Unlike eo_man the tests do not open their own serial connections - they use
the gateways of the running standalone runtime and the covers (incl. their
sender ids) of the configuration.

Used by `python -m eltako_standalone devicetest ...` and the 'Tests' page of
the web ui (websocket commands eltako/device_tests/*).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Callable

from eltakobus.eep import G5_3F_7F, H5_3F_7F
from eltakobus.message import EltakoPoll, EltakoTimeout, Regular4BSMessage, prettify
from eltakobus.util import AddressExpression, b2s

from homeassistant.const import CONF_ID
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from custom_components.eltako import config_helpers
from custom_components.eltako.const import (
    CONF_SENDER, CONF_TIME_CLOSES, CONF_TIME_OPENS,
    DATA_ELTAKO, ELTAKO_CONFIG, SIGNAL_RECEIVE_MESSAGE)
from custom_components.eltako.websocket import get_gateways

LOGGER = logging.getLogger("eltako_standalone.device_tests")

DATA_DEVICE_TEST_MANAGER = "eltako_standalone_device_test_manager"

WS_DEVICE_TESTS_INFO = "eltako/device_tests/info"
WS_DEVICE_TESTS_START = "eltako/device_tests/start"
WS_DEVICE_TESTS_STOP = "eltako/device_tests/stop"
WS_DEVICE_TESTS_SUBSCRIBE = "eltako/device_tests/subscribe"

# cover command values of EEP H5-3F-7F (DB1)
COVER_STOP, COVER_UP, COVER_DOWN = 0x00, 0x01, 0x02
COVER_COMMANDS = {"up": COVER_UP, "down": COVER_DOWN, "stop": COVER_STOP}
DIRECTION_NAMES = {COVER_UP: "UP", COVER_DOWN: "DOWN", COVER_STOP: "STOP"}
# RPS status telegrams of EEP G5-3F-7F
COVER_END_POSITIONS = {0x70: "top end position", 0x50: "bottom end position"}
COVER_MOVEMENT_STARTED = {0x01: COVER_UP, 0x02: COVER_DOWN}
# a command telegram can carry at most 25.5s travel time (DB2, 100ms steps)
MAX_COMMAND_TRAVEL_TIME = 25.5

TEST_DESCRIPTORS = [
    {
        "id": "burst",
        "name": "Bus burst test",
        "description": "Sends a burst of test telegrams through gateway 1 and verifies that "
                       "gateway 2 receives every single one. Checks the reliability of the "
                       "link and whether the message delay is sufficient. Needs two "
                       "connected gateways (like in the EnOcean Device Manager).",
    },
    {
        "id": "cover",
        "name": "Cover travel time test",
        "description": "Drives the selected covers with a sequence of movement commands "
                       "(e.g. up:25, pause:2, down:25), records their status telegrams and "
                       "measures the real travel times - the base for configuring the "
                       "runtime of an FSB actuator (time_closes / time_opens).",
    },
]


def _parse_sequence(text: str) -> list[tuple[str, float]]:
    """'up:25, pause:2, down:25, stop' -> [('up', 25.0), ('pause', 2.0), ...]"""
    steps = []
    for part in str(text).split(","):
        part = part.strip()
        if not part:
            continue
        pieces = [p.strip() for p in part.split(":")]
        name = pieces[0].lower()
        if name not in ("up", "down", "stop", "pause"):
            raise ValueError(f"Unknown movement command '{pieces[0]}'. "
                             f"Supported: up, down, stop, pause (e.g. 'up:25,pause:2,down:25').")
        if len(pieces) > 1 and pieces[1] != "":
            duration = float(pieces[1].replace(",", "."))
        elif name == "stop":
            duration = 0.0
        else:
            raise ValueError(f"Missing duration for '{part}' - use e.g. '{name}:20'.")
        if duration < 0:
            raise ValueError(f"Duration of '{part}' must not be negative.")
        steps.append((name, duration))
    if not steps:
        raise ValueError("The movement sequence is empty - use e.g. 'up:25,pause:2,down:25'.")
    return steps


def _find_gateway(hass, gateway_id):
    return next((gw for gw in get_gateways(hass) if gw.dev_id == int(gateway_id)), None)


def _is_connected(gateway) -> bool:
    try:
        return bool(gateway._bus.is_active())
    except Exception:  # noqa: BLE001
        return False


def get_configured_covers(hass, gateway_id: int) -> list[dict]:
    """Covers of the configuration of one gateway incl. their sender ids."""
    config = hass.data.get(DATA_ELTAKO, {}).get(ELTAKO_CONFIG, {}) or {}
    devices = config_helpers.get_device_config(config, int(gateway_id)) or {}
    covers = []
    for entry in devices.get("cover", []) or []:
        sender = entry.get(CONF_SENDER) or {}
        covers.append({
            "id": str(entry.get(CONF_ID, "")).upper(),
            "name": entry.get("name") or str(entry.get(CONF_ID, "")),
            "sender_id": str(sender.get(CONF_ID, "")).upper(),
            "time_closes": entry.get(CONF_TIME_CLOSES),
            "time_opens": entry.get(CONF_TIME_OPENS),
        })
    return covers


def resolve_covers(hass, gateway_id: int, addresses: list | None,
                   senders: list | None) -> list[dict]:
    """Covers to test, from the configuration and/or from explicit address arrays.

    Three ways to select them - a calibration run must not require the device to be
    configured first:

    * neither array: every configured cover of the gateway
    * only `addresses`: those configured covers (a filter, as before)
    * `addresses` + `senders`: used pairwise by position, also for covers which are NOT
      configured. For a configured address the given sender overrides the configured one,
      everything else (name, known travel times) is kept.

    A single sender for several addresses is applied to all of them - handy for a rack where
    one Home Assistant sender is taught into several channels.
    """
    configured = {cover["id"]: cover for cover in get_configured_covers(hass, gateway_id)}

    wanted = [str(address).strip().upper() for address in (addresses or []) if str(address).strip()]
    sender_list = [str(sender).strip().upper() for sender in (senders or []) if str(sender).strip()]

    if not wanted:
        if sender_list:
            raise ValueError("Sender addresses were given without actuator addresses - "
                             "the two arrays are used pairwise by position.")
        return [cover for cover in configured.values()]

    if sender_list and len(sender_list) not in (1, len(wanted)):
        raise ValueError(f"{len(wanted)} actuator address(es) but {len(sender_list)} sender "
                         f"address(es). Give one sender per actuator, or a single sender for "
                         f"all of them.")

    covers = []
    for index, address in enumerate(wanted):
        cover = dict(configured.get(address) or {
            "id": address, "name": address, "sender_id": "",
            "time_closes": None, "time_opens": None,
        })
        if sender_list:
            cover["sender_id"] = sender_list[index] if len(sender_list) > 1 else sender_list[0]
            if address not in configured:
                cover["name"] = f"{address} (not configured)"
        covers.append(cover)
    return covers


def default_cover_sequence(covers: list[dict]) -> str:
    """up long enough for the slowest cover, short pause, down again."""
    up = max([c.get("time_opens") or 0 for c in covers] + [0]) or 22
    down = max([c.get("time_closes") or 0 for c in covers] + [0]) or 22
    return f"up:{min(up + 3, 120):g},pause:2,down:{min(down + 3, 120):g}"


### ---------------------------------------------------------------------------
### burst test (port of eo_man BusBurstTester)
### ---------------------------------------------------------------------------

async def run_burst_test(hass, params: dict, log: Callable[[str, str], None],
                         stop_event: asyncio.Event) -> dict:
    gateway1 = _find_gateway(hass, params.get("gateway1"))
    gateway2 = _find_gateway(hass, params.get("gateway2"))
    if gateway1 is None or gateway2 is None:
        raise ValueError("The burst test needs two gateways (gateway1 sends, gateway2 receives).")
    if gateway1.dev_id == gateway2.dev_id:
        raise ValueError("gateway1 and gateway2 must be different gateways.")
    for gateway in (gateway1, gateway2):
        if not _is_connected(gateway):
            raise ValueError(f"Gateway {gateway.dev_id} ({gateway.serial_path}) is not connected.")

    message_count = int(params.get("count") or 44)
    message_delay = float(params.get("delay") or 0.01)
    runs = int(params.get("runs") or 1)

    # the same test addresses eo_man uses: FF-00-00-01 ...
    messages, addresses = [], []
    for n in range(1, message_count + 1):
        address = (0xFF000000 + n).to_bytes(4, "big")
        messages.append(Regular4BSMessage(address, 0x20, b"\x00\x00\x00\x00", True))
        addresses.append(b2s(address))

    received: set[str] = set()
    other_count = 0

    def on_receive(data) -> None:
        nonlocal other_count
        msg = data.get("esp2_msg")
        if msg is None or isinstance(msg, (EltakoPoll, EltakoTimeout)):
            return
        try:
            address = b2s(msg.body[6:10])
        except Exception:  # noqa: BLE001
            return
        if address in addresses:
            received.add(address)
        else:
            other_count += 1

    event_id = config_helpers.get_bus_event_type(gateway2.dev_id, SIGNAL_RECEIVE_MESSAGE)
    unsubscribe = async_dispatcher_connect(hass, event_id, on_receive)

    results = []
    try:
        for run in range(1, runs + 1):
            if stop_event.is_set():
                break
            received.clear()
            other_count = 0
            log(f"Burst test run {run}/{runs}: sending {message_count} telegrams via gateway "
                f"{gateway1.dev_id}, delay {message_delay}s ...", "info")

            for message in messages:
                if stop_event.is_set():
                    break
                gateway1.send_message(message)
                await asyncio.sleep(message_delay)

            settle = float(params.get("settle", 4.0))
            log(f"Waiting {settle:g}s for the telegrams to arrive on gateway "
                f"{gateway2.dev_id} ...", "info")
            await asyncio.sleep(settle)

            missing = [address for address in addresses if address not in received]
            ok = len(missing) == 0
            if ok:
                log(f"=> Run {run} SUCCESSFUL: all {message_count} telegrams were received.", "ok")
            else:
                log(f"=> Run {run} FAILED: {len(missing)} telegram(s) were not received: "
                    f"{', '.join(missing[:10])}{' ...' if len(missing) > 10 else ''}", "error")
            results.append({"run": run, "sent": message_count,
                            "received": message_count - len(missing),
                            "missing": len(missing), "missing_addresses": missing,
                            "other_messages": other_count, "success": ok})
    finally:
        unsubscribe()

    successful = len([r for r in results if r["success"]])
    log(f"{successful} of {len(results)} runs were successful "
        f"({message_count} telegrams per run, delay {message_delay}s).",
        "ok" if successful == len(results) else "error")
    return {"test": "burst", "success": bool(results) and successful == len(results),
            "runs": results,
            "gateway1": gateway1.dev_id, "gateway2": gateway2.dev_id,
            "message_count": message_count, "message_delay": message_delay}


### ---------------------------------------------------------------------------
### cover travel time test (port of eo_man CoverTravelTester, reduced)
### ---------------------------------------------------------------------------

async def run_cover_test(hass, params: dict, log: Callable[[str, str], None],
                         stop_event: asyncio.Event) -> dict:
    gateway = _find_gateway(hass, params.get("gateway"))
    if gateway is None:
        raise ValueError(f"No gateway with id {params.get('gateway')}.")
    if not _is_connected(gateway):
        raise ValueError(f"Gateway {gateway.dev_id} ({gateway.serial_path}) is not connected.")

    covers = resolve_covers(hass, gateway.dev_id, params.get("covers"), params.get("senders"))
    if not covers:
        raise ValueError("No covers to test. Configure covers for this gateway, or give the "
                         "actuator and sender addresses explicitly.")
    without_sender = [cover["id"] for cover in covers if not cover["sender_id"]]
    covers = [cover for cover in covers if cover["sender_id"]]
    if not covers:
        raise ValueError(f"No sender address for {', '.join(without_sender)} - Home Assistant "
                         f"needs one to send commands. Configure the cover with a sender or "
                         f"pass the sender addresses along with the actuator addresses.")
    if without_sender:
        log(f"Skipped (no sender address): {', '.join(without_sender)}", "warning")

    sequence = _parse_sequence(params.get("sequence") or default_cover_sequence(covers))
    runs = int(params.get("runs") or 1)
    message_delay = float(params.get("delay") or 0.1)

    log(f"Cover travel time test on gateway {gateway.dev_id}: "
        f"{', '.join(c['id'] for c in covers)}", "info")
    log("Sequence: " + " -> ".join(f"{name.upper()} {duration:g}s"
                                   for name, duration in sequence), "info")

    movements: list[dict] = []
    open_movements: dict[str, dict] = {}
    interference_count = 0
    start_timestamp = time.time()

    def now() -> float:
        return time.time() - start_timestamp

    def on_receive(data) -> None:
        nonlocal interference_count
        msg = data.get("esp2_msg")
        if msg is None or isinstance(msg, (EltakoPoll, EltakoTimeout)):
            return
        try:
            telegram = prettify(msg)
            address = b2s(telegram.address)
        except Exception:  # noqa: BLE001
            return

        movement = open_movements.get(address)
        if movement is None:
            # telegram of a device which is not under test while a movement runs
            if open_movements and not isinstance(getattr(telegram, "address", None), int):
                interference_count += 1
            return

        event = {"time": now() - movement["start_time"]}
        try:
            status = G5_3F_7F.decode_message(telegram)
        except Exception:  # noqa: BLE001
            movement["events"].append(event)
            return

        if status.time is not None:
            # 4BS: the actuator reports direction and how long it really moved
            event["travel_report_s"] = status.time / 10.0
            event["direction"] = status.direction
            movement["reported_s"] = status.time / 10.0
            movement["direction"] = status.direction
            log(f"  [{now():7.2f}s] {address}: moved "
                f"{DIRECTION_NAMES.get(status.direction, status.direction)} for "
                f"{status.time / 10.0:.1f}s (travel report)", "received")
        elif status.state in COVER_END_POSITIONS:
            event["end_position"] = status.state
            movement["end_position"] = COVER_END_POSITIONS[status.state]
            movement["measured_s"] = event["time"]
            log(f"  [{now():7.2f}s] {address}: reached {COVER_END_POSITIONS[status.state]}",
                "received")
        elif status.state in COVER_MOVEMENT_STARTED:
            event["movement_started"] = COVER_MOVEMENT_STARTED[status.state]
            movement.setdefault("direction", COVER_MOVEMENT_STARTED[status.state])
            log(f"  [{now():7.2f}s] {address}: started to move "
                f"{DIRECTION_NAMES.get(COVER_MOVEMENT_STARTED[status.state])}", "received")
        movement["events"].append(event)
        movement.setdefault("reaction_s", event["time"])

    event_id = config_helpers.get_bus_event_type(gateway.dev_id, SIGNAL_RECEIVE_MESSAGE)
    unsubscribe = async_dispatcher_connect(hass, event_id, on_receive)

    def send_command(cover: dict, command: int, travel_time: float) -> None:
        sender = AddressExpression.parse(cover["sender_id"])
        message = H5_3F_7F(time=int(round(travel_time * 10)), command=command,
                           learn_button=1).encode_message(sender[0])
        gateway.send_message(message)

    try:
        for run in range(1, runs + 1):
            if stop_event.is_set():
                break
            log(f"Run {run}/{runs}", "info")
            for step_index, (name, duration) in enumerate(sequence, start=1):
                if stop_event.is_set():
                    break
                log(f"[{now():7.2f}s] Step {step_index}/{len(sequence)}: "
                    f"{name.upper()} {duration:g}s", "info")

                if name == "pause":
                    await asyncio.sleep(duration)
                    continue
                if name == "stop":
                    for cover in covers:
                        send_command(cover, COVER_STOP, 0)
                        await asyncio.sleep(message_delay)
                    open_movements.clear()
                    await asyncio.sleep(duration)
                    continue

                # command telegrams carry the travel time when it fits (eo_man 'timed'
                # mode), otherwise the movement is terminated with a STOP command
                travel_time = duration if duration <= MAX_COMMAND_TRAVEL_TIME else 0
                for cover in covers:
                    movement = {"run": run, "step": step_index,
                                "command": f"{name.upper()} {duration:g}s",
                                "cover": cover["id"], "start_time": now(), "events": []}
                    movements.append(movement)
                    open_movements[cover["id"]] = movement
                    send_command(cover, COVER_COMMANDS[name], travel_time)
                    await asyncio.sleep(message_delay)

                await asyncio.sleep(duration)
                if travel_time == 0:
                    for cover in covers:
                        send_command(cover, COVER_STOP, 0)
                        await asyncio.sleep(message_delay)
                open_movements.clear()

        # bus actuators need up to ~2.5s until their travel report has passed the bus
        settle = float(params.get("settle", 3.0))
        log(f"Waiting {settle:g}s for late travel reports ...", "info")
        await asyncio.sleep(settle)
    finally:
        unsubscribe()
        open_movements.clear()

    # ------------------------------------------------------------------ report
    rows = []
    for movement in movements:
        expected = COVER_COMMANDS[movement["command"].split(" ")[0].lower()]
        direction = movement.get("direction")
        problems = []
        if movement.get("reaction_s") is None:
            problems.append("no reaction")
        if direction is not None and direction != expected:
            problems.append("wrong direction")
        rows.append({
            "run": movement["run"], "step": movement["step"], "cover": movement["cover"],
            "command": movement["command"],
            "reaction_s": movement.get("reaction_s"),
            "measured_s": movement.get("measured_s"),
            "reported_s": movement.get("reported_s"),
            "direction": DIRECTION_NAMES.get(direction) if direction is not None else None,
            "end_position": movement.get("end_position"),
            "problems": problems,
        })

    recommendations = []
    for cover in covers:
        def _times(command: int) -> list[float]:
            return [row["reported_s"] or row["measured_s"] for row in rows
                    if row["cover"] == cover["id"] and not row["problems"]
                    and row["command"].startswith(DIRECTION_NAMES[command])
                    and (row["reported_s"] or row["measured_s"]) is not None]
        up_times, down_times = _times(COVER_UP), _times(COVER_DOWN)
        if up_times or down_times:
            recommendations.append({
                "cover": cover["id"],
                "up_s": max(up_times) if up_times else None,
                "down_s": max(down_times) if down_times else None,
                "configured_opens": cover.get("time_opens"),
                "configured_closes": cover.get("time_closes"),
            })

    for recommendation in recommendations:
        up_s, down_s = recommendation["up_s"], recommendation["down_s"]
        log(f"Cover {recommendation['cover']}: up "
            f"{f'{up_s:.1f}s' if up_s else 'unknown'} (configured time_opens: "
            f"{recommendation['configured_opens']}), down "
            f"{f'{down_s:.1f}s' if down_s else 'unknown'} (configured time_closes: "
            f"{recommendation['configured_closes']})", "ok")

    ok_rows = len([row for row in rows if not row["problems"]])
    success = bool(rows) and ok_rows == len(rows)
    log(f"RESULT: {ok_rows} of {len(rows)} movements behaved as requested."
        + (f" {interference_count} foreign telegram(s) were received." if interference_count else ""),
        "ok" if success else "error")
    return {"test": "cover", "success": success, "movements": rows,
            "recommendations": recommendations, "interference_count": interference_count,
            "gateway": gateway.dev_id,
            # what was actually driven - the caller may have passed addresses which are not
            # configured, so report both arrays back
            "covers": [cover["id"] for cover in covers],
            "senders": [cover["sender_id"] for cover in covers]}


TEST_RUNNERS = {"burst": run_burst_test, "cover": run_cover_test}


### ---------------------------------------------------------------------------
### manager: one test at a time, log streaming for CLI and web ui
### ---------------------------------------------------------------------------

class DeviceTestManager:
    MAX_LOG_LINES = 500

    def __init__(self, hass):
        self.hass = hass
        self.task: asyncio.Task | None = None
        self.test_id: str | None = None
        self.result: dict | None = None
        self.log_lines: list[dict] = []
        self._subscribers: list[Callable[[dict], None]] = []
        self._stop_event = asyncio.Event()

    @property
    def is_running(self) -> bool:
        return self.task is not None and not self.task.done()

    def subscribe(self, callback: Callable[[dict], None]) -> Callable[[], None]:
        self._subscribers.append(callback)

        def remove():
            try:
                self._subscribers.remove(callback)
            except ValueError:
                pass
        return remove

    def _emit(self, event: dict) -> None:
        for callback in list(self._subscribers):
            try:
                callback(event)
            except Exception:  # noqa: BLE001
                LOGGER.debug("Device test subscriber failed", exc_info=True)

    def log(self, line: str, style: str = "info") -> None:
        entry = {"line": line, "style": style}
        self.log_lines.append(entry)
        del self.log_lines[:-self.MAX_LOG_LINES]
        self._emit({"kind": "log", **entry})

    def start(self, test_id: str, params: dict) -> None:
        if self.is_running:
            raise ValueError(f"Test '{self.test_id}' is still running - stop it first.")
        runner = TEST_RUNNERS.get(test_id)
        if runner is None:
            raise ValueError(f"Unknown test '{test_id}'. Available: "
                             f"{', '.join(TEST_RUNNERS)}")
        self.test_id = test_id
        self.result = None
        self.log_lines = []
        self._stop_event = asyncio.Event()
        self._emit({"kind": "status", "running": True, "test": test_id})
        self.task = self.hass.async_create_task(self._run(runner, params))

    async def _run(self, runner, params: dict) -> None:
        try:
            self.result = await runner(self.hass, params, self.log, self._stop_event)
        except ValueError as e:
            self.log(str(e), "error")
            self.result = {"test": self.test_id, "success": False, "error": str(e)}
        except asyncio.CancelledError:
            self.log("Test was stopped.", "error")
            self.result = {"test": self.test_id, "success": False, "error": "stopped"}
        except Exception as e:  # noqa: BLE001
            LOGGER.exception("Device test '%s' failed", self.test_id)
            self.log(f"Test failed: {e}", "error")
            self.result = {"test": self.test_id, "success": False, "error": str(e)}
        finally:
            self._emit({"kind": "result", "result": self.result})
            self._emit({"kind": "status", "running": False, "test": self.test_id})

    def stop(self) -> None:
        self._stop_event.set()
        if self.is_running:
            self.log("Stop requested - the test terminates after the current step.", "info")


def get_manager(hass) -> DeviceTestManager:
    manager = hass.data.get(DATA_DEVICE_TEST_MANAGER)
    if manager is None:
        manager = DeviceTestManager(hass)
        hass.data[DATA_DEVICE_TEST_MANAGER] = manager
    return manager


### ---------------------------------------------------------------------------
### websocket api (standalone web ui)
### ---------------------------------------------------------------------------

def _info(hass) -> dict:
    manager = get_manager(hass)
    gateways = [{"id": gw.dev_id, "name": gw.dev_name, "connected": _is_connected(gw)}
                for gw in sorted(get_gateways(hass), key=lambda g: g.dev_id)]
    covers = {}
    for gateway in gateways:
        entries = get_configured_covers(hass, gateway["id"])
        if entries:
            covers[str(gateway["id"])] = {
                "covers": entries,
                "default_sequence": default_cover_sequence(entries),
            }
    return {
        "tests": TEST_DESCRIPTORS,
        "gateways": gateways,
        "covers": covers,
        "running": manager.is_running,
        "test": manager.test_id,
        "log": manager.log_lines[-200:],
        "result": manager.result,
    }


def register_websocket_commands(hass) -> None:
    import voluptuous as vol
    from homeassistant.components import websocket_api
    from homeassistant.core import callback

    @websocket_api.websocket_command({vol.Required("type"): WS_DEVICE_TESTS_INFO})
    @callback
    def ws_info(hass, connection, msg) -> None:
        connection.send_result(msg["id"], _info(hass))

    @websocket_api.websocket_command({
        vol.Required("type"): WS_DEVICE_TESTS_START,
        vol.Required("test"): str,
        vol.Optional("params"): dict,
    })
    @callback
    def ws_start(hass, connection, msg) -> None:
        try:
            get_manager(hass).start(msg["test"], msg.get("params") or {})
        except ValueError as e:
            connection.send_error(msg["id"], "cannot_start", str(e))
            return
        connection.send_result(msg["id"], {"started": True})

    @websocket_api.websocket_command({vol.Required("type"): WS_DEVICE_TESTS_STOP})
    @callback
    def ws_stop(hass, connection, msg) -> None:
        get_manager(hass).stop()
        connection.send_result(msg["id"], {"stopped": True})

    @websocket_api.websocket_command({vol.Required("type"): WS_DEVICE_TESTS_SUBSCRIBE})
    @callback
    def ws_subscribe(hass, connection, msg) -> None:
        def forward(event: dict) -> None:
            connection.send_message(websocket_api.event_message(msg["id"], event))
        connection.subscriptions[msg["id"]] = get_manager(hass).subscribe(forward)
        connection.send_result(msg["id"])

    websocket_api.async_register_command(hass, ws_info)
    websocket_api.async_register_command(hass, ws_start)
    websocket_api.async_register_command(hass, ws_stop)
    websocket_api.async_register_command(hass, ws_subscribe)
