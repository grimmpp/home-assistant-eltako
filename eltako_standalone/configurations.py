"""Named configuration profiles for the standalone runtime.

The legacy ``--config`` directory remains the profile named ``default``. Additional profiles
are stored below ``.configurations`` and contain a normal ``configuration.yaml``. This keeps
existing installations compatible while making test installations easy to switch.
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

import voluptuous as vol
import yaml

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant

WS_LIST = "eltako/standalone/configurations/list"
WS_IMPORT = "eltako/standalone/configurations/import"
WS_EXPORT = "eltako/standalone/configurations/export"
WS_SWITCH = "eltako/standalone/configurations/switch"
WS_SAVE = "eltako/standalone/configurations/save"
WS_LOAD = "eltako/standalone/configurations/load"
WS_LOAD_CONTENT = "eltako/standalone/configurations/load_content"
WS_LOAD_EMPTY = "eltako/standalone/configurations/load_empty"
WS_DETAILS = "eltako/standalone/configurations/details"
WS_STORAGE = "eltako/standalone/configurations/storage"
WS_DELETE = "eltako/standalone/configurations/delete"
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


def _runtime(hass: HomeAssistant):
    return hass.data.get("eltako_standalone", {}).get("runtime")


def _profile_dir(runtime, name: str) -> Path:
    if name == "default":
        return Path(runtime.config_dir)
    if not _SAFE_NAME.fullmatch(name):
        raise vol.Invalid("Configuration name must contain only letters, numbers, '_', '-' or '.'.")
    return _storage_dir(runtime) / ".configurations" / name


def _storage_dir(runtime) -> Path:
    path = Path(runtime.storage_dir).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _storage_path(runtime, filename: str) -> Path:
    root = _storage_dir(runtime)
    candidate = (root / filename).resolve()
    if candidate != root and root not in candidate.parents:
        raise vol.Invalid("The configuration file must be inside the selected storage folder.")
    return candidate


def _summary(content: str) -> dict:
    parsed = yaml.safe_load(content) or {}
    if not isinstance(parsed, dict):
        raise vol.Invalid("The configuration must contain a YAML mapping.")
    eltako = parsed.get("eltako") or {}
    gateways = eltako.get("gateway") or [] if isinstance(eltako, dict) else []
    if isinstance(gateways, dict):
        gateways = [gateways]
    devices = 0
    platforms = {}
    for gateway in gateways:
        for platform, values in (gateway.get("devices") or {}).items():
            count = len(values) if isinstance(values, list) else (1 if values else 0)
            devices += count
            platforms[platform] = platforms.get(platform, 0) + count
    return {"description": str(parsed.get("description") or "").strip(),
            "gateways": len(gateways), "devices": devices, "platforms": platforms}


def list_configurations(runtime) -> list[dict]:
    root = _storage_dir(runtime)
    result = []
    for path in sorted(root.rglob("*.yaml"), key=lambda item: str(item).lower()):
        if path.name == "configuration.yaml":
            continue
        relative = path.relative_to(root).as_posix()
        try:
            summary = _summary(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, vol.Invalid, yaml.YAMLError) as err:
            summary = {"description": f"Cannot read configuration: {err}",
                       "gateways": 0, "devices": 0, "platforms": {}}
        result.append({"name": path.stem, "filename": relative, "kind": "file",
                       "active": os.path.abspath(runtime.config_dir) == str(path.parent),
                       "path": str(path), **summary})
    profiles = root / ".configurations"
    if profiles.is_dir():
        for child in sorted(profiles.iterdir(), key=lambda item: item.name.lower()):
            config = child / "configuration.yaml"
            if child.is_dir() and _SAFE_NAME.fullmatch(child.name) and config.is_file():
                try:
                    summary = _summary(config.read_text(encoding="utf-8"))
                except (OSError, UnicodeError, vol.Invalid, yaml.YAMLError):
                    summary = {"description": "Cannot read configuration", "gateways": 0,
                               "devices": 0, "platforms": {}}
                result.append({"name": child.name, "kind": "profile", "path": str(child),
                               "filename": f".configurations/{child.name}/configuration.yaml",
                               "active": os.path.abspath(runtime.config_dir) == str(child),
                               **summary})
    return result


async def async_import(runtime, name: str, content: str) -> dict:
    if not _SAFE_NAME.fullmatch(name):
        raise vol.Invalid("Configuration name must contain only letters, numbers, '_' '-' or '.'.")
    target = _storage_dir(runtime) / f"{name}.yaml"
    parsed = yaml.safe_load(content) or {}
    if not isinstance(parsed, dict):
        raise vol.Invalid("The configuration must contain a YAML mapping.")
    target.write_text(content, encoding="utf-8")
    return {"name": name, "created": True, "filename": target.name, "path": str(target)}


def register_websocket_commands(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, ws_list)
    websocket_api.async_register_command(hass, ws_import)
    websocket_api.async_register_command(hass, ws_export)
    websocket_api.async_register_command(hass, ws_switch)
    websocket_api.async_register_command(hass, ws_save)
    websocket_api.async_register_command(hass, ws_load)
    websocket_api.async_register_command(hass, ws_load_content)
    websocket_api.async_register_command(hass, ws_load_empty)
    websocket_api.async_register_command(hass, ws_details)
    websocket_api.async_register_command(hass, ws_storage)
    websocket_api.async_register_command(hass, ws_delete)


@websocket_api.websocket_command({vol.Required("type"): WS_LIST})
def ws_list(hass, connection, msg) -> None:
    runtime = _runtime(hass)
    connection.send_result(msg["id"], {"configurations": list_configurations(runtime),
                                       "active": os.path.abspath(runtime.config_dir),
                                       "storage_dir": str(_storage_dir(runtime))})


@websocket_api.websocket_command({vol.Required("type"): WS_IMPORT,
                                  vol.Required("name"): str,
                                  vol.Required("content"): str})
@websocket_api.async_response
async def ws_import(hass, connection, msg) -> None:
    try:
        result = await async_import(_runtime(hass), msg["name"], msg["content"])
    except (vol.Invalid, yaml.YAMLError) as err:
        connection.send_error(msg["id"], "invalid_configuration", str(err))
        return
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command({vol.Required("type"): WS_EXPORT})
@websocket_api.async_response
async def ws_export(hass, connection, msg) -> None:
    from custom_components.eltako.config.config_import import async_export

    runtime = _runtime(hass)
    content = await async_export(hass)
    connection.send_result(msg["id"], {"filename": f"eltako-{runtime.active_name}.yaml",
                                       "content": content})


@websocket_api.websocket_command({vol.Required("type"): WS_SWITCH,
                                  vol.Required("name"): str})
@websocket_api.async_response
async def ws_switch(hass, connection, msg) -> None:
    runtime = _runtime(hass)
    try:
        target = _profile_dir(runtime, msg["name"])
    except vol.Invalid as err:
        connection.send_error(msg["id"], "invalid_configuration", str(err))
        return
    if not target.is_dir():
        connection.send_error(msg["id"], "unknown_configuration", msg["name"])
        return
    await runtime.async_switch_configuration(msg["name"])
    connection.send_result(msg["id"], {"switched": True, "name": msg["name"],
                                       "reload_required": True})


def _saved_path(runtime, name: str) -> Path:
    if not _SAFE_NAME.fullmatch(name) or name in ("configuration", "default"):
        raise vol.Invalid("Use a simple configuration name other than 'configuration' or 'default'.")
    return Path(runtime.config_dir) / f"{name}.yaml"


@websocket_api.websocket_command({vol.Required("type"): WS_SAVE,
                                  vol.Required("name"): str})
@websocket_api.async_response
async def ws_save(hass, connection, msg) -> None:
    from custom_components.eltako.config.config_import import async_export

    runtime = _runtime(hass)
    try:
        if not _SAFE_NAME.fullmatch(msg["name"]):
            raise vol.Invalid("Use a simple configuration name.")
        path = _storage_dir(runtime) / f"{msg['name']}.yaml"
        path.write_text(await async_export(hass), encoding="utf-8")
    except (vol.Invalid, OSError) as err:
        connection.send_error(msg["id"], "save_failed", str(err))
        return
    connection.send_result(msg["id"], {"saved": True, "name": path.stem,
                                       "filename": path.name, "path": str(path)})


@websocket_api.websocket_command({vol.Required("type"): WS_LOAD,
                                  vol.Required("filename"): str})
@websocket_api.async_response
async def ws_load(hass, connection, msg) -> None:
    runtime = _runtime(hass)
    filename = msg["filename"]
    try:
        path = _storage_path(runtime, filename)
    except vol.Invalid as err:
        connection.send_error(msg["id"], "invalid_configuration", str(err))
        return
    if path.suffix.lower() not in (".yaml", ".yml") or path == Path(runtime.config_dir).resolve() / "configuration.yaml":
        connection.send_error(msg["id"], "invalid_configuration", "Only saved YAML files can be loaded.")
        return
    try:
        content = path.read_text(encoding="utf-8")
        parsed = yaml.safe_load(content) or {}
        if not isinstance(parsed, dict):
            raise vol.Invalid("The configuration must contain a YAML mapping.")
        # The selected folder is only the library of saved configurations. The active runtime
        # always reads its own configuration.yaml from --config, so write the selected content
        # there before restarting and clearing the old persisted UI entities.
        active_path = Path(runtime.config_dir).resolve() / "configuration.yaml"
        active_path.parent.mkdir(parents=True, exist_ok=True)
        active_path.write_text(content, encoding="utf-8")
        await runtime.async_reload_configuration()
    except (vol.Invalid, OSError, yaml.YAMLError) as err:
        connection.send_error(msg["id"], "load_failed", str(err))
        return
    connection.send_result(msg["id"], {"loaded": True, "filename": filename,
                                       "reload_required": True})


@websocket_api.websocket_command({vol.Required("type"): WS_LOAD_CONTENT,
                                  vol.Required("content"): str,
                                  vol.Optional("filename", default="browser-configuration.yaml"): str})
@websocket_api.async_response
async def ws_load_content(hass, connection, msg) -> None:
    """Load content selected through the browser's native directory picker."""
    runtime = _runtime(hass)
    try:
        content = msg["content"]
        parsed = yaml.safe_load(content) or {}
        if not isinstance(parsed, dict):
            raise vol.Invalid("The configuration must contain a YAML mapping.")
        active_path = Path(runtime.config_dir).resolve() / "configuration.yaml"
        active_path.parent.mkdir(parents=True, exist_ok=True)
        active_path.write_text(content, encoding="utf-8")
        await runtime.async_reload_configuration()
    except (vol.Invalid, OSError, yaml.YAMLError) as err:
        connection.send_error(msg["id"], "load_failed", str(err))
        return
    connection.send_result(msg["id"], {"loaded": True, "filename": msg["filename"],
                                       "reload_required": True})


@websocket_api.websocket_command({vol.Required("type"): WS_LOAD_EMPTY})
@websocket_api.async_response
async def ws_load_empty(hass, connection, msg) -> None:
    """Replace the active configuration with an empty, integration-only YAML file."""
    runtime = _runtime(hass)
    try:
        active_path = Path(runtime.config_dir).resolve() / "configuration.yaml"
        active_path.parent.mkdir(parents=True, exist_ok=True)
        active_path.write_text("eltako:\n", encoding="utf-8")
        await runtime.async_reload_configuration()
    except OSError as err:
        connection.send_error(msg["id"], "load_failed", str(err))
        return
    connection.send_result(msg["id"], {"loaded": True, "filename": "empty",
                                       "reload_required": True})


@websocket_api.websocket_command({vol.Required("type"): WS_DETAILS,
                                  vol.Required("filename"): str})
@websocket_api.async_response
async def ws_details(hass, connection, msg) -> None:
    try:
        path = _storage_path(_runtime(hass), msg["filename"])
        content = path.read_text(encoding="utf-8")
        summary = _summary(content)
    except (vol.Invalid, OSError, UnicodeError, yaml.YAMLError) as err:
        connection.send_error(msg["id"], "details_failed", str(err))
        return
    connection.send_result(msg["id"], {"filename": msg["filename"], "content": content,
                                       **summary})


@websocket_api.websocket_command({vol.Required("type"): WS_STORAGE,
                                  vol.Optional("path"): str})
@websocket_api.async_response
async def ws_storage(hass, connection, msg) -> None:
    runtime = _runtime(hass)
    if "path" not in msg:
        connection.send_result(msg["id"], {"storage_dir": str(_storage_dir(runtime))})
        return
    try:
        selected = runtime.set_storage_dir(msg["path"])
    except OSError as err:
        connection.send_error(msg["id"], "storage_failed", str(err))
        return
    connection.send_result(msg["id"], {"storage_dir": selected,
                                       "configurations": list_configurations(runtime)})


@websocket_api.websocket_command({vol.Required("type"): WS_DELETE,
                                  vol.Required("filename"): str})
@websocket_api.async_response
async def ws_delete(hass, connection, msg) -> None:
    runtime = _runtime(hass)
    filename = msg["filename"]
    try:
        path = _storage_path(runtime, filename)
        if path.suffix.lower() not in (".yaml", ".yml"):
            raise vol.Invalid("Only YAML configurations can be deleted.")
        if path.name == "configuration.yaml":
            if path.parent == Path(runtime.config_dir).resolve():
                raise vol.Invalid("The active configuration.yaml cannot be deleted.")
            if path.parent.parent.name != ".configurations":
                raise vol.Invalid("Only saved configuration profiles can be deleted.")
            shutil.rmtree(path.parent)
        else:
            path.unlink()
    except (vol.Invalid, OSError) as err:
        connection.send_error(msg["id"], "delete_failed", str(err))
        return
    connection.send_result(msg["id"], {"deleted": True, "filename": filename})
