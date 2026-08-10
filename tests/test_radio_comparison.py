"""One radio telegram as several gateways received it (observation/radio_comparison.py).

The module answers a question which cannot be answered by looking at a single telegram: three
transceivers receive the same button press, and whether all three really report the same bytes
is what this compares. The tests below pin the grouping (which receptions belong to the same
transmission), the comparison (which field differs and who is the odd one out) and the
statistics per gateway and per address - including the cases which are *not* an error: a
telegram which came in through a repeater, and a gateway which was added later.
"""
import unittest

from custom_components.eltako.const import TelegramDirection
from custom_components.eltako.observation.radio_comparison import (
    DEFAULT_WINDOW_MS,
    MAX_NAMED_ADDRESSES,
    MAX_WINDOW_MS,
    WINDOW_CHOICES,
    RadioComparison,
    is_radio_telegram,
)

ADDRESS = 'FE-DC-BA-98'
# a fixed point in the past: `get_report()` closes every burst whose window has passed, so the
# receptions fed in below are always complete when they are read - no waiting, no fake clock
BASE_MS = 1_775_000_000_000


def record(seq: int, gateway_id: int, timestamp_ms: int, data: str = '70', status: str = '0x30',
           rp_count: int = 0, rssi: int = None, address: str = ADDRESS,
           direction: str = TelegramDirection.INCOMING.value, msg_type: str = 'RPSMessage',
           org: str = '0x05', eep: str = 'F6-02-01', decoded: dict = None) -> dict:
    """A telegram record as the logger builds it (EnOceanTelegramLogger._create_record)."""
    result = {
        'seq': seq, 'timestamp_ms': timestamp_ms, 'direction': direction,
        'gateway_id': gateway_id, 'gateway_name': f"GW{gateway_id}", 'msg_type': msg_type,
        'org': org, 'address': address, 'data': data, 'status': status, 'rp_count': rp_count,
        'raw': 'ab5a', 'known': True, 'device_name': 'Rocker switch', 'eep': eep,
        'decoded': decoded, 'simulated': False,
    }
    if rssi is not None:
        result['rssi_dbm'] = rssi
    return result


class TestWhatIsCompared(unittest.TestCase):

    def test_a_radio_telegram_is_compared(self):
        self.assertTrue(is_radio_telegram(record(1, 1, BASE_MS)))

    def test_bus_messages_are_not(self):
        """Polling, discovery and memory telegrams never leave the wire of one bus."""
        self.assertFalse(is_radio_telegram({'gateway_id': 1, 'address': 'bus 5',
                                            'role': 'bus_message'}))
        self.assertFalse(is_radio_telegram({'gateway_id': 1, 'address': None, 'bus_address': 5}))

    def test_a_telegram_without_an_address_is_not(self):
        self.assertFalse(is_radio_telegram({'gateway_id': 1, 'address': None}))

    def test_what_a_gateway_read_off_its_bus_is_not(self):
        """An actuator on an RS485 bus is addressed relative to the base id of its gateway.

        Its status telegram reaches the FAM14 over the wire - counting that as reception would
        make every bus gateway the best receiver of the installation.
        """
        self.assertFalse(is_radio_telegram(record(1, 1, BASE_MS, address='FF-AA-BB-05')
                                           | {'local_address': '00-00-00-05'}))

    def test_but_what_a_bus_gateway_sends_stays(self):
        """A FAM14 puts its bus traffic on air, so it is the sender other gateways receive."""
        outgoing = record(1, 1, BASE_MS, address='FF-AA-BB-05',
                          direction=TelegramDirection.OUTGOING.value)
        self.assertTrue(is_radio_telegram(outgoing | {'local_address': '00-00-00-05'}))


class TestGrouping(unittest.TestCase):

    def setUp(self):
        self.comparison = RadioComparison()

    def report(self) -> dict:
        return self.comparison.get_report()

    def test_what_came_over_the_wire_is_not_part_of_the_burst(self):
        """The FAM14 read the actuator off its bus, only the transceiver heard it on air."""
        self.comparison.add(record(1, 1, BASE_MS, address='FF-AA-BB-05')
                            | {'local_address': '00-00-00-05'})
        self.comparison.add(record(2, 2, BASE_MS + 8, address='FF-AA-BB-05', rssi=-72))

        report = self.report()

        self.assertEqual(1, len(report['bursts']))
        self.assertEqual([2], [member['gateway_id']
                               for member in report['bursts'][0]['members']])

    def test_receptions_within_the_window_are_one_telegram(self):
        self.comparison.add(record(1, 1, BASE_MS, rssi=-60))
        self.comparison.add(record(2, 2, BASE_MS + 9, rssi=-78))
        self.comparison.add(record(3, 3, BASE_MS + 14, rssi=-85))

        summary = self.report()['summary']
        self.assertEqual(summary['burst_count'], 1)
        self.assertEqual(summary['multi_gateway_bursts'], 1)
        self.assertEqual(summary['telegram_count'], 3)

    def test_receptions_outside_the_window_are_two_telegrams(self):
        self.comparison.add(record(1, 1, BASE_MS))
        self.comparison.add(record(2, 2, BASE_MS + DEFAULT_WINDOW_MS + 1))

        summary = self.report()['summary']
        self.assertEqual(summary['burst_count'], 2)
        self.assertEqual(summary['single_gateway_bursts'], 2)

    def test_a_new_payload_of_the_same_gateway_starts_a_new_telegram(self):
        """Press and release of a rocker switch can be milliseconds apart - and are two
        telegrams, not one telegram two gateways disagree about."""
        self.comparison.add(record(1, 1, BASE_MS, data='70'))
        self.comparison.add(record(2, 1, BASE_MS + 20, data='00'))

        summary = self.report()['summary']
        self.assertEqual(summary['burst_count'], 2)
        self.assertEqual(summary['differing_bursts'], 0)

    def test_the_same_telegram_through_a_repeater_is_one_reception(self):
        """The same gateway receives the telegram again over a repeater: the same
        transmission, counted as a repetition instead of a second telegram."""
        self.comparison.add(record(1, 1, BASE_MS, rssi=-60))
        self.comparison.add(record(2, 1, BASE_MS + 45, status='0x31', rp_count=1, rssi=-70))

        report = self.report()
        self.assertEqual(report['summary']['burst_count'], 1)
        burst = report['bursts'][0]
        self.assertEqual(len(burst['members']), 1)
        self.assertEqual(burst['members'][0]['repeats'], 1)
        self.assertEqual(burst['members'][0]['rp_count_max'], 1)
        # the values of the repetition are part of the signal range of that gateway
        self.assertEqual(burst['members'][0]['rssi_min'], -70)
        self.assertEqual(burst['members'][0]['rssi_max'], -60)

    def test_two_addresses_are_never_merged(self):
        self.comparison.add(record(1, 1, BASE_MS, address='FE-DC-BA-98'))
        self.comparison.add(record(2, 2, BASE_MS + 5, address='01-23-45-67'))

        report = self.comparison.get_report()
        self.assertEqual(report['summary']['address_count'], 2)
        self.assertEqual(report['summary']['burst_count'], 2)


def _differing(report: dict) -> dict:
    """The one burst of a report the gateways did not agree about."""
    differing = [burst for burst in report['bursts'] if burst['differences']]
    assert len(differing) == 1, f"expected exactly one differing telegram, got {len(differing)}"
    return differing[0]


class TestComparison(unittest.TestCase):

    def setUp(self):
        self.comparison = RadioComparison()

    def differing(self, report: dict) -> dict:
        return _differing(report)

    def test_identical_receptions_have_no_difference(self):
        self.comparison.add(record(1, 1, BASE_MS, rssi=-60))
        self.comparison.add(record(2, 2, BASE_MS + 5, rssi=-80))

        report = self.comparison.get_report()
        self.assertEqual(report['summary']['differing_bursts'], 0)
        self.assertEqual([b for b in report['bursts'] if b['differences']], [])
        burst = report['bursts'][0]
        self.assertEqual(burst['differences'], [])
        self.assertEqual(burst['rssi_spread'], 20)

    def test_different_data_names_the_field_and_the_outlier(self):
        self.comparison.add(record(1, 1, BASE_MS, data='70'))
        self.comparison.add(record(2, 2, BASE_MS + 5, data='50'))
        self.comparison.add(record(3, 3, BASE_MS + 8, data='70'))

        report = self.comparison.get_report()
        self.assertEqual(report['summary']['differing_bursts'], 1)
        self.assertEqual(report['summary']['disagreeing_bursts'], 1)
        self.assertEqual(report['summary']['by_field']['data'], 1)

        burst = self.differing(report)
        self.assertEqual(burst['differences'], ['data'])
        self.assertEqual(burst['disagreement'], ['data'])
        # the value two of the three gateways reported wins, the third one is the outlier
        self.assertEqual(burst['majority']['data'], '70')
        self.assertEqual(burst['outlier_gateway_ids'], [2])
        self.assertEqual(burst['values']['data'], {'70': [1, 3], '50': [2]})

    def test_two_gateways_which_disagree_have_no_majority_and_no_outlier(self):
        """1:1 is not a vote. Calling one of the two bytes the truth would blame a gateway at
        random, so both values stand next to each other and the difference is marked against
        the reception which came in first."""
        self.comparison.add(record(1, 1, BASE_MS, data='70'))
        self.comparison.add(record(2, 2, BASE_MS + 5, data='50'))

        report = self.comparison.get_report()
        burst = self.differing(report)
        self.assertEqual(burst['differences'], ['data'])
        self.assertEqual(burst['tied'], ['data'])
        self.assertNotIn('data', burst['majority'])
        self.assertEqual(burst['outlier_gateway_ids'], [])
        self.assertEqual(burst['reference'], {'msg_type': 'RPSMessage', 'org': '0x05',
                                              'data': '70', 'status': '0x30', 'gateway_id': 1})
        # the burst is still a disagreement - the gateways did not receive the same telegram
        self.assertEqual(report['summary']['disagreeing_bursts'], 1)
        self.assertEqual([gateway['outlier'] for gateway in report['gateways']], [0, 0])

    def test_a_repeater_hop_is_a_difference_but_not_a_disagreement(self):
        self.comparison.add(record(1, 1, BASE_MS, status='0x30', rp_count=0))
        self.comparison.add(record(2, 2, BASE_MS + 40, status='0x31', rp_count=1))

        report = self.comparison.get_report()
        self.assertEqual(report['summary']['differing_bursts'], 1)
        self.assertEqual(report['summary']['disagreeing_bursts'], 0)
        burst = self.differing(report)
        self.assertEqual(burst['differences'], ['rp_count'])
        self.assertEqual(burst['disagreement'], [])
        # the hop count is not held against the gateway which only heard the repeater
        self.assertEqual(burst['outlier_gateway_ids'], [])
        self.assertEqual([gateway['outlier'] for gateway in report['gateways']], [0, 0])
        self.assertEqual([gateway['hops'] for gateway in report['gateways']], [0, 1])

    def test_the_status_bits_are_compared_without_the_repeater_counter(self):
        """0x30 and 0x31 differ only in the hop count; 0x30 and 0x20 really differ."""
        self.comparison.add(record(1, 1, BASE_MS, status='0x30'))
        self.comparison.add(record(2, 2, BASE_MS + 5, status='0x20'))

        burst = self.differing(self.comparison.get_report())
        self.assertIn('status', burst['differences'])
        self.assertIn('status', burst['disagreement'])

    def test_a_different_message_type_is_reported(self):
        self.comparison.add(record(1, 1, BASE_MS, msg_type='RPSMessage', org='0x05'))
        self.comparison.add(record(2, 2, BASE_MS + 5, msg_type='Regular4BSMessage', org='0x07'))

        burst = self.differing(self.comparison.get_report())
        self.assertEqual(sorted(burst['disagreement']), ['msg_type', 'org'])

    def test_the_telegram_a_gateway_sent_is_not_compared_but_kept(self):
        """A telegram Home Assistant sent through one gateway and another one received: the
        sender is shown for context, and it did not 'miss' its own telegram."""
        self.comparison.add(record(1, 1, BASE_MS, direction=TelegramDirection.OUTGOING.value))
        self.comparison.add(record(2, 2, BASE_MS + 6, data='50'))

        report = self.comparison.get_report()
        burst = report['bursts'][0]
        self.assertEqual(burst['sender_gateway_ids'], [1])
        self.assertEqual(burst['gateway_count'], 1)
        self.assertEqual(burst['differences'], [])
        gateways = {gateway['gateway_id']: gateway for gateway in report['gateways']}
        self.assertEqual(gateways[1]['sent'], 1)
        self.assertEqual(gateways[1]['received'], 0)
        self.assertEqual(gateways[1]['missed'], 0)


class TestStatistics(unittest.TestCase):

    def setUp(self):
        self.comparison = RadioComparison()
        # burst 1: all three hear it
        self.comparison.add(record(1, 1, BASE_MS, rssi=-60))
        self.comparison.add(record(2, 2, BASE_MS + 5, rssi=-78))
        self.comparison.add(record(3, 3, BASE_MS + 9, rssi=-88))
        # burst 2: gateway 3 misses it
        self.comparison.add(record(4, 1, BASE_MS + 10_000, rssi=-62))
        self.comparison.add(record(5, 2, BASE_MS + 10_004, rssi=-80))
        # burst 3: only gateway 1 hears it
        self.comparison.add(record(6, 1, BASE_MS + 20_000, rssi=-64))
        self.report = self.comparison.get_report()
        self.gateways = {gateway['gateway_id']: gateway for gateway in self.report['gateways']}

    def test_reception_rate_per_gateway(self):
        self.assertEqual(self.gateways[1]['received'], 3)
        self.assertEqual(self.gateways[1]['share'], 1.0)
        self.assertEqual(self.gateways[2]['received'], 2)
        self.assertEqual(self.gateways[2]['missed'], 1)
        self.assertEqual(self.gateways[2]['offered'], 3)
        self.assertEqual(self.gateways[3]['received'], 1)
        self.assertEqual(self.gateways[3]['missed'], 2)

    def test_who_was_there_first_and_who_was_alone(self):
        # only counted where there was a race: bursts 1 and 2
        self.assertEqual(self.gateways[1]['first'], 2)
        self.assertEqual(self.gateways[2]['first'], 0)
        # burst 3 was received by gateway 1 alone
        self.assertEqual(self.gateways[1]['alone'], 1)

    def test_signal_strength_per_gateway(self):
        self.assertEqual(self.gateways[1]['rssi_max'], -60)
        self.assertEqual(self.gateways[1]['rssi_min'], -64)
        self.assertEqual(self.gateways[1]['rssi_avg'], -62.0)
        self.assertEqual(self.gateways[3]['rssi_avg'], -88.0)

    def test_a_gateway_which_showed_up_later_did_not_miss_the_earlier_telegrams(self):
        comparison = RadioComparison()
        comparison.add(record(1, 1, BASE_MS))
        comparison.add(record(2, 1, BASE_MS + 10_000))
        comparison.add(record(3, 1, BASE_MS + 20_000))
        # a second gateway is plugged in and hears the next telegram right away
        comparison.add(record(4, 1, BASE_MS + 30_000))
        comparison.add(record(5, 2, BASE_MS + 30_005))

        gateways = {gateway['gateway_id']: gateway
                    for gateway in comparison.get_report()['gateways']}
        self.assertEqual(gateways[2]['received'], 1)
        self.assertEqual(gateways[2]['missed'], 0)
        self.assertEqual(gateways[2]['offered'], 1)
        self.assertEqual(gateways[2]['share'], 1.0)

    def test_which_gateway_receives_which_address(self):
        address = [entry for entry in self.report['addresses']
                   if entry['address'] == ADDRESS][0]
        self.assertEqual(address['bursts'], 3)
        self.assertEqual(address['max_gateway_count'], 3)
        self.assertEqual(address['name'], 'Rocker switch')
        self.assertEqual(address['gateways']['1']['count'], 3)
        self.assertEqual(address['gateways']['2']['count'], 2)
        self.assertEqual(address['gateways']['2']['missed'], 1)
        self.assertEqual(address['gateways']['3']['count'], 1)
        self.assertEqual(address['gateways']['3']['rssi_avg'], -88.0)

    def test_the_bursts_are_returned_newest_first(self):
        stamps = [burst['timestamp_ms'] for burst in self.report['bursts']]
        self.assertEqual(stamps, sorted(stamps, reverse=True))

    def test_the_limit_only_bounds_the_lists(self):
        report = self.comparison.get_report(limit=1)
        self.assertEqual(len(report['bursts']), 1)
        self.assertEqual(report['summary']['burst_count'], 3)

    def test_reset(self):
        self.comparison.clear()
        report = self.comparison.get_report()
        self.assertEqual(report['summary']['burst_count'], 0)
        self.assertEqual(report['gateways'], [])
        self.assertEqual(report['addresses'], [])
        self.assertEqual(report['bursts'], [])


class TestWhereTheDifferencesAre(unittest.TestCase):
    """Per kind of difference: on which device it happens, and which gateway is the odd one out.

    The count alone ("the data bytes differed twelve times") is the beginning of the question -
    the summary has to carry the answer to "where do I look" as well, otherwise the only way to
    find it is scrolling through the telegram list.
    """

    def setUp(self):
        self.comparison = RadioComparison()
        # two telegrams of one device in which gateway 3 reports another data byte than the two
        # others - a real majority, so gateway 3 can be named
        for index, offset in enumerate((0, 10_000)):
            self.comparison.add(record(index * 3 + 1, 1, BASE_MS + offset, data='70'))
            self.comparison.add(record(index * 3 + 2, 2, BASE_MS + offset + 5, data='70'))
            self.comparison.add(record(index * 3 + 3, 3, BASE_MS + offset + 9, data='50'))
        # a second device on which only the repeater hop count differs
        self.comparison.add(record(7, 1, BASE_MS + 20_000, address='01-23-45-67'))
        self.comparison.add(record(8, 2, BASE_MS + 20_006, address='01-23-45-67',
                                   status='0x31', rp_count=1))
        self.detail = self.comparison.get_report()['summary']['by_field_detail']

    def test_the_device_a_difference_happens_on_is_named(self):
        data = self.detail['data']
        self.assertEqual(data['count'], 2)
        self.assertEqual(data['address_count'], 1)
        self.assertEqual([entry['address'] for entry in data['addresses']], [ADDRESS])
        self.assertEqual(data['addresses'][0]['count'], 2)
        self.assertEqual(data['addresses'][0]['name'], 'Rocker switch')

    def test_the_gateway_which_reported_something_else_is_named(self):
        self.assertEqual([(entry['gateway_id'], entry['gateway_name'], entry['count'])
                          for entry in self.detail['data']['gateways']], [(3, 'GW3', 2)])

    def test_two_gateways_against_each_other_name_nobody(self):
        """No majority, no odd one out - naming one of the two would blame it at random."""
        comparison = RadioComparison()
        comparison.add(record(1, 1, BASE_MS, data='70'))
        comparison.add(record(2, 2, BASE_MS + 5, data='50'))

        data = comparison.get_report()['summary']['by_field_detail']['data']
        self.assertEqual(data['gateways'], [])
        self.assertEqual(data['tied'], 1)

    def test_the_repeater_hop_keeps_its_own_entry(self):
        hops = self.detail['rp_count']
        self.assertEqual(hops['count'], 1)
        self.assertEqual([entry['address'] for entry in hops['addresses']], ['01-23-45-67'])

    def test_a_field_which_never_differed_has_no_entry(self):
        self.assertNotIn('org', self.detail)
        self.assertNotIn('eep', self.detail)

    def test_only_the_worst_devices_are_named_and_the_rest_is_counted(self):
        comparison = RadioComparison()
        for index in range(MAX_NAMED_ADDRESSES + 3):
            comparison.add(record(index * 2 + 1, 1, BASE_MS + index * 10_000,
                                  address=f"FE-DC-BA-{index:02X}", data='70'))
            comparison.add(record(index * 2 + 2, 2, BASE_MS + index * 10_000 + 5,
                                  address=f"FE-DC-BA-{index:02X}", data='50'))

        data = comparison.get_report()['summary']['by_field_detail']['data']
        self.assertEqual(data['address_count'], MAX_NAMED_ADDRESSES + 3)
        self.assertEqual(len(data['addresses']), MAX_NAMED_ADDRESSES)


class TestTheAdjustableWindow(unittest.TestCase):
    """The window is a control, not a setting: the same recording is regrouped for it.

    How far apart two receptions of the same transmission can be depends on the installation -
    a gateway behind a LAN connection or a chain of repeaters reports later than a stick on the
    same machine. Getting that wrong in either direction is visible in the numbers (one
    transmission counted twice, or two telegrams merged into a fake difference), so it has to
    be answerable without throwing the recording away.
    """

    def setUp(self):
        self.comparison = RadioComparison()
        self.comparison.add(record(1, 1, BASE_MS, rssi=-60))
        self.comparison.add(record(2, 2, BASE_MS + 250, rssi=-80))

    def test_a_narrow_window_keeps_them_apart(self):
        report = self.comparison.get_report(window_ms=100)

        self.assertEqual(report['summary']['window_ms'], 100)
        self.assertEqual(report['summary']['burst_count'], 2)
        self.assertEqual(report['summary']['multi_gateway_bursts'], 0)

    def test_a_wide_window_makes_them_one_telegram(self):
        report = self.comparison.get_report(window_ms=500)

        self.assertEqual(report['summary']['burst_count'], 1)
        self.assertEqual(report['summary']['multi_gateway_bursts'], 1)
        self.assertEqual(report['bursts'][0]['span_ms'], 250)

    def test_the_window_is_clamped_to_what_makes_sense(self):
        self.assertEqual(self.comparison.get_report(window_ms=0)['summary']['window_ms'],
                         DEFAULT_WINDOW_MS)
        self.assertEqual(self.comparison.get_report(window_ms=999_999)['summary']['window_ms'],
                         MAX_WINDOW_MS)

    def test_the_offered_choices_are_part_of_the_answer(self):
        """The web ui builds its window selection from this instead of hard coding it."""
        self.assertEqual(self.comparison.get_report()['summary']['window_choices'],
                         list(WINDOW_CHOICES))


class TestTheViews(unittest.TestCase):
    """Filtering the telegram list - "only the differing ones", "who missed something"."""

    def setUp(self):
        self.comparison = RadioComparison()
        # 1) both agree
        self.comparison.add(record(1, 1, BASE_MS, rssi=-60))
        self.comparison.add(record(2, 2, BASE_MS + 5, rssi=-80))
        # 2) different data
        self.comparison.add(record(3, 1, BASE_MS + 10_000, data='70'))
        self.comparison.add(record(4, 2, BASE_MS + 10_005, data='50'))
        # 3) only gateway 1 - gateway 2 missed it
        self.comparison.add(record(5, 1, BASE_MS + 20_000))
        # 4) gateway 2 got it over a repeater, and twice
        self.comparison.add(record(6, 1, BASE_MS + 30_000))
        self.comparison.add(record(7, 2, BASE_MS + 30_040, status='0x31', rp_count=1))
        self.comparison.add(record(8, 2, BASE_MS + 30_080, status='0x31', rp_count=1))
        # 5) same bytes, but the gateways read them differently
        self.comparison.add(record(9, 1, BASE_MS + 40_000, eep='F6-02-01',
                                   decoded={'button_pressed': True}))
        self.comparison.add(record(10, 2, BASE_MS + 40_004, eep='F6-02-02',
                                   decoded={'button_pressed': False}))

    def counts(self) -> dict:
        return self.comparison.get_report()['summary']['filter_counts']

    def selected(self, name: str) -> list:
        report = self.comparison.get_report(telegram_filter=name)
        return report['bursts']

    def test_every_view_is_counted(self):
        counts = self.counts()

        self.assertEqual(counts['all'], 5)
        # only telegram 1: 4 differs in the hop count, 5 in the interpretation
        self.assertEqual(counts['identical'], 1)
        self.assertEqual(counts['disagreeing'], 1)      # 2
        self.assertEqual(counts['interpreted'], 1)      # 5
        self.assertEqual(counts['hops'], 1)             # 4
        self.assertEqual(counts['missing'], 1)          # 3
        self.assertEqual(counts['single'], 1)           # 3
        self.assertEqual(counts['repeated'], 1)         # 4

    def test_a_view_only_selects_its_telegrams(self):
        self.assertEqual(len(self.selected('disagreeing')), 1)
        self.assertEqual(self.selected('disagreeing')[0]['differences'], ['data'])
        self.assertEqual(self.selected('missing')[0]['missing_gateway_ids'], [2])
        self.assertEqual(self.selected('hops')[0]['differences'], ['rp_count'])
        self.assertEqual(len(self.selected('all')), 5)

    def test_the_numbers_are_not_filtered_with_the_list(self):
        """A view must not make a gateway look better than it is."""
        report = self.comparison.get_report(telegram_filter='identical')

        self.assertEqual(report['summary']['burst_count'], 5)
        self.assertEqual(report['summary']['disagreeing_bursts'], 1)
        gateways = {gateway['gateway_id']: gateway for gateway in report['gateways']}
        self.assertEqual(gateways[2]['missed'], 1)

    def test_reading_a_telegram_differently_is_kept_apart_from_receiving_it_differently(self):
        """The bytes can be identical and the values still different - then it is not the
        reception which is at fault but the configuration behind the address."""
        burst = self.selected('interpreted')[0]

        self.assertEqual(burst['disagreement'], [])
        self.assertEqual(sorted(burst['interpretation']), ['decoded', 'eep'])
        self.assertEqual(burst['values']['eep'], {'F6-02-01': [1], 'F6-02-02': [2]})
        self.assertEqual(sorted(burst['values']['decoded']),
                         ['button_pressed=False', 'button_pressed=True'])
        # and what each gateway made of it is part of the telegram
        self.assertEqual([member['eep'] for member in burst['members']],
                         ['F6-02-01', 'F6-02-02'])


class TestTheDirectComparison(unittest.TestCase):
    """Two gateways and one sender against each other - see get_report(gateway_ids, address)."""

    def setUp(self):
        self.comparison = RadioComparison()
        # a button both gateways hear, once with different data
        self.comparison.add(record(1, 1, BASE_MS, rssi=-60))
        self.comparison.add(record(2, 2, BASE_MS + 5, rssi=-80))
        self.comparison.add(record(3, 1, BASE_MS + 10_000, data='70', rssi=-62))
        self.comparison.add(record(4, 2, BASE_MS + 10_004, data='50', rssi=-88))
        # a telegram only gateway 3 is in range of - none of the other two missed it
        self.comparison.add(record(5, 3, BASE_MS + 20_000, address='01-23-45-67', rssi=-70))
        # a second sender which only gateway 1 hears
        self.comparison.add(record(6, 1, BASE_MS + 30_000, address='0A-0B-0C-0D', rssi=-55))

    def test_only_the_selected_gateways_take_part(self):
        report = self.comparison.get_report(gateway_ids=[1, 2])

        self.assertEqual([gateway['gateway_id'] for gateway in report['gateways']], [1, 2])
        self.assertEqual(report['summary']['selected_gateway_ids'], ['1', '2'])
        # the telegram of gateway 3 is gone, so nobody missed it
        self.assertEqual(report['summary']['burst_count'], 3)
        gateways = {gateway['gateway_id']: gateway for gateway in report['gateways']}
        self.assertEqual(gateways[2]['missed'], 1)      # the second sender

    def test_only_the_selected_sender_takes_part(self):
        report = self.comparison.get_report(address=ADDRESS)

        self.assertEqual(report['summary']['burst_count'], 2)
        self.assertEqual([address['address'] for address in report['addresses']], [ADDRESS])
        self.assertEqual(report['summary']['selected_address'], ADDRESS)

    def test_gateways_and_sender_together_are_the_head_to_head(self):
        report = self.comparison.get_report(gateway_ids=[1, 2], address=ADDRESS)

        self.assertEqual(report['summary']['burst_count'], 2)
        self.assertEqual(len(report['pairs']), 1)
        pair = report['pairs'][0]
        self.assertEqual((pair['gateway_a'], pair['gateway_b']), (1, 2))
        self.assertEqual(pair['together'], 2)
        self.assertEqual(pair['agreed'], 1)
        self.assertEqual(pair['disagreed'], 1)
        self.assertEqual(pair['only_a'], 0)
        self.assertEqual(pair['only_b'], 0)
        # gateway 1 hears this sender ~24 dB stronger than gateway 2
        self.assertEqual(pair['rssi_delta_avg'], 23.0)
        self.assertEqual(pair['a_stronger'], 2)

    def test_a_repeater_hop_is_not_a_disagreement_of_the_pair_either(self):
        """The status byte carries the hop count - comparing it raw would make every repeated
        telegram look like the two gateways disagreed."""
        comparison = RadioComparison()
        comparison.add(record(1, 1, BASE_MS, status='0x30', rp_count=0))
        comparison.add(record(2, 2, BASE_MS + 40, status='0x31', rp_count=1))

        pair = comparison.get_report()['pairs'][0]
        self.assertEqual(pair['disagreed'], 0)
        self.assertEqual(pair['agreed'], 1)
        self.assertEqual(pair['hops'], 1)

    def test_the_pair_only_counts_what_both_could_have_received(self):
        pairs = {(pair['gateway_a'], pair['gateway_b']): pair
                 for pair in self.comparison.get_report()['pairs']}

        # gateway 1 heard the second sender alone
        self.assertEqual(pairs[(1, 2)]['only_a'], 1)
        # the telegram of gateway 3 is in neither of their columns
        self.assertEqual(pairs[(1, 2)]['neither'], 1)
        self.assertEqual(pairs[(1, 3)]['only_b'], 1)

    def test_what_can_be_selected_is_part_of_the_answer(self):
        """Restricted to one sender, the list of senders must not shrink to that one."""
        available = self.comparison.get_report(address=ADDRESS)['summary']['available']

        self.assertEqual([gateway['gateway_id'] for gateway in available['gateways']], [1, 2, 3])
        self.assertEqual([address['address'] for address in available['addresses']],
                         [ADDRESS, '01-23-45-67', '0A-0B-0C-0D'])
        self.assertEqual(available['addresses'][0]['count'], 4)

    def test_an_unknown_selection_simply_finds_nothing(self):
        report = self.comparison.get_report(gateway_ids=[99])

        self.assertEqual(report['summary']['burst_count'], 0)
        self.assertEqual(report['gateways'], [])
        self.assertEqual(report['pairs'], [])


class TestTheRepeaterPath(unittest.TestCase):
    """Direct, repeater level 1 or level 2 - per gateway and per device."""

    def setUp(self):
        self.comparison = RadioComparison()
        # gateway 1 hears the device directly, gateway 2 only over repeaters
        self.comparison.add(record(1, 1, BASE_MS, rssi=-60))
        self.comparison.add(record(2, 2, BASE_MS + 40, status='0x31', rp_count=1, rssi=-85))
        self.comparison.add(record(3, 1, BASE_MS + 10_000, rssi=-61))
        self.comparison.add(record(4, 2, BASE_MS + 10_080, status='0x32', rp_count=2, rssi=-90))
        self.report = self.comparison.get_report()

    def test_the_path_is_counted_per_gateway(self):
        gateways = {gateway['gateway_id']: gateway for gateway in self.report['gateways']}

        self.assertEqual(gateways[1]['by_level'], {'0': 2})
        self.assertEqual(gateways[2]['by_level'], {'1': 1, '2': 1})
        self.assertEqual(gateways[2]['hops'], 2)

    def test_the_device_table_says_how_each_gateway_hears_it(self):
        address = self.report['addresses'][0]

        direct = address['gateways']['1']
        self.assertEqual(direct['by_level'], {'0': 2})
        self.assertEqual(direct['direct'], 2)
        self.assertEqual(direct['best_level'], 0)

        repeated = address['gateways']['2']
        self.assertEqual(repeated['by_level'], {'1': 1, '2': 1})
        self.assertEqual(repeated['direct'], 0)
        # never heard directly: this gateway depends on the repeaters for this device
        self.assertEqual(repeated['best_level'], 1)
        self.assertEqual(repeated['worst_level'], 2)


class TestRobustness(unittest.TestCase):

    def test_a_telegram_without_data_or_signal_strength_is_compared_as_well(self):
        comparison = RadioComparison()
        for gateway_id in (1, 2):
            comparison.add({'seq': gateway_id, 'timestamp_ms': BASE_MS + gateway_id,
                            'direction': TelegramDirection.INCOMING.value,
                            'gateway_id': gateway_id, 'address': ADDRESS,
                            'msg_type': 'RPSMessage'})

        report = comparison.get_report()
        self.assertEqual(report['summary']['differing_bursts'], 0)
        burst = report['bursts'][0]
        self.assertEqual(burst['gateway_count'], 2)
        self.assertIsNone(burst['rssi_spread'])

    def test_a_broken_status_byte_does_not_break_the_comparison(self):
        comparison = RadioComparison()
        comparison.add(record(1, 1, BASE_MS, status='not a byte'))
        comparison.add(record(2, 2, BASE_MS + 3, status='0x30'))

        burst = _differing(comparison.get_report())
        self.assertIn('status', burst['differences'])


class TestFedByTheTelegramLogger(unittest.IsolatedAsyncioTestCase):
    """The comparison is filled by the recording itself, not by the page which reads it.

    Whoever opens the page later has to see the differences which happened meanwhile, so the
    logger hands every telegram it records over (see _compare_radio_reception).
    """

    def setUp(self):
        from eltakobus.message import RPSMessage
        from eltakobus.util import AddressExpression

        from homeassistant.const import CONF_ID

        from custom_components.eltako.const import (CONF_BASE_ID, CONF_GATEWAY,
                                                    CONF_LOG_ENOCEAN_TELEGRAMS)
        from custom_components.eltako.observation.enocean_logger import EnOceanTelegramLogger

        from tests.mocks import GatewayMock
        from tests.test_enocean_logger import HassDataMock, get_general_settings

        self.message = RPSMessage
        base_id = AddressExpression.parse('FF-AA-80-00')
        self.gateways = [GatewayMock(dev_id=1, base_id=base_id),
                         GatewayMock(dev_id=2, base_id=base_id)]
        hass = HassDataMock(config={CONF_GATEWAY: [{CONF_ID: 1, CONF_BASE_ID: 'FF-AA-80-00'}]})
        for gateway in self.gateways:
            gateway.hass = hass
        self.logger = EnOceanTelegramLogger(
            hass, get_general_settings(**{CONF_LOG_ENOCEAN_TELEGRAMS: True}))
        self.logger.refresh_device_map()

    def receive(self, gateway, data: bytes, rssi: int = None):
        message = self.message(b'\xFE\xDB\xB6\x40', status=0x30, data=data)
        if rssi is not None:
            message.dBm = rssi
        self.logger.record_message(gateway, message, TelegramDirection.INCOMING.value)

    def test_both_gateways_end_up_in_one_comparison(self):
        self.receive(self.gateways[0], b'\x70', rssi=-61)
        self.receive(self.gateways[1], b'\x70', rssi=-84)

        report = self.logger.radio_comparison.get_report()
        # the burst is still open (it just happened) - the summary counts the receptions
        self.assertEqual(report['summary']['telegram_count'], 2)

    def test_a_difference_between_the_gateways_is_recorded(self):
        self.receive(self.gateways[0], b'\x70', rssi=-61)
        self.receive(self.gateways[1], b'\x50', rssi=-90)
        report = self.logger.radio_comparison.get_report()
        self.assertEqual(report['summary']['disagreeing_bursts'], 1)
        burst = _differing(report)
        self.assertEqual(burst['address'], 'FE-DB-B6-40')
        self.assertEqual(burst['differences'], ['data'])
        self.assertEqual(sorted(member['gateway_id'] for member in burst['members']), [1, 2])
        self.assertEqual(burst['rssi_spread'], 29)

    async def test_the_websocket_command_answers_what_the_page_reads(self):
        from custom_components.eltako.const import DATA_ELTAKO, DATA_TELEGRAM_LOGGER
        from custom_components.eltako.observation.enocean_logger import (
            async_radio_comparison_report, ws_radio_comparison_clear)

        results = []

        class UserMock:
            is_admin = True

        class ConnectionMock:
            user = UserMock()

            def send_result(self, _id, result):
                results.append(result)

        hass = self.logger.hass
        hass.data[DATA_ELTAKO][DATA_TELEGRAM_LOGGER] = self.logger
        self.receive(self.gateways[0], b'\x70', rssi=-61)
        self.receive(self.gateways[1], b'\x50', rssi=-90)

        # the websocket handler is a thin wrapper around this - it only sends the result
        report = await async_radio_comparison_report(hass, {'id': 1, 'limit': 50})
        self.assertEqual(set(report),
                         {'summary', 'gateways', 'addresses', 'pairs', 'bursts', 'selected_count'})
        self.assertTrue(report['summary']['enabled'])
        self.assertEqual(report['summary']['window_ms'], DEFAULT_WINDOW_MS)
        self.assertEqual(len([b for b in report['bursts'] if b['differences']]), 1)

        ws_radio_comparison_clear(hass, ConnectionMock(), {'id': 2})
        self.assertEqual(results[0], {'cleared': True})
        self.assertEqual(self.logger.radio_comparison.get_report()['summary']['burst_count'], 0)

    async def test_the_page_is_told_when_recording_is_off(self):
        """Without the recording there is no comparison - and the page needs to know why."""
        from custom_components.eltako.const import DATA_ELTAKO, DATA_TELEGRAM_LOGGER
        from custom_components.eltako.observation.enocean_logger import (
            async_radio_comparison_report)

        hass = self.logger.hass
        hass.data[DATA_ELTAKO].pop(DATA_TELEGRAM_LOGGER, None)

        report = await async_radio_comparison_report(hass, {'id': 1, 'limit': 50})

        self.assertFalse(report['summary']['enabled'])
        self.assertIn('hint', report['summary'])
        self.assertEqual(report['bursts'], [])

    def test_bus_polling_is_not_compared(self):
        from eltakobus.message import EltakoPoll

        self.logger.include_polling = True
        self.logger.record_message(self.gateways[0], EltakoPoll(1),
                                   TelegramDirection.INCOMING.value)

        self.assertEqual(self.logger.radio_comparison.get_report()['summary']['telegram_count'], 0)
