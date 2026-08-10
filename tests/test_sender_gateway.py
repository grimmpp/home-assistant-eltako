"""Which gateway switches an actuator - the address in the device and the sender in HA.

An RS485 actuator only reacts to the sender addresses in its own memory, and a transceiver
only transmits senders out of its own base id range. Picking a gateway for a device therefore
has to do both things or neither: write `base id + last byte of the actuator address` into the
actuator **and** store the same address as the sender of that device in Home Assistant. A
configured sender which is in no memory is a device which looks fine and does nothing.

That is what these tests pin: which address is picked, whose sender it is, that a device out
of `configuration.yaml` is left alone, and that an actuator which refused the write keeps its
old sender instead of being switched over on paper.
"""
from unittest import IsolatedAsyncioTestCase, TestCase, mock

from custom_components.eltako.config import sender_gateway
from custom_components.eltako.const import (CONF_DEVICE_TYPE, CONF_EEP, CONF_GATEWAY,
                                            CONF_GATEWAY_DESCRIPTION, CONF_SENDER, CONF_UI_DEVICES,
                                            DATA_ELTAKO, ELTAKO_CONFIG, GatewayDeviceType)

from homeassistant.const import CONF_DEVICES, CONF_ID, CONF_NAME

from eltakobus.util import AddressExpression


class GatewayStub:
    def __init__(self, dev_id, dev_type, name, base_id=None):
        self.dev_id = dev_id
        self.dev_type = dev_type
        self.dev_name = name
        self.base_id = AddressExpression.parse(base_id) if base_id else None
        self.is_bus_busy = False
        self.bus_busy_reason = None
        self.sent = []

    def send_message(self, telegram):
        self.sent.append(telegram)


def fam14(dev_id=1, base_id='FF-AA-80-00'):
    return GatewayStub(dev_id, GatewayDeviceType.GatewayEltakoFAM14, 'FAM14', base_id)


def fam_usb(dev_id=2, base_id='FF-C0-02-00'):
    return GatewayStub(dev_id, GatewayDeviceType.GatewayEltakoFAMUSB, 'FAM-USB', base_id)


def fgw14usb(dev_id=3):
    return GatewayStub(dev_id, GatewayDeviceType.GatewayEltakoFGW14USB, 'FGW14-USB')


class ConfigEntryWithOptions:
    def __init__(self, gateway_id=1, description='FAM14 - fam14 (Id: 1)'):
        self.options = {}
        self.entry_id = f'entry-{gateway_id}'
        self.title = description
        self.data = {CONF_GATEWAY_DESCRIPTION: description}


class HassStub:
    """Just enough hass: the yaml configuration, one config entry and its options."""

    def __init__(self, entries, yaml_devices=None, gateway_id=1):
        self.data = {DATA_ELTAKO: {ELTAKO_CONFIG: {CONF_GATEWAY: [{
            CONF_ID: gateway_id, CONF_DEVICE_TYPE: 'fam14', CONF_NAME: 'FAM14',
            CONF_DEVICES: yaml_devices or {}}]}}}
        self.config_entries = self
        self.entries = entries

    def async_update_entry(self, entry, options=None, **kwargs):
        entry.options = options

    def async_entries(self, domain=None):
        return list(self.entries)


LIGHT = {CONF_ID: '00-00-00-04', CONF_EEP: 'M5-38-08', CONF_NAME: 'Kitchen',
         CONF_SENDER: {CONF_ID: '00-00-B0-04', CONF_EEP: 'A5-38-08'}}


class TestWhichAddressIsPicked(TestCase):

    def test_a_wireless_gateway_hands_out_an_address_of_its_base_id(self):
        self.assertEqual('FF-C0-02-04', sender_gateway.sender_id_for(fam_usb(), '00-00-00-04'))

    def test_the_bus_itself_keeps_the_local_senders(self):
        """The FAM14 default: 00-00-B0-xx, what the detection and the yaml import hand out."""
        self.assertEqual('00-00-B0-04', sender_gateway.sender_id_for(fam14(), '00-00-00-04'))

    def test_a_wireless_device_has_no_address_on_the_bus(self):
        self.assertIsNone(sender_gateway.sender_id_for(fam_usb(), 'FE-DC-BA-98'))

    def test_only_a_fam14_can_write_into_an_actuator(self):
        self.assertTrue(sender_gateway.can_program(fam14()))
        self.assertFalse(sender_gateway.can_program(fgw14usb()))
        self.assertFalse(sender_gateway.can_program(fam_usb()))

    def test_a_wireless_actuator_keeps_the_offset_of_its_old_gateway(self):
        gateways = [fam14(), fam_usb()]

        self.assertEqual('FF-C0-02-05', sender_gateway.radio_sender_id_for(
            fam_usb(), gateways, 'FF-AA-80-05'))

    def test_an_address_which_is_taken_moves_to_the_first_free_one(self):
        """Two devices with the same sender would switch each other."""
        gateways = [fam14(), fam_usb()]
        taken = {int.from_bytes(AddressExpression.parse('FF-C0-02-05')[0], 'big')}

        self.assertEqual('FF-C0-02-01', sender_gateway.radio_sender_id_for(
            fam_usb(), gateways, 'FF-AA-80-05', taken))

    def test_a_gateway_which_never_reported_a_base_id_has_nothing_to_hand_out(self):
        never_connected = GatewayStub(9, GatewayDeviceType.GatewayEltakoFAMUSB, 'FAM-USB')

        self.assertIsNone(sender_gateway.radio_sender_id_for(
            never_connected, [fam14()], 'FF-AA-80-05'))

    def test_a_sender_names_the_gateway_it_belongs_to(self):
        gateways = [fam14(), fam_usb()]

        self.assertEqual(1, sender_gateway.gateway_of_sender(gateways, 1, '00-00-B0-04').dev_id)
        self.assertEqual(2, sender_gateway.gateway_of_sender(gateways, 1, 'FF-C0-02-04').dev_id)
        # an address which belongs to no configured gateway: imported, or a gateway which is gone
        self.assertIsNone(sender_gateway.gateway_of_sender(gateways, 1, 'FE-DC-BA-98'))


class TestTheDevicesWhichAreSwitchedOver(IsolatedAsyncioTestCase):

    def setUp(self):
        self.entry = ConfigEntryWithOptions()
        self.entry.options = {CONF_UI_DEVICES: {'light': [dict(LIGHT)]}}
        self.hass = HassStub([self.entry])

    def _stored_sender(self, address='00-00-00-04'):
        for device in (self.entry.options.get(CONF_UI_DEVICES) or {}).get('light', []):
            if device[CONF_ID] == address:
                return device.get(CONF_SENDER) or {}
        return {}

    async def _assign(self, target, results=None, **kwargs):
        """Run the assignment with the bus write faked - the bus itself is not the subject."""
        written = results if results is not None else 'written'

        async def write(hass, gateway, jobs, reason):
            return [{**job, 'result': written if isinstance(written, str)
                     else written.get(job['address'], 'written')} for job in jobs]

        with mock.patch('custom_components.eltako.observation.bus_members'
                        '._async_write_teach_in_jobs', side_effect=write) as writer:
            answer = await sender_gateway.async_assign_sender_gateway(
                self.hass, fam14(), target, **kwargs)
        return answer, writer

    async def test_the_actuator_is_written_and_the_device_sends_with_it(self):
        answer, writer = await self._assign(fam_usb())

        jobs = writer.call_args[0][2]
        self.assertEqual([('00-00-00-04', 'FF-C0-02-04')],
                         [(job['address'], job['sender_id']) for job in jobs])
        self.assertEqual('FF-C0-02-04', self._stored_sender()[CONF_ID])
        self.assertEqual('A5-38-08', self._stored_sender()[CONF_EEP])
        self.assertEqual(['00-00-00-04'], [entry['address'] for entry in answer['updated']])
        self.assertEqual('00-00-B0-04', answer['updated'][0]['previous_sender_id'])

    async def test_back_to_the_bus_gives_the_local_sender_again(self):
        await self._assign(fam_usb())

        await self._assign(fam14())

        self.assertEqual('00-00-B0-04', self._stored_sender()[CONF_ID])

    async def test_an_actuator_which_refused_the_write_keeps_its_sender(self):
        """Otherwise Home Assistant would send an address which is in no memory - a device
        which is configured, listed and dead."""
        answer, _writer = await self._assign(fam_usb(), results={'00-00-00-04': 'error'})

        self.assertEqual('00-00-B0-04', self._stored_sender()[CONF_ID])
        self.assertEqual([], answer['updated'])

    async def test_a_device_of_the_yaml_is_left_alone(self):
        self.hass = HassStub([self.entry], yaml_devices={'light': [
            {CONF_ID: '00-00-00-05', CONF_EEP: 'M5-38-08', CONF_NAME: 'Hall',
             CONF_SENDER: {CONF_ID: '00-00-B0-05', CONF_EEP: 'A5-38-08'}}]})

        answer, writer = await self._assign(fam_usb())

        jobs = writer.call_args[0][2]
        self.assertEqual(['00-00-00-04'], [job['address'] for job in jobs])
        self.assertEqual([('00-00-00-05', 'yaml')],
                         [(entry['address'], entry['result']) for entry in answer['skipped']])

    async def test_one_device_can_be_switched_over_alone(self):
        self.entry.options = {CONF_UI_DEVICES: {'light': [
            dict(LIGHT), {CONF_ID: '00-00-00-06', CONF_EEP: 'M5-38-08', CONF_NAME: 'Hall',
                          CONF_SENDER: {CONF_ID: '00-00-B0-06', CONF_EEP: 'A5-38-08'}}]}}

        _answer, writer = await self._assign(fam_usb(), address='00-00-00-04')

        self.assertEqual(['00-00-00-04'], [job['address'] for job in writer.call_args[0][2]])
        self.assertEqual('00-00-B0-06', self._stored_sender('00-00-00-06')[CONF_ID])

    async def test_without_a_fam14_nothing_is_written_and_nothing_is_stored(self):
        """An FGW14-USB is on the same bus but can neither read nor program a device - and an
        address which is in no actuator must not become the sender of anything."""
        answer = await sender_gateway.async_assign_sender_gateway(
            self.hass, fgw14usb(dev_id=1), fam_usb())

        self.assertEqual('no_fam14', answer['error'])
        self.assertEqual('00-00-B0-04', self._stored_sender()[CONF_ID])

    async def test_a_busy_bus_changes_nothing(self):
        gateway = fam14()
        gateway.is_bus_busy = True
        gateway.bus_busy_reason = 'bus scan'

        answer = await sender_gateway.async_assign_sender_gateway(self.hass, gateway, fam_usb())

        self.assertEqual('bus_busy', answer['error'])
        self.assertEqual('00-00-B0-04', self._stored_sender()[CONF_ID])

    async def test_without_a_base_id_the_device_is_reported_not_rewritten(self):
        """A gateway which never reported a base id has no addresses to hand out."""
        answer, _writer = await self._assign(GatewayStub(9, GatewayDeviceType.GatewayEltakoFAMUSB,
                                                         'FAM-USB (never connected)'))

        self.assertEqual([('00-00-00-04', 'out_of_range')],
                         [(entry['address'], entry['result']) for entry in answer['skipped']])
        self.assertEqual('00-00-B0-04', self._stored_sender()[CONF_ID])

    async def test_a_wireless_actuator_keeps_its_place_in_the_new_range(self):
        """It has no bus position to derive an address from, so the offset inside the range of
        its old gateway is what carries over: FF-AA-80-05 -> FF-C0-02-05."""
        radio = {CONF_ID: 'FE-DC-BA-98', CONF_EEP: 'A5-38-08', CONF_NAME: 'Radio dimmer',
                 CONF_SENDER: {CONF_ID: 'FF-AA-80-05', CONF_EEP: 'A5-38-08'}}
        self.entry.options = {CONF_UI_DEVICES: {'light': [radio]}}
        target = fam_usb()

        with mock.patch('custom_components.eltako.core.websocket.get_gateways',
                        return_value=[fam14(), target]):
            answer = await sender_gateway.async_assign_radio_sender(
                self.hass, target, 'FE-DC-BA-98', gateway_id=1)

        stored = self.entry.options[CONF_UI_DEVICES]['light'][0][CONF_SENDER]
        self.assertEqual('FF-C0-02-05', stored[CONF_ID])
        self.assertEqual('telegram', answer['kind'])
        self.assertEqual('written', answer['results'][0]['result'])
        # the telegram goes out through the gateway which owns that address - nobody else
        # may transmit it
        self.assertEqual(1, len(target.sent))
        self.assertIn('FF-C0-02-05'.replace('-', ''), str(target.sent[0]).replace('-', '').upper())

    async def test_storing_without_programming_is_possible(self):
        """For an installation whose FAM14 is not plugged in right now - the addresses are
        stored, the memories are written by the teach-in button later."""
        answer = await sender_gateway.async_assign_sender_gateway(
            self.hass, fam14(), fam_usb(), program=False)

        self.assertEqual('FF-C0-02-04', self._stored_sender()[CONF_ID])
        self.assertEqual(['not_programmed'], [entry['result'] for entry in answer['results']])


class TestOnlyWhatIsMissingIsWritten(IsolatedAsyncioTestCase):
    """An address which is already in the memory of its actuator is not written again.

    That is what makes the choice of a gateway usable in both directions. Going back to the bus
    hands out the local senders `00-00-B0-xx` - the ones the search wrote into the actuators in
    the first place - so there is nothing left to write, and demanding a connected FAM14 for a
    change which only rewrites the Home Assistant configuration would be a dead end.
    """

    SECOND = {CONF_ID: '00-00-00-05', CONF_EEP: 'M5-38-08', CONF_NAME: 'Hall',
              CONF_SENDER: {CONF_ID: '00-00-B0-05', CONF_EEP: 'A5-38-08'}}

    def setUp(self):
        self.entry = ConfigEntryWithOptions()
        self.entry.options = {CONF_UI_DEVICES: {'light': [dict(LIGHT), dict(self.SECOND)]}}
        self.hass = HassStub([self.entry])

    def _stored_sender(self, address='00-00-00-04'):
        for device in (self.entry.options.get(CONF_UI_DEVICES) or {}).get('light', []):
            if device[CONF_ID] == address:
                return device.get(CONF_SENDER) or {}
        return {}

    async def _assign(self, bus_gateway, target, taught_in):
        """`taught_in` says which sender ids the actuators already carry."""
        async def write(hass, gateway, jobs, reason):
            return [{**job, 'result': 'written'} for job in jobs]

        with mock.patch('custom_components.eltako.observation.bus_members'
                        '._async_write_teach_in_jobs', side_effect=write) as writer, \
             mock.patch('custom_components.eltako.observation.bus_members.sender_is_taught_in',
                        side_effect=lambda _hass, _id, address, sender: sender in taught_in):
            answer = await sender_gateway.async_assign_sender_gateway(
                self.hass, bus_gateway, target)
        return answer, writer

    async def test_only_the_actuator_which_lacks_the_address_goes_onto_the_bus(self):
        answer, writer = await self._assign(fam14(), fam_usb(), taught_in={'FF-C0-02-04'})

        self.assertEqual(['00-00-00-05'],
                         [job['address'] for job in writer.call_args[0][2]])
        # both devices are switched over in Home Assistant - the written one and the one which
        # carried the address all along
        self.assertEqual('FF-C0-02-04', self._stored_sender()[CONF_ID])
        self.assertEqual('FF-C0-02-05', self._stored_sender('00-00-00-05')[CONF_ID])
        self.assertEqual({'00-00-00-04': 'already_taught_in', '00-00-00-05': 'written'},
                         {entry['address']: entry['result'] for entry in answer['results']})

    async def test_a_run_which_writes_nothing_never_touches_the_bus(self):
        _answer, writer = await self._assign(fam14(), fam14(),
                                             taught_in={'00-00-B0-04', '00-00-B0-05'})

        writer.assert_not_called()

    async def test_and_needs_no_fam14_for_it(self):
        """The case this is about: an installation which runs on an FGW14-USB moves back onto
        the local senders. Nothing has to be written, so nothing has to be connected."""
        answer, writer = await self._assign(fgw14usb(dev_id=1), fam14(),
                                            taught_in={'00-00-B0-04', '00-00-B0-05'})

        self.assertIsNone(answer.get('error'))
        writer.assert_not_called()
        self.assertEqual('00-00-B0-04', self._stored_sender()[CONF_ID])

    async def test_a_missing_address_still_demands_the_fam14(self):
        """Nothing is quietly skipped: what has to be written needs the gateway which can."""
        answer, writer = await self._assign(fgw14usb(dev_id=1), fam_usb(), taught_in=set())

        self.assertEqual('no_fam14', answer['error'])
        writer.assert_not_called()
        self.assertEqual('00-00-B0-04', self._stored_sender()[CONF_ID])

    async def test_a_memory_which_was_never_read_counts_as_missing(self):
        """sender_is_taught_in() answers None there - and a write which turns out to be
        unnecessary is checked by the actuator itself (ensure_programmed)."""
        async def write(hass, gateway, jobs, reason):
            return [{**job, 'result': 'already_taught_in'} for job in jobs]

        with mock.patch('custom_components.eltako.observation.bus_members'
                        '._async_write_teach_in_jobs', side_effect=write) as writer, \
             mock.patch('custom_components.eltako.observation.bus_members.sender_is_taught_in',
                        return_value=None):
            await sender_gateway.async_assign_sender_gateway(self.hass, fam14(), fam_usb())

        self.assertEqual(['00-00-00-04', '00-00-00-05'],
                         [job['address'] for job in writer.call_args[0][2]])
