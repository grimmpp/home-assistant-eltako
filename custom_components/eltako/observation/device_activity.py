"""Long term activity of EnOcean addresses: who has ever reported, how often and when.

The telegram logger (enocean_logger.py) only knows the traffic since Home Assistant was
started. To be able to answer

* "did this configured device ever report itself, or is the entry wrong?"
* "how often is this device actually used?"

the activity is additionally counted here and persisted, so it survives restarts.

The tracker is intentionally independent of the telegram logging setting: it is cheap
(one dictionary update per telegram, debounced writes) and its information is needed exactly
when something does not work.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store

from ..const import *

if TYPE_CHECKING:
    from ..core.gateway import EnOceanGateway

LOG_PREFIX_ACTIVITY = "Device Activity"

STORAGE_KEY = f"{DOMAIN}_device_activity"
STORAGE_VERSION = 1

# writes are debounced, the data is not critical enough for an immediate save
SAVE_DELAY_SECONDS = 60

# addresses which were not seen for this long are dropped when loading
MAX_AGE_DAYS = 180

# upper limit of tracked addresses (foreign devices of the neighbourhood can be many).
# The least recently seen entries are dropped first.
MAX_ADDRESSES = 2000


def get_activity_tracker(hass: HomeAssistant) -> "DeviceActivityTracker | None":
    data = getattr(hass, 'data', None)
    if not isinstance(data, dict):
        return None
    return data.get(DATA_ELTAKO, {}).get(DATA_DEVICE_ACTIVITY, None)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


class DeviceActivityTracker:
    """Counts telegrams per EnOcean address and remembers when they were seen."""

    def __init__(self, hass: HomeAssistant):
        self.hass = hass
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._activity: dict[str, dict] = {}
        self._session_started = _utc_now_iso()
        self._unsubscribe = None
        self._loaded = False

    ### setup / teardown

    async def async_load(self) -> None:
        stored = await self._store.async_load()
        if stored and isinstance(stored.get('activity'), dict):
            self._activity = self._prune(stored['activity'])
        self._loaded = True

        # every address which is seen again in this session increases its session counter
        for entry in self._activity.values():
            entry['seen_in_session'] = False

        LOGGER.debug(f"[{LOG_PREFIX_ACTIVITY}] Loaded activity of {len(self._activity)} addresses.")

        self._unsubscribe = self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, self._async_on_stop)

        register_websocket_commands(self.hass)

    @callback
    def _async_on_stop(self, event) -> None:
        self._store.async_delay_save(self._data_to_save, 0)

    def unload(self) -> None:
        if self._unsubscribe:
            try:
                self._unsubscribe()
            except Exception:   # noqa: BLE001
                pass
            self._unsubscribe = None
        self._store.async_delay_save(self._data_to_save, 0)

    def _data_to_save(self) -> dict:
        return {'activity': {address: {key: value for key, value in entry.items() if key != 'seen_in_session'}
                             for address, entry in self._activity.items()}}

    def _prune(self, activity: dict) -> dict:
        """Drop very old entries and limit the number of tracked addresses."""
        threshold = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)
        result = {}
        for address, entry in activity.items():
            if not isinstance(entry, dict):
                continue
            last_seen = entry.get('last_seen')
            try:
                if last_seen and datetime.fromisoformat(last_seen) < threshold:
                    continue
            except ValueError:
                pass
            result[address] = entry

        if len(result) > MAX_ADDRESSES:
            ordered = sorted(result.items(), key=lambda item: item[1].get('last_seen') or '', reverse=True)
            dropped = len(result) - MAX_ADDRESSES
            result = dict(ordered[:MAX_ADDRESSES])
            LOGGER.debug(f"[{LOG_PREFIX_ACTIVITY}] Dropped {dropped} rarely used addresses.")

        return result

    ### recording (called for every telegram, must stay cheap)

    def record(self, address: str | None, direction: str, msg_type: str,
               gateway: "EnOceanGateway" = None, data: str = None, decoded_ok: bool = None) -> None:
        if not address or not self._loaded:
            return

        entry = self._activity.get(address)
        if entry is None:
            entry = {
                'first_seen': _utc_now_iso(),
                'count': 0,
                'count_incoming': 0,
                'count_outgoing': 0,
                'sessions': 0,
                'msg_types': {},
                'decode_errors': 0,
            }
            self._activity[address] = entry

        if not entry.get('seen_in_session'):
            entry['seen_in_session'] = True
            entry['sessions'] = entry.get('sessions', 0) + 1
            entry['first_seen_in_session'] = _utc_now_iso()

        entry['last_seen'] = _utc_now_iso()
        entry['count'] = entry.get('count', 0) + 1
        if direction == TelegramDirection.OUTGOING.value:
            entry['count_outgoing'] = entry.get('count_outgoing', 0) + 1
        else:
            entry['count_incoming'] = entry.get('count_incoming', 0) + 1

        msg_types = entry.setdefault('msg_types', {})
        msg_types[msg_type] = msg_types.get(msg_type, 0) + 1

        if data:
            entry['last_data'] = data
        if gateway is not None:
            entry['last_gateway_id'] = getattr(gateway, 'dev_id', None)
        if decoded_ok is False:
            entry['decode_errors'] = entry.get('decode_errors', 0) + 1

        self._store.async_delay_save(self._data_to_save, SAVE_DELAY_SECONDS)

    ### queries

    def get_activity(self, address: str | None) -> dict | None:
        if not address:
            return None
        entry = self._activity.get(address.upper())
        if entry is None:
            return None
        return self._describe(address.upper(), entry)

    def get_all(self) -> list[dict]:
        return [self._describe(address, entry) for address, entry in self._activity.items()]

    def _describe(self, address: str, entry: dict) -> dict:
        first_seen = entry.get('first_seen')
        last_seen = entry.get('last_seen')
        return {
            'address': address,
            'first_seen': first_seen,
            'last_seen': last_seen,
            'seen_in_this_session': bool(entry.get('seen_in_session')),
            'count': entry.get('count', 0),
            'count_incoming': entry.get('count_incoming', 0),
            'count_outgoing': entry.get('count_outgoing', 0),
            'sessions': entry.get('sessions', 0),
            'msg_types': dict(entry.get('msg_types', {})),
            'last_data': entry.get('last_data'),
            'last_gateway_id': entry.get('last_gateway_id'),
            'decode_errors': entry.get('decode_errors', 0),
            'telegrams_per_day': self._per_day(entry),
            'silent_since_seconds': self._silent_since(last_seen),
        }

    def _per_day(self, entry: dict) -> float | None:
        """Average number of telegrams per day - a feeling for how often a device is used."""
        first_seen, last_seen = entry.get('first_seen'), entry.get('last_seen')
        if not first_seen or not last_seen:
            return None
        try:
            days = (datetime.fromisoformat(last_seen) - datetime.fromisoformat(first_seen)).total_seconds() / 86400
        except ValueError:
            return None
        if days < 1 / 24:       # less than an hour of history is not meaningful yet
            return None
        return round(entry.get('count', 0) / max(days, 1 / 24), 1)

    def _silent_since(self, last_seen: str | None) -> int | None:
        if not last_seen:
            return None
        try:
            return int((datetime.now(timezone.utc) - datetime.fromisoformat(last_seen)).total_seconds())
        except ValueError:
            return None

    def clear(self) -> None:
        self._activity.clear()
        self._store.async_delay_save(self._data_to_save, 0)
        LOGGER.info(f"[{LOG_PREFIX_ACTIVITY}] Activity history cleared.")


### ---------------------------------------------------------------------------
### websocket api
### ---------------------------------------------------------------------------

WS_ACTIVITY_REGISTERED = "device_activity_ws_registered"


def register_websocket_commands(hass: HomeAssistant) -> None:
    domain_data = hass.data.setdefault(DATA_ELTAKO, {})
    if domain_data.get(WS_ACTIVITY_REGISTERED, False):
        return
    websocket_api.async_register_command(hass, ws_device_activity)
    websocket_api.async_register_command(hass, ws_device_activity_clear)
    domain_data[WS_ACTIVITY_REGISTERED] = True


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required('type'): WS_DEVICE_ACTIVITY})
@callback
def ws_device_activity(hass: HomeAssistant, connection, msg) -> None:
    tracker = get_activity_tracker(hass)
    connection.send_result(msg['id'], {
        'activity': [] if tracker is None else tracker.get_all(),
        'session_started': None if tracker is None else tracker._session_started,
    })


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required('type'): WS_DEVICE_ACTIVITY_CLEAR})
@callback
def ws_device_activity_clear(hass: HomeAssistant, connection, msg) -> None:
    tracker = get_activity_tracker(hass)
    if tracker is not None:
        tracker.clear()
    connection.send_result(msg['id'], {'cleared': tracker is not None})


### ---------------------------------------------------------------------------
### setup
### ---------------------------------------------------------------------------

async def async_setup_activity_tracker(hass: HomeAssistant) -> DeviceActivityTracker:
    """Create the tracker. It is always active, independent of the telegram logging."""
    domain_data = hass.data.setdefault(DATA_ELTAKO, {})

    existing: DeviceActivityTracker = domain_data.pop(DATA_DEVICE_ACTIVITY, None)
    if existing is not None:
        existing.unload()

    tracker = DeviceActivityTracker(hass)
    await tracker.async_load()
    domain_data[DATA_DEVICE_ACTIVITY] = tracker
    return tracker
