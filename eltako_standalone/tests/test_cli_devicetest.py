"""Every device test has to be usable from the command line, without the web ui.

The web ui and the CLI call the same runners (`device_tests.TEST_RUNNERS`), so what is checked
here is the part which can drift apart: a test which has no subcommand, an option which is not
passed on to the runner, and the output of the configuration check.
"""

import asyncio
import io
import json
from contextlib import redirect_stdout
from unittest import mock

import pytest

from eltako_standalone.cli import build_parser


def parse(*argv):
    return build_parser().parse_args(argv)


def test_every_test_of_the_backend_has_a_subcommand():
    from custom_components.eltako.device_tests import TEST_RUNNERS

    parser = build_parser()
    devicetest = next(action for action in parser._subparsers._group_actions[0].choices.values()
                      if action.prog.endswith("devicetest"))
    subcommands = set(devicetest._subparsers._group_actions[0].choices)

    missing = set(TEST_RUNNERS) - subcommands
    assert not missing, f"no CLI subcommand for {missing}"
    assert "list" in subcommands, "devicetest list shows what is available"


def test_the_parser_accepts_the_new_tests():
    actuator = parse("devicetest", "actuator", "--gateway", "1", "--devices", "00-00-00-01",
                     "--command", "off", "--timeout", "5", "--settle", "0")

    # 'command' must stay the top level subcommand - --command of the actuator test uses its
    # own dest, otherwise the dispatch in _async_main would not find 'devicetest' anymore
    assert actuator.command == "devicetest"
    assert actuator.devicetest == "actuator"
    assert actuator.actuator_command == "off"
    assert actuator.gateway == 1
    assert actuator.devices == "00-00-00-01"
    assert actuator.timeout == 5
    assert actuator.settle == 0

    config = parse("devicetest", "config", "--gateway", "1", "--gateway", "2", "--json")

    assert config.gateways == [1, 2]
    assert config.json is True


def test_an_unknown_command_value_is_refused():
    with pytest.raises(SystemExit):
        parse("devicetest", "actuator", "--gateway", "1", "--command", "blink")


class RuntimeStub:
    def __init__(self):
        self.hass = object()


def _run_cli(args, runner):
    """_cmd_devicetest with a faked runner - what params does it build?"""
    from eltako_standalone import cli

    with mock.patch.dict("custom_components.eltako.device_tests.TEST_RUNNERS",
                         {args.devicetest: runner}):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = asyncio.run(cli._cmd_devicetest(RuntimeStub(), args))
    return code, buffer.getvalue()


def test_the_actuator_options_reach_the_runner():
    seen = {}

    async def runner(hass, params, log, stop_event):
        seen.update(params)
        log("running", "info")
        return {"success": True}

    args = parse("devicetest", "actuator", "--gateway", "2", "--devices",
                 "00-00-00-01, 00-00-00-02", "--command", "off_on", "--timeout", "4",
                 "--settle", "0.5", "--wait", "0")
    code, output = _run_cli(args, runner)

    assert code == 0
    assert seen == {"gateway": 2, "devices": ["00-00-00-01", "00-00-00-02"],
                    "command": "off_on", "timeout": 4.0, "settle": 0.5}
    assert "running" in output


def test_the_config_check_prints_its_findings():
    findings = [
        {"severity": "error", "check": "sender_missing", "gateway_id": 1,
         "device": "00-00-00-03", "name": "Lamp", "message": "No sender configured."},
        {"severity": "info", "check": "cover_times", "gateway_id": 1,
         "device": "00-00-00-06", "name": "Cover", "message": "No travel times."},
    ]
    result = {"test": "config", "success": False, "findings": findings,
              "counts": {"error": 1, "warning": 0, "info": 1},
              "gateway_count": 1, "device_count": 3}

    async def runner(hass, params, log, stop_event):
        return result

    args = parse("devicetest", "config")
    code, output = _run_cli(args, runner)

    assert code == 1                       # an error makes the exit code non zero
    assert "1 error(s), 0 warning(s), 1 hint(s)" in output
    assert "No sender configured." in output
    assert "No travel times." in output


def test_the_severity_filter_hides_the_hints():
    result = {"test": "config", "success": False,
              "findings": [{"severity": "info", "check": "cover_times", "gateway_id": 1,
                            "device": "00-00-00-06", "name": "Cover", "message": "No travel times."}],
              "counts": {"error": 0, "warning": 0, "info": 1},
              "gateway_count": 1, "device_count": 1}

    async def runner(hass, params, log, stop_event):
        return result

    args = parse("devicetest", "config", "--severity", "warning")
    _code, output = _run_cli(args, runner)

    assert "No travel times." not in output
    assert "0 error(s)" in output


def test_json_output_is_machine_readable():
    result = {"test": "config", "success": True, "findings": [],
              "counts": {"error": 0, "warning": 0, "info": 0},
              "gateway_count": 2, "device_count": 5}

    async def runner(hass, params, log, stop_event):
        return result

    args = parse("devicetest", "config", "--json")
    code, output = _run_cli(args, runner)

    assert code == 0
    assert json.loads(output)["device_count"] == 5


def test_list_prints_every_test_without_touching_the_hardware():
    from custom_components.eltako.device_tests import TEST_DESCRIPTORS
    from eltako_standalone import cli

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = asyncio.run(cli._cmd_devicetest(RuntimeStub(), parse("devicetest", "list")))
    output = buffer.getvalue()

    assert code == 0
    for descriptor in TEST_DESCRIPTORS:
        assert descriptor["id"] in output
        assert descriptor["name"] in output


def test_a_failing_runner_reports_the_reason():
    async def runner(hass, params, log, stop_event):
        raise ValueError("Gateway 9 is not connected.")

    args = parse("devicetest", "actuator", "--gateway", "9", "--wait", "0")
    code, _output = _run_cli(args, runner)

    assert code == 2
