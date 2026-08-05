"""Command line interface of the Eltako standalone runtime.

    python -m eltako_standalone serve      web ui + runtime (like HA, just fast)
    python -m eltako_standalone run        headless runtime (no web ui)
    python -m eltako_standalone listen     print the live telegram stream
    python -m eltako_standalone send       send a telegram (raw or built from an EEP)
    python -m eltako_standalone scan       list serial ports incl. gateway suggestions
    python -m eltako_standalone devices    list all entities with their state
    python -m eltako_standalone state      show one entity
    python -m eltako_standalone control    invoke an action (turn_on, set_cover_position, ...)
    python -m eltako_standalone devicetest functional tests against the hardware
                                           (config, actuator, burst, cover - see `devicetest list`)

Everything runs against a config folder (--config, default ~/.eltako-standalone)
which works exactly like the Home Assistant one: configuration.yaml with the
same `eltako:` section, .storage/ for the things created in the web ui.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
import sys

DEFAULT_CONFIG_DIR = os.environ.get("ELTAKO_CONFIG_DIR", "~/.eltako-standalone")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="eltako_standalone",
        description="Run the Eltako integration without Home Assistant.")
    parser.add_argument("--config", default=DEFAULT_CONFIG_DIR,
                        help=f"config folder (default: {DEFAULT_CONFIG_DIR})")
    parser.add_argument("--debug", action="store_true", help="verbose logging")
    parser.add_argument("--demo", action="store_true",
                        help="load the example data of the EnOcean Device Manager "
                             "(eltako_standalone/examples/demo.eodm) at startup")
    parser.add_argument("--import", dest="import_file", metavar="FILE", default=None,
                        help="import a configuration file (.eodm, PCT14 export .xml or "
                             "eltako yaml) at startup")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="start runtime + web ui")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8123)
    serve.add_argument("--token", default=None,
                       help="require this access token (default: no auth, bind localhost)")

    sub.add_parser("run", help="start the runtime without web ui")

    listen = sub.add_parser("listen", help="print the live telegram stream")
    listen.add_argument("--json", action="store_true", help="one json object per line")
    listen.add_argument("--gateway", type=int, default=None, help="only this gateway id")

    send = sub.add_parser("send", help="send a telegram")
    send.add_argument("--gateway", type=int, required=True, help="gateway id")
    send.add_argument("--raw", help="ESP2 telegram as hex (11 body or 14 frame bytes)")
    send.add_argument("--sender", help="sender address, e.g. 00-00-B0-01")
    send.add_argument("--eep", help="EEP to encode, e.g. A5-38-08")
    send.add_argument("--field", action="append", default=[], metavar="NAME=VALUE",
                      help="EEP field, e.g. --field command=1 --field switching_command=1")
    send.add_argument("--wait", type=float, default=5.0,
                      help="seconds to wait for the gateway connection (default 5)")

    scan = sub.add_parser("scan", help="list serial ports (no runtime, fast)")
    scan.add_argument("--json", action="store_true")

    devices = sub.add_parser("devices", help="list all entities with state")
    devices.add_argument("--json", action="store_true")
    devices.add_argument("--platform", default=None, help="filter, e.g. light")
    devices.add_argument("--wait", type=float, default=2.0,
                         help="seconds to wait for initial states (default 2)")

    state = sub.add_parser("state", help="show one entity")
    state.add_argument("entity_id")
    state.add_argument("--json", action="store_true")
    state.add_argument("--wait", type=float, default=2.0)

    control = sub.add_parser("control", help="invoke an action on an entity")
    control.add_argument("entity_id")
    control.add_argument("action", help="e.g. turn_on, turn_off, set_cover_position")
    control.add_argument("data", nargs="*", metavar="NAME=VALUE",
                         help="e.g. brightness=128 or position=50")
    control.add_argument("--wait", type=float, default=3.0,
                         help="seconds to wait for the gateway connection (default 3)")

    test = sub.add_parser("test", help="run the pytest suites (integration, standalone, "
                                       "EnOcean Device Manager)")
    test.add_argument("suites", nargs="*",
                      help="suite ids to run (default: all available). See --list.")
    test.add_argument("--list", action="store_true", help="only list the available suites")

    devicetest = sub.add_parser(
        "devicetest", help="functional device tests of the EnOcean Device Manager")
    devicetest_sub = devicetest.add_subparsers(dest="devicetest", required=True)

    burst = devicetest_sub.add_parser(
        "burst", help="send a telegram burst via gateway 1 and verify gateway 2 receives it")
    burst.add_argument("--gateway1", type=int, required=True, help="gateway id which sends")
    burst.add_argument("--gateway2", type=int, required=True, help="gateway id which receives")
    burst.add_argument("--count", type=int, default=44, help="telegrams per run (default 44)")
    burst.add_argument("--delay", type=float, default=0.01,
                       help="delay between two telegrams in seconds (default 0.01)")
    burst.add_argument("--runs", type=int, default=1)
    burst.add_argument("--wait", type=float, default=5.0,
                       help="seconds to wait for the gateway connections (default 5)")

    cover = devicetest_sub.add_parser(
        "cover", help="measure the travel times of the configured covers")
    cover.add_argument("--gateway", type=int, required=True, help="gateway id")
    cover.add_argument("--covers", default=None,
                       help="comma separated actuator addresses (default: all configured covers)")
    cover.add_argument("--senders", default=None,
                       help="comma separated sender addresses, used pairwise with --covers. "
                            "Lets you test an actuator which is not configured yet, or with a "
                            "different sender. One sender for all: --senders 00-00-B0-06")
    cover.add_argument("--sequence", default=None,
                       help="movement sequence, e.g. 'up:25,pause:2,down:25' "
                            "(default: derived from time_opens/time_closes)")
    cover.add_argument("--runs", type=int, default=1)
    cover.add_argument("--wait", type=float, default=5.0,
                       help="seconds to wait for the gateway connection (default 5)")

    actuator = devicetest_sub.add_parser(
        "actuator", help="switch the configured switches/lights and check that they answer "
                         "(does the teach-in work?)")
    actuator.add_argument("--gateway", type=int, required=True, help="gateway id")
    actuator.add_argument("--devices", default=None,
                          help="comma separated actuator addresses "
                               "(default: every configured switch and light of the gateway)")
    # dest is explicit: 'command' is already taken by the top level subcommand
    actuator.add_argument("--command", dest="actuator_command", default="on_off",
                          choices=["on_off", "off_on", "on", "off"],
                          help="what to send per device (default on_off: switch on, then off)")
    actuator.add_argument("--timeout", type=float, default=3.0,
                          help="seconds to wait for the status telegram of the actuator (default 3)")
    actuator.add_argument("--settle", type=float, default=1.0,
                          help="pause between two commands in seconds (default 1)")
    actuator.add_argument("--wait", type=float, default=5.0,
                          help="seconds to wait for the gateway connection (default 5)")

    config_check = devicetest_sub.add_parser(
        "config", help="check the configuration (addresses, senders, teach-in, models) - "
                       "sends nothing")
    config_check.add_argument("--gateway", type=int, default=None, action="append",
                              dest="gateways", help="only this gateway id (repeatable)")
    config_check.add_argument("--severity", default="info", choices=["error", "warning", "info"],
                              help="lowest severity to report (default info = everything)")
    config_check.add_argument("--json", action="store_true",
                              help="print the findings as json instead of text")
    config_check.add_argument("--wait", type=float, default=0.0,
                              help="seconds to wait for the gateway connections (default 0 - "
                                   "the check does not need them)")

    devicetest_sub.add_parser("list", help="list the available device tests")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not args.debug:
        # keep the CLI output clean, the integration logs a lot on INFO
        logging.getLogger("eltako").setLevel(logging.ERROR)
        logging.getLogger("eltako_standalone").setLevel(logging.WARNING)

    from .runtime import install_shim
    install_shim()

    if args.command == "scan":
        return _cmd_scan(args)          # no runtime needed
    if args.command == "test":
        return _cmd_test(args)          # no runtime needed
    try:
        exit_code = asyncio.run(_async_main(args))
    except KeyboardInterrupt:
        # windows: asyncio cannot register posix signal handlers (add_signal_handler raises
        # NotImplementedError), so Ctrl+C arrives as KeyboardInterrupt - same clean exit here
        exit_code = 0
    return _exit(exit_code)


def _exit(exit_code: int) -> int:
    """Exit even when a serial thread is stuck.

    The reader thread of eltakobus is not a daemon thread and its reconnect
    sleep (10s, time.sleep) ignores the stop flag - a normal interpreter exit
    would wait for it. If such a thread is still alive after the clean
    shutdown, the process leaves via os._exit.
    """
    import threading

    stuck = [thread for thread in threading.enumerate()
             if thread is not threading.main_thread()
             and thread.is_alive() and not thread.daemon]
    if stuck:
        logging.getLogger("eltako_standalone").debug(
            "Forcing exit, non-daemon threads still alive: %s",
            ", ".join(thread.name for thread in stuck))
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(exit_code)
    return exit_code


### ---------------------------------------------------------------------------
### commands without runtime
### ---------------------------------------------------------------------------

def _cmd_scan(args) -> int:
    from custom_components.eltako.gateway_scan import scan_serial_ports

    ports = scan_serial_ports()
    if args.json:
        print(json.dumps(ports, indent=2, default=str))
        return 0
    if not ports:
        print("No serial ports found.")
        return 0
    for port in ports:
        types = ", ".join(port.get("suggested_device_types") or []) or "-"
        print(f"{port['device']:35s} {port.get('name') or '':45s} types: {types}")
        if port.get("hint"):
            print(f"{'':35s} {port['hint']}")
    return 0


def _cmd_test(args) -> int:
    from .test_runner import get_suites, run_suite

    suites = get_suites()
    if args.list:
        for suite in suites:
            status = "" if suite["available"] else "  (not available on this machine)"
            print(f"{suite['id']:16s} {suite['name']}{status}")
            print(f"{'':16s} {suite['description']}")
        return 0

    wanted = args.suites or [suite["id"] for suite in suites if suite["available"]]
    exit_code = 0
    for suite_id in wanted:
        print(f"\n=== {suite_id} ===", flush=True)
        try:
            result = run_suite(suite_id, stream_to_stdout=True)
        except ValueError as e:
            print(str(e), file=sys.stderr)
            exit_code = 2
            continue
        if not result["success"]:
            exit_code = 1
    return exit_code


### ---------------------------------------------------------------------------
### commands with runtime
### ---------------------------------------------------------------------------

async def _async_main(args) -> int:
    from .runtime import EltakoRuntime

    runtime = EltakoRuntime(os.path.expanduser(args.config))
    await runtime.async_start()
    try:
        await _apply_startup_imports(runtime, args)
        if args.command == "serve":
            return await _cmd_serve(runtime, args)
        if args.command == "run":
            return await _wait_forever(runtime)
        if args.command == "listen":
            return await _cmd_listen(runtime, args)
        if args.command == "send":
            return await _cmd_send(runtime, args)
        if args.command == "devices":
            return await _cmd_devices(runtime, args)
        if args.command == "state":
            return await _cmd_state(runtime, args)
        if args.command == "control":
            return await _cmd_control(runtime, args)
        if args.command == "devicetest":
            return await _cmd_devicetest(runtime, args)
        return 2
    finally:
        await runtime.async_stop()


EXAMPLE_EODM = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "examples", "demo.eodm")


async def _apply_startup_imports(runtime, args) -> None:
    """--demo / --import FILE: load a configuration at startup.

    Idempotent: gateways whose base id is already configured are skipped by the
    importer, so restarting with --demo does not duplicate anything.
    """
    # (path, overrides): demo gateways have placeholder serial ports, endless
    # reconnect attempts would only produce log noise
    files = []
    if args.demo:
        files.append((EXAMPLE_EODM, {"auto_reconnect": False}))
    if args.import_file:
        files.append((os.path.expanduser(args.import_file), None))
    if not files:
        return

    from custom_components.eltako.config_import import async_import

    for path, overrides in files:
        try:
            with open(path, encoding="utf-8") as handle:
                content = handle.read()
        except OSError as e:
            print(f"Cannot read '{path}': {e}", file=sys.stderr)
            continue
        try:
            result = await async_import(runtime.hass, content, dry_run=False,
                                        gateway_overrides=overrides)
        except Exception as e:  # noqa: BLE001 - a broken file must not stop the runtime
            print(f"Cannot import '{path}': {e}", file=sys.stderr)
            continue
        print(f"Imported '{os.path.basename(path)}': {result['created_gateways']} gateway(s), "
              f"{result['created_devices']} device(s)"
              f"{f', {result['skipped_gateways']} already configured' if result['skipped_gateways'] else ''}.",
              flush=True)
        for warning in result["warnings"]:
            print(f"  note: {warning}", flush=True)
    await asyncio.sleep(0.5)        # let the platform setups finish


async def _wait_for_shutdown_signal() -> None:
    loop = asyncio.get_event_loop()
    stop = asyncio.Event()

    def on_signal() -> None:
        if stop.is_set():
            # second Ctrl+C: the clean shutdown is stuck (e.g. a serial thread in
            # its reconnect sleep) - leave immediately
            print("\nForced exit.", file=sys.stderr, flush=True)
            os._exit(130)
        print("\nShutting down (press Ctrl+C again to force quit) ...", flush=True)
        stop.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, on_signal)
        except NotImplementedError:
            pass
    await stop.wait()


async def _wait_forever(runtime) -> int:
    print("Eltako standalone runtime is running (Ctrl+C to stop).")
    await _wait_for_shutdown_signal()
    return 0


async def _cmd_serve(runtime, args) -> int:
    from .server import StandaloneServer

    server = StandaloneServer(runtime.hass, host=args.host, port=args.port, token=args.token)
    await server.async_start()
    print(f"Eltako web ui: http://{args.host}:{args.port}/  (Ctrl+C to stop)")
    await _wait_for_shutdown_signal()
    await server.async_stop()
    return 0


async def _ensure_telegram_logger(runtime):
    """listen works even when telegram recording is disabled in the settings."""
    from custom_components.eltako import config_helpers
    from custom_components.eltako.const import CONF_LOG_ENOCEAN_TELEGRAMS
    from custom_components.eltako.enocean_logger import (
        async_setup_telegram_logger, get_telegram_logger)

    logger = get_telegram_logger(runtime.hass)
    if logger is not None:
        return logger
    settings = config_helpers.get_general_settings_from_configuration(runtime.hass)
    settings[CONF_LOG_ENOCEAN_TELEGRAMS] = True
    return await async_setup_telegram_logger(runtime.hass, settings)


async def _cmd_listen(runtime, args) -> int:
    logger = await _ensure_telegram_logger(runtime)
    if logger is None:
        print("Cannot start the telegram logger.", file=sys.stderr)
        return 1

    def print_record(record: dict) -> None:
        if args.gateway is not None and record.get("gateway_id") != args.gateway:
            return
        if args.json:
            print(json.dumps(record, default=str), flush=True)
            return
        direction = "->" if record.get("direction") == "incoming" else "<-"
        name = record.get("device_name") or ("known" if record.get("known") else "unknown")
        decoded = record.get("decoded")
        decoded_text = ""
        if isinstance(decoded, dict):
            decoded_text = "  " + ", ".join(f"{key}={value}" for key, value in decoded.items())
        print(f"{record.get('timestamp', '')} {direction} gw{record.get('gateway_id')} "
              f"{record.get('address') or record.get('msg_type'):17s} "
              f"{record.get('msg_type', ''):22s} {name}{decoded_text}", flush=True)

    unsubscribe = logger.add_subscriber(print_record)
    print("Listening for EnOcean telegrams (Ctrl+C to stop) ...", flush=True)
    try:
        await _wait_for_shutdown_signal()
    finally:
        unsubscribe()
    return 0


def _find_gateway(runtime, gateway_id: int):
    from custom_components.eltako.websocket import get_gateways

    return next((gw for gw in get_gateways(runtime.hass) if gw.dev_id == gateway_id), None)


async def _wait_for_connection(gateway, timeout: float) -> bool:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        try:
            if gateway._bus.is_active():
                return True
        except Exception:  # noqa: BLE001
            pass
        await asyncio.sleep(0.2)
    return False


def _parse_kv(pairs: list[str]) -> dict:
    result = {}
    for pair in pairs:
        if "=" not in pair:
            raise SystemExit(f"'{pair}' is not NAME=VALUE")
        name, value = pair.split("=", 1)
        try:
            result[name] = int(value, 0)
        except ValueError:
            try:
                result[name] = float(value)
            except ValueError:
                result[name] = value
    return result


async def _cmd_send(runtime, args) -> int:
    from custom_components.eltako.websocket import build_eep_telegram, parse_raw_esp2

    gateway = _find_gateway(runtime, args.gateway)
    if gateway is None:
        print(f"No gateway with id {args.gateway}.", file=sys.stderr)
        return 1
    if not await _wait_for_connection(gateway, args.wait):
        print(f"Gateway {args.gateway} ({gateway.serial_path}) is not connected.",
              file=sys.stderr)
        return 1

    try:
        if args.raw:
            telegram = parse_raw_esp2(args.raw)
        elif args.sender and args.eep:
            telegram = build_eep_telegram(args.sender, args.eep, _parse_kv(args.field))
        else:
            print("Either --raw or --sender + --eep is required.", file=sys.stderr)
            return 2
    except Exception as e:  # noqa: BLE001
        print(f"Cannot build the telegram: {e}", file=sys.stderr)
        return 1

    gateway.send_message(telegram)
    await asyncio.sleep(0.5)        # give the bus task time to write
    print(f"Sent: {telegram}  hex: {telegram.serialize().hex()}")
    return 0


async def _cmd_devices(runtime, args) -> int:
    from .entity_api import list_entities

    await asyncio.sleep(args.wait)
    entities = list_entities(runtime.hass)
    if args.platform:
        entities = [entity for entity in entities if entity["platform"] == args.platform]
    if args.json:
        print(json.dumps(entities, indent=2, default=str))
        return 0
    for entity in entities:
        unit = entity["attributes"].get("unit_of_measurement", "")
        state = f"{entity['state']} {unit}".strip()
        area = f"  [{entity['area']}]" if entity.get("area") else ""
        print(f"{entity['entity_id']:60s} {state:20s} {entity['name']}{area}")
    return 0


async def _cmd_state(runtime, args) -> int:
    from .entity_api import get_entity, list_entities

    await asyncio.sleep(args.wait)
    entity = get_entity(runtime.hass, args.entity_id)
    if entity is None:
        print(f"Unknown entity '{args.entity_id}'.", file=sys.stderr)
        return 1
    description = next(item for item in list_entities(runtime.hass)
                       if item["entity_id"] == args.entity_id)
    if args.json:
        print(json.dumps(description, indent=2, default=str))
    else:
        print(f"{description['entity_id']}: {description['state']}")
        for key, value in description["attributes"].items():
            print(f"  {key}: {value}")
        if description["actions"]:
            print(f"  actions: {', '.join(description['actions'])}")
    return 0


async def _cmd_control(runtime, args) -> int:
    from .entity_api import async_call_entity, get_entity

    entity = get_entity(runtime.hass, args.entity_id)
    if entity is None:
        print(f"Unknown entity '{args.entity_id}'.", file=sys.stderr)
        return 1
    gateway = getattr(entity, "gateway", None)
    if gateway is not None:
        await _wait_for_connection(gateway, args.wait)

    try:
        await async_call_entity(runtime.hass, args.entity_id, args.action,
                                _parse_kv(args.data))
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    await asyncio.sleep(1.0)        # wait for the actuator response telegram
    state = runtime.hass.states.get(args.entity_id)
    print(f"{args.entity_id}: {state.state if state else 'unknown'}")
    return 0


def _address_list(value: str | None) -> list[str] | None:
    return [part.strip() for part in value.split(",") if part.strip()] if value else None


async def _cmd_devicetest(runtime, args) -> int:
    """Every device test of the web ui, on the command line.

    The page and the CLI call the same runners of `device_tests.TEST_RUNNERS`, so a test never
    exists on one side only.
    """
    import asyncio as _asyncio

    from custom_components.eltako.device_tests import TEST_DESCRIPTORS, TEST_RUNNERS

    if args.devicetest == "list":
        for descriptor in TEST_DESCRIPTORS:
            print(f"{descriptor['id']:10} {descriptor['name']}")
            print(f"{'':10} {descriptor['description']}")
            if descriptor.get("warning"):
                print(f"{'':10} ! {descriptor['warning']}")
            if descriptor.get("sends_nothing"):
                print(f"{'':10} (sends no telegram)")
        return 0

    def log(line: str, style: str = "info") -> None:
        marker = {"ok": "+ ", "error": "! ", "received": "  "}.get(style, "")
        print(f"{marker}{line}", flush=True)

    if args.devicetest == "burst":
        gateway_ids = [args.gateway1, args.gateway2]
        params = {"gateway1": args.gateway1, "gateway2": args.gateway2,
                  "count": args.count, "delay": args.delay, "runs": args.runs}
    elif args.devicetest == "cover":
        gateway_ids = [args.gateway]
        params = {"gateway": args.gateway, "runs": args.runs,
                  "covers": _address_list(args.covers),
                  "senders": _address_list(args.senders),
                  "sequence": args.sequence}
    elif args.devicetest == "actuator":
        gateway_ids = [args.gateway]
        params = {"gateway": args.gateway, "devices": _address_list(args.devices),
                  "command": args.actuator_command, "timeout": args.timeout,
                  "settle": args.settle}
    elif args.devicetest == "config":
        gateway_ids = []
        # the findings are printed by _print_config_findings (sorted, filtered by --severity),
        # so the runner does not log them a second time
        params = {"gateways": args.gateways, "log_findings": False}
    else:
        print(f"Unknown device test '{args.devicetest}'. Available: "
              f"{', '.join(TEST_RUNNERS)}", file=sys.stderr)
        return 2

    if args.wait:
        for gateway_id in gateway_ids:
            gateway = _find_gateway(runtime, gateway_id)
            if gateway is not None:
                await _wait_for_connection(gateway, args.wait)

    runner = TEST_RUNNERS[args.devicetest]
    try:
        result = await runner(runtime.hass, params, log, _asyncio.Event())
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2

    if args.devicetest == "config":
        _print_config_findings(result, args)
    return 0 if result.get("success") else 1


def _print_config_findings(result: dict, args) -> None:
    """Machine readable output for the configuration check (the log already had the text)."""
    if getattr(args, "json", False):
        print(json.dumps(result, indent=2, default=str))
        return

    order = {"error": 0, "warning": 1, "info": 2}
    minimum = order[getattr(args, "severity", "info")]
    counts = result["counts"]
    print(f"\n{counts['error']} error(s), {counts['warning']} warning(s), {counts['info']} hint(s) "
          f"for {result['device_count']} device(s) of {result['gateway_count']} gateway(s).")
    for finding in result["findings"]:
        if order[finding["severity"]] > minimum:
            continue
        where = f" {finding['name']} ({finding['device']})" if finding["device"] else ""
        gateway = f" [gateway {finding['gateway_id']}]" if finding["gateway_id"] is not None else ""
        print(f"  {finding['severity'].upper():7}{gateway}{where}: {finding['message']}")


if __name__ == "__main__":
    sys.exit(main())
