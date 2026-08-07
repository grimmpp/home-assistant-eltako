"""The configuration check (config_check.py).

It answers the question which fills the issue tracker: "Home Assistant sends but nothing
happens" - almost always a configuration which cannot work. Every check has its own test with
a configuration that is wrong in exactly one way, plus one healthy configuration which has to
stay silent (a check which cries wolf is worse than no check).
"""
import unittest
from unittest import mock

import yaml

from custom_components.eltako.config import config_check
from custom_components.eltako.config.config_check import (
    SEVERITY_ERROR, SEVERITY_INFO, SEVERITY_WARNING, check_configuration)
from custom_components.eltako.const import DATA_ELTAKO, ELTAKO_CONFIG


class HassStub:
    """Just enough hass for the check: the eltako configuration."""

    def __init__(self, config: dict):
        self.data = {DATA_ELTAKO: {ELTAKO_CONFIG: config}}


def config_of(yaml_text: str) -> dict:
    """The eltako section of a configuration.yaml."""
    return yaml.safe_load(yaml_text)["eltako"]


HEALTHY = """
eltako:
  gateway:
  - id: 1
    device_type: fgw14usb
    base_id: FF-AA-80-00
    devices:
      switch:
      - id: 00-00-00-01
        eep: M5-38-08
        name: Relay
        sender: {id: 00-00-B0-01, eep: A5-38-08}
      cover:
      - id: 00-00-00-06
        eep: G5-3F-7F
        name: Cover
        sender: {id: 00-00-B0-06, eep: H5-3F-7F}
        time_closes: 24
        time_opens: 25
      binary_sensor:
      - id: FF-BB-CC-DD
        eep: F6-02-01
        name: Rocker
  - id: 2
    device_type: fam-usb
    base_id: FF-BC-00-00
    devices:
      light:
      - id: FF-BC-00-10
        eep: A5-38-08
        name: Wireless light
        sender: {id: FF-BC-00-01, eep: A5-38-08}
"""


def check(yaml_text: str, hass=None) -> dict:
    config = config_of(yaml_text)
    return check_configuration(hass if hass is not None else HassStub(config))


def findings_of(result: dict, check_name: str) -> list[dict]:
    return [finding for finding in result["findings"] if finding["check"] == check_name]


class TestHealthyConfiguration(unittest.TestCase):

    def test_nothing_is_reported(self):
        result = check(HEALTHY)

        self.assertEqual([], result["findings"], msg=result["findings"])
        self.assertTrue(result["success"])
        self.assertEqual(2, result["gateway_count"])
        self.assertEqual(4, result["device_count"])

    def test_a_wireless_sensor_needs_no_sender(self):
        """Only actuators are driven by Home Assistant - a rocker switch only reports."""
        self.assertEqual([], findings_of(check(HEALTHY), "sender_missing"))


class TestAddressClasses(unittest.TestCase):

    def test_wireless_actuator_on_a_bus_gateway_is_a_hint(self):
        """Only a hint: a FAM14 does transmit by radio, an FGW14-USB does not."""
        result = check("""
eltako:
  gateway:
  - id: 1
    device_type: fgw14usb
    devices:
      switch:
      - id: FF-AA-BB-CC
        eep: M5-38-08
        sender: {id: 00-00-B0-01, eep: A5-38-08}
""")
        finding = findings_of(result, "address_class")[0]

        self.assertEqual(SEVERITY_INFO, finding["severity"])
        self.assertIn("FF-AA-BB-CC", finding["message"])
        self.assertIn("00-00-XX-XX", finding["message"])

    def test_a_wireless_sensor_on_a_bus_gateway_is_normal(self):
        """The FAM14 forwards radio telegrams onto the bus - this is the standard setup."""
        result = check("""
eltako:
  gateway:
  - id: 1
    device_type: fgw14usb
    devices:
      binary_sensor:
      - id: FF-AA-BB-CC
        eep: F6-02-01
""")
        self.assertEqual([], findings_of(result, "address_class"))

    def test_local_address_on_a_transceiver(self):
        result = check("""
eltako:
  gateway:
  - id: 1
    device_type: fam-usb
    base_id: FF-BC-00-00
    devices:
      switch:
      - id: 00-00-00-01
        eep: M5-38-08
        sender: {id: FF-BC-00-01, eep: A5-38-08}
""")
        finding = findings_of(result, "address_class")[0]

        self.assertEqual(SEVERITY_ERROR, finding["severity"])
        self.assertIn("FF-XX-XX-XX", finding["message"])

    def test_unknown_gateway_type(self):
        result = check("""
eltako:
  gateway:
  - id: 1
    device_type: fam-99
""")
        finding = findings_of(result, "gateway_type")[0]

        self.assertEqual(SEVERITY_ERROR, finding["severity"])

    def test_no_gateway_at_all(self):
        result = check("eltako: {}")

        self.assertEqual(SEVERITY_WARNING, findings_of(result, "no_gateway")[0]["severity"])


class TestSenders(unittest.TestCase):

    def test_actuator_without_sender(self):
        result = check("""
eltako:
  gateway:
  - id: 1
    device_type: fgw14usb
    devices:
      light:
      - id: 00-00-00-01
        eep: M5-38-08
""")
        finding = findings_of(result, "sender_missing")[0]

        self.assertEqual(SEVERITY_ERROR, finding["severity"])
        self.assertEqual("00-00-00-01", finding["device"])

    def test_sender_outside_the_base_id_range_of_a_transceiver(self):
        """The gateway drops those telegrams silently - the most invisible mistake there is."""
        result = check("""
eltako:
  gateway:
  - id: 1
    device_type: fam-usb
    base_id: FF-BC-00-00
    devices:
      switch:
      - id: FF-BC-00-10
        eep: M5-38-08
        sender: {id: FF-11-22-33, eep: A5-38-08}
""")
        finding = findings_of(result, "sender_base_id")[0]

        self.assertEqual(SEVERITY_WARNING, finding["severity"])
        self.assertIn("FF-11-22-33", finding["message"])
        self.assertIn("FF-BC-00", finding["message"])

    def test_sender_inside_the_base_id_range_is_fine(self):
        result = check("""
eltako:
  gateway:
  - id: 1
    device_type: fam-usb
    base_id: FF-BC-00-00
    devices:
      switch:
      - id: FF-BC-00-10
        eep: M5-38-08
        sender: {id: FF-BC-00-7F, eep: A5-38-08}
""")
        self.assertEqual([], findings_of(result, "sender_base_id"))

    def test_wireless_sender_on_a_bus_gateway(self):
        result = check("""
eltako:
  gateway:
  - id: 1
    device_type: fgw14usb
    devices:
      switch:
      - id: 00-00-00-01
        eep: M5-38-08
        sender: {id: FF-AA-80-01, eep: A5-38-08}
""")
        self.assertEqual(SEVERITY_WARNING, findings_of(result, "sender_base_id")[0]["severity"])

    def test_unknown_base_id_is_only_a_hint(self):
        """The base id is queried from the hardware, so it may be missing in the yaml."""
        result = check("""
eltako:
  gateway:
  - id: 1
    device_type: fam-usb
    devices:
      switch:
      - id: FF-BC-00-10
        eep: M5-38-08
        sender: {id: FF-11-22-33, eep: A5-38-08}
""")
        self.assertEqual(SEVERITY_INFO, findings_of(result, "base_id")[0]["severity"])
        self.assertEqual([], findings_of(result, "sender_base_id"))

    def test_a_shared_sender_is_reported_as_hint(self):
        result = check("""
eltako:
  gateway:
  - id: 1
    device_type: fgw14usb
    devices:
      switch:
      - id: 00-00-00-01
        eep: M5-38-08
        sender: {id: 00-00-B0-01, eep: A5-38-08}
      - id: 00-00-00-02
        eep: M5-38-08
        sender: {id: 00-00-B0-01, eep: A5-38-08}
""")
        finding = findings_of(result, "sender_shared")[0]

        self.assertEqual(SEVERITY_INFO, finding["severity"])
        self.assertIn("2 devices", finding["message"])


class TestDuplicatesAndPlatforms(unittest.TestCase):

    def test_the_same_address_twice(self):
        result = check("""
eltako:
  gateway:
  - id: 1
    device_type: fgw14usb
    devices:
      switch:
      - id: 00-00-00-01
        eep: M5-38-08
        sender: {id: 00-00-B0-01, eep: A5-38-08}
      light:
      - id: 00-00-00-01
        eep: M5-38-08
        sender: {id: 00-00-B0-02, eep: A5-38-08}
""")
        finding = findings_of(result, "duplicate_device")[0]

        self.assertEqual(SEVERITY_ERROR, finding["severity"])

    def test_cover_without_travel_times(self):
        result = check("""
eltako:
  gateway:
  - id: 1
    device_type: fgw14usb
    devices:
      cover:
      - id: 00-00-00-06
        eep: G5-3F-7F
        sender: {id: 00-00-B0-06, eep: H5-3F-7F}
""")
        finding = findings_of(result, "cover_times")[0]

        self.assertEqual(SEVERITY_INFO, finding["severity"])
        self.assertIn("time_closes", finding["message"])


class TestWhatTheBusKnows(unittest.TestCase):
    """The check also uses the bus member registry: which model answered at which position and
    which senders are in its memory."""

    BUS_CONFIG = """
eltako:
  gateway:
  - id: 1
    device_type: fgw14usb
    devices:
      switch:
      - id: 00-00-00-01
        eep: M5-38-08
        name: Relay
        sender: {id: 00-00-B0-01, eep: A5-38-08}
"""

    def check_with_members(self, members: list[dict], config: str = None) -> dict:
        config = config_of(config or self.BUS_CONFIG)
        with mock.patch.object(config_check, "_bus_members_by_address",
                               return_value={member["bus_address"]: member for member in members}):
            return check_configuration(HassStub(config))

    def test_position_which_never_answered(self):
        result = self.check_with_members([
            {"bus_address": 5, "device_class": "FSR14_4x"},
        ])
        finding = findings_of(result, "not_on_the_bus")[0]

        self.assertEqual(SEVERITY_WARNING, finding["severity"])
        self.assertIn("1", finding["message"])

    def test_eep_which_differs_from_the_model(self):
        result = self.check_with_members([
            {"bus_address": 1, "device_class": "FUD14", "suggested_eep": "A5-38-08"},
        ])
        finding = findings_of(result, "eep_differs")[0]

        self.assertEqual(SEVERITY_INFO, finding["severity"])
        self.assertIn("FUD14", finding["message"])
        self.assertIn("A5-38-08", finding["message"])

    def test_sender_which_is_not_taught_in(self):
        result = self.check_with_members([
            {"bus_address": 1, "device_class": "FSR14_4x", "suggested_eep": "M5-38-08",
             "scanned_at": "2026-08-01T10:00:00+00:00",
             "taught_in": [{"sensor_id": "00-00-B0-99"}]},
        ])
        finding = findings_of(result, "sender_not_taught_in")[0]

        self.assertEqual(SEVERITY_WARNING, finding["severity"])
        self.assertIn("00-00-B0-01", finding["message"])

    def test_a_taught_in_sender_is_not_reported(self):
        result = self.check_with_members([
            {"bus_address": 1, "device_class": "FSR14_4x", "suggested_eep": "M5-38-08",
             "scanned_at": "2026-08-01T10:00:00+00:00",
             "taught_in": [{"sensor_id": "00-00-B0-01"}]},
        ])
        self.assertEqual([], findings_of(result, "sender_not_taught_in"))

    def test_without_a_memory_image_nothing_is_claimed(self):
        """No scan, no statement about the teach-in."""
        result = self.check_with_members([
            {"bus_address": 1, "device_class": "FSR14_4x", "suggested_eep": "M5-38-08"},
        ])
        self.assertEqual([], findings_of(result, "sender_not_taught_in"))


class TestActivity(unittest.TestCase):

    def test_a_device_which_never_reported(self):
        config = config_of(TestWhatTheBusKnows.BUS_CONFIG)
        with mock.patch.object(config_check, "_activity", return_value={"count": 0}):
            result = check_configuration(HassStub(config))

        finding = findings_of(result, "never_heard_of")[0]
        self.assertEqual(SEVERITY_WARNING, finding["severity"])

    def test_no_activity_data_means_no_finding(self):
        config = config_of(TestWhatTheBusKnows.BUS_CONFIG)
        with mock.patch.object(config_check, "_activity", return_value=None):
            result = check_configuration(HassStub(config))

        self.assertEqual([], findings_of(result, "never_heard_of"))


class TestResultShape(unittest.TestCase):

    def test_counts_and_filter_by_gateway(self):
        config = config_of(HEALTHY)
        hass = HassStub(config)

        everything = check_configuration(hass)
        only_two = check_configuration(hass, [2])

        self.assertEqual(2, everything["gateway_count"])
        self.assertEqual(1, only_two["gateway_count"])
        self.assertEqual(1, only_two["device_count"])
        self.assertEqual({"error": 0, "warning": 0, "info": 0}, everything["counts"])

    def test_success_is_false_for_errors_and_warnings_only(self):
        info_only = check("""
eltako:
  gateway:
  - id: 1
    device_type: fgw14usb
    devices:
      cover:
      - id: 00-00-00-06
        eep: G5-3F-7F
        sender: {id: 00-00-B0-06, eep: H5-3F-7F}
""")
        self.assertEqual(1, info_only["counts"][SEVERITY_INFO])
        self.assertTrue(info_only["success"], msg="a hint must not fail the check")


class TestRunner(unittest.IsolatedAsyncioTestCase):
    """The runner is what the tests page and the command line call."""

    async def test_it_logs_every_finding_and_returns_the_result(self):
        config = config_of("""
eltako:
  gateway:
  - id: 1
    device_type: fgw14usb
    devices:
      light:
      - id: FF-AA-BB-CC
        eep: M5-38-08
        name: Wrong address
""")
        lines = []
        result = await config_check.run_config_test(
            HassStub(config), {}, lambda line, style="info": lines.append((style, line)))

        self.assertEqual("config", result["test"])
        self.assertFalse(result["success"])
        self.assertTrue(any("ERROR" in line for _style, line in lines))
        self.assertTrue(any(line.startswith("RESULT:") for _style, line in lines))

    async def test_the_findings_can_be_left_out_of_the_log(self):
        """The command line prints them itself (sorted, filtered by --severity)."""
        config = config_of("""
eltako:
  gateway:
  - id: 1
    device_type: fam-usb
    base_id: FF-BC-00-00
    devices:
      switch:
      - id: 00-00-00-01
        eep: M5-38-08
        sender: {id: 00-00-B0-01, eep: A5-38-08}
""")
        with_findings, without = [], []
        await config_check.run_config_test(HassStub(config), {},
                                          lambda line, style="info": with_findings.append(line))
        result = await config_check.run_config_test(
            HassStub(config), {"log_findings": False},
            lambda line, style="info": without.append(line))

        self.assertTrue(any("ERROR" in line for line in with_findings))
        self.assertFalse(any("ERROR" in line for line in without))
        self.assertTrue(any(line.startswith("RESULT:") for line in without))
        self.assertTrue(result["findings"], msg="the findings still have to be in the result")

    async def test_it_accepts_a_single_gateway_id(self):
        config = config_of(HEALTHY)

        result = await config_check.run_config_test(HassStub(config), {"gateways": 2},
                                                    lambda line, style="info": None)

        self.assertEqual(1, result["gateway_count"])
