"""How well the radio gateways hear - a site survey out of the recorded telegrams.

An EnOcean installation lives and dies with the reception of its gateways, and "it works
here" is not something one can see: a device which is heard with -90 dBm works today and
stops working when a door is closed or a cupboard is moved. Two things say what is going on,
and both are in every recorded telegram already:

* **the signal strength** (`rssi_dbm`) - reported by ESP3 transceivers (FAM-USB, USB300,
  LAN gateways). It says how much reserve a link has, not just whether it arrived.
* **the repeater count** (`rp_count` / `repeated`) - a telegram which arrives *through a
  repeater* did not make it directly. A high share of repeated telegrams is the clearest
  sign that a gateway sits in the wrong place, even where the signal strength looks fine.

This module aggregates both per **link** (one sender heard by one gateway) and per gateway
over a time window, so the web ui can show what a gateway hears *right now*. That is what
makes it usable while walking through the building with a gateway (or with a transmitter):
the window is short, the numbers follow within seconds, and a measured spot can be kept to
compare it with the next one.

Everything here is a pure function over the telegram records of the ring buffer
(observation/enocean_logger.py) - no state of its own, nothing to switch on, and testable
without hardware.
"""
from datetime import datetime, timedelta, timezone

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from ..const import LOGGER, WS_RECEPTION_SURVEY
from .radio_comparison import is_radio_telegram

LOG_PREFIX_RECEPTION = "Reception"

# Signal strength in dBm and what it means for an EnOcean link. The steps follow the usual
# commissioning practice: a device is not "working or not", it has reserve or it has not.
# -60 and better survives a closed door and a moved cupboard, below -85 a single obstacle
# more is enough to lose it.
QUALITY_STEPS = (
    (-60, 'excellent'),
    (-75, 'good'),
    (-85, 'fair'),
)
WEAK_QUALITY = 'weak'

# a link whose telegrams arrive through a repeater this often is reported as repeated-heavy:
# the direct path does not carry, the repeater is doing the work
REPEATED_WARNING_SHARE = 0.25

DEFAULT_WINDOW = 300
MAX_WINDOW = 3600


def quality_of(rssi) -> str | None:
    """Name of the signal quality, or None if the gateway does not report a strength."""
    if rssi is None:
        return None
    for threshold, name in QUALITY_STEPS:
        if rssi >= threshold:
            return name
    return WEAK_QUALITY


def _parse_time(value) -> datetime | None:
    if not value:
        return None
    try:
        stamp = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)


def _is_radio(record: dict) -> bool:
    """Only incoming radio telegrams say something about the reception.

    Outgoing ones were sent by the gateway itself, and everything which reached a gateway over
    its RS485 wire says nothing about radio coverage: the bus messages of a FAM14 (polling,
    discovery, memory) as well as the telegrams of the actuators on that bus, which are
    addressed relative to its base id. They would drown every radio statistic - and a bus
    gateway would look like the best receiver of the installation because a wire never fades.
    The same rule as on the radio page, so both show the same reception (radio_comparison.py).
    """
    if record.get('direction') != 'incoming':
        return False
    return is_radio_telegram(record)


def _summary(values: list[int]) -> dict:
    """last / avg / min / max of the signal strengths of one link."""
    if not values:
        return {'last': None, 'avg': None, 'min': None, 'max': None, 'count': 0}
    return {
        'last': values[-1],
        'avg': round(sum(values) / len(values), 1),
        'min': min(values),
        'max': max(values),
        'count': len(values),
    }


def survey(records: list[dict], window_seconds: int = DEFAULT_WINDOW, now: datetime = None,
           address: str = None, gateway_id=None) -> dict:
    """Reception per link and per gateway over the last `window_seconds`.

    `records` are the telegram records of the ring buffer, oldest first. `address` and
    `gateway_id` narrow the survey down to one sender / one gateway - which is what the
    "walk around" mode of the web ui uses: one device is pressed over and over while the
    gateway moves, and only that link is watched.

    A record without a timestamp is counted but cannot be placed in time; a gateway which
    reports no signal strength (an ESP2 transceiver, a bus gateway) still delivers counts and
    the repeater share, so the survey stays useful for it - the quality is None then.
    """
    now = now or datetime.now(timezone.utc)
    window_seconds = max(int(window_seconds or DEFAULT_WINDOW), 1)
    start = now - timedelta(seconds=window_seconds)

    wanted_address = str(address).upper() if address else None
    wanted_gateway = str(gateway_id) if gateway_id is not None else None

    links: dict[tuple, dict] = {}
    oldest: datetime | None = None
    newest: datetime | None = None
    total = 0
    has_rssi = False

    for record in records or []:
        if not _is_radio(record):
            continue
        stamp = _parse_time(record.get('timestamp'))
        if stamp is not None:
            if oldest is None or stamp < oldest:
                oldest = stamp
            if stamp < start:
                continue
            if newest is None or stamp > newest:
                newest = stamp

        sender = str(record.get('address')).upper()
        gateway = record.get('gateway_id')
        if wanted_address and sender != wanted_address:
            continue
        if wanted_gateway is not None and str(gateway) != wanted_gateway:
            continue

        key = (sender, str(gateway))
        link = links.get(key)
        if link is None:
            link = links[key] = {
                'address': sender,
                'local_address': record.get('local_address'),
                'name': record.get('device_name'),
                'known': bool(record.get('known')),
                'gateway_id': gateway,
                'gateway_name': record.get('gateway_name'),
                'count': 0,
                'repeated': 0,
                'rssi_values': [],
                'last_seen': None,
                'msg_types': {},
            }
        link['count'] += 1
        total += 1
        if record.get('repeated') or (record.get('rp_count') or 0) > 0:
            link['repeated'] += 1
        rssi = record.get('rssi_dbm')
        if isinstance(rssi, (int, float)):
            link['rssi_values'].append(int(rssi))
            has_rssi = True
        if not link['name'] and record.get('device_name'):
            link['name'] = record['device_name']
        msg_type = record.get('msg_type')
        if msg_type:
            link['msg_types'][msg_type] = link['msg_types'].get(msg_type, 0) + 1
        if stamp is not None and (link['last_seen'] is None or stamp > link['last_seen']):
            link['last_seen'] = stamp

    minutes = window_seconds / 60
    result_links = []
    for link in links.values():
        rssi = _summary(link.pop('rssi_values'))
        result_links.append({
            **link,
            'rssi': rssi,
            'quality': quality_of(rssi['avg']),
            'repeated_share': round(link['repeated'] / link['count'], 3) if link['count'] else 0,
            'per_minute': round(link['count'] / minutes, 2),
            'last_seen': link['last_seen'].isoformat() if link['last_seen'] else None,
        })

    # strongest link first - that is the order somebody comparing two spots reads it in
    result_links.sort(key=lambda entry: (entry['rssi']['avg'] is None,
                                         -(entry['rssi']['avg'] or -999), -entry['count']))

    return {
        'window_seconds': window_seconds,
        'from': start.isoformat(),
        'to': now.isoformat(),
        'telegrams': total,
        'has_rssi': has_rssi,
        'links': result_links,
        'gateways': _per_gateway(result_links, minutes),
        # the ring buffer is finite: if its oldest telegram is younger than the window, the
        # numbers describe less time than they claim - the web ui says so instead of showing
        # a survey which silently covers 20 seconds
        'buffer_limited': bool(oldest and oldest > start),
        'covers_from': oldest.isoformat() if oldest else None,
        'last_telegram': newest.isoformat() if newest else None,
    }


def _per_gateway(links: list[dict], minutes: float) -> list[dict]:
    """One row per receiving gateway: what it hears in total."""
    gateways: dict[str, dict] = {}
    for link in links:
        key = str(link['gateway_id'])
        gateway = gateways.get(key)
        if gateway is None:
            gateway = gateways[key] = {
                'gateway_id': link['gateway_id'],
                'gateway_name': link['gateway_name'],
                'telegrams': 0,
                'senders': 0,
                'repeated': 0,
                'rssi_sum': 0.0,
                'rssi_count': 0,
                'worst': None,
                'best': None,
            }
        gateway['telegrams'] += link['count']
        gateway['senders'] += 1
        gateway['repeated'] += link['repeated']
        average = link['rssi']['avg']
        if average is not None:
            gateway['rssi_sum'] += average * link['count']
            gateway['rssi_count'] += link['count']
            if gateway['worst'] is None or average < gateway['worst']:
                gateway['worst'] = average
            if gateway['best'] is None or average > gateway['best']:
                gateway['best'] = average

    result = []
    for gateway in gateways.values():
        count = gateway.pop('rssi_count')
        total = gateway.pop('rssi_sum')
        # weighted by the number of telegrams: a sender which is heard often says more about
        # this position than one which sent twice
        average = round(total / count, 1) if count else None
        result.append({
            **gateway,
            'rssi_avg': average,
            'quality': quality_of(average),
            'repeated_share': round(gateway['repeated'] / gateway['telegrams'], 3)
                              if gateway['telegrams'] else 0,
            'per_minute': round(gateway['telegrams'] / minutes, 2),
        })
    result.sort(key=lambda entry: (entry['rssi_avg'] is None, -(entry['rssi_avg'] or -999)))
    return result


### ---------------------------------------------------------------------------
### websocket api
### ---------------------------------------------------------------------------

def register_websocket_commands(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, ws_reception_survey)


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required('type'): WS_RECEPTION_SURVEY,
    vol.Optional('window', default=DEFAULT_WINDOW):
        vol.All(vol.Coerce(int), vol.Range(min=5, max=MAX_WINDOW)),
    vol.Optional('address'): vol.Any(str, None),
    vol.Optional('gateway_id'): vol.Any(int, str, None),
})
@callback
def ws_reception_survey(hass: HomeAssistant, connection, msg) -> None:
    """The current reception, computed from the recorded telegrams."""
    from .enocean_logger import get_telegram_logger

    logger = get_telegram_logger(hass)
    if logger is None:
        connection.send_result(msg['id'], {
            'recording': False, 'window_seconds': msg['window'], 'telegrams': 0,
            'links': [], 'gateways': [], 'has_rssi': False, 'buffer_limited': False,
        })
        return

    try:
        records = logger.get_recent_telegrams(0)
    except Exception as e:  # noqa: BLE001 - the survey must never break the panel
        LOGGER.error(f"[{LOG_PREFIX_RECEPTION}] Cannot read the telegram buffer: {e}")
        records = []

    result = survey(records, window_seconds=msg['window'], address=msg.get('address'),
                    gateway_id=msg.get('gateway_id'))
    result['recording'] = True
    result['buffer_size'] = getattr(logger, 'buffer_size', None)
    connection.send_result(msg['id'], result)
