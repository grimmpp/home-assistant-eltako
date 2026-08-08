"""Opens the web ui once, right after the integration was installed.

'Add integration' does not ask for anything (see config_flow.async_step_auto), so the moment it
is finished the interesting part - the web ui, where gateways and devices are configured - is a
sidebar entry the user has never seen. This module takes them there once.

How it works: while the redirect is pending, a very small javascript module is registered as an
extra frontend module. Home Assistant pushes that registration to every open browser, so the
module is loaded without a reload. It asks the backend whether the redirect is still pending
(`WS_ONBOARDING_CONSUME`), and the first browser which asks gets it - the flag is flipped in the
same call and the module is unregistered again. Everybody else gets 'no' and does nothing.

The flag lives in the data of the core entry, so it survives a restart: whoever installs
the integration from a terminal and opens Home Assistant the next morning still gets the tour.
Removing and adding the integration again starts over, which is exactly what it looks like.
"""

from __future__ import annotations

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from ..const import (CONF_ONBOARDING_SHOWN, DATA_ELTAKO, DATA_ONBOARDING, LOGGER, PANEL_ONBOARDING_JS_URL,
                     PANEL_TITLE, PANEL_URL_PATH, WS_ONBOARDING_CONSUME)
from ..config import config_helpers

LOG_PREFIX_ONBOARDING = "First start"


def _state(hass: HomeAssistant) -> dict:
    return hass.data.setdefault(DATA_ELTAKO, {}).setdefault(DATA_ONBOARDING, {})


def is_pending(hass: HomeAssistant) -> bool:
    """True while the web ui still has to be opened for the first time."""
    return bool(_state(hass).get('pending'))


async def async_setup_onboarding(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Arrange for the web ui to be opened once. Returns True if that is still pending.

    Called for the core entry on every start. Everything in here is a convenience, so a runtime
    which does not offer the frontend hooks (the standalone runtime, the tests) simply gets no
    redirect instead of a failing setup.
    """
    if config_entry.data.get(CONF_ONBOARDING_SHOWN):
        return False

    try:
        general_settings = config_helpers.get_general_settings_from_configuration(hass)
        if not config_helpers.is_frontend_enabled(general_settings):
            # nothing to open - and it must not be retried once the web ui is switched on again
            # years later, so the entry is marked here as well
            await _async_mark_as_shown(hass, config_entry)
            return False

        _state(hass).update({'entry_id': config_entry.entry_id, 'pending': True})
        websocket_api.async_register_command(hass, ws_onboarding_consume)
        _async_add_module(hass)
    except Exception as e:  # noqa: BLE001 - never let the tour break the setup
        LOGGER.debug(f"[{LOG_PREFIX_ONBOARDING}] Cannot open the web ui automatically: {e}")
        _state(hass)['pending'] = False
        return False

    LOGGER.info(f"[{LOG_PREFIX_ONBOARDING}] The web ui is opened once so you can see what the "
                f"integration offers. Afterwards it is the '{PANEL_TITLE}' entry in the sidebar.")
    return True


def _async_add_module(hass: HomeAssistant) -> None:
    from homeassistant.components.frontend import add_extra_js_url

    add_extra_js_url(hass, PANEL_ONBOARDING_JS_URL)


def _async_remove_module(hass: HomeAssistant) -> None:
    try:
        from homeassistant.components.frontend import remove_extra_js_url

        remove_extra_js_url(hass, PANEL_ONBOARDING_JS_URL)
    except Exception as e:  # noqa: BLE001 - it is gone at the latest with the next restart
        LOGGER.debug(f"[{LOG_PREFIX_ONBOARDING}] Cannot remove the module again: {e}")


async def _async_mark_as_shown(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Remember in the config entry that the web ui was offered."""
    try:
        hass.config_entries.async_update_entry(
            config_entry, data={**config_entry.data, CONF_ONBOARDING_SHOWN: True})
    except Exception as e:  # noqa: BLE001
        LOGGER.debug(f"[{LOG_PREFIX_ONBOARDING}] Cannot store that the web ui was shown: {e}")


async def async_consume(hass: HomeAssistant) -> bool:
    """Hand the redirect out to the first caller. Every later call gets False."""
    state = _state(hass)
    if not state.get('pending'):
        return False

    state['pending'] = False
    _async_remove_module(hass)

    entry_id = state.get('entry_id')
    entry = None
    if entry_id:
        try:
            entry = hass.config_entries.async_get_entry(entry_id)
        except Exception as e:  # noqa: BLE001
            LOGGER.debug(f"[{LOG_PREFIX_ONBOARDING}] Cannot look the core entry up: {e}")
    if entry is not None:
        await _async_mark_as_shown(hass, entry)

    return True


### ---------------------------------------------------------------------------
### websocket api
### ---------------------------------------------------------------------------

@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required('type'): WS_ONBOARDING_CONSUME})
@websocket_api.async_response
async def ws_onboarding_consume(hass: HomeAssistant, connection, msg) -> None:
    connection.send_result(msg['id'], {
        'open': await async_consume(hass),
        'url': f"/{PANEL_URL_PATH}",
    })
