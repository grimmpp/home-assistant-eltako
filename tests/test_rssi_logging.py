"""Signal strength (RSSI) of radio telegrams in the telegram log.

ESP3 transceivers report the RSSI per radio packet. The value is carried over
the ESP3 -> ESP2 translation as a `dBm` attribute on the converted message
(see gateway._attach_rssi_to_esp2_conversion) and ends up as `rssi_dbm` in the
telegram record. ESP2 gateways do not report a signal strength - their records
must not contain the field.
"""

import unittest

from eltakobus.message import RPSMessage
from eltakobus.util import AddressExpression

from homeassistant.const import CONF_ID

from custom_components.eltako.const import (CONF_BASE_ID, CONF_GATEWAY, CONF_LOG_ENOCEAN_TELEGRAMS,
                                            TelegramDirection)
from custom_components.eltako.observation.enocean_logger import EnOceanTelegramLogger, CSV_COLUMNS

from tests.mocks import GatewayMock
from tests.test_enocean_logger import HassDataMock, get_general_settings


class TestRssiLogging(unittest.TestCase):

    def setUp(self):
        self.gateway = GatewayMock(base_id=AddressExpression.parse('FF-AA-80-00'))
        self.hass = HassDataMock(config={CONF_GATEWAY: [{CONF_ID: self.gateway.dev_id,
                                                         CONF_BASE_ID: 'FF-AA-80-00'}]})
        self.gateway.hass = self.hass
        self.logger = EnOceanTelegramLogger(
            self.hass, get_general_settings(**{CONF_LOG_ENOCEAN_TELEGRAMS: True}))
        self.logger.refresh_device_map()

    def record(self, msg) -> dict:
        self.logger.record_message(self.gateway, msg, TelegramDirection.INCOMING.value)
        return self.logger.get_recent_telegrams()[-1]

    def test_radio_telegram_with_rssi(self):
        msg = RPSMessage(b'\xFE\xDB\xB6\x40', status=0x30, data=b'\x70')
        msg.dBm = -67       # attached by the ESP3 -> ESP2 conversion wrapper

        record = self.record(msg)
        self.assertEqual(record['rssi_dbm'], -67)

    def test_esp2_telegram_has_no_rssi(self):
        # ESP2 gateways (FAM14, FGW14-USB) never report a signal strength
        record = self.record(RPSMessage(b'\xFE\xDB\xB6\x40', status=0x30, data=b'\x70'))
        self.assertNotIn('rssi_dbm', record)

    def test_invalid_rssi_is_ignored(self):
        msg = RPSMessage(b'\xFE\xDB\xB6\x40', status=0x30, data=b'\x70')
        msg.dBm = 0         # 0 = not reported (default of the enocean library)

        record = self.record(msg)
        self.assertNotIn('rssi_dbm', record)

    def test_rssi_is_part_of_the_csv_columns(self):
        self.assertIn('rssi_dbm', CSV_COLUMNS)

    def test_conversion_wrapper_is_installed(self):
        from esp2_gateway_adapter.esp3_serial_com import ESP3SerialCommunicator
        import custom_components.eltako.core.gateway  # noqa: F401 - installs the wrapper

        self.assertTrue(getattr(
            ESP3SerialCommunicator.convert_esp3_to_esp2_message.__func__, '_adds_rssi', False))


if __name__ == '__main__':
    unittest.main()
