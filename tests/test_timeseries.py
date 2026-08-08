"""Export of telegrams into a timeseries database (InfluxDB line protocol)."""
import json
import os
import tempfile
import unittest
from unittest import TestCase

from custom_components.eltako.const import (CONF_TIMESERIES_BUCKET, CONF_TIMESERIES_ENABLED,
                                            CONF_TIMESERIES_ORG, CONF_TIMESERIES_TOKEN, CONF_TIMESERIES_URL)
from custom_components.eltako.observation.timeseries import (
    TimeseriesExporter,
    backfill_log_files,
    create_exporter_from_settings,
    record_to_line_protocol,
)


def record(**overrides) -> dict:
    base = {
        'timestamp': '2026-08-04T10:00:00.000+00:00',
        'direction': 'incoming',
        'gateway_id': 1,
        'msg_type': 'Regular4BSMessage',
        'address': 'FF-AA-DD-81',
        'device_name': 'Temp Living Room',
        'eep': 'A5-04-02',
        'area': 'Living room',
        'known': True,
        'role': 'device',
        'platforms': ['sensor'],
        'status': '0x00',
        'data': '12-34-56-78',
        'decoded': {'temperature': 21.5, 'humidity': 44.0},
    }
    base.update(overrides)
    return base


class TestLineProtocol(TestCase):

    def test_full_record(self):
        line = record_to_line_protocol(record(), 'eltako_telegram')

        measurement_and_tags, fields, timestamp = line.rsplit(' ', 2)
        self.assertTrue(measurement_and_tags.startswith('eltako_telegram,'))
        self.assertIn('address=FF-AA-DD-81', measurement_and_tags)
        self.assertIn('device_name=Temp\\ Living\\ Room', measurement_and_tags)
        self.assertIn('area=Living\\ room', measurement_and_tags)
        self.assertIn('eep=A5-04-02', measurement_and_tags)
        self.assertIn('platform=sensor', measurement_and_tags)
        self.assertIn('known=True', measurement_and_tags)

        self.assertIn('count=1i', fields)
        self.assertIn('temperature=21.5', fields)
        self.assertIn('humidity=44.0', fields)
        self.assertIn('status="0x00"', fields)
        self.assertIn('data="12-34-56-78"', fields)

        # timestamp of the telegram in nanoseconds
        from datetime import datetime
        expected = int(datetime.fromisoformat('2026-08-04T10:00:00.000+00:00').timestamp())
        self.assertEqual(timestamp, str(expected * 1_000_000_000))

    def test_record_without_timestamp_is_skipped(self):
        self.assertIsNone(record_to_line_protocol(record(timestamp=None), 'm'))
        self.assertIsNone(record_to_line_protocol(record(timestamp='not-a-date'), 'm'))

    def test_telegrams_of_the_same_microsecond_keep_distinct_timestamps(self):
        """InfluxDB overwrites a point with the same measurement + tags + timestamp. Telegrams
        are events, not samples: a burst (repeaters, a command repeated through several
        gateways) shares address, type and microsecond. Without the sequence number filling
        the nanoseconds, only the last telegram of such a burst survives - verified against a
        real InfluxDB, where 20 telegrams collapsed into 2 points."""
        lines = [record_to_line_protocol(record(seq=seq), 'm') for seq in range(1, 21)]
        timestamps = [line.rsplit(' ', 1)[1] for line in lines]

        self.assertEqual(len(set(timestamps)), 20)
        # tags and fields stay identical - only the nanoseconds differ
        self.assertEqual(len({line.rsplit(' ', 1)[0] for line in lines}), 1)
        # the introduced offset stays below one microsecond
        self.assertLess(max(int(t) for t in timestamps) - min(int(t) for t in timestamps), 1000)

    def test_missing_sequence_number_does_not_break_the_line(self):
        line = record_to_line_protocol(record(seq=None), 'm')

        self.assertIsNotNone(line)
        self.assertTrue(line.rsplit(' ', 1)[1].isdigit())

    def test_missing_meta_data_produces_no_empty_tags(self):
        line = record_to_line_protocol(record(device_name=None, area=None, eep=None,
                                              platforms=[], decoded=None), 'm')

        self.assertNotIn('device_name=', line)
        self.assertNotIn('area=', line)
        self.assertNotIn('platform=', line)
        self.assertIn('count=1i', line)

    def test_field_types(self):
        line = record_to_line_protocol(record(decoded={
            'temperature': 21.5,        # float
            'rocker_first_action': 3,   # int -> 3i
            'button_pushed': True,      # bool
            'mode': 'heating',          # string, quoted
            'raw_bytes': b'\x01',       # not representable -> dropped
        }), 'm')

        self.assertIn('temperature=21.5', line)
        self.assertIn('rocker_first_action=3i', line)
        self.assertIn('button_pushed=true', line)
        self.assertIn('mode="heating"', line)
        self.assertNotIn('raw_bytes', line)

    def test_escaping(self):
        line = record_to_line_protocol(record(device_name='a=b,c d', decoded={'note': 'say "hi"'}), 'my measurement')

        self.assertTrue(line.startswith('my\\ measurement,'))
        self.assertIn('device_name=a\\=b\\,c\\ d', line)
        self.assertIn('note="say \\"hi\\""', line)


class ExporterWithoutNetwork(TimeseriesExporter):
    """Collects the posted bodies instead of talking to a real InfluxDB."""

    def __init__(self, fail: bool = False, **kwargs):
        kwargs.setdefault('url', 'http://influx:8086')
        kwargs.setdefault('token', 't')
        kwargs.setdefault('org', 'o')
        kwargs.setdefault('bucket', 'b')
        super().__init__(**kwargs)
        self.posted: list[str] = []
        self.fail = fail

    def _post(self, body: str) -> None:
        if self.fail:
            raise RuntimeError("db is down")
        self.posted.append(body)


class TestExporter(TestCase):

    def _run(self, exporter: TimeseriesExporter, records: list[dict]) -> None:
        exporter.start()
        for entry in records:
            exporter.submit(entry)
        exporter.stop()
        exporter.join(10)
        self.assertFalse(exporter.is_alive())

    def test_records_are_exported_in_batches(self):
        exporter = ExporterWithoutNetwork()
        self._run(exporter, [record(), record(address='FF-AA-DD-82')])

        self.assertEqual(exporter.exported_count, 2)
        self.assertEqual(exporter.failed_count, 0)
        lines = '\n'.join(exporter.posted).split('\n')
        self.assertEqual(len(lines), 2)
        self.assertIsNotNone(exporter.last_export_at)
        self.assertIsNone(exporter.last_error)

    def test_failures_are_counted_not_raised(self):
        exporter = ExporterWithoutNetwork(fail=True)
        self._run(exporter, [record()])

        self.assertEqual(exporter.exported_count, 0)
        self.assertEqual(exporter.failed_count, 1)
        self.assertIn("db is down", exporter.last_error)

    def test_records_without_timestamp_are_dropped_silently(self):
        exporter = ExporterWithoutNetwork()
        self._run(exporter, [record(timestamp=None), record()])

        self.assertEqual(exporter.exported_count, 1)

    def test_status(self):
        exporter = ExporterWithoutNetwork()
        self._run(exporter, [record()])

        status = exporter.get_status()
        self.assertEqual(status['exported_count'], 1)
        self.assertEqual(status['bucket'], 'b')
        self.assertEqual(status['queued_count'], 0)
        self.assertIsNotNone(status['last_export_at'])


class TestCreateFromSettings(TestCase):

    def test_disabled(self):
        self.assertIsNone(create_exporter_from_settings({CONF_TIMESERIES_ENABLED: False}))

    def test_enabled_without_url_stays_off(self):
        self.assertIsNone(create_exporter_from_settings({CONF_TIMESERIES_ENABLED: True,
                                                         CONF_TIMESERIES_URL: '  '}))

    def test_enabled(self):
        exporter = create_exporter_from_settings({
            CONF_TIMESERIES_ENABLED: True,
            CONF_TIMESERIES_URL: 'http://influx:8086/',
            CONF_TIMESERIES_TOKEN: 'token',
            CONF_TIMESERIES_ORG: 'home',
            CONF_TIMESERIES_BUCKET: 'eltako',
        })
        self.assertIsNotNone(exporter)
        self.assertEqual(exporter.url, 'http://influx:8086')    # trailing slash stripped
        self.assertEqual(exporter.measurement, 'eltako_telegram')


class TestBackfill(TestCase):

    def test_backfill_reads_all_rotated_files_oldest_first(self):
        directory = tempfile.mkdtemp()
        path = os.path.join(directory, 'telegrams.jsonl')
        with open(f"{path}.2", 'w') as file:
            file.write(json.dumps(record(address='0-OLDEST')) + '\n')
        with open(f"{path}.1", 'w') as file:
            file.write(json.dumps(record(address='1-MIDDLE')) + '\n')
        with open(path, 'w') as file:
            file.write(json.dumps(record(address='2-NEWEST')) + '\n')
            file.write('not json\n')                                    # skipped
            file.write(json.dumps({'no': 'timestamp'}) + '\n')          # skipped

        exporter = ExporterWithoutNetwork()
        result = backfill_log_files(exporter, path)
        exporter.start()
        exporter.stop()
        exporter.join(10)

        self.assertEqual(result, {'files': 3, 'submitted': 3, 'skipped': 2})
        body = '\n'.join(exporter.posted)
        self.assertLess(body.index('0-OLDEST'), body.index('1-MIDDLE'))
        self.assertLess(body.index('1-MIDDLE'), body.index('2-NEWEST'))

    def test_backfill_without_files(self):
        exporter = ExporterWithoutNetwork()
        result = backfill_log_files(exporter, os.path.join(tempfile.mkdtemp(), 'missing.jsonl'))

        self.assertEqual(result, {'files': 0, 'submitted': 0, 'skipped': 0})


if __name__ == '__main__':
    unittest.main()
