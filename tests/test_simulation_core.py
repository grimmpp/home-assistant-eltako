"""The simulation without Home Assistant: addresses, telegrams, actuators, model, presets.

Everything here uses `custom_components.eltako.simulation.core` only - that package must stay
free of Home Assistant imports so it can be moved into a library of its own, and these tests
prove it does (see TestItIsIndependentOfHomeAssistant).
"""
import os
import unittest
from unittest import TestCase

from eltakobus.message import Regular4BSMessage, RPSMessage, prettify
from eltakobus.eep import EEP

from custom_components.eltako.simulation import core as sim

CORE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                        'custom_components', 'eltako', 'simulation', 'core')


class TestItIsIndependentOfHomeAssistant(TestCase):
    """The core is the part which can become a library - it must not need Home Assistant."""

    def test_no_module_imports_homeassistant(self):
        offenders = []
        for name in sorted(os.listdir(CORE_DIR)):
            if not name.endswith('.py'):
                continue
            with open(os.path.join(CORE_DIR, name), encoding='utf-8') as handle:
                for number, line in enumerate(handle, start=1):
                    stripped = line.strip()
                    if not (stripped.startswith('import ') or stripped.startswith('from ')):
                        continue
                    if 'homeassistant' in stripped or stripped.startswith('from ..'):
                        offenders.append(f"core/{name}:{number} {stripped}")
        self.assertEqual(offenders, [], "the simulation core must stay hardware and "
                                        "Home Assistant independent")


class TestAddresses(TestCase):

    def test_a_bus_gateway_uses_local_addresses(self):
        model = sim.SimulationModel()
        gateway = model.add_gateway(2, 'fam14')

        self.assertTrue(gateway.is_bus_gateway)
        self.assertEqual(gateway.base_id, 'FF-C0-02-00')
        suggestion = gateway.suggest_device('light', 'M5-38-08', 'A5-38-08')
        self.assertEqual(suggestion['address'], '00-00-00-01')
        # same convention as plug_and_play.local_sender_id / the EnOcean Device Manager
        self.assertEqual(suggestion['sender_id'], '00-00-B0-01')

    def test_a_transceiver_uses_its_base_id_range(self):
        model = sim.SimulationModel()
        gateway = model.add_gateway(3, 'enocean-usb300')

        self.assertFalse(gateway.is_bus_gateway)
        suggestion = gateway.suggest_device('light', 'M5-38-08', 'A5-38-08')
        self.assertEqual(suggestion['address'], 'FF-C0-03-01')
        # a wireless transceiver only transmits senders of its own base id range
        self.assertEqual(suggestion['sender_id'], 'FF-C0-03-81')
        self.assertTrue(suggestion['sender_id'].startswith('FF-C0-03-'))

    def test_addresses_are_handed_out_without_gaps_and_without_collisions(self):
        model = sim.SimulationModel()
        gateway = model.add_gateway(1, 'fam14')
        for _ in range(3):
            gateway.add(gateway.suggest_device('sensor', 'A5-04-02'))

        self.assertEqual([device.address for device in gateway.devices],
                         ['00-00-00-01', '00-00-00-02', '00-00-00-03'])

    def test_a_removed_address_is_used_again(self):
        model = sim.SimulationModel()
        gateway = model.add_gateway(1, 'fam14')
        for _ in range(3):
            gateway.add(gateway.suggest_device('sensor', 'A5-04-02'))
        gateway.remove('00-00-00-02')

        self.assertEqual(gateway.suggest_device('sensor', 'A5-04-02')['address'], '00-00-00-02')

    def test_a_malformed_address_is_rejected(self):
        with self.assertRaises(sim.SimulationError):
            sim.normalize_address('nonsense')

    def test_a_chosen_address_of_a_transceiver_stays_inside_its_base_id_range(self):
        """The ESP3 chip of a real transceiver only transmits base id .. base id + 127."""
        self.assertEqual(sim.validate_hosted_address('FF-80-14-00', 'ff-80-14-7f'), 'FF-80-14-7F')
        self.assertEqual(sim.validate_hosted_address('FF-80-14-00', 'FF-80-14-00'), 'FF-80-14-00')

        for outside in ('FF-80-14-80', 'FF-80-13-FF', 'AA-BB-CC-DD'):
            with self.assertRaises(sim.SimulationError) as context:
                sim.validate_hosted_address('FF-80-14-00', outside)
            # the valid range is in the message - the base id cannot be read off the housing
            self.assertIn('FF-80-14-00 to FF-80-14-7F', str(context.exception))

    def test_the_range_follows_the_base_id_instead_of_assuming_a_round_one(self):
        self.assertEqual(sim.validate_hosted_address('FF-80-14-40', 'FF-80-14-BF'), 'FF-80-14-BF')
        with self.assertRaises(sim.SimulationError):
            sim.validate_hosted_address('FF-80-14-40', 'FF-80-14-C0')
        with self.assertRaises(sim.SimulationError):
            sim.validate_hosted_address('FF-80-14-40', 'FF-80-14-3F')

    def test_a_bus_gateway_addresses_freely(self):
        self.assertEqual(sim.validate_hosted_address('FF-AA-80-00', '00-00-00-05', bus=True),
                         '00-00-00-05')
        with self.assertRaises(sim.SimulationError):
            sim.validate_hosted_address('FF-AA-80-00', 'nonsense', bus=True)

    def test_the_serial_path_is_recognizable(self):
        self.assertEqual(sim.serial_path(4), 'simulator-4')
        self.assertTrue(sim.is_simulator_serial_path('simulator-4'))
        self.assertFalse(sim.is_simulator_serial_path('/dev/ttyUSB0'))


class TestDevices(TestCase):

    def test_a_sensor_needs_no_sender(self):
        device = sim.SimulatedDevice.create(address='FF-C0-02-05', platform='sensor',
                                            eep='A5-04-02')
        self.assertFalse(device.is_actuator)
        self.assertIsNone(device.sender_id)
        # the state starts with plausible values instead of zeros
        self.assertEqual(device.state['temperature'], 21)
        self.assertEqual(device.state['learn_button'], 1)

    def test_an_actuator_without_sender_is_rejected(self):
        with self.assertRaises(sim.SimulationError) as context:
            sim.SimulatedDevice.create(address='FF-C0-02-01', platform='light', eep='M5-38-08')
        self.assertIn('sender', str(context.exception))

    def test_an_unknown_eep_is_rejected(self):
        with self.assertRaises(sim.SimulationError):
            sim.SimulatedDevice.create(address='FF-C0-02-05', platform='sensor', eep='A5-99-99')

    def test_an_unknown_platform_is_rejected(self):
        with self.assertRaises(sim.SimulationError):
            sim.SimulatedDevice.create(address='FF-C0-02-05', platform='vacuum', eep='A5-04-02')

    def test_two_devices_cannot_share_an_address(self):
        model = sim.SimulationModel()
        gateway = model.add_gateway(1, 'fam14')
        gateway.add(gateway.suggest_device('sensor', 'A5-04-02'))
        with self.assertRaises(sim.SimulationError):
            gateway.add({'address': '00-00-00-01', 'platform': 'sensor', 'eep': 'A5-04-02'})

    def test_two_actuators_cannot_share_a_sender(self):
        model = sim.SimulationModel()
        gateway = model.add_gateway(1, 'fam14')
        gateway.add(gateway.suggest_device('light', 'M5-38-08', 'A5-38-08'))
        with self.assertRaises(sim.SimulationError) as context:
            gateway.add({'address': '00-00-00-09', 'platform': 'light', 'eep': 'M5-38-08',
                         'sender_id': '00-00-B0-01', 'sender_eep': 'A5-38-08'})
        self.assertIn('already used', str(context.exception))

    def test_changing_the_eep_starts_with_the_values_of_the_new_profile(self):
        model = sim.SimulationModel()
        gateway = model.add_gateway(1, 'fam14')
        gateway.add(gateway.suggest_device('sensor', 'A5-04-02'))
        gateway.update('00-00-00-01', {'state': {'temperature': 25}})
        self.assertEqual(gateway.find('00-00-00-01').state['temperature'], 25)

        updated = gateway.update('00-00-00-01', {'eep': 'A5-06-01'})

        self.assertEqual(updated.eep, 'A5-06-01')
        self.assertNotIn('temperature', updated.state)
        self.assertIn('illumination', updated.state)


class TestTelegrams(TestCase):

    def _device(self, eep, platform='sensor', sender_eep=None, **values):
        sender = {'sender_id': 'FF-C0-02-85', 'sender_eep': sender_eep or eep} \
            if platform in sim.ACTUATOR_PLATFORMS else {}
        device = sim.SimulatedDevice.create(address='FF-C0-02-05', platform=platform, eep=eep,
                                            **sender)
        if values:
            device.apply_state(values)
        return device

    def test_a_simulated_telegram_looks_like_a_received_one(self):
        """A real gateway reads incoming telegrams - not outgoing ones (h_seq 0 vs 3)."""
        device = self._device('A5-04-02', temperature=21.5, humidity=45)

        telegram = device.state_telegram()

        self.assertIsInstance(telegram, Regular4BSMessage)
        self.assertFalse(telegram.outgoing)
        self.assertEqual(telegram.body[0], 11)
        self.assertEqual(telegram.address, b'\xff\xc0\x02\x05')

    def test_the_values_survive_the_encoding(self):
        device = self._device('A5-04-02', temperature=21.5, humidity=45)

        decoded = EEP.find('A5-04-02').decode_message(device.state_telegram())

        self.assertAlmostEqual(decoded.current_temperature, 21.5, delta=0.3)
        self.assertAlmostEqual(decoded.humidity, 45, delta=1)

    def test_a_rocker_telegram_carries_the_pressed_button(self):
        device = self._device('F6-02-01', platform='binary_sensor',
                              rocker_first_action=3, energy_bow=1)

        telegram = device.state_telegram()

        self.assertIsInstance(telegram, RPSMessage)
        decoded = EEP.find('F6-02-01').decode_message(telegram)
        self.assertEqual(decoded.rocker_first_action, 3)
        self.assertEqual(decoded.energy_bow, 1)

    def test_a_teach_in_telegram_is_a_received_one_too(self):
        """See TestTeachIn for what each profile family announces."""
        device = self._device('A5-04-02')

        telegram = prettify(device.teach_in_telegrams()[0])

        self.assertEqual(telegram.profile, (0xA5, 0x04, 0x02))
        self.assertFalse(telegram.outgoing)

    def test_a_climate_telegram_needs_the_enums_of_its_eep(self):
        """A5-10-06 takes enums (mode/priority) - a plain number must still work."""
        device = self._device('A5-10-06', platform='climate')
        device.apply_state({'mode': 0x70, 'target_temp': 21, 'current_temp': 20, 'priority': 0x0F})

        decoded = EEP.find('A5-10-06').decode_message(device.state_telegram())

        self.assertAlmostEqual(decoded.target_temperature, 21, delta=0.3)
        self.assertAlmostEqual(decoded.current_temperature, 20, delta=0.3)

    def test_the_internal_state_is_not_encoded(self):
        """'_on' remembers whether an actuator is on - it is no telegram field."""
        device = self._device('M5-38-08', platform='light', sender_eep='A5-38-08')
        device.apply_state({'state': 1, '_on': True})

        self.assertEqual(device.public_state(), {'state': 1})
        self.assertIsNotNone(device.state_telegram())


class TestTeachIn(TestCase):
    """Every device shall be able to announce its profile - as far as its family can."""

    def _device(self, eep, platform='sensor'):
        sender = {'sender_id': 'FF-C0-02-85', 'sender_eep': eep} \
            if platform in sim.ACTUATOR_PLATFORMS else {}
        return sim.SimulatedDevice.create(address='FF-C0-02-05', platform=platform, eep=eep,
                                          **sender)

    def test_a_4bs_profile_is_named_in_the_telegram(self):
        device = self._device('A5-04-02')

        telegrams = device.teach_in_telegrams()

        self.assertEqual(device.teach_in_kind, '4bs')
        self.assertEqual(len(telegrams), 1)
        self.assertEqual(prettify(telegrams[0]).profile, (0xA5, 0x04, 0x02))

    def test_a_1bs_profile_sends_a_learn_telegram(self):
        device = self._device('D5-00-01', platform='binary_sensor')

        telegrams = device.teach_in_telegrams()

        self.assertEqual(device.teach_in_kind, '1bs')
        self.assertEqual(len(telegrams), 1)
        body = telegrams[0].body
        self.assertEqual(body[1], 0x06)             # 1BS
        self.assertEqual(body[2] & 0x08, 0)         # LRN bit cleared = teach-in
        self.assertEqual(body[6:10], b'\xff\xc0\x02\x05')

    def test_rps_sends_a_press_and_its_release(self):
        """RPS has no teach-in telegram at all - a receiver learns from a button press."""
        device = self._device('F6-02-01', platform='binary_sensor')

        telegrams = device.teach_in_telegrams()

        self.assertEqual(device.teach_in_kind, 'rps')
        self.assertEqual(len(telegrams), 2)
        first = EEP.find('F6-02-01').decode_message(telegrams[0])
        second = EEP.find('F6-02-01').decode_message(telegrams[1])
        self.assertEqual(first.energy_bow, 1)       # pressed
        self.assertEqual(second.energy_bow, 0)      # released

    def test_the_eltako_status_profiles_count_as_rps(self):
        """M5-38-08 and G5-3F-7F are Eltako's names for RPS status telegrams."""
        self.assertEqual(sim.teach_in_kind('M5-38-08'), 'rps')
        self.assertEqual(sim.teach_in_kind('G5-3F-7F'), 'rps')

    def test_every_device_of_the_starter_set_can_announce_itself(self):
        model = sim.SimulationModel()
        gateway = model.add_gateway(1, 'fam14')

        for device in sim.add_preset_devices(gateway):
            self.assertTrue(device.has_teach_in,
                            msg=f"{device.name} ({device.eep}) cannot announce itself")
            telegrams = device.teach_in_telegrams()
            self.assertTrue(telegrams)
            self.assertTrue(device.teach_in_description)

    def test_the_eltako_teach_in_is_a_different_telegram(self):
        """Two telegrams are called teach-in and they run in opposite directions.

        The profile teach-in announces what a sensor is; the Eltako one is what a sender sends so
        that an actuator takes it into its memory (its payload comes from catalog/teach_in.py).
        """
        device = self._device('A5-38-08', platform='light')

        profile = device.teach_in_telegrams()[0]
        eltako = sim.encode_eltako_teach_in_telegram('00-00-B0-01', b'\xE0\x40\x0D\x80')

        self.assertNotEqual(profile.serialize(), eltako.serialize())
        # the Eltako one carries the payload of the sender profile and comes from the sender
        self.assertEqual(eltako.body[2:6], b'\xE0\x40\x0D\x80')
        self.assertEqual(eltako.body[6:10], b'\x00\x00\xb0\x01')
        self.assertFalse(eltako.outgoing)       # it is received, like every simulated telegram

    def test_an_eltako_teach_in_needs_four_data_bytes(self):
        with self.assertRaises(sim.SimulationError):
            sim.encode_eltako_teach_in_telegram('00-00-B0-01', b'\x01\x02')

    def test_the_description_says_what_is_sent(self):
        self.assertIn('4BS', sim.teach_in_description('A5-04-02'))
        self.assertIn('no teach-in telegram', sim.teach_in_description('F6-02-01'))

    def test_an_unknown_family_cannot_announce_itself(self):
        self.assertIsNone(sim.teach_in_kind('B0-00-00'))
        self.assertFalse(sim.has_teach_in_telegram('B0-00-00'))


class TestRepeating(TestCase):
    """A device can repeat its telegram like a real sensor which reports every few minutes."""

    def _sensor(self, **values):
        return sim.SimulatedDevice.create(address='FF-C0-02-05', platform='sensor',
                                          eep='A5-04-02', **values)

    def test_a_device_does_not_repeat_by_default(self):
        device = self._sensor()

        self.assertEqual(device.interval, 0)
        self.assertFalse(device.is_repeating)
        self.assertFalse(device.describe()['repeating'])

    def test_an_interval_makes_it_repeat(self):
        device = self._sensor(interval=30)

        self.assertEqual(device.interval, 30)
        self.assertTrue(device.is_repeating)

    def test_the_interval_is_kept_when_it_is_switched_off(self):
        """Zero means 'not now' - the number stays in the ui so it can be started again."""
        model = sim.SimulationModel()
        gateway = model.add_gateway(1, 'fam14')
        gateway.add(gateway.suggest_device('sensor', 'A5-04-02'))
        gateway.update('00-00-00-01', {'interval': 60})
        self.assertTrue(gateway.find('00-00-00-01').is_repeating)

        updated = gateway.update('00-00-00-01', {'interval': 0})

        self.assertEqual(updated.interval, 0)
        self.assertFalse(updated.is_repeating)

    def test_it_survives_being_stored(self):
        model = sim.SimulationModel()
        gateway = model.add_gateway(1, 'fam14')
        gateway.add(gateway.suggest_device('sensor', 'A5-04-02'))
        gateway.update('00-00-00-01', {'interval': 15})

        restored = sim.SimulationModel.from_dict(model.to_dict())

        self.assertEqual(restored.find(1, '00-00-00-01').interval, 15)

    def test_a_nonsense_interval_is_rejected(self):
        for value in (-1, 'soon', 999999):
            with self.assertRaises(sim.SimulationError, msg=value):
                self._sensor(interval=value)

    def test_a_number_as_text_is_accepted(self):
        """The web ui sends what was typed into the input."""
        self.assertEqual(self._sensor(interval='30').interval, 30)
        self.assertEqual(self._sensor(interval='').interval, 0)


class TestActuators(TestCase):
    """A command of Home Assistant has to switch the simulated actuator."""

    def _actuator(self, eep, sender_eep, platform='light'):
        return sim.SimulatedDevice.create(address='00-00-00-01', platform=platform, eep=eep,
                                          sender_id='00-00-B0-01', sender_eep=sender_eep)

    def _command(self, sender_eep, **fields):
        return sim.as_incoming(sim.encode_eep_telegram('00-00-B0-01', sender_eep, fields))

    def test_a_relay_reports_on_and_off(self):
        device = self._actuator('M5-38-08', 'A5-38-08')

        telegram, state = sim.answer_command(
            device, self._command('A5-38-08', command=1, switching_command=1, learn_button=1))
        self.assertEqual(state['state'], 1)
        self.assertEqual(EEP.find('M5-38-08').decode_message(telegram).state, 1)

        device.apply_state(state)
        telegram, state = sim.answer_command(
            device, self._command('A5-38-08', command=1, switching_command=0, learn_button=1))
        self.assertEqual(state['state'], 0)
        self.assertEqual(EEP.find('M5-38-08').decode_message(telegram).state, 0)

    def test_a_rocker_sender_switches_a_relay(self):
        device = self._actuator('M5-38-08', 'F6-02-01')

        # top (action 1) switches on, bottom (0) off - see switch.py of the integration
        _telegram, state = sim.answer_command(
            device, self._command('F6-02-01', rocker_first_action=1, energy_bow=1))
        self.assertEqual(state['state'], 1)

        _telegram, state = sim.answer_command(
            device, self._command('F6-02-01', rocker_first_action=0, energy_bow=1))
        self.assertEqual(state['state'], 0)

    def test_the_release_of_a_rocker_is_no_command(self):
        device = self._actuator('M5-38-08', 'F6-02-01')

        self.assertIsNone(sim.answer_command(
            device, self._command('F6-02-01', rocker_first_action=1, energy_bow=0)))

    def test_a_dimmer_reports_its_brightness(self):
        device = self._actuator('A5-38-08', 'A5-38-08')

        telegram, state = sim.answer_command(
            device, self._command('A5-38-08', command=2, dimming_value=40, dimming_range=0,
                                  switching_command=1, learn_button=1))

        self.assertEqual(state['dimming_value'], 40)
        decoded = EEP.find('A5-38-08').decode_message(telegram)
        self.assertEqual(decoded.command, 2)
        self.assertEqual(decoded.dimming.dimming_value, 40)
        # light.py only takes a telegram with the learn button bit set
        self.assertEqual(decoded.dimming.learn_button, 1)

    def test_a_cover_reports_the_end_position(self):
        device = self._actuator('G5-3F-7F', 'H5-3F-7F', platform='cover')

        # cover.py always sends with the learn button bit set - so does a real remote
        _telegram, state = sim.answer_command(
            device, self._command('H5-3F-7F', command=1, learn_button=1))
        self.assertEqual(state['state'], 0x70)          # completely open

        device.apply_state(state)
        _telegram, state = sim.answer_command(
            device, self._command('H5-3F-7F', command=2, learn_button=1))
        self.assertEqual(state['state'], 0x50)          # completely closed

        # a stop command has no end position to report
        device.apply_state(state)
        self.assertIsNone(sim.answer_command(
            device, self._command('H5-3F-7F', command=0, learn_button=1)))

    def test_a_heating_actuator_acknowledges_the_target_temperature(self):
        device = self._actuator('A5-10-06', 'A5-10-06', platform='climate')

        telegram, state = sim.answer_command(
            device, self._command('A5-10-06', mode=0x70, target_temp=22, current_temp=20,
                                  priority=0x08))

        self.assertAlmostEqual(state['target_temp'], 22, delta=0.3)
        decoded = EEP.find('A5-10-06').decode_message(telegram)
        self.assertAlmostEqual(decoded.target_temperature, 22, delta=0.3)

    def test_a_command_for_another_device_is_ignored(self):
        self._actuator('M5-38-08', 'A5-38-08')    # registers the device on the bus
        foreign = sim.as_incoming(sim.encode_eep_telegram('00-00-B0-09', 'A5-38-08',
                                                          {'command': 1, 'switching_command': 1}))
        # the gateway looks the device up by the sender address, so this never reaches it -
        # but even if it does, the answer is the state of THIS device, never a crash
        self.assertIsNotNone(sim.sender_of(foreign))
        self.assertNotEqual(sim.sender_of(foreign), b'\x00\x00\xb0\x01')

    def test_a_sensor_answers_nothing(self):
        sensor = sim.SimulatedDevice.create(address='FF-C0-02-05', platform='sensor',
                                            eep='A5-04-02')
        self.assertIsNone(sim.answer_command(sensor, self._command('A5-38-08', command=1)))

    def test_every_actuator_of_the_presets_can_be_controlled(self):
        for preset in sim.DEVICE_PRESETS:
            if preset['platform'] not in sim.ACTUATOR_PLATFORMS:
                continue
            self.assertTrue(sim.can_be_controlled(preset['eep']),
                            msg=f"the simulation cannot control {preset['eep']} "
                                f"({preset['key']})")
            self.assertIn(preset['sender_eep'], sim.SENDER_DECODERS,
                          msg=f"no command decoder for the sender EEP {preset['sender_eep']}")


class TestTeachingSendersIn(TestCase):
    """An actuator has a memory: every sender which was taught into it may control it."""

    def _actuator(self):
        return sim.SimulatedDevice.create(address='00-00-00-01', platform='light', eep='M5-38-08',
                                          sender_id='00-00-B0-01', sender_eep='A5-38-08')

    def test_the_sender_of_the_automation_system_is_always_known(self):
        device = self._actuator()

        self.assertEqual([sender['id'] for sender in device.senders], ['00-00-B0-01'])
        self.assertEqual(device.senders[0]['role'], 'ha_sender')
        self.assertTrue(device.knows_sender('00-00-B0-01'))

    def test_a_wall_switch_can_be_taught_in(self):
        device = self._actuator()

        device.teach_in('ff-aa-bb-cc', 'F6-02-01', 'Wall switch in the hall')

        self.assertTrue(device.knows_sender('FF-AA-BB-CC'))
        entry = device.find_sender('FF-AA-BB-CC')
        self.assertEqual(entry['eep'], 'F6-02-01')
        self.assertEqual(entry['name'], 'Wall switch in the hall')
        self.assertEqual(entry['role'], 'taught_in')

    def test_without_a_profile_the_one_of_the_automation_system_is_assumed(self):
        device = self._actuator()

        device.teach_in('FF-AA-BB-CC')

        self.assertEqual(device.find_sender('FF-AA-BB-CC')['eep'], 'A5-38-08')

    def test_teaching_the_same_sender_in_twice_changes_it(self):
        device = self._actuator()
        device.teach_in('FF-AA-BB-CC', 'F6-02-01')

        device.teach_in('FF-AA-BB-CC', 'F6-02-02', 'US rocker')

        self.assertEqual(len(device.taught_in), 1)
        self.assertEqual(device.find_sender('FF-AA-BB-CC')['eep'], 'F6-02-02')

    def test_a_sender_can_be_removed_again(self):
        device = self._actuator()
        device.teach_in('FF-AA-BB-CC', 'F6-02-01')

        self.assertTrue(device.forget_sender('ff-aa-bb-cc'))
        self.assertFalse(device.knows_sender('FF-AA-BB-CC'))
        self.assertFalse(device.forget_sender('FF-AA-BB-CC'))

    def test_a_sensor_has_no_memory(self):
        """Nobody sends to a sensor - teaching something into it would do nothing."""
        sensor = sim.SimulatedDevice.create(address='FF-C0-02-05', platform='sensor',
                                            eep='A5-04-02')

        with self.assertRaises(sim.SimulationError):
            sensor.teach_in('FF-AA-BB-CC')

    def test_the_own_sender_cannot_be_taught_in_again(self):
        device = self._actuator()

        with self.assertRaises(sim.SimulationError):
            device.teach_in('00-00-B0-01')

    def test_an_unknown_profile_is_rejected(self):
        device = self._actuator()

        with self.assertRaises(sim.SimulationError):
            device.teach_in('FF-AA-BB-CC', 'A5-99-99')

    def test_it_survives_being_stored(self):
        device = self._actuator()
        device.teach_in('FF-AA-BB-CC', 'F6-02-01', 'Wall switch')

        restored = sim.SimulatedDevice.from_dict(device.to_dict())

        self.assertEqual(restored.taught_in, device.taught_in)
        self.assertTrue(restored.knows_sender('FF-AA-BB-CC'))

    def test_a_taught_in_switch_really_switches_the_actuator(self):
        """The whole point: the telegram of that switch has to reach the actuator."""
        device = self._actuator()
        device.teach_in('FF-AA-BB-CC', 'F6-02-01', 'Wall switch')
        press = sim.as_incoming(sim.encode_eep_telegram(
            'FF-AA-BB-CC', 'F6-02-01', {'rocker_first_action': 1, 'energy_bow': 1}))

        answer = sim.answer_command(device, press, device.find_sender('FF-AA-BB-CC')['eep'])

        self.assertIsNotNone(answer)
        _telegram, state = answer
        self.assertEqual(state['state'], 1)

    def test_one_switch_can_control_several_actuators(self):
        model = sim.SimulationModel()
        gateway = model.add_gateway(1, 'fam14')
        first = gateway.add(gateway.suggest_device('light', 'M5-38-08', 'A5-38-08'))
        second = gateway.add(gateway.suggest_device('light', 'M5-38-08', 'A5-38-08'))
        third = gateway.add(gateway.suggest_device('light', 'M5-38-08', 'A5-38-08'))
        for device in (first, second):
            device.teach_in('FF-AA-BB-CC', 'F6-02-01')

        controlled = gateway.find_all_by_sender('FF-AA-BB-CC')

        self.assertEqual([device.address for device in controlled],
                         [first.address, second.address])
        self.assertNotIn(third.address, [device.address for device in controlled])

    def test_the_own_sender_still_finds_its_device(self):
        model = sim.SimulationModel()
        gateway = model.add_gateway(1, 'fam14')
        device = gateway.add(gateway.suggest_device('light', 'M5-38-08', 'A5-38-08'))

        self.assertEqual([found.address for found in gateway.find_all_by_sender(device.sender_id)],
                         [device.address])
        self.assertEqual(gateway.find_all_by_sender('00-00-B0-63'), [])


class TestActivating(TestCase):
    """A deactivated simulation exists, but nothing of it runs."""

    def test_it_is_active_by_default(self):
        model = sim.SimulationModel()

        self.assertTrue(model.active)
        self.assertFalse(model.paused)

    def test_the_state_is_stored(self):
        model = sim.SimulationModel()
        sim.add_preset_devices(model.add_gateway(1, 'fam14'))
        model.active = False

        restored = sim.SimulationModel.from_dict(model.to_dict())

        self.assertFalse(restored.active)
        self.assertTrue(restored.paused)
        # deactivating loses nothing - that is the whole point
        self.assertEqual(len(restored.get_devices()), len(sim.DEVICE_PRESETS))

    def test_a_simulation_stored_by_an_older_version_is_active(self):
        """Earlier versions stored 'paused' instead."""
        self.assertTrue(sim.SimulationModel.from_dict({'gateways': []}).active)
        self.assertFalse(sim.SimulationModel.from_dict({'paused': True, 'gateways': []}).active)


class TestPresets(TestCase):

    def test_the_starter_set_covers_the_three_kinds_of_gateway(self):
        types = [preset['device_type'] for preset in sim.GATEWAY_PRESETS]

        self.assertIn('mgw-lan', types)             # LAN gateway
        self.assertIn('enocean-usb300', types)      # USB ESP3 stick
        self.assertIn('fam14', types)               # bus gateway

    def test_the_example_devices_cover_what_an_installation_has(self):
        model = sim.SimulationModel()
        gateway = model.add_gateway(1, 'fam14')

        devices = sim.add_preset_devices(gateway)

        platforms = {device.platform for device in devices}
        self.assertEqual(platforms, {'light', 'cover', 'climate', 'sensor', 'binary_sensor'})
        eeps = {device.eep for device in devices}
        # light, dimmer, cover, heating/cooling
        self.assertLessEqual({'M5-38-08', 'A5-38-08', 'G5-3F-7F', 'A5-10-06'}, eeps)
        # temperature and humidity, motion, 4-way wall switch, window contact
        self.assertLessEqual({'A5-04-02', 'A5-07-01', 'F6-02-01', 'F6-10-00'}, eeps)

    def test_a_bus_preset_uses_the_bus_device_of_the_catalog(self):
        model = sim.SimulationModel()
        bus = sim.add_preset_devices(model.add_gateway(1, 'fam14'))
        radio = sim.add_preset_devices(model.add_gateway(2, 'enocean-usb300'))

        light_on_bus = next(device for device in bus if device.eep == 'M5-38-08')
        light_wireless = next(device for device in radio if device.eep == 'M5-38-08')

        self.assertEqual(light_on_bus.hw_type, 'FSR14_4x')       # series 14, on the bus
        self.assertEqual(light_wireless.hw_type, 'FSR61NP-230V')  # decentralized

    def test_every_preset_device_sends_a_telegram_its_entity_can_read(self):
        """A default of 0 is not a valid state for every profile.

        A window handle encodes its position in the upper nibble of `movement` and nothing else
        can be decoded at all; the central command has to say whether it switches or dims. A
        freshly created device must not send a telegram which the entity has to discard.
        """
        model = sim.SimulationModel()
        gateway = model.add_gateway(1, 'fam14')

        for device in sim.add_preset_devices(gateway):
            telegram = device.state_telegram()
            try:
                decoded = EEP.find(device.eep).decode_message(telegram)
            except Exception as e:      # noqa: BLE001 - that is what is being tested
                self.fail(f"the telegram of the preset '{device.name}' ({device.eep}) cannot be "
                          f"decoded: {type(e).__name__}: {e}")
            self.assertIsNotNone(decoded)

    def test_the_window_contact_starts_closed(self):
        model = sim.SimulationModel()
        gateway = model.add_gateway(1, 'enocean-usb300')
        device = gateway.add(gateway.suggest_device('binary_sensor', 'F6-10-00'))

        decoded = EEP.find('F6-10-00').decode_message(device.state_telegram())

        # 0xF0 = closed, 0xC0/0xE0 = open, 0xD0 = tilted
        self.assertEqual(device.state['movement'], 0xF0)
        self.assertEqual(int(decoded.handle_position), 0)

    def test_every_preset_device_is_valid(self):
        model = sim.SimulationModel()
        for preset in sim.GATEWAY_PRESETS:
            gateway = model.add_gateway(sim.GATEWAY_PRESETS.index(preset) + 1,
                                        preset['device_type'])
            for device in sim.add_preset_devices(gateway):
                self.assertTrue(device.address)
                self.assertTrue(device.eep)
                self.assertIsNotNone(device.state_telegram())
                if device.is_actuator:
                    self.assertTrue(device.sender_id)
                    self.assertTrue(device.sender_eep)

    def test_an_unknown_preset_is_rejected(self):
        with self.assertRaises(sim.SimulationError):
            sim.find_gateway_preset('nonsense')


class TestModel(TestCase):

    def _model(self) -> sim.SimulationModel:
        model = sim.SimulationModel()
        sim.add_preset_devices(model.add_gateway(1, 'fam14', 'Simulated FAM14'))
        sim.add_preset_devices(model.add_gateway(2, 'mgw-lan'))
        return model

    def test_it_survives_being_stored_and_read_back(self):
        model = self._model()

        restored = sim.SimulationModel.from_dict(model.to_dict())

        self.assertEqual(restored.get_gateway_ids(), [1, 2])
        self.assertEqual(len(restored.get_devices()), len(model.get_devices()))
        original = model.find(1, '00-00-00-01')
        copy = restored.find(1, '00-00-00-01')
        self.assertEqual(copy.eep, original.eep)
        self.assertEqual(copy.sender_id, original.sender_id)
        self.assertEqual(copy.state, original.state)

    def test_a_broken_stored_device_is_skipped_instead_of_breaking_everything(self):
        data = self._model().to_dict()
        data['gateways'][0]['devices'].append({'address': 'nonsense', 'platform': 'sensor',
                                              'eep': 'A5-04-02'})
        problems = []

        restored = sim.SimulationModel.from_dict(data, on_error=problems.append)

        self.assertEqual(len(problems), 1)
        self.assertEqual(len(restored.get_devices()), 16)

    def test_an_actuator_is_found_by_its_sender_address(self):
        model = self._model()

        device = model.find_by_sender(1, b'\x00\x00\xb0\x01')

        self.assertIsNotNone(device)
        self.assertEqual(device.address, '00-00-00-01')
        self.assertIsNone(model.find_by_sender(1, b'\x00\x00\xb0\x63'))

    def test_removing_a_gateway_takes_its_devices_with_it(self):
        model = self._model()

        removed = model.remove_gateway(1)

        self.assertEqual(removed, 8)
        self.assertIsNone(model.get_gateway(1))
        self.assertEqual(len(model.get_devices()), 8)

    def test_a_device_of_an_unknown_gateway_is_rejected(self):
        with self.assertRaises(sim.SimulationError):
            sim.SimulationModel().add_device(9, {'address': '00-00-00-01', 'platform': 'sensor',
                                                 'eep': 'A5-04-02'})

    def test_the_description_carries_what_a_ui_needs(self):
        model = self._model()

        description = model.find(1, '00-00-00-05').describe()

        self.assertIn('temperature', description['fields'])
        self.assertFalse(description['actuator'])
        self.assertTrue(description['teach_in'])


if __name__ == '__main__':
    unittest.main()
