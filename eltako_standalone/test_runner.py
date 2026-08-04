"""Run the test suites of the project - from the CLI or from the web ui.

Suites:
    integration      pytest tests of the integration (needs the homeassistant package)
    standalone       pytest of the standalone runtime (own process, uses the shim)
    device-manager   pytest of the EnOcean Device Manager (eo_man). Its repository is
                     looked up next to this one (../enocean-device-manager) or via the
                     environment variable ELTAKO_EO_MAN_DIR.

Every suite runs as its own pytest subprocess: the integration tests import the
real homeassistant package while the standalone tests must not - they can never
share a process (see eltako_standalone/tests/conftest.py).

Used by `python -m eltako_standalone test` and the 'Tests' page of the web ui
(websocket commands eltako/tests/suites and eltako/tests/run).
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
import time

LOGGER = logging.getLogger("eltako_standalone.test_runner")

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

WS_TEST_SUITES = "eltako/tests/suites"
WS_TEST_RUN = "eltako/tests/run"

SUITE_TIMEOUT_SECONDS = 600


def _eo_man_dir() -> str | None:
    candidates = [os.environ.get("ELTAKO_EO_MAN_DIR"),
                  os.path.join(os.path.dirname(REPO_ROOT), "enocean-device-manager")]
    for candidate in candidates:
        if candidate and os.path.isdir(os.path.join(candidate, "tests")):
            return candidate
    return None


def get_suites() -> list[dict]:
    eo_man = _eo_man_dir()
    return [
        {
            "id": "integration",
            "name": "Eltako integration",
            "description": "Unit tests of custom_components/eltako (entities, EEP decoding, "
                           "telegram logger, device config).",
            "path": os.path.join(REPO_ROOT, "tests"),
            "cwd": REPO_ROOT,
            "args": [],
            "available": os.path.isdir(os.path.join(REPO_ROOT, "tests")),
        },
        {
            "id": "standalone",
            "name": "Standalone runtime",
            "description": "Tests of the standalone runtime (homeassistant shim, entity api, "
                           "web server).",
            "path": os.path.join(REPO_ROOT, "eltako_standalone", "tests"),
            "cwd": REPO_ROOT,
            "args": [],
            "available": os.path.isdir(os.path.join(REPO_ROOT, "eltako_standalone", "tests")),
        },
        {
            "id": "device-manager",
            "name": "EnOcean Device Manager",
            "description": "Test suite of the EnOcean Device Manager (eo_man). Requires its "
                           "repository next to this one or ELTAKO_EO_MAN_DIR.",
            "path": os.path.join(eo_man, "tests") if eo_man else None,
            "cwd": eo_man,
            # some of its tests need a display (tkinter) - keep collecting anyway
            "args": ["--continue-on-collection-errors"],
            "available": eo_man is not None,
        },
    ]


def get_suite(suite_id: str) -> dict | None:
    return next((suite for suite in get_suites() if suite["id"] == suite_id), None)


_SUMMARY_PATTERNS = {"passed": r"(\d+) passed", "failed": r"(\d+) failed",
                     "skipped": r"(\d+) skipped", "errors": r"(\d+) error"}


def _parse_summary(output: str) -> dict:
    """passed/failed/skipped/errors from the last pytest summary line."""
    result = {"passed": 0, "failed": 0, "skipped": 0, "errors": 0}
    for line in reversed(output.splitlines()):
        if ("passed" in line or "failed" in line or "error" in line) and "=" in line:
            for key, pattern in _SUMMARY_PATTERNS.items():
                match = re.search(pattern, line)
                if match:
                    result[key] = int(match.group(1))
            break
    return result


def run_suite(suite_id: str, stream_to_stdout: bool = False) -> dict:
    """Run one suite in a pytest subprocess and return a result dict."""
    suite = get_suite(suite_id)
    if suite is None:
        raise ValueError(f"Unknown test suite '{suite_id}'. "
                         f"Available: {', '.join(s['id'] for s in get_suites())}")
    if not suite["available"]:
        raise ValueError(f"Test suite '{suite_id}' is not available on this machine "
                         f"({suite['description']})")

    command = [sys.executable, "-m", "pytest", suite["path"], "-q", *suite["args"]]
    started = time.time()
    LOGGER.info("Running test suite '%s': %s", suite_id, " ".join(command))

    if stream_to_stdout:
        completed = subprocess.run(command, cwd=suite["cwd"], timeout=SUITE_TIMEOUT_SECONDS)
        output = ""
    else:
        completed = subprocess.run(command, cwd=suite["cwd"], capture_output=True,
                                   text=True, timeout=SUITE_TIMEOUT_SECONDS)
        output = (completed.stdout or "") + (completed.stderr or "")

    duration = round(time.time() - started, 1)
    summary = _parse_summary(output)
    return {
        "suite": suite_id,
        "command": " ".join(command),
        "returncode": completed.returncode,
        "success": completed.returncode == 0,
        "duration_seconds": duration,
        "output": output[-100_000:],        # keep the payload bounded
        **summary,
    }


### ---------------------------------------------------------------------------
### websocket api (standalone web ui)
### ---------------------------------------------------------------------------

def register_websocket_commands(hass) -> None:
    import voluptuous as vol
    from homeassistant.components import websocket_api
    from homeassistant.core import callback

    @websocket_api.websocket_command({vol.Required("type"): WS_TEST_SUITES})
    @callback
    def ws_test_suites(hass, connection, msg) -> None:
        suites = [{key: suite[key] for key in ("id", "name", "description", "path", "available")}
                  for suite in get_suites()]
        connection.send_result(msg["id"], {"suites": suites})

    @websocket_api.websocket_command({
        vol.Required("type"): WS_TEST_RUN,
        vol.Required("suite"): str,
    })
    @websocket_api.async_response
    async def ws_test_run(hass, connection, msg) -> None:
        try:
            result = await hass.async_add_executor_job(run_suite, msg["suite"])
        except ValueError as e:
            connection.send_error(msg["id"], "invalid_suite", str(e))
            return
        except subprocess.TimeoutExpired:
            connection.send_error(msg["id"], "timeout",
                                  f"Test suite did not finish within {SUITE_TIMEOUT_SECONDS}s.")
            return
        connection.send_result(msg["id"], result)

    websocket_api.async_register_command(hass, ws_test_suites)
    websocket_api.async_register_command(hass, ws_test_run)
