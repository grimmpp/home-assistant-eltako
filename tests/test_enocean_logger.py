import asyncio
import json
import os
import tempfile
import threading
import unittest
from unittest import IsolatedAsyncioTestCase, TestCase

from tests.mocks import *

from custom_components.eltako.const import *
from custom_components.eltako import config_helpers
from custom_components.eltako.config_helpers import DEFAULT_GENERAL_SETTINGS
from custom_components.eltako.enocean_logger import (
    EnOceanTelegramLogger,
    TelegramFileWriter,
    _json_safe,
    decoded_eep_to_dict,
    get_telegram_logger,
    is_telegram_logging_enabled,
)
from custom_components.eltako.schema import CONFIG_SCHEMA

from eltakobus.eep import A5_04_02, F6_02_01
from eltakobus.message import EltakoDiscoveryRequest, EltakoPoll, RPSMessage, Regular4BSMessage, TeachIn4BSMessage2
from eltakobus.util import AddressExpression


def get_general_settings(**overrides) -> dict:
    settings = dict(DEFAULT_GENERAL_SETTINGS)
    settings.update(overrides)
    return settings


class HassDataMock(HassMock):
    """Hass mock which additionally provides the data dict and the config folder."""

    def __init__(self, config: dict = None, config_dir: str = "/config"):
        super().__init__()
        self.data = {
            DATA_ELTAKO: {
                ELTAKO_CONFIG: config if config is not None else {},
            }
        }
        self.config = ConfigMock(config_dir)


class ConfigMock:
    def __init__(self, config_dir: str):
        self.config_dir = config_dir

    def path(self, *args) -> str:
        return os.path.join(self.config_dir, *args)


class TestEnabledDetection(TestCase):

    def test_disabled_by_default(self):
        self.assertFalse(is_telegram_logging_enabled(get_general_settings()))

    def test_enabled_by_flag(self):
        self.assertTrue(is_telegram_logging_enabled(get_general_settings(**{CONF_LOG_ENOCEAN_TELEGRAMS: True})))

    def test_enabled_by_filename(self):
        """Providing a filename is enough to enable telegram logging."""
        self.assertTrue(is_telegram_logging_enabled(get_general_settings(**{CONF_TELEGRAM_LOG_FILENAME: "telegrams.jsonl"})))
        self.assertFalse(is_telegram_logging_enabled(get_general_settings(**{CONF_TELEGRAM_LOG_FILENAME: "   "})))

    def test_get_telegram_logger_is_defensive(self):
        self.assertIsNone(get_telegram_logger(HassMock()))
        self.assertIsNone(get_telegram_logger(HassDataMock()))


class TestGeneralSettingsSchema(TestCase):

    def test_defaults_of_telegram_log_settings(self):
        config = CONFIG_SCHEMA({DOMAIN: {CONF_GERNERAL_SETTINGS: {}}})[DOMAIN][CONF_GERNERAL_SETTINGS]

        self.assertFalse(config[CONF_LOG_ENOCEAN_TELEGRAMS])
        self.assertEqual(config[CONF_TELEGRAM_LOG_FILENAME], "")
        self.assertEqual(config[CONF_TELEGRAM_LOG_FORMAT], TelegramLogFormat.JSONL.value)
        self.assertEqual(config[CONF_TELEGRAM_LOG_MAX_FILE_SIZE_MB], 10)
        self.assertEqual(config[CONF_TELEGRAM_LOG_BACKUP_COUNT], 3)
        self.assertFalse(config[CONF_TELEGRAM_LOG_INCLUDE_POLLING])
        self.assertTrue(config[CONF_TELEGRAM_LOG_DECODE_EEP])
        self.assertEqual(config[CONF_TELEGRAM_LOG_BUFFER_SIZE], 500)

        # all schema keys need a default in DEFAULT_GENERAL_SETTINGS as well
        for key in config.keys():
            self.assertIn(key, DEFAULT_GENERAL_SETTINGS)

    def test_custom_telegram_log_settings(self):
        config = CONFIG_SCHEMA({DOMAIN: {CONF_GERNERAL_SETTINGS: {
            CONF_LOG_ENOCEAN_TELEGRAMS: True,
            CONF_TELEGRAM_LOG_FILENAME: "enocean.csv",
            CONF_TELEGRAM_LOG_FORMAT: "csv",
            CONF_TELEGRAM_LOG_BUFFER_SIZE: 42,
        }}})[DOMAIN][CONF_GERNERAL_SETTINGS]

        self.assertTrue(config[CONF_LOG_ENOCEAN_TELEGRAMS])
        self.assertEqual(config[CONF_TELEGRAM_LOG_FILENAME], "enocean.csv")
        self.assertEqual(config[CONF_TELEGRAM_LOG_FORMAT], TelegramLogFormat.CSV.value)
        self.assertEqual(config[CONF_TELEGRAM_LOG_BUFFER_SIZE], 42)


class TestJsonSafeConversion(TestCase):

    def test_values_are_json_serializable(self):
        values = {
            'enum': GatewayDeviceType.GatewayEltakoFGW14USB,
            'address_expression': AddressExpression.parse('FF-AA-80-01'),
            'bytes': b'\x01\xAB',
            'float': 1.23456789,
            'list': [1, b'\xFF', GatewayDeviceType.LAN],
            'object': object(),
        }

        converted = {key: _json_safe(value) for key, value in values.items()}

        self.assertEqual(converted['enum'], 'fgw14usb')
        self.assertEqual(converted['address_expression'], 'FF-AA-80-01')
        self.assertEqual(converted['bytes'], '01-AB')
        self.assertEqual(converted['float'], 1.2346)
        self.assertEqual(converted['list'], [1, 'FF', 'lan'])
        self.assertIsInstance(converted['object'], str)

        # json.dumps must not fall back to the default= handler
        json.dumps(converted)


class TestFrontendSettings(TestCase):
    """The web ui is controlled by one single option, deprecated ones still work."""

    def test_frontend_disabled_by_default(self):
        self.assertFalse(config_helpers.is_frontend_enabled(get_general_settings()))

    def test_frontend_enabled(self):
        self.assertTrue(config_helpers.is_frontend_enabled(get_general_settings(**{CONF_ENABLE_FRONTEND: True})))

    def test_deprecated_option_still_enables_the_frontend(self):
        settings = get_general_settings()
        settings[CONF_DEPRECATED_ENABLE_FRONTEND] = True

        self.assertTrue(config_helpers.is_frontend_enabled(settings))

    def test_deprecated_options_are_reported(self):
        settings = get_general_settings(**{CONF_ENABLE_FRONTEND: True})
        self.assertEqual(config_helpers.log_deprecated_general_settings(settings), [])

        settings[CONF_DEPRECATED_ENABLE_FRONTEND] = True
        settings[CONF_DEPRECATED_FRONTEND_DEV_URL] = "http://localhost:5173"
        settings[CONF_DEPRECATED_ENABLE_TELEGRAM_WEB_UI] = True

        self.assertEqual(sorted(config_helpers.log_deprecated_general_settings(settings)),
                         sorted([CONF_DEPRECATED_ENABLE_FRONTEND, CONF_DEPRECATED_FRONTEND_DEV_URL,
                                 CONF_DEPRECATED_ENABLE_TELEGRAM_WEB_UI]))

    def test_deprecated_options_do_not_break_the_configuration(self):
        """Existing configurations with the old option names must still be valid."""
        config = CONFIG_SCHEMA({DOMAIN: {CONF_GERNERAL_SETTINGS: {
            CONF_DEPRECATED_ENABLE_FRONTEND: True,
            CONF_DEPRECATED_FRONTEND_DEV_URL: "http://localhost:5173",
            CONF_DEPRECATED_ENABLE_TELEGRAM_WEB_UI: False,
        }}})[DOMAIN][CONF_GERNERAL_SETTINGS]

        self.assertTrue(config_helpers.is_frontend_enabled(config))
        # the new option is not set, so its default is used
        self.assertFalse(config[CONF_ENABLE_FRONTEND])

    FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                'custom_components', 'eltako', 'frontend')

    def test_frontend_files_exist(self):
        self.assertTrue(os.path.isfile(os.path.join(self.FRONTEND_DIR, PANEL_JS_FILE)))
        for module in ['lib/api.js', 'lib/utils.js', 'lib/styles.js',
                       'pages/overview.js', 'pages/telegrams.js', 'pages/devices.js',
                       'pages/unknown.js', 'pages/about.js']:
            self.assertTrue(os.path.isfile(os.path.join(self.FRONTEND_DIR, *module.split('/'))), msg=module)

        # the frontend folder is served as static path, it must not contain any python code
        for root, _dirs, files in os.walk(self.FRONTEND_DIR):
            for file in files:
                self.assertFalse(file.endswith('.py'), msg=f"{os.path.join(root, file)} is not frontend code")

    def test_frontend_files_are_not_excluded_by_gitignore(self):
        """The frontend is shipped with the integration. Rules like 'lib/' must not exclude it."""
        import shutil
        import subprocess

        if shutil.which('git') is None:      # pragma: no cover - git is not available
            self.skipTest("git is not available")

        frontend_files = [os.path.join(root, file)
                          for root, _dirs, files in os.walk(self.FRONTEND_DIR)
                          for file in files if file.endswith('.js')]
        self.assertTrue(len(frontend_files) > 5)

        # 'git check-ignore' returns the files which would NOT be committed
        result = subprocess.run(['git', 'check-ignore', *frontend_files],
                                cwd=os.path.dirname(self.FRONTEND_DIR), capture_output=True, text=True)
        ignored = [line for line in result.stdout.splitlines() if line.strip()]
        self.assertEqual(ignored, [], msg=f"These frontend files are excluded by .gitignore: {ignored}")


class TestDecodedEepToDict(TestCase):

    def test_decode_temperature_and_humidity(self):
        decoded = decoded_eep_to_dict(A5_04_02(21.5, 44.0))

        self.assertIn('current_temperature', decoded)
        self.assertIn('humidity', decoded)
        self.assertEqual(decoded['current_temperature'], 21.5)
        # class attributes (temp_min, temp_max, ...) are not part of the result
        self.assertNotIn('temp_max', decoded)

    def test_decode_rocker_switch(self):
        decoded = decoded_eep_to_dict(F6_02_01(0x10, True, 0, False))

        self.assertEqual(decoded['rocker_first_action'], 0x10)
        self.assertTrue(decoded['energy_bow'])
        # everything must be json serializable
        json.dumps(decoded)


class TestTelegramRecording(TestCase):

    GATEWAY_BASE_ID = AddressExpression.parse('FF-AA-80-00')

    def setUp(self):
        self.gateway = GatewayMock(base_id=self.GATEWAY_BASE_ID)
        self.hass = HassDataMock(config={
            CONF_GATEWAY: [{
                CONF_ID: self.gateway.dev_id,
                CONF_BASE_ID: 'FF-AA-80-00',
                CONF_DEVICES: {
                    'sensor': [{
                        CONF_ID: 'FF-AA-DD-81',
                        CONF_EEP: 'A5-04-02',
                        CONF_NAME: 'Temperature Sensor',
                        CONF_AREA: 'Living Room',
                    }],
                    'light': [{
                        CONF_ID: '00-00-00-01',
                        CONF_EEP: 'M5-38-08',
                        CONF_NAME: 'FSR14 - 1',
                        CONF_SENDER: {CONF_ID: '00-00-B0-01', CONF_EEP: 'A5-38-08'},
                    }],
                },
            }],
        })
        self.gateway.hass = self.hass
        self.logger = EnOceanTelegramLogger(self.hass, get_general_settings(**{CONF_LOG_ENOCEAN_TELEGRAMS: True}))
        self.logger.refresh_device_map()

    def record(self, msg, direction=TelegramDirection.INCOMING) -> dict:
        self.logger.record_message(self.gateway, msg, direction.value)
        telegrams = self.logger.get_recent_telegrams()
        return telegrams[-1] if telegrams else None

    def test_known_device_is_resolved_and_decoded(self):
        # A5-04-02: humidity in data[1], temperature in data[2]
        msg = Regular4BSMessage(address=b'\xFF\xAA\xDD\x81', status=0x00, data=b'\x00\x7D\x7D\x0A')

        record = self.record(msg)

        self.assertEqual(record['address'], 'FF-AA-DD-81')
        self.assertTrue(record['known'])
        self.assertEqual(record['eep'], 'A5-04-02')
        self.assertEqual(record['device_name'], 'Temperature Sensor')
        self.assertEqual(record['area'], 'Living Room')
        self.assertEqual(record['role'], 'device')
        self.assertEqual(record['platforms'], ['sensor'])
        self.assertEqual(record['direction'], TelegramDirection.INCOMING.value)
        self.assertEqual(record['gateway_id'], self.gateway.dev_id)
        self.assertEqual(record['gateway_type'], GatewayDeviceType.GatewayEltakoFAM14.value)
        self.assertEqual(record['msg_type'], 'Regular4BSMessage')
        self.assertEqual(record['data'], '00-7D-7D-0A')
        self.assertIsNotNone(record['raw'])
        self.assertAlmostEqual(record['decoded']['current_temperature'], 20.0, places=1)
        self.assertAlmostEqual(record['decoded']['humidity'], 50.0, places=1)

    def test_unknown_device_is_marked(self):
        record = self.record(RPSMessage(address=b'\x12\x34\x56\x78', status=0x30, data=b'\x10'))

        self.assertEqual(record['address'], '12-34-56-78')
        self.assertFalse(record['known'])
        self.assertIsNone(record['eep'])
        self.assertNotIn('decoded', record)
        self.assertEqual(record['entity_ids'], [])

    def test_local_bus_address_is_translated_to_external_address(self):
        """Devices of a bus gateway use addresses relative to the base id of the gateway."""
        record = self.record(Regular4BSMessage(address=b'\x00\x00\x00\x01', status=0x00, data=b'\x01\x02\x03\x04'))

        self.assertEqual(record['local_address'], '00-00-00-01')
        self.assertEqual(record['address'], 'FF-AA-80-01')
        self.assertTrue(record['known'])
        self.assertEqual(record['device_name'], 'FSR14 - 1')
        self.assertEqual(record['eep'], 'M5-38-08')

    def test_configured_sender_is_known_as_well(self):
        record = self.record(Regular4BSMessage(address=b'\x00\x00\xB0\x01', status=0x00, data=b'\x01\x02\x03\x04'),
                             TelegramDirection.OUTGOING)

        self.assertTrue(record['known'])
        self.assertEqual(record['role'], 'sender')
        self.assertEqual(record['direction'], TelegramDirection.OUTGOING.value)

    def test_polling_telegrams_are_filtered_by_default(self):
        self.logger.record_message(self.gateway, EltakoPoll(1), TelegramDirection.INCOMING.value)

        self.assertEqual(self.logger.get_recent_telegrams(), [])
        self.assertEqual(self.logger.get_info()['total_count'], 0)
        self.assertEqual(self.logger.get_info()['filtered_count'], 1)

    def test_polling_telegrams_can_be_included(self):
        logger = EnOceanTelegramLogger(self.hass, get_general_settings(**{
            CONF_LOG_ENOCEAN_TELEGRAMS: True,
            CONF_TELEGRAM_LOG_INCLUDE_POLLING: True,
        }))
        logger.record_message(self.gateway, EltakoPoll(3), TelegramDirection.INCOMING.value)

        telegrams = logger.get_recent_telegrams()
        self.assertEqual(len(telegrams), 1)
        self.assertEqual(telegrams[0]['msg_type'], 'EltakoPoll')
        self.assertEqual(telegrams[0]['bus_address'], 3)

    def test_bus_messages_are_counted_as_well(self):
        """Bus internal telegrams have no EnOcean address but must not get lost in the statistics."""
        record = self.record(EltakoDiscoveryRequest(8))

        self.assertEqual(record['bus_address'], 8)
        self.assertEqual(record['address'], 'bus 8')
        self.assertEqual(record['role'], 'bus_message')
        self.assertFalse(record['known'])

        statistics = self.logger.get_statistics()
        self.assertEqual(statistics['summary']['total_count'], 1)
        self.assertEqual(statistics['summary']['device_count'], 1)
        self.assertEqual(statistics['devices'][0]['address'], 'bus 8')
        self.assertEqual(statistics['devices'][0]['role'], 'bus_message')

        # they are counted separately: neither a known nor a configurable unknown device
        self.assertEqual(statistics['summary']['bus_message_count'], 1)
        self.assertEqual(statistics['summary']['unknown_device_count'], 0)
        self.assertEqual(statistics['summary']['known_device_count'], 0)

    def test_statistics(self):
        for _ in range(3):
            self.record(Regular4BSMessage(address=b'\xFF\xAA\xDD\x81', status=0x00, data=b'\x00\x7D\x7D\x0A'))
        self.record(RPSMessage(address=b'\x12\x34\x56\x78', status=0x30, data=b'\x10'))

        statistics = self.logger.get_statistics()

        self.assertEqual(statistics['summary']['total_count'], 4)
        self.assertEqual(statistics['summary']['device_count'], 2)
        self.assertEqual(statistics['summary']['known_device_count'], 1)
        self.assertEqual(statistics['summary']['unknown_device_count'], 1)
        self.assertEqual(statistics['summary']['count_by_msg_type']['Regular4BSMessage'], 3)

        known = [d for d in statistics['devices'] if d['address'] == 'FF-AA-DD-81'][0]
        self.assertEqual(known['count'], 3)
        self.assertEqual(known['count_incoming'], 3)
        self.assertEqual(known['count_outgoing'], 0)
        self.assertEqual(known['eep'], 'A5-04-02')
        self.assertIsNotNone(known['first_seen'])
        self.assertIsNotNone(known['avg_interval'])
        self.assertIsNotNone(known['last_decoded'])

        # statistics are serializable so that they can be sent via websocket
        json.dumps(statistics)

    def test_teach_in_telegram_reveals_eep_of_unknown_device(self):
        # 4BS teach-in telegram of profile A5-04-02 sent by manufacturer 11
        record = self.record(TeachIn4BSMessage2(address=b'\x11\x22\x33\x44', status=0x00,
                                               data=bytes((0x10, 0x10, 0x0B, 0x00))))

        self.assertFalse(record['known'])
        self.assertEqual(record['teach_in_profile'], 'A5-04-02')
        self.assertEqual(record['teach_in_manufacturer'], 11)

        statistics = [d for d in self.logger.get_statistics()['devices'] if d['address'] == '11-22-33-44'][0]
        self.assertEqual(statistics['teach_in_count'], 1)
        self.assertEqual(statistics['teach_in_profile'], 'A5-04-02')

    def test_telegram_of_a_taught_in_device_is_decoded_although_it_is_not_configured(self):
        """The profile of a teach-in telegram is remembered so that the values are shown."""
        teach_in = self.record(TeachIn4BSMessage2(address=b'\x11\x22\x33\x44', status=0x00,
                                                  data=bytes((0x10, 0x10, 0x0B, 0x00))))
        # the teach-in telegram itself carries the profile instead of values
        self.assertNotIn('decoded', teach_in)

        record = self.record(Regular4BSMessage(address=b'\x11\x22\x33\x44', status=0x00, data=b'\x00\x7D\x7D\x0A'))

        self.assertFalse(record['known'])
        self.assertIsNone(record['eep'])
        self.assertEqual(record['decoded_eep'], 'A5-04-02')
        self.assertEqual(record['decoded_source'], 'teach_in')
        self.assertAlmostEqual(record['decoded']['current_temperature'], 20.0, places=1)
        self.assertAlmostEqual(record['decoded']['humidity'], 50.0, places=1)

    def test_configured_eep_wins_over_a_teach_in_profile(self):
        teach_in = self.record(TeachIn4BSMessage2(address=b'\xFF\xAA\xDD\x81', status=0x00,
                                                  data=bytes((0x07, 0x28, 0x0B, 0x00))))
        # a teach-in telegram carries the profile, decoding it as sensor data would be nonsense
        self.assertNotIn('decoded', teach_in)

        record = self.record(Regular4BSMessage(address=b'\xFF\xAA\xDD\x81', status=0x00, data=b'\x00\x7D\x7D\x0A'))

        self.assertEqual(record['decoded_eep'], 'A5-04-02')
        self.assertEqual(record['decoded_source'], 'device')

    def test_a_wrong_teach_in_profile_is_not_counted_as_a_decode_error(self):
        """A remembered profile is a guess - only a configured EEP which does not fit is an error."""
        self.record(TeachIn4BSMessage2(address=b'\x11\x22\x33\x44', status=0x00,
                                       data=bytes((0x10, 0x10, 0x0B, 0x00))))

        record = self.record(RPSMessage(address=b'\x11\x22\x33\x44', status=0x30, data=b'\x10'))

        self.assertIsNone(record['decoded'])
        self.assertEqual(self.logger.get_info()['decode_error_count'], 0)

    def test_decoding_can_be_switched_off(self):
        logger = EnOceanTelegramLogger(self.hass, get_general_settings(**{
            CONF_LOG_ENOCEAN_TELEGRAMS: True,
            CONF_TELEGRAM_LOG_DECODE_EEP: False,
        }))
        logger.refresh_device_map()
        logger.record_message(self.gateway, Regular4BSMessage(address=b'\xFF\xAA\xDD\x81', status=0x00,
                                                              data=b'\x00\x7D\x7D\x0A'), 'incoming')

        self.assertNotIn('decoded', logger.get_recent_telegrams()[-1])

    def test_clear(self):
        self.record(RPSMessage(address=b'\x12\x34\x56\x78', status=0x30, data=b'\x10'))
        self.assertEqual(self.logger.get_info()['total_count'], 1)

        self.logger.clear()

        self.assertEqual(self.logger.get_info()['total_count'], 0)
        self.assertEqual(self.logger.get_recent_telegrams(), [])
        self.assertEqual(self.logger.get_statistics()['devices'], [])

    def test_buffer_size_is_limited(self):
        logger = EnOceanTelegramLogger(self.hass, get_general_settings(**{
            CONF_LOG_ENOCEAN_TELEGRAMS: True,
            CONF_TELEGRAM_LOG_BUFFER_SIZE: 5,
        }))
        for i in range(20):
            logger.record_message(self.gateway, RPSMessage(address=b'\x12\x34\x56\x78', status=0x30, data=bytes([i])),
                                  TelegramDirection.INCOMING.value)

        self.assertEqual(len(logger.get_recent_telegrams()), 5)
        self.assertEqual(logger.get_info()['total_count'], 20)

    def test_recording_does_not_raise_on_broken_telegram(self):
        class BrokenMessage:
            org = property(lambda self: 1 / 0)

        self.logger.record_message(self.gateway, BrokenMessage(), TelegramDirection.INCOMING.value)

        # no exception, telegram is counted as recorded (org is optional)
        self.assertEqual(self.logger.get_info()['error_count'], 0)


class TestLiveSubscription(IsolatedAsyncioTestCase):
    """The live view of the web ui is fed by subscribers which must be called inside the event loop."""

    async def asyncSetUp(self):
        self.gateway = GatewayMock()
        self.hass = HassDataMock()
        self.hass.loop = asyncio.get_running_loop()
        self.gateway.hass = self.hass
        self.logger = EnOceanTelegramLogger(self.hass, get_general_settings(**{CONF_LOG_ENOCEAN_TELEGRAMS: True}))

    def send_telegram(self):
        self.logger.record_message(self.gateway, RPSMessage(address=b'\x12\x34\x56\x78', status=0x30, data=b'\x10'),
                                   TelegramDirection.INCOMING.value)

    async def test_subscribers_get_notified_and_can_be_removed(self):
        received = []
        remove = self.logger.add_subscriber(received.append)

        self.send_telegram()
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]['address'], '12-34-56-78')

        remove()
        self.send_telegram()
        self.assertEqual(len(received), 1)

    async def test_telegrams_recorded_in_another_thread_are_forwarded_into_the_event_loop(self):
        """Telegrams are received in the serial bus thread, the websocket api needs the event loop."""
        received = []
        self.logger.add_subscriber(lambda record: received.append((record, threading.current_thread())))

        thread = threading.Thread(target=self.send_telegram)
        thread.start()
        thread.join(5)

        self.assertEqual(len(received), 0)      # scheduled into the event loop, not called in the bus thread
        await asyncio.sleep(0)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0][1], threading.current_thread())
        self.assertEqual(self.logger.get_info()['total_count'], 1)


class TestTelegramFileWriter(TestCase):

    def write_records(self, log_format: str, records: list[dict], max_bytes: int = 0, backup_count: int = 3) -> str:
        directory = tempfile.mkdtemp()
        path = os.path.join(directory, 'sub-folder', f"telegrams.{log_format}")
        writer = TelegramFileWriter(path, log_format, max_bytes, backup_count)
        writer.start()
        for record in records:
            writer.submit(record)
        writer.stop()
        writer.join(10)
        self.assertFalse(writer.is_alive())
        self.assertIsNone(writer.last_error)
        return path

    def test_jsonl_file(self):
        records = [
            {'seq': 1, 'address': 'FF-AA-DD-81', 'decoded': {'temperature': 21.5}, 'entity_ids': ['sensor.a']},
            {'seq': 2, 'address': '12-34-56-78', 'known': False},
        ]

        path = self.write_records(TelegramLogFormat.JSONL.value, records)

        with open(path) as file:
            lines = [json.loads(line) for line in file if line.strip()]
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0]['decoded']['temperature'], 21.5)
        self.assertEqual(lines[1]['address'], '12-34-56-78')

    def test_csv_file_has_header_and_serialized_columns(self):
        records = [{'seq': 1, 'address': 'FF-AA-DD-81', 'known': True,
                    'entity_ids': ['sensor.a', 'sensor.b'], 'decoded': {'temperature': 21.5}}]

        path = self.write_records(TelegramLogFormat.CSV.value, records)

        with open(path) as file:
            lines = file.read().strip().split('\n')
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].startswith('seq;timestamp;direction'))
        self.assertIn('FF-AA-DD-81', lines[1])
        self.assertIn('true', lines[1])
        self.assertIn('"[""sensor.a"",""sensor.b""]"', lines[1])

    def test_rotation(self):
        records = [{'seq': i, 'data': 'x' * 200} for i in range(20)]

        path = self.write_records(TelegramLogFormat.JSONL.value, records, max_bytes=500, backup_count=2)

        self.assertTrue(os.path.exists(path))
        self.assertTrue(os.path.exists(path + '.1'))
        self.assertTrue(os.path.exists(path + '.2'))
        self.assertFalse(os.path.exists(path + '.3'))
        self.assertLessEqual(os.path.getsize(path), 500 + 300)


class TestTelegramLoggerSetup(IsolatedAsyncioTestCase):

    async def test_file_path_is_resolved_relative_to_config_folder(self):
        directory = tempfile.mkdtemp()
        hass = HassDataMock(config_dir=directory)
        logger = EnOceanTelegramLogger(hass, get_general_settings(**{
            CONF_LOG_ENOCEAN_TELEGRAMS: True,
            CONF_TELEGRAM_LOG_FILENAME: 'telegrams.jsonl',
        }))

        self.assertEqual(logger.filename, 'telegrams.jsonl')
        self.assertIsNone(logger.file_path)

        # emulate async_setup without the home assistant event bus
        logger.file_path = os.path.join(directory, logger.filename)
        self.assertTrue(logger.file_path.startswith(directory))

    async def test_absolute_file_path_is_kept(self):
        logger = EnOceanTelegramLogger(HassDataMock(), get_general_settings(**{
            CONF_TELEGRAM_LOG_FILENAME: '/share/telegrams.jsonl',
        }))
        self.assertTrue(os.path.isabs(logger.filename))


if __name__ == '__main__':
    unittest.main()


class TestTelegramLogLevels(TestCase):
    """Each telegram category can be logged at its own level."""

    def setUp(self):
        self.gateway = GatewayMock(base_id=AddressExpression.parse('FF-AA-80-00'))
        self.hass = HassDataMock(config={
            CONF_GATEWAY: [{
                CONF_ID: self.gateway.dev_id, CONF_BASE_ID: 'FF-AA-80-00',
                CONF_DEVICES: {'sensor': [{CONF_ID: 'FF-AA-DD-81', CONF_EEP: 'A5-04-02',
                                           CONF_NAME: 'Temp Sensor'}]},
            }],
        })
        self.gateway.hass = self.hass

    def create_logger(self, **levels) -> EnOceanTelegramLogger:
        logger = EnOceanTelegramLogger(self.hass, get_general_settings(**{
            CONF_LOG_ENOCEAN_TELEGRAMS: True, **levels}))
        logger.refresh_device_map()
        return logger

    def test_nothing_is_logged_by_default(self):
        logger = self.create_logger()

        self.assertIsNone(logger._lowest_log_level)
        self.assertTrue(all(level is None for level in logger.log_levels.values()))

    def test_levels_are_translated(self):
        import logging

        logger = self.create_logger(**{CONF_LOG_LEVEL_INCOMING: 'info',
                                       CONF_LOG_LEVEL_UNKNOWN_DEVICES: 'warning',
                                       CONF_LOG_LEVEL_POLLING: 'debug'})

        self.assertEqual(logger.log_levels['incoming'], logging.INFO)
        self.assertEqual(logger.log_levels['unknown'], logging.WARNING)
        self.assertEqual(logger.log_levels['polling'], logging.DEBUG)
        self.assertIsNone(logger.log_levels['outgoing'])
        self.assertEqual(logger._lowest_log_level, logging.DEBUG)

    def test_category_of_telegrams(self):
        logger = self.create_logger()

        self.assertEqual(logger._category_of({'known': True, 'direction': 'incoming'}), 'incoming')
        self.assertEqual(logger._category_of({'known': False, 'direction': 'incoming'}), 'unknown')
        self.assertEqual(logger._category_of({'known': True, 'direction': 'outgoing'}), 'outgoing')
        self.assertEqual(logger._category_of({'role': 'bus_message', 'direction': 'incoming'}), 'bus')

    def test_unknown_device_is_logged_with_its_level(self):
        logger = self.create_logger(**{CONF_LOG_LEVEL_UNKNOWN_DEVICES: 'warning'})

        with self.assertLogs('eltako.telegrams', level='WARNING') as captured:
            logger.record_message(self.gateway, RPSMessage(address=b'\x81\x04\xE5\x54', status=0x30,
                                                           data=b'\x10'), 'incoming')

        self.assertIn('UNKNOWN device', captured.output[0])
        self.assertIn('81-04-E5-54', captured.output[0])

    def test_known_device_is_logged_with_decoded_values(self):
        logger = self.create_logger(**{CONF_LOG_LEVEL_INCOMING: 'info'})

        with self.assertLogs('eltako.telegrams', level='INFO') as captured:
            logger.record_message(self.gateway, Regular4BSMessage(address=b'\xFF\xAA\xDD\x81', status=0x00,
                                                                  data=b'\x00\x7D\x7D\x0A'), 'incoming')

        self.assertIn('Temp Sensor', captured.output[0])
        self.assertIn('current_temperature', captured.output[0])

    def test_polling_is_logged_even_when_it_is_filtered_from_the_recording(self):
        """Polling floods the log, so it is logged without being buffered."""
        logger = self.create_logger(**{CONF_LOG_LEVEL_POLLING: 'debug'})

        with self.assertLogs('eltako.telegrams', level='DEBUG') as captured:
            logger.record_message(self.gateway, EltakoPoll(3), 'incoming')

        self.assertIn('polling', captured.output[0])
        self.assertEqual(logger.get_recent_telegrams(), [])     # not buffered

    def test_decode_error_points_to_a_wrong_eep(self):
        logger = self.create_logger(**{CONF_LOG_LEVEL_DECODE_ERRORS: 'warning'})

        with self.assertLogs('eltako.telegrams', level='WARNING') as captured:
            # an RPS telegram cannot be decoded with the configured A5-04-02
            logger.record_message(self.gateway, RPSMessage(address=b'\xFF\xAA\xDD\x81', status=0x30,
                                                           data=b'\x10'), 'incoming')

        self.assertIn('wrong EEP', captured.output[0])

    def test_categories_which_are_off_are_not_logged(self):
        import logging

        logger = self.create_logger(**{CONF_LOG_LEVEL_UNKNOWN_DEVICES: 'warning'})
        telegram_logger = logging.getLogger('eltako.telegrams')

        with self.assertLogs('eltako.telegrams', level='DEBUG') as captured:
            telegram_logger.debug("marker")     # so that assertLogs has at least one record
            logger.record_message(self.gateway, Regular4BSMessage(address=b'\xFF\xAA\xDD\x81', status=0x00,
                                                                  data=b'\x00\x7D\x7D\x0A'), 'incoming')

        self.assertEqual(len(captured.output), 1)    # only the marker, incoming is 'off'

    def test_levels_are_reported_in_the_info(self):
        logger = self.create_logger(**{CONF_LOG_LEVEL_INCOMING: 'info'})

        levels = logger.get_info()['log_levels']

        self.assertEqual(levels['incoming'], 'INFO')
        self.assertEqual(levels['outgoing'], 'off')
