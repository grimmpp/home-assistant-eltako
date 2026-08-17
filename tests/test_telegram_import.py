"""Tests for replaying exported live telegram records."""

import json
import unittest

from custom_components.eltako.observation.enocean_logger import (
    _import_raw_message,
    _import_telegram_rows,
)
from eltakobus.message import RPSMessage


class TestTelegramImport(unittest.TestCase):
    def test_jsonl_rows_and_raw_esp2_frame_are_read(self):
        message = RPSMessage(address=b"\x12\x34\x56\x78", status=0x30, data=b"\x10")
        row = {"gateway_id": 1, "direction": "incoming", "raw": message.serialize().hex()}

        rows = _import_telegram_rows(json.dumps(row))

        self.assertEqual(rows, [row])
        self.assertEqual(_import_raw_message(rows[0]["raw"]).serialize(), message.serialize())

    def test_csv_rows_use_the_frontend_semicolon_format(self):
        content = "gateway_id;direction;raw\n1;incoming;a55a0b05100000001234567830b0\n"

        rows = _import_telegram_rows(content)

        self.assertEqual(rows[0]["gateway_id"], "1")
        self.assertEqual(rows[0]["direction"], "incoming")

    def test_jsonl_reads_multiple_telegram_records(self):
        rows = _import_telegram_rows(
            '{"gateway_id": 1, "raw": "a"}\n{"gateway_id": 1, "raw": "b"}\n')

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]["raw"], "b")

    def test_old_jsonl_without_raw_is_reconstructed(self):
        message = _import_raw_message(None, {
            "msg_type": "Regular4BSMessage", "address": "12-34-56-78",
            "data": "01-02-03-04", "status": "0x00", "direction": "incoming",
        })

        self.assertEqual(message.serialize().hex(), "a55a0b0701020304123456780030")


if __name__ == "__main__":
    unittest.main()
