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
the gateways of the running runtime and the covers (incl. their sender ids) of the
configuration.

Used by the 'Tests' page of the web ui (websocket commands `eltako/device_tests/*`) and by
`python -m eltako_standalone devicetest ...`. It runs against the gateways of the running
runtime, so it works in Home Assistant as well as in the standalone runtime.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Callable

from eltakobus.eep import (A5_38_08, CentralCommandDimming, CentralCommandSwitching, EEP,
                           F6_02_01, F6_02_02, G5_3F_7F, H5_3F_7F)
from eltakobus.message import EltakoPoll, EltakoTimeout, Regular4BSMessage, prettify
from eltakobus.util import AddressExpression, b2s

from homeassistant.const import CONF_ID
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from ..config import config_helpers
from ..config.config_check import check_configuration, run_config_test
from ..const import (
    CONF_EEP, CONF_SENDER, CONF_TIME_CLOSES, CONF_TIME_OPENS,
    DATA_ELTAKO, ELTAKO_CONFIG, SIGNAL_RECEIVE_MESSAGE, GatewayDeviceType)
from ..core.websocket import get_gateways

LOGGER = logging.getLogger("eltako.device_tests")

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
        # only gateways on the RS485 bus can carry the test addresses - see is_wired()
        "wired_gateways_only": True,
        "gateway_requirement": "Two different gateways on the same RS485 bus (FAM14, "
                               "FGW14-USB). Wireless transceivers cannot send the test "
                               "addresses FF-00-00-01.. - they are outside every base id range.",
    },
    {
        "id": "cover",
        "name": "Cover travel time test",
        "description": "Drives the selected covers with a sequence of movement commands "
                       "(e.g. up:25, pause:2, down:25), records their status telegrams and "
                       "measures the real travel times - the base for configuring the "
                       "runtime of an FSB actuator (time_closes / time_opens).",
    },
    {
        "id": "actuator",
        "name": "Actuator / teach-in test",
        "description": "Switches every selected switch or light once and waits for its status "
                       "telegram. An actuator only answers when the sender of Home Assistant is "
                       "taught into it - this is the test for 'Home Assistant sends but nothing "
                       "happens'. The round trip time comes along and shows an overloaded bus.",
        "warning": "The actuators really switch. With the default sequence (ON, then OFF) every "
                   "device ends up switched off.",
    },
    {
        "id": "config",
        "name": "Configuration check",
        "description": "Checks the configuration against everything the integration already "
                       "knows - address classes, sender ids and base id ranges, duplicates, the "
                       "models which answered on the bus, the taught-in senders of the memory "
                       "images and the recorded activity. Sends nothing, changes nothing.",
        "sends_nothing": True,
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


# every key under which a test names a gateway it talks to
GATEWAY_PARAMS = ("gateway", "gateway1", "gateway2")


def _check_bus_is_free(hass, params: dict) -> None:
    """Refuse a test while an exclusive operation has the bus of one of its gateways.

    A test measures answer times, so its telegrams may not be queued behind a bus scan (that
    would falsify every measurement) - it is stopped before it starts instead.
    """
    for key in GATEWAY_PARAMS:
        if params.get(key) in (None, ""):
            continue
        gateway = _find_gateway(hass, params[key])
        if gateway is not None and getattr(gateway, 'is_bus_busy', False):
            raise ValueError(f"Gateway {gateway.dev_id} is busy with "
                             f"'{gateway.bus_busy_reason}'. While that runs no other telegram "
                             f"may go over its bus - start the test afterwards.")


def _is_connected(gateway) -> bool:
    try:
        return bool(gateway._bus.is_active())
    except Exception:  # noqa: BLE001
        return False


def is_wired(gateway) -> bool:
    """True for a gateway which sits on the RS485 bus (FAM14, FGW14-USB).

    The burst test needs this: it sends with the fixed addresses FF-00-00-01.. of the EnOcean
    Device Manager, which are not derived from any base id. A wireless transceiver only
    transmits telegrams whose sender address lies inside its own base id range (base id ..
    base id + 127, and valid base ids start at FF-80-00-00), so it drops these silently - the
    test would then report every telegram as missing without saying why. A bus gateway puts
    the frame on the wire whatever the address is.
    """
    return bool(GatewayDeviceType.is_bus_gateway(gateway.dev_type))


def _devices_of_gateway(hass, gateway_id: int) -> dict:
    """Devices of a gateway from configuration.yaml AND from the web ui."""
    from ..config.device_config import get_devices_of_gateway
    return get_devices_of_gateway(hass, gateway_id)


def get_configured_covers(hass, gateway_id: int) -> list[dict]:
    """Covers of the configuration of one gateway incl. their sender ids."""
    devices = _devices_of_gateway(hass, gateway_id)
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
        if not is_wired(gateway):
            raise ValueError(
                f"Gateway {gateway.dev_id} ({gateway.dev_type}) is a wireless transceiver. "
                f"The burst test sends with the fixed addresses FF-00-00-01.., which lie "
                f"outside every base id range, so a transceiver does not transmit them and "
                f"hears nothing on the wire. Use gateways on the RS485 bus "
                f"(FAM14, FGW14-USB) for both sides.")

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


### ---------------------------------------------------------------------------
### actuator test: does the actuator answer a command of Home Assistant?
### ---------------------------------------------------------------------------

# platforms whose actuators can be switched on and off. Covers have their own test (a stop
# telegram of a standing cover is not answered, so it proves nothing), climate actuators are
# driven with a temperature and are left alone here.
SWITCHABLE_PLATFORMS = ("switch", "light")


def get_configured_actuators(hass, gateway_id: int) -> list[dict]:
    """Switchable actuators of one gateway incl. their sender - the candidates of the test."""
    devices = _devices_of_gateway(hass, gateway_id)
    actuators = []
    for platform in SWITCHABLE_PLATFORMS:
        for entry in devices.get(platform, []) or []:
            sender = entry.get(CONF_SENDER) or {}
            actuators.append({
                "id": str(entry.get(CONF_ID, "")).upper(),
                "name": entry.get("name") or str(entry.get(CONF_ID, "")),
                "platform": platform,
                "eep": str(entry.get(CONF_EEP, "") or ""),
                "sender_id": str(sender.get(CONF_ID, "") or "").upper(),
                "sender_eep": str(sender.get(CONF_EEP, "") or ""),
            })
    return actuators


def resolve_actuators(hass, gateway_id: int, addresses: list | None) -> list[dict]:
    """The actuators to test: all configured ones, or the given subset of them."""
    configured = {actuator["id"]: actuator for actuator in get_configured_actuators(hass, gateway_id)}
    wanted = [str(address).strip().upper() for address in (addresses or []) if str(address).strip()]
    if not wanted:
        return list(configured.values())

    unknown = [address for address in wanted if address not in configured]
    if unknown:
        raise ValueError(f"Not configured as switch or light for gateway {gateway_id}: "
                         f"{', '.join(unknown)}. The test switches through the configuration, so "
                         f"the device (with its sender) has to be configured first.")
    return [configured[address] for address in wanted]


def build_switch_telegrams(actuator: dict, turn_on: bool) -> list:
    """The telegrams Home Assistant itself would send to switch this actuator.

    Same encoding as light.py/switch.py - a test which built its own telegrams would prove
    something the integration never sends.
    """
    sender_eep_name = str(actuator.get("sender_eep") or "").upper()
    try:
        sender_eep = EEP.find(sender_eep_name)
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"Unknown sender eep '{sender_eep_name}': {e}") from e

    address = AddressExpression.parse(actuator["sender_id"])[0]

    if sender_eep == A5_38_08:
        if actuator["platform"] == "light":
            dimming = CentralCommandDimming(100 if turn_on else 0, 0, 1, 0, 0, 1 if turn_on else 0)
            return [A5_38_08(command=0x02, dimming=dimming).encode_message(address)]
        switching = CentralCommandSwitching(0, 1, 0, 0, 1 if turn_on else 0)
        return [A5_38_08(command=0x01, switching=switching).encode_message(address)]

    if sender_eep in (F6_02_01, F6_02_02):
        # a rocker sends a press and a release; which button switches on depends on the key
        # function configured in PCT14 (direct pushbutton top on)
        action = 1 if turn_on else 0
        return [F6_02_01(action, 1, 0, 0).encode_message(address),
                F6_02_01(action, 0, 0, 0).encode_message(address)]

    raise ValueError(f"Sender eep {sender_eep_name} cannot be switched by this test "
                     f"(supported: A5-38-08, F6-02-01, F6-02-02).")


async def run_actuator_test(hass, params: dict, log: Callable[[str, str], None],
                            stop_event: asyncio.Event) -> dict:
    """Switch every selected actuator and wait for its status telegram.

    This is the answer to "Home Assistant sends, nothing happens": the actuator only answers
    when the sender of Home Assistant is taught into it. The round trip time comes for free and
    shows an overloaded bus.
    """
    gateway = _find_gateway(hass, params.get("gateway"))
    if gateway is None:
        raise ValueError(f"No gateway with id {params.get('gateway')}.")
    if not _is_connected(gateway):
        raise ValueError(f"Gateway {gateway.dev_id} ({gateway.serial_path}) is not connected.")

    actuators = resolve_actuators(hass, gateway.dev_id, params.get("devices"))
    if not actuators:
        raise ValueError("No switch or light is configured for this gateway. Covers have their "
                         "own test (cover travel time test).")

    without_sender = [actuator["id"] for actuator in actuators if not actuator["sender_id"]]
    actuators = [actuator for actuator in actuators if actuator["sender_id"]]
    if without_sender:
        log(f"Skipped (no sender configured): {', '.join(without_sender)}", "error")
    if not actuators:
        raise ValueError("None of the selected devices has a sender address. Home Assistant "
                         "needs one to send commands.")

    command = str(params.get("command") or "on_off").lower()
    if command not in ("on_off", "off_on", "on", "off"):
        raise ValueError(f"Unknown command '{command}' (use on_off, off_on, on or off).")
    steps_per_device = {"on_off": (True, False), "off_on": (False, True),
                        "on": (True,), "off": (False,)}[command]
    timeout = float(params.get("timeout") or 3.0)
    settle = float(params.get("settle") or 1.0)

    log(f"Actuator test on gateway {gateway.dev_id}: "
        f"{', '.join(actuator['id'] for actuator in actuators)}", "info")
    log(f"Command sequence per device: {' -> '.join('ON' if on else 'OFF' for on in steps_per_device)}"
        f", answer timeout {timeout:g}s.", "info")

    answers: dict[str, float] = {}
    waiting_for: str | None = None
    answer_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def on_receive(data) -> None:
        msg = data.get("esp2_msg")
        if msg is None or isinstance(msg, (EltakoPoll, EltakoTimeout)):
            return
        try:
            address = b2s(prettify(msg).address)
        except Exception:  # noqa: BLE001
            return
        if waiting_for and address == waiting_for:
            answers[address] = time.time()
            loop.call_soon_threadsafe(answer_event.set)

    event_id = config_helpers.get_bus_event_type(gateway.dev_id, SIGNAL_RECEIVE_MESSAGE)
    unsubscribe = async_dispatcher_connect(hass, event_id, on_receive)

    rows: list[dict] = []
    try:
        for actuator in actuators:
            if stop_event.is_set():
                break
            for turn_on in steps_per_device:
                if stop_event.is_set():
                    break
                label = "ON" if turn_on else "OFF"
                try:
                    telegrams = build_switch_telegrams(actuator, turn_on)
                except ValueError as e:
                    log(f"{actuator['id']}: {e}", "error")
                    rows.append({"device": actuator["id"], "name": actuator["name"],
                                 "platform": actuator["platform"], "sender": actuator["sender_id"],
                                 "command": label, "answered": False, "response_s": None,
                                 "problems": [str(e)]})
                    break

                waiting_for = actuator["id"]
                answers.pop(actuator["id"], None)
                answer_event.clear()
                sent_at = time.time()
                for telegram in telegrams:
                    gateway.send_message(telegram)

                try:
                    await asyncio.wait_for(answer_event.wait(), timeout)
                except asyncio.TimeoutError:
                    pass
                waiting_for = None

                answered_at = answers.get(actuator["id"])
                response = round(answered_at - sent_at, 3) if answered_at else None
                problems = [] if answered_at else [
                    f"no status telegram within {timeout:g}s - sender {actuator['sender_id']} is "
                    f"probably not taught into the actuator"]

                if answered_at:
                    log(f"  {actuator['name']} ({actuator['id']}) {label}: answered after "
                        f"{response:.3f}s.", "ok")
                else:
                    log(f"  {actuator['name']} ({actuator['id']}) {label}: NO ANSWER within "
                        f"{timeout:g}s.", "error")

                rows.append({"device": actuator["id"], "name": actuator["name"],
                             "platform": actuator["platform"], "sender": actuator["sender_id"],
                             "command": label, "answered": bool(answered_at),
                             "response_s": response, "problems": problems})

                if settle:
                    await asyncio.sleep(settle)
    finally:
        unsubscribe()

    answered = len([row for row in rows if row["answered"]])
    success = bool(rows) and answered == len(rows)
    log(f"RESULT: {answered} of {len(rows)} command(s) were answered by the actuator.",
        "ok" if success else "error")

    silent = sorted({row["device"] for row in rows if not row["answered"]})
    if silent:
        log(f"Not answering: {', '.join(silent)}. Check the sender id and teach it in "
            f"('check & teach in HA senders' or PCT14).", "error")

    return {"test": "actuator", "success": success, "steps": rows,
            "gateway": gateway.dev_id, "command": command,
            "devices": [actuator["id"] for actuator in actuators],
            "answered": answered, "total": len(rows)}


TEST_RUNNERS = {"burst": run_burst_test, "cover": run_cover_test,
                "actuator": run_actuator_test, "config": run_config_test}


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
        _check_bus_is_free(self.hass, params)
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
    gateways = [{"id": gw.dev_id, "name": gw.dev_name, "connected": _is_connected(gw),
                 "device_type": str(gw.dev_type), "wired": is_wired(gw)}
                for gw in sorted(get_gateways(hass), key=lambda g: g.dev_id)]
    covers = {}
    actuators = {}
    for gateway in gateways:
        entries = get_configured_covers(hass, gateway["id"])
        if entries:
            covers[str(gateway["id"])] = {
                "covers": entries,
                "default_sequence": default_cover_sequence(entries),
            }
        switchable = get_configured_actuators(hass, gateway["id"])
        if switchable:
            actuators[str(gateway["id"])] = {"actuators": switchable}
    return {
        "tests": TEST_DESCRIPTORS,
        "gateways": gateways,
        "covers": covers,
        "actuators": actuators,
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
