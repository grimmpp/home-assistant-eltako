"""Websocket command registry mirroring homeassistant.components.websocket_api.

The decorators of this module register the command handlers of the integration
into hass.data[DATA_WS_COMMANDS]. The standalone web server (and the CLI) look
the handlers up there and call them with an ActiveConnection - the handlers of
the integration run completely unchanged.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

import voluptuous as vol

LOGGER = logging.getLogger("homeassistant.shim.websocket_api")

DATA_WS_COMMANDS = "websocket_api_commands"

ERR_UNKNOWN_COMMAND = "unknown_command"
ERR_INVALID_FORMAT = "invalid_format"
ERR_UNKNOWN_ERROR = "unknown_error"


def _extract_command(schema: dict) -> str:
    for key, value in schema.items():
        name = key.schema if isinstance(key, vol.Marker) else key
        if name == "type":
            return str(value)
    raise ValueError("websocket_command schema has no 'type' key")


def websocket_command(schema: dict):
    command = _extract_command(schema)
    # 'id' is added by the protocol; ignore protocol level keys during validation
    validator = vol.Schema(schema, extra=vol.ALLOW_EXTRA)

    def decorator(func):
        func._ws_command = command
        func._ws_schema = validator
        return func
    return decorator


def async_response(func):
    func._ws_async = True
    return func


def require_admin(func):
    # standalone runs locally as admin
    return func


def async_register_command(hass, handler) -> None:
    command = getattr(handler, "_ws_command", None)
    if command is None:
        raise ValueError(f"handler {handler} was not decorated with websocket_command")
    hass.data.setdefault(DATA_WS_COMMANDS, {})[command] = handler


def get_commands(hass) -> dict[str, Callable]:
    return hass.data.setdefault(DATA_WS_COMMANDS, {})


def result_message(iden: int, result: Any = None) -> dict:
    return {"id": iden, "type": "result", "success": True, "result": result}


def error_message(iden: int, code: str, message: str) -> dict:
    return {"id": iden, "type": "result", "success": False,
            "error": {"code": code, "message": message}}


def event_message(iden: int, event: Any) -> dict:
    return {"id": iden, "type": "event", "event": event}


class ActiveConnection:
    """One websocket client connection (or a synthetic one for the CLI)."""

    def __init__(self, hass, send_message: Callable[[dict], None]):
        self.hass = hass
        self._send_message = send_message
        self.subscriptions: dict[int, Callable[[], None]] = {}

    def send_message(self, message: dict) -> None:
        self._send_message(message)

    def send_result(self, iden: int, result: Any = None) -> None:
        self.send_message(result_message(iden, result))

    def send_error(self, iden: int, code: str, message: str) -> None:
        self.send_message(error_message(iden, code, message))

    def async_handle_close(self) -> None:
        for unsubscribe in self.subscriptions.values():
            try:
                unsubscribe()
            except Exception:  # noqa: BLE001
                LOGGER.debug("Unsubscribe failed", exc_info=True)
        self.subscriptions.clear()


async def async_handle_message(hass, connection: ActiveConnection, msg: dict) -> None:
    """Dispatch one incoming {id, type, ...} message to the registered handler."""
    iden = msg.get("id", 0)
    command = msg.get("type")
    handler = get_commands(hass).get(command)
    if handler is None:
        connection.send_error(iden, ERR_UNKNOWN_COMMAND, f"Unknown command '{command}'")
        return

    schema = getattr(handler, "_ws_schema", None)
    if schema is not None:
        try:
            payload = {key: value for key, value in msg.items() if key != "id"}
            msg = {**schema(payload), "id": iden}
        except vol.Invalid as e:
            connection.send_error(iden, ERR_INVALID_FORMAT, str(e))
            return

    try:
        if getattr(handler, "_ws_async", False):
            await handler(hass, connection, msg)
        else:
            handler(hass, connection, msg)
    except Exception as e:  # noqa: BLE001 - a handler error is reported to the client
        LOGGER.exception("Websocket command '%s' failed", command)
        connection.send_error(iden, ERR_UNKNOWN_ERROR, str(e))
