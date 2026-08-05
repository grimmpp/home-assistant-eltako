"""The actuator / teach-in test (device_tests.run_actuator_test and its helpers).

The test switches real actuators, so the telegrams it sends have to be byte for byte the ones
light.py/switch.py send - otherwise it would prove something the integration never does. That
is what is pinned here, together with the selection of the devices.

The end to end run (send, wait for the answer, report the round trip) is in
eltako_standalone/tests/test_device_tests_actuator.py, which has a booted runtime.
"""
import unittest

import yaml

from eltakobus.eep import A5_38_08, CentralCommandDimming, CentralCommandSwitching, F6_02_01

from custom_components.eltako.device_tests import (
    build_switch_telegrams, get_configured_actuators, resolve_actuators)
from custom_components.eltako.const import DATA_ELTAKO, ELTAKO_CONFIG

CONFIG = """
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
      light:
      - id: 00-00-00-02
        eep: M5-38-08
        name: Lamp
        sender: {id: 00-00-B0-02, eep: A5-38-08}
      - id: 00-00-00-03
        eep: M5-38-08
        name: Lamp without sender
      cover:
      - id: 00-00-00-06
        eep: G5-3F-7F
        name: Cover
        sender: {id: 00-00-B0-06, eep: H5-3F-7F}
      binary_sensor:
      - id: FF-BB-CC-DD
        eep: F6-02-01
        name: Rocker
"""


class HassStub:
    def __init__(self, config: dict):
        self.data = {DATA_ELTAKO: {ELTAKO_CONFIG: config}}


def hass() -> HassStub:
    return HassStub(yaml.safe_load(CONFIG)["eltako"])


class TestTheSelection(unittest.TestCase):
    """Covers and sensors are not part of this test - covers have their own one."""

    def test_only_switchable_actuators_are_offered(self):
        actuators = get_configured_actuators(hass(), 1)

        self.assertEqual(["00-00-00-01", "00-00-00-02", "00-00-00-03"],
                         [actuator["id"] for actuator in actuators])
        self.assertEqual({"switch", "light"}, {actuator["platform"] for actuator in actuators})

    def test_the_sender_comes_along(self):
        relay = get_configured_actuators(hass(), 1)[0]

        self.assertEqual("00-00-B0-01", relay["sender_id"])
        self.assertEqual("A5-38-08", relay["sender_eep"])
        self.assertEqual("Relay", relay["name"])

    def test_a_device_without_sender_is_listed_with_an_empty_sender(self):
        """The runner reports it as skipped - the reason belongs into the result, not into an
        exception which hides the other devices."""
        without = get_configured_actuators(hass(), 1)[2]

        self.assertEqual("00-00-00-03", without["id"])
        self.assertEqual("", without["sender_id"])

    def test_without_a_selection_all_of_them(self):
        self.assertEqual(3, len(resolve_actuators(hass(), 1, None)))
        self.assertEqual(3, len(resolve_actuators(hass(), 1, [])))

    def test_a_subset_keeps_the_given_order(self):
        actuators = resolve_actuators(hass(), 1, ["00-00-00-02", "00-00-00-01"])

        self.assertEqual(["00-00-00-02", "00-00-00-01"], [a["id"] for a in actuators])

    def test_lower_case_addresses_are_accepted(self):
        self.assertEqual("00-00-00-01", resolve_actuators(hass(), 1, ["00-00-00-01 "])[0]["id"])

    def test_an_unknown_address_is_refused_with_a_reason(self):
        with self.assertRaises(ValueError) as caught:
            resolve_actuators(hass(), 1, ["00-00-00-99"])

        self.assertIn("00-00-00-99", str(caught.exception))
        self.assertIn("configured", str(caught.exception))

    def test_a_cover_is_not_switchable(self):
        with self.assertRaises(ValueError):
            resolve_actuators(hass(), 1, ["00-00-00-06"])


class TestTheTelegrams(unittest.TestCase):
    """Byte for byte what switch.py / light.py send."""

    SWITCH = {"id": "00-00-00-01", "name": "Relay", "platform": "switch",
              "sender_id": "00-00-B0-01", "sender_eep": "A5-38-08"}
    LIGHT = {"id": "00-00-00-02", "name": "Lamp", "platform": "light",
             "sender_id": "00-00-B0-01", "sender_eep": "A5-38-08"}

    def expected(self, message):
        return message.body

    def test_switch_on_and_off(self):
        address = b"\x00\x00\xb0\x01"

        on = build_switch_telegrams(self.SWITCH, True)
        off = build_switch_telegrams(self.SWITCH, False)

        self.assertEqual(1, len(on))
        self.assertEqual(A5_38_08(command=0x01, switching=CentralCommandSwitching(0, 1, 0, 0, 1))
                         .encode_message(address).body, on[0].body)
        self.assertEqual(A5_38_08(command=0x01, switching=CentralCommandSwitching(0, 1, 0, 0, 0))
                         .encode_message(address).body, off[0].body)

    def test_light_uses_the_dimming_variant(self):
        address = b"\x00\x00\xb0\x01"

        on = build_switch_telegrams(self.LIGHT, True)

        self.assertEqual(A5_38_08(command=0x02, dimming=CentralCommandDimming(100, 0, 1, 0, 0, 1))
                         .encode_message(address).body, on[0].body)

    def test_a_rocker_sends_press_and_release(self):
        rocker = dict(self.SWITCH, sender_eep="F6-02-01")
        address = b"\x00\x00\xb0\x01"

        telegrams = build_switch_telegrams(rocker, True)

        self.assertEqual(2, len(telegrams))
        self.assertEqual(F6_02_01(1, 1, 0, 0).encode_message(address).body, telegrams[0].body)
        self.assertEqual(F6_02_01(1, 0, 0, 0).encode_message(address).body, telegrams[1].body)

    def test_the_sender_address_is_used_not_the_device_address(self):
        telegram = build_switch_telegrams(self.SWITCH, True)[0]

        self.assertEqual(b"\x00\x00\xb0\x01", telegram.address)

    def test_an_unsupported_sender_eep_says_which_ones_work(self):
        cover_sender = dict(self.SWITCH, sender_eep="H5-3F-7F")

        with self.assertRaises(ValueError) as caught:
            build_switch_telegrams(cover_sender, True)

        self.assertIn("A5-38-08", str(caught.exception))

    def test_an_unknown_sender_eep_is_reported(self):
        with self.assertRaises(ValueError):
            build_switch_telegrams(dict(self.SWITCH, sender_eep="X5-99-99"), True)
