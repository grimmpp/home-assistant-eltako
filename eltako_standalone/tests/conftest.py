"""Test setup for the standalone runtime.

IMPORTANT: these tests must run in their own pytest process:

    pytest eltako_standalone/tests

They activate the homeassistant shim via sys.path. If the real homeassistant
package was already imported (e.g. because the tests of the integration ran in
the same process), the whole suite is skipped.
"""

import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from eltako_standalone.runtime import install_shim  # noqa: E402

try:
    install_shim()
except RuntimeError:
    pytest.skip("real homeassistant already imported - run these tests in their own "
                "pytest process: pytest eltako_standalone/tests", allow_module_level=True)


CONFIG_YAML = """
eltako:
  general_settings:
    enable_frontend: True
    log_enocean_telegrams: True
  gateway:
  - id: 1
    device_type: fgw14usb
    base_id: FF-AA-80-00
    name: Test-Gateway
    auto_reconnect: False
    serial_path: /dev/tty.does-not-exist
    devices:
      light:
      - id: 00-00-00-01
        eep: M5-38-08
        name: Testlampe
        area: Kitchen
        sender: {id: 00-00-B0-01, eep: A5-38-08}
      binary_sensor:
      - id: ff-bb-0a-1b
        eep: F6-02-01
        name: Taster
"""


@pytest.fixture
def config_dir(tmp_path):
    (tmp_path / "configuration.yaml").write_text(CONFIG_YAML, encoding="utf-8")
    return str(tmp_path)


@pytest.fixture
def empty_config_dir(tmp_path):
    (tmp_path / "configuration.yaml").write_text(
        "eltako:\n  general_settings:\n    enable_frontend: True\n", encoding="utf-8")
    return str(tmp_path)
