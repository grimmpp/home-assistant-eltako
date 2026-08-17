"""Tests for the standalone configuration browser."""

import asyncio

import pytest
import voluptuous as vol

from eltako_standalone.configurations import _storage_path, async_import, list_configurations


class _Runtime:
    def __init__(self, root):
        self.workspace_dir = str(root / "active")
        self.config_dir = self.workspace_dir
        self.storage_dir = str(root / "storage")


def test_list_includes_description_and_summary(tmp_path):
    runtime = _Runtime(tmp_path)
    storage = tmp_path / "storage" / "examples"
    storage.mkdir(parents=True)
    (storage / "test.yaml").write_text(
        "description: Test setup\neltako:\n  gateway:\n  - id: 1\n    devices:\n      light: [{id: 1}, {id: 2}]\n",
        encoding="utf-8")

    result = list_configurations(runtime)

    assert result == [{
        "name": "test", "filename": "examples/test.yaml", "kind": "file",
        "active": False, "path": str(storage / "test.yaml"),
        "description": "Test setup", "gateways": 1, "devices": 2,
        "platforms": {"light": 2},
    }]


def test_import_writes_to_selected_storage_folder(tmp_path):
    runtime = _Runtime(tmp_path)
    content = "description: Imported\neltako: {}\n"

    result = asyncio.run(async_import(runtime, "imported", content))

    assert result["filename"] == "imported.yaml"
    assert (tmp_path / "storage" / "imported.yaml").read_text(encoding="utf-8") == content


def test_storage_path_rejects_escape(tmp_path):
    with pytest.raises(vol.Invalid):
        _storage_path(_Runtime(tmp_path), "../outside.yaml")
