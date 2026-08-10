"""The log of the integration itself, readable in the web ui.

Everything this integration logs goes into the Home Assistant log - which is exactly where it
is hard to get at: it needs file access or the log viewer of Home Assistant, it is full of
every other integration, and on a standalone runtime it is a file next to the process. Yet the
log is what answers the questions this integration produces ("did the command go out?", "why
did the scan stop?", "which telegram could not be decoded?").

So the records of the `eltako` logger are additionally kept in memory, in a ring buffer, and
the *Logs* page of the web ui reads them from there. Nothing is redirected: the handler is
added next to the ones Home Assistant installed, so the log file keeps everything it had.

Two things this module owns:

* `RingBufferHandler` - the buffer, attached to the `eltako` logger (and therefore to
  `eltako.telegrams` and every other child).
* the log level of that logger, changeable from the page and persisted as a general setting,
  so `debug` survives a restart while a problem is being chased.

Websocket commands: eltako/logs/recent, eltako/logs/level, eltako/logs/clear.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from datetime import datetime

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from ..const import (CONF_LOG_LEVEL, DATA_ELTAKO, DATA_INTEGRATION_LOG, DOMAIN, LOGGER,
                     WS_LOGS_CLEAR, WS_LOGS_LEVEL, WS_LOGS_RECENT)

LOG_PREFIX_LOGS = "Integration Log"

# How many records are kept. 2000 lines are a few hundred kilobytes and cover a bus scan with
# debug logging switched on - which is the case this exists for.
BUFFER_SIZE = 2000

# What the page offers. 'inherit' is the default and means: whatever Home Assistant configures
# for this integration (`logger:` in configuration.yaml) - the integration does not touch it.
INHERIT = 'inherit'
LOG_LEVELS = [INHERIT, 'debug', 'info', 'warning', 'error']

_LEVEL_NUMBERS = {'debug': logging.DEBUG, 'info': logging.INFO, 'warning': logging.WARNING,
                  'error': logging.ERROR, 'critical': logging.CRITICAL}


def level_number(level: str | None) -> int | None:
    """Level name of the settings -> logging constant. None for 'inherit'/unknown."""
    return _LEVEL_NUMBERS.get(str(level or '').strip().lower())


class RingBufferHandler(logging.Handler):
    """Keeps the last records of the `eltako` logger in memory.

    Deliberately does nothing but store: no formatting of the whole record, no io, no lock of
    its own (a deque with maxlen is thread safe for append). This runs in whichever thread
    logged - the serial thread of a gateway, the scan thread, the event loop - and a handler
    which can block or throw would take that thread with it.
    """

    def __init__(self, capacity: int = BUFFER_SIZE):
        super().__init__(level=logging.NOTSET)
        self.records: deque = deque(maxlen=capacity)
        # everything the buffer ever saw, so the page can say that older lines are gone
        self.seen = 0

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.records.append(self._as_dict(record))
            self.seen += 1
        except Exception:   # noqa: BLE001 - a logging handler must never raise, see above
            pass

    def _as_dict(self, record: logging.LogRecord) -> dict:
        try:
            message = record.getMessage()
        except Exception as e:  # noqa: BLE001 - a broken format string is a bug worth showing
            message = f"<cannot format log record: {e}> {record.msg!r}"

        entry = {
            # local time with milliseconds, like the Home Assistant log: without them the
            # order of two records of the same second is invisible
            'time': datetime.fromtimestamp(record.created).isoformat(timespec='milliseconds'),
            'timestamp': record.created,
            'level': record.levelname,
            'levelno': record.levelno,
            'logger': record.name,
            'message': message,
        }
        if record.exc_info:
            try:
                entry['exception'] = self.format_exception(record)
            except Exception:   # noqa: BLE001
                entry['exception'] = None
        return entry

    @staticmethod
    def format_exception(record: logging.LogRecord) -> str:
        import traceback
        return ''.join(traceback.format_exception(*record.exc_info)).rstrip()

    def clear(self) -> None:
        self.records.clear()


### ---------------------------------------------------------------------------
### setup
### ---------------------------------------------------------------------------

def get_handler(hass: HomeAssistant) -> RingBufferHandler | None:
    return (hass.data.get(DATA_ELTAKO) or {}).get(DATA_INTEGRATION_LOG)


def async_setup_integration_log(hass: HomeAssistant, settings: dict = None) -> RingBufferHandler:
    """Attach the buffer to the `eltako` logger and apply the configured level.

    Called once while the integration starts and again whenever the settings change. Attaching
    twice would store every record twice, so an existing handler is reused.
    """
    domain_data = hass.data.setdefault(DATA_ELTAKO, {})
    handler = domain_data.get(DATA_INTEGRATION_LOG)
    logger = logging.getLogger(DOMAIN)

    if handler is None:
        handler = RingBufferHandler()
        domain_data[DATA_INTEGRATION_LOG] = handler
    if handler not in logger.handlers:
        logger.addHandler(handler)
        # a record must reach the handler even when the logger of Home Assistant would drop
        # it further up - propagation stays on, so the Home Assistant log keeps everything
        LOGGER.debug(f"[{LOG_PREFIX_LOGS}] The web ui log buffer is attached "
                     f"({handler.records.maxlen} records).")

    apply_log_level(hass, (settings or {}).get(CONF_LOG_LEVEL))
    return handler


def async_unload_integration_log(hass: HomeAssistant) -> None:
    """Detach the buffer - the integration is being removed."""
    handler = get_handler(hass)
    if handler is None:
        return
    logging.getLogger(DOMAIN).removeHandler(handler)
    (hass.data.get(DATA_ELTAKO) or {}).pop(DATA_INTEGRATION_LOG, None)


def apply_log_level(hass: HomeAssistant, level: str | None) -> dict:
    """Set the level of the `eltako` logger. 'inherit' (or empty) gives it back to HA.

    Applied immediately and without reloading anything: this is switched on *while* a problem
    is being chased, and reloading the gateways would close the serial ports in that moment.
    """
    logger = logging.getLogger(DOMAIN)
    number = level_number(level)
    if number is None:
        # NOTSET means: ask the parent again - the level Home Assistant configured
        logger.setLevel(logging.NOTSET)
    else:
        logger.setLevel(number)
    LOGGER.info(f"[{LOG_PREFIX_LOGS}] Log level of '{DOMAIN}' is now "
                f"{logging.getLevelName(logger.getEffectiveLevel())} "
                f"(setting: {level or INHERIT}).")
    return describe_level(hass)


def describe_level(hass: HomeAssistant = None) -> dict:
    """What the page shows above its level selector."""
    logger = logging.getLogger(DOMAIN)
    configured = INHERIT
    if hass is not None:
        try:
            from ..config import config_helpers
            configured = (config_helpers.get_general_settings_from_configuration(hass)
                          .get(CONF_LOG_LEVEL) or INHERIT)
        except Exception:   # noqa: BLE001 - the settings are not readable yet (early startup):
            pass            # the effective level below is still the truth, and that is what
                            # the page needs most

    return {
        'level': configured,
        'effective': logging.getLevelName(logger.getEffectiveLevel()).lower(),
        'options': LOG_LEVELS,
    }


### ---------------------------------------------------------------------------
### websocket api
### ---------------------------------------------------------------------------

WS_LOGS_REGISTERED = "integration_log_ws_registered"


def register_websocket_commands(hass: HomeAssistant) -> None:
    domain_data = hass.data.setdefault(DATA_ELTAKO, {})
    if domain_data.get(WS_LOGS_REGISTERED, False):
        return
    websocket_api.async_register_command(hass, ws_logs_recent)
    websocket_api.async_register_command(hass, ws_logs_level)
    websocket_api.async_register_command(hass, ws_logs_clear)
    domain_data[WS_LOGS_REGISTERED] = True


def get_entries(hass: HomeAssistant, limit: int = 300, level: str = None,
                search: str = None) -> dict:
    """The buffered records, newest last, filtered like the page asks for it."""
    handler = get_handler(hass)
    if handler is None:
        return {'entries': [], 'total': 0, 'dropped': 0, 'buffer_size': BUFFER_SIZE,
                **describe_level(hass)}

    minimum = level_number(level) or 0
    needle = (search or '').strip().lower()
    entries = [entry for entry in list(handler.records)
               if entry['levelno'] >= minimum
               and (not needle or needle in entry['message'].lower()
                    or needle in entry['logger'].lower())]

    return {
        'entries': entries[-max(1, int(limit)):],
        'total': len(entries),
        # records which fell out of the ring buffer - the page says so instead of pretending
        # that the oldest line it shows is the beginning
        'dropped': max(0, handler.seen - len(handler.records)),
        'buffer_size': handler.records.maxlen,
        'now': time.time(),
        **describe_level(hass),
    }


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required('type'): WS_LOGS_RECENT,
    vol.Optional('limit', default=300): vol.All(vol.Coerce(int), vol.Range(min=1, max=BUFFER_SIZE)),
    vol.Optional('level'): vol.Any(None, str),
    vol.Optional('search'): vol.Any(None, str),
})
@callback
def ws_logs_recent(hass: HomeAssistant, connection, msg) -> None:
    connection.send_result(msg['id'], get_entries(hass, msg.get('limit', 300),
                                                  msg.get('level'), msg.get('search')))


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required('type'): WS_LOGS_LEVEL,
    vol.Required('level'): vol.In(LOG_LEVELS),
})
@websocket_api.async_response
async def ws_logs_level(hass: HomeAssistant, connection, msg) -> None:
    """Change the log level of the integration and remember it.

    Stored as the general setting `log_level`, but applied directly instead of through
    async_apply_settings: that one reloads every gateway config entry, which closes the serial
    ports - the last thing anybody wants while they are debugging a bus.
    """
    from ..config.general_settings import async_set_overrides

    level = msg['level']
    try:
        await async_set_overrides(hass, {CONF_LOG_LEVEL: level})
    except vol.Invalid as e:
        connection.send_error(msg['id'], 'invalid_level', str(e))
        return

    connection.send_result(msg['id'], apply_log_level(hass, level))


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required('type'): WS_LOGS_CLEAR})
@callback
def ws_logs_clear(hass: HomeAssistant, connection, msg) -> None:
    handler = get_handler(hass)
    if handler is not None:
        handler.clear()
        handler.seen = 0
    connection.send_result(msg['id'], {'cleared': True})
