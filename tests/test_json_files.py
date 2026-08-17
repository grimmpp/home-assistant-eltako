"""Repository JSON files must be strict JSON, not JSONC or JavaScript config syntax."""

import json
import unittest
from pathlib import Path


class TestJsonFiles(unittest.TestCase):
    def test_every_repository_json_file_is_strict_json(self):
        root = Path(__file__).resolve().parents[1]
        # VS Code's launch/settings files are intentionally JSONC. The integration and its
        # package metadata, however, are consumed as strict JSON by Home Assistant and HACS.
        json_files = sorted(root.joinpath("custom_components").rglob("*.json"))
        json_files.extend(root / name for name in ("form.json", "hacs.json"))

        self.assertTrue(json_files)
        for path in json_files:
            with self.subTest(path=path.relative_to(root)):
                try:
                    json.loads(path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError) as err:
                    self.fail(f"{path.relative_to(root)} is not strict JSON: {err}")
