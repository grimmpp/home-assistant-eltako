"""The site survey: how well the radio gateways hear.

Whether an EnOcean installation still works in a year is decided by the reserve of its links,
and that is not visible from "the telegram arrived". Two numbers say it, and both are in every
recorded telegram already:

* the **signal strength** the receiver reports (only ESP3 transceivers do)
* the **repeater count** - a telegram which came through a repeater did not make it directly

`observation/reception.survey` aggregates them per link (one sender heard by one gateway) and
per gateway over a time window. It is a pure function over the telegram records, so everything
which decides what a user sees while walking through the building is tested here without any
hardware.
"""
import unittest
from datetime import datetime, timedelta, timezone
from unittest import TestCase, mock

from custom_components.eltako.observation import reception
from custom_components.eltako.observation.reception import quality_of, survey

NOW = datetime.now(timezone.utc).replace(microsecond=0)


def telegram(seconds_ago: int = 0, **overrides) -> dict:
    """One record of the telegram ring buffer."""
    record = {
        'timestamp': (NOW - timedelta(seconds=seconds_ago)).isoformat(),
        'direction': 'incoming',
        'gateway_id': 1,
        'gateway_name': 'FAM-USB',
        'address': 'FF-EE-DD-CC',
        'device_name': 'Kitchen button',
        'known': True,
        'msg_type': 'RPS',
        'rssi_dbm': -70,
        'rp_count': 0,
        'repeated': False,
    }
    record.update(overrides)
    return record


class TestQualitySteps(TestCase):
    """The steps are what turns a number nobody can judge into a decision."""

    def test_the_steps(self):
        self.assertEqual('excellent', quality_of(-45))
        self.assertEqual('excellent', quality_of(-60))
        self.assertEqual('good', quality_of(-61))
        self.assertEqual('good', quality_of(-75))
        self.assertEqual('fair', quality_of(-80))
        self.assertEqual('weak', quality_of(-90))

    def test_no_signal_strength_is_no_quality(self):
        """A FAM14 or an ESP2 stick reports none - that is not 'weak', it is unknown."""
        self.assertIsNone(quality_of(None))


class TestWhatCounts(TestCase):

    def test_outgoing_telegrams_are_not_reception(self):
        result = survey([telegram(direction='outgoing')], now=NOW)

        self.assertEqual(0, result['telegrams'])
        self.assertEqual([], result['links'])

    def test_bus_messages_do_not_drown_the_radio(self):
        """A FAM14 polls its bus constantly - none of it says anything about radio coverage."""
        records = [telegram(), telegram(address='bus 5', role='bus_message'),
                   telegram(role='bus_message', address='bus 12')]

        result = survey(records, now=NOW)

        self.assertEqual(1, result['telegrams'])

    def test_what_a_gateway_read_off_its_bus_is_no_reception(self):
        """An FSR14 reaches its FAM14 over the wire - a wire has no signal strength to survey.

        Such a telegram is addressed relative to the base id of its gateway (`local_address`),
        and counting it would make every bus gateway the best receiver of the installation.
        """
        records = [telegram(),
                   telegram(gateway_id=2, gateway_name='FAM14', rssi_dbm=None,
                            address='FF-AA-BB-05', local_address='00-00-00-05')]

        result = survey(records, now=NOW)

        self.assertEqual(1, result['telegrams'])
        self.assertEqual(['FF-EE-DD-CC'], [link['address'] for link in result['links']])
        self.assertEqual([1], [gateway['gateway_id'] for gateway in result['gateways']])

    def test_a_radio_telegram_of_a_bus_gateway_still_counts(self):
        """A FAM14 receives by radio as well - what its antenna hears is a measurement."""
        records = [telegram(gateway_id=2, gateway_name='FAM14', rssi_dbm=None)]

        result = survey(records, now=NOW)

        self.assertEqual(1, result['telegrams'])
        self.assertEqual([2], [gateway['gateway_id'] for gateway in result['gateways']])

    def test_only_the_window_counts(self):
        records = [telegram(seconds_ago=1000), telegram(seconds_ago=30), telegram(seconds_ago=10)]

        result = survey(records, window_seconds=60, now=NOW)

        self.assertEqual(2, result['telegrams'])
        self.assertEqual(2, result['links'][0]['count'])

    def test_it_says_when_the_buffer_is_shorter_than_the_window(self):
        """Otherwise a survey silently describes 20 seconds and claims to describe an hour."""
        result = survey([telegram(seconds_ago=20)], window_seconds=3600, now=NOW)

        self.assertTrue(result['buffer_limited'])
        self.assertEqual((NOW - timedelta(seconds=20)).isoformat(), result['covers_from'])

    def test_a_full_window_is_not_marked(self):
        records = [telegram(seconds_ago=200), telegram(seconds_ago=10)]

        self.assertFalse(survey(records, window_seconds=60, now=NOW)['buffer_limited'])


class TestOneLinkPerSenderAndGateway(TestCase):
    """The same transmitter heard by two gateways is two links - that *is* the survey."""

    def test_the_same_sender_on_two_gateways(self):
        records = [
            telegram(gateway_id=1, gateway_name='FAM-USB', rssi_dbm=-60),
            telegram(gateway_id=2, gateway_name='USB300', rssi_dbm=-88),
        ]

        result = survey(records, now=NOW)

        self.assertEqual(2, len(result['links']))
        self.assertEqual([1, 2], [link['gateway_id'] for link in result['links']],
                         'the stronger link comes first')
        self.assertEqual('excellent', result['links'][0]['quality'])
        self.assertEqual('weak', result['links'][1]['quality'])

    def test_the_signal_is_summarized_over_the_window(self):
        records = [telegram(rssi_dbm=-60), telegram(rssi_dbm=-80), telegram(rssi_dbm=-70)]

        link = survey(records, now=NOW)['links'][0]

        self.assertEqual(-70, link['rssi']['last'])
        self.assertEqual(-70, link['rssi']['avg'])
        self.assertEqual(-80, link['rssi']['min'])
        self.assertEqual(-60, link['rssi']['max'])
        self.assertEqual('good', link['quality'])

    def test_a_gateway_without_signal_strength_still_delivers_a_survey(self):
        """An ESP2 stick reports no dBm - the counters and the repeaters are the measurement."""
        records = [telegram(rssi_dbm=None), telegram(rssi_dbm=None, repeated=True, rp_count=1)]

        result = survey(records, now=NOW)
        link = result['links'][0]

        self.assertFalse(result['has_rssi'])
        self.assertEqual(2, link['count'])
        self.assertIsNone(link['quality'])
        self.assertEqual(0.5, link['repeated_share'])

    def test_the_telegram_rate_is_per_minute(self):
        records = [telegram(seconds_ago=seconds) for seconds in range(0, 120, 10)]

        link = survey(records, window_seconds=120, now=NOW)['links'][0]

        self.assertEqual(12, link['count'])
        self.assertEqual(6.0, link['per_minute'])


class TestRepeatedTelegrams(TestCase):
    """A link which is mostly repeated is coverage which only exists through the repeater."""

    def test_the_repeater_count_marks_a_telegram(self):
        records = [telegram(), telegram(rp_count=1, repeated=True), telegram(rp_count=2)]

        link = survey(records, now=NOW)['links'][0]

        self.assertEqual(2, link['repeated'])
        self.assertEqual(round(2 / 3, 3), link['repeated_share'])

    def test_a_direct_link_has_no_repeated_share(self):
        link = survey([telegram(), telegram()], now=NOW)['links'][0]

        self.assertEqual(0, link['repeated'])
        self.assertEqual(0, link['repeated_share'])


class TestPerGateway(TestCase):
    """What one gateway hears from where it is - the number one compares between spots."""

    def test_the_average_is_weighted_by_the_telegrams(self):
        """A sender which is heard 10 times says more about this position than one heard once."""
        records = [telegram(address='AA-AA-AA-AA', rssi_dbm=-60) for _ in range(9)]
        records += [telegram(address='BB-BB-BB-BB', rssi_dbm=-90)]

        gateway = survey(records, now=NOW)['gateways'][0]

        self.assertEqual(10, gateway['telegrams'])
        self.assertEqual(2, gateway['senders'])
        self.assertEqual(-63.0, gateway['rssi_avg'])
        self.assertEqual('good', gateway['quality'])
        self.assertEqual(-90, gateway['worst'])
        self.assertEqual(-60, gateway['best'])

    def test_the_repeated_share_of_a_gateway_counts_all_its_links(self):
        records = [telegram(address='AA-AA-AA-AA'), telegram(address='BB-BB-BB-BB', rp_count=1),
                   telegram(address='BB-BB-BB-BB', rp_count=1)]

        gateway = survey(records, now=NOW)['gateways'][0]

        self.assertEqual(2, gateway['repeated'])
        self.assertEqual(round(2 / 3, 3), gateway['repeated_share'])

    def test_gateways_are_sorted_by_what_they_hear(self):
        records = [telegram(gateway_id=1, rssi_dbm=-85), telegram(gateway_id=2, rssi_dbm=-55)]

        gateways = survey(records, now=NOW)['gateways']

        self.assertEqual([2, 1], [gateway['gateway_id'] for gateway in gateways])


class TestWalkingAround(TestCase):
    """Carrying a transmitter: only that address matters, and the window is short."""

    def test_one_address_can_be_watched(self):
        records = [telegram(address='AA-AA-AA-AA'), telegram(address='BB-BB-BB-BB')]

        result = survey(records, address='aa-aa-aa-aa', now=NOW)

        self.assertEqual(1, len(result['links']))
        self.assertEqual('AA-AA-AA-AA', result['links'][0]['address'])

    def test_one_gateway_can_be_watched(self):
        records = [telegram(gateway_id=1), telegram(gateway_id=2)]

        result = survey(records, gateway_id=2, now=NOW)

        self.assertEqual([2], [link['gateway_id'] for link in result['links']])

    def test_a_short_window_follows_the_movement(self):
        """What was measured two rooms ago must not be part of the reading here."""
        records = [telegram(seconds_ago=90, rssi_dbm=-55), telegram(seconds_ago=5, rssi_dbm=-88)]

        result = survey(records, window_seconds=30, now=NOW)

        self.assertEqual(-88, result['links'][0]['rssi']['avg'])
        self.assertEqual('weak', result['links'][0]['quality'])

    def test_nothing_heard_is_a_valid_answer(self):
        result = survey([], now=NOW)

        self.assertEqual(0, result['telegrams'])
        self.assertEqual([], result['links'])
        self.assertEqual([], result['gateways'])
        self.assertFalse(result['has_rssi'])


class TestTheWebsocketCommand(TestCase):

    def _call(self, records, **payload):
        connection = mock.Mock()
        connection.results = []
        connection.send_result = lambda _id, result: connection.results.append(result)

        logger = mock.Mock()
        logger.get_recent_telegrams = lambda limit=0: records
        logger.buffer_size = 500

        handler = reception.ws_reception_survey
        while hasattr(handler, '__wrapped__'):
            handler = handler.__wrapped__
        with mock.patch('custom_components.eltako.observation.enocean_logger.get_telegram_logger',
                        return_value=logger if records is not None else None):
            handler(mock.Mock(), connection, {'id': 1, 'window': 60, **payload})
        return connection.results[0]

    def test_it_answers_from_the_recorded_telegrams(self):
        result = self._call([telegram(), telegram(gateway_id=2, rssi_dbm=-90)])

        self.assertTrue(result['recording'])
        self.assertEqual(2, result['telegrams'])
        self.assertEqual(2, len(result['gateways']))
        self.assertEqual(500, result['buffer_size'])

    def test_without_recording_it_says_so_instead_of_failing(self):
        result = self._call(None)

        self.assertFalse(result['recording'])
        self.assertEqual([], result['links'])

    def test_a_broken_buffer_does_not_break_the_panel(self):
        connection = mock.Mock()
        connection.results = []
        connection.send_result = lambda _id, result: connection.results.append(result)
        logger = mock.Mock()
        logger.get_recent_telegrams = mock.Mock(side_effect=RuntimeError("buffer is gone"))

        handler = reception.ws_reception_survey
        while hasattr(handler, '__wrapped__'):
            handler = handler.__wrapped__
        with mock.patch('custom_components.eltako.observation.enocean_logger.get_telegram_logger',
                        return_value=logger):
            handler(mock.Mock(), connection, {'id': 1, 'window': 60})

        self.assertEqual(0, connection.results[0]['telegrams'])


if __name__ == '__main__':
    unittest.main()
