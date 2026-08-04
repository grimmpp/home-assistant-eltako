"""Websocket commands to list, watch and control the entities of the integration.

These commands only exist in the standalone runtime (they are registered by
runtime.py, not by the integration). The CLI and the 'Control' page of the web
ui use them - together they replace the Home Assistant dashboard:

    eltako/entities/list        all entities incl. state and attributes
    eltako/entities/call        invoke an action (turn_on, set_cover_position, ...)
    eltako/entities/subscribe   push state changes to the client
"""

from __future__ import annotations

import inspect
import logging

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import DATA_ENTITY_PLATFORM

from custom_components.eltako.const import DOMAIN

LOGGER = logging.getLogger("eltako_standalone.entity_api")

WS_ENTITY_LIST = "eltako/entities/list"
WS_ENTITY_CALL = "eltako/entities/call"
WS_ENTITY_SUBSCRIBE = "eltako/entities/subscribe"

# action -> (accepted keyword arguments). Only whitelisted actions are callable.
ACTIONS: dict[str, dict[str, list[str]]] = {
    "light": {"turn_on": ["brightness"], "turn_off": []},
    "switch": {"turn_on": [], "turn_off": []},
    "cover": {"open_cover": [], "close_cover": [], "stop_cover": [],
              "set_cover_position": ["position"],
              "set_cover_tilt_position": ["tilt_position"]},
    "climate": {"set_temperature": ["temperature"], "set_hvac_mode": ["hvac_mode"],
                "set_preset_mode": ["preset_mode"]},
    "button": {"press": []},
    "select": {"select_option": ["option"]},
    "datetime": {"set_value": ["value"]},
}


def register_websocket_commands(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, ws_entity_list)
    websocket_api.async_register_command(hass, ws_entity_call)
    websocket_api.async_register_command(hass, ws_entity_subscribe)


def _iter_entities(hass: HomeAssistant):
    for platform in hass.data.get(DATA_ENTITY_PLATFORM, {}).get(DOMAIN, []):
        for entity in platform.entities.values():
            yield platform, entity


def get_entity(hass: HomeAssistant, entity_id: str):
    for _platform, entity in _iter_entities(hass):
        if entity.entity_id == entity_id:
            return entity
    return None


def _describe_entity(hass: HomeAssistant, platform, entity) -> dict:
    from eltakobus.util import b2s

    state = hass.states.get(entity.entity_id)
    dev_id = getattr(entity, "dev_id", None)
    dev_eep = getattr(entity, "dev_eep", None)
    gateway = getattr(entity, "gateway", None)

    return {
        "entity_id": entity.entity_id,
        "unique_id": getattr(entity, "unique_id", None),
        "platform": platform.domain,
        "name": str(getattr(entity, "dev_name", None) or getattr(entity, "name", None)
                    or entity.entity_id),
        "state": state.state if state else None,
        "attributes": dict(state.attributes) if state else {},
        "last_changed": state.last_changed.isoformat() if state else None,
        "address": b2s(dev_id) if dev_id is not None else None,
        "eep": getattr(dev_eep, "eep_string", None),
        "area": getattr(entity, "_attr_dev_area", None),
        "gateway_id": getattr(gateway, "dev_id", None),
        "gateway_name": getattr(gateway, "dev_name", None),
        "actions": sorted(ACTIONS.get(platform.domain, {}).keys()),
    }


def list_entities(hass: HomeAssistant) -> list[dict]:
    result = [_describe_entity(hass, platform, entity)
              for platform, entity in _iter_entities(hass)]
    return sorted(result, key=lambda item: (item["platform"], item["entity_id"]))


async def async_call_entity(hass: HomeAssistant, entity_id: str, action: str,
                            data: dict | None = None) -> None:
    """Invoke a whitelisted action on an entity. Raises ValueError on bad input."""
    entity = get_entity(hass, entity_id)
    if entity is None:
        raise ValueError(f"Unknown entity '{entity_id}'")

    domain = entity_id.split(".")[0]
    allowed = ACTIONS.get(domain, {})
    if action not in allowed:
        raise ValueError(f"Action '{action}' is not supported for {domain} entities. "
                         f"Supported: {', '.join(sorted(allowed)) or 'none'}")

    kwargs = {key: value for key, value in (data or {}).items() if key in allowed[action]}
    missing = [key for key in allowed[action] if key not in kwargs
               and action.startswith(("set_", "select_"))]
    if missing:
        raise ValueError(f"Action '{action}' needs: {', '.join(missing)}")

    method = getattr(entity, f"async_{action}", None)
    if method is not None and inspect.iscoroutinefunction(method):
        await _invoke(method, action, kwargs)
    else:
        method = getattr(entity, action, None)
        if method is None:
            raise ValueError(f"Entity '{entity_id}' does not implement '{action}'")
        await hass.async_add_executor_job(lambda: _invoke_sync(method, action, kwargs))


async def _invoke(method, action: str, kwargs: dict):
    if action in ("select_option", "set_hvac_mode", "set_preset_mode", "set_value"):
        # these take one positional argument
        await method(next(iter(kwargs.values())))
    else:
        await method(**kwargs)


def _invoke_sync(method, action: str, kwargs: dict):
    if action in ("select_option", "set_hvac_mode", "set_preset_mode", "set_value"):
        method(next(iter(kwargs.values())))
    else:
        method(**kwargs)


### ---------------------------------------------------------------------------
### websocket commands
### ---------------------------------------------------------------------------

@websocket_api.websocket_command({vol.Required("type"): WS_ENTITY_LIST})
@callback
def ws_entity_list(hass: HomeAssistant, connection, msg) -> None:
    connection.send_result(msg["id"], {"entities": list_entities(hass)})


@websocket_api.websocket_command({
    vol.Required("type"): WS_ENTITY_CALL,
    vol.Required("entity_id"): str,
    vol.Required("action"): str,
    vol.Optional("data"): dict,
})
@websocket_api.async_response
async def ws_entity_call(hass: HomeAssistant, connection, msg) -> None:
    try:
        await async_call_entity(hass, msg["entity_id"], msg["action"], msg.get("data"))
    except ValueError as e:
        connection.send_error(msg["id"], "invalid_action", str(e))
        return
    except Exception as e:  # noqa: BLE001 - report what the device layer complained about
        LOGGER.exception("Action %s on %s failed", msg["action"], msg["entity_id"])
        connection.send_error(msg["id"], "action_failed", str(e))
        return
    state = hass.states.get(msg["entity_id"])
    connection.send_result(msg["id"], {
        "done": True,
        "state": state.state if state else None,
        "attributes": dict(state.attributes) if state else {},
    })


@websocket_api.websocket_command({vol.Required("type"): WS_ENTITY_SUBSCRIBE})
@callback
def ws_entity_subscribe(hass: HomeAssistant, connection, msg) -> None:
    def forward(entity_id, old_state, new_state):
        connection.send_message(websocket_api.event_message(msg["id"], {
            "entity_id": entity_id,
            "state": new_state.state if new_state else None,
            "attributes": dict(new_state.attributes) if new_state else {},
        }))

    connection.subscriptions[msg["id"]] = hass.states.add_listener(forward)
    connection.send_result(msg["id"])
