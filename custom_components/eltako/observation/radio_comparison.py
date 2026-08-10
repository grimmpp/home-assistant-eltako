"""Which gateway received which radio telegram - and did all of them receive the same thing?

An installation with several transceivers sees every radio telegram more than once: each
gateway in range receives the same transmission. Usually all of them report the same bytes,
sometimes they do not - one gateway misses the telegram completely, another one reports
different data bytes, a third one only got it through a repeater. In the live view those
receptions are just consecutive rows of different gateways, and a rare difference between them
is invisible.

This module groups the receptions of **one** transmission into a *burst* (same EnOcean address,
within the time window) and compares them:

* which gateways heard it - and which ones did not,
* what each of them made of it (message type, data, status, repeater hops),
* where exactly the bytes differ, and which gateway is the odd one out,
* how strong the signal was at each of them.

**Recording and analysis are separate.** Every telegram is only appended to a ring buffer of
its own (cheap - it happens in the serial thread of a gateway), and the whole comparison is
computed when it is read. That is what makes the **time window adjustable**: how far apart two
receptions may be to count as the same transmission is a question of the installation
(repeaters, gateways behind a LAN connection), and answering it must not mean throwing the
recording away and starting over. The same goes for the filters - "only the differing ones",
"only the ones somebody missed" - they are views of the same buffer.

`observation/enocean_logger.py` feeds every recorded telegram in here, the web ui reads it
through the websocket api (page `frontend/pages/radio.js`).
"""

from __future__ import annotations

import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any

from ..const import TelegramDirection

# How far apart the receptions of one transmission may be to count as the same telegram.
# An EnOcean transmission consists of three sub telegrams within ~40 ms, and a repeater sends
# the whole thing again - 200 ms covers a repeater hop comfortably and is still far below the
# repetition interval of any sensor, so two telegrams of one device are never merged.
DEFAULT_WINDOW_MS = 200
MIN_WINDOW_MS = 10
MAX_WINDOW_MS = 5000
# what the web ui offers as a choice. 50 ms is "direct receptions only" (the sub telegrams of
# one transmission), 1000 ms and above also catches gateways which report late because they
# hang on a LAN connection or behind a chain of repeaters.
WINDOW_CHOICES = (50, 100, 200, 300, 500, 1000, 2000)

# How many receptions are kept. The differences this page is about are rare, so the buffer is
# what decides whether one can still be found afterwards - at one telegram per second these
# 10000 receptions are about three hours. Independent of the ring buffer of the telegram log
# (`telegram_log_buffer_size`, 500 by default), which is far too short for that.
DEFAULT_BUFFER_SIZE = 10_000

# What was *received*: the telegram itself as it came out of the air. 'status' is compared
# *without* the repeater counter in its low nibble (ESP2Message.rp_count = status & 0x0F): a
# telegram which came over a repeater is the same telegram, so the hop count is reported as its
# own kind of difference instead of making every repeated telegram look like a status mismatch.
COMPARED_FIELDS = ('msg_type', 'org', 'data', 'status', 'rp_count')

# What was *made of it*: the profile the telegram was decoded with and the values which came
# out. Kept apart from the received bytes because the two have different causes - identical
# bytes read as different values mean the gateways disagree about the device (a different EEP,
# an address which resolves differently), not about the reception.
INTERPRETATION_FIELDS = ('eep', 'decoded')

ALL_COMPARED_FIELDS = COMPARED_FIELDS + INTERPRETATION_FIELDS

# How a telegram reached a gateway: EnOcean counts the repeater hops in the low nibble of the
# status byte, and the standard allows two levels. 0 is the direct path - which is the one a
# commissioning wants to see, because a device which only arrives over a repeater has no
# reserve of its own left.
HOP_LEVEL_LABELS = {0: 'direct', 1: 'repeater level 1', 2: 'repeater level 2'}

# A difference in the hop count is normal (one gateway hears the device directly, another one
# only the repeater). Everything else means the gateways disagree about the telegram itself.
HOP_FIELD = 'rp_count'

# How many devices are named per kind of difference ("the data bytes differ - on these
# senders"). Enough to recognise a pattern, short enough to stay a sentence; the total number
# is reported next to it, and the address table below lists every one of them.
MAX_NAMED_ADDRESSES = 5

# Which telegrams the burst list shows. Every one of them is a question somebody actually has:
# "do my gateways agree?", "which ones did I nearly lose?", "who is not being heard at all?"
FILTERS = {
    'all': "every telegram",
    'identical': "received by several gateways, all of them identical",
    'differing': "any difference, including a repeater hop",
    'disagreeing': "received differently: message type, data or status",
    'interpreted': "read differently: another profile or other values",
    'hops': "only the repeater hop count differs",
    'missing': "at least one gateway did not receive it",
    'single': "only one gateway received it",
    'repeated': "a repeater delivered it to the same gateway twice",
}
DEFAULT_FILTER = 'all'


def _now_ms() -> int:
    return int(time.time() * 1000)


def _iso(timestamp_ms: int) -> str:
    return datetime.fromtimestamp(timestamp_ms / 1000, timezone.utc).isoformat(timespec='milliseconds')


def is_radio_telegram(record: dict) -> bool:
    """Whether a recorded telegram is a radio telegram which can be compared at all.

    Excluded are the house keeping messages of an RS485 bus (polling, discovery, memory): they
    are addressed by the position of an actuator on the bus instead of by an EnOcean address,
    they never leave the wire and therefore no second gateway can receive them.

    Excluded as well is everything a gateway read off its **wire** instead of out of the air: a
    device on an RS485 bus is addressed relative to the base id of its gateway, so a reception
    which carries a `local_address` came in over the bus (the status telegram of an FSR14
    reaching its FAM14). Counting it as reception would make a bus gateway the best receiver of
    every installation - it "hears" every actuator perfectly, over a wire - and would hide that
    the same telegram, put on air by the FAM14, was received by exactly one real transceiver.

    An *outgoing* telegram with a local address stays: a FAM14 transmits what goes over its bus
    on air as well, so it is the sender of a burst other gateways then receive - and a telegram
    a gateway sent itself is never counted as its reception anyway (see _Burst.receivers).
    """
    address = record.get('address')
    if not address or str(address).startswith('bus '):
        return False
    if record.get('role') == 'bus_message' or record.get('bus_address') is not None:
        return False
    if record.get('local_address') and record.get('direction') != TelegramDirection.OUTGOING.value:
        return False
    return record.get('gateway_id') is not None


def _text(value: Any) -> str:
    """One comparable string per field value ('-' for a field the telegram does not carry)."""
    return '-' if value is None else str(value)


def _status_base(status: Any) -> str | None:
    """Status byte without the repeater counter - see COMPARED_FIELDS."""
    if status is None:
        return None
    try:
        return f"0x{int(str(status), 16) & 0xF0:02X}"
    except (TypeError, ValueError):
        return str(status)


def decoded_to_text(decoded: Any) -> str | None:
    """The decoded values of a telegram as one comparable line.

    Only the text is kept, not the dict: ten thousand receptions with a dict of a dozen values
    each would be megabytes, and a line like `button_pressed=True, rocker_first_action=0` is
    what is compared and what is shown.
    """
    if not isinstance(decoded, dict) or not decoded:
        return None
    parts = []
    for key, value in sorted(decoded.items()):
        if key == 'eep_string':
            continue
        if isinstance(value, float):
            value = round(value, 2)
        parts.append(f"{key}={value}")
    return ", ".join(parts) or None


class _Reception:
    """One reception of one telegram by one gateway - what the comparison needs of a record.

    `__slots__` on purpose: ten thousand of these are kept, and a dict per reception would be
    an order of magnitude more memory for the same fields.
    """

    __slots__ = ('address', 'local_address', 'timestamp_ms', 'gateway_id', 'gateway_name',
                 'direction', 'seq', 'msg_type', 'org', 'data', 'status', 'status_base',
                 'rp_count', 'raw', 'rssi_dbm', 'simulated', 'device_name', 'known', 'eep',
                 'decoded')

    def __init__(self, record: dict, timestamp_ms: int):
        self.address = str(record['address']).upper()
        # a device on an RS485 bus is addressed relative to the base id of its gateway: the same
        # telegram carries a local address there and the absolute one everywhere else
        self.local_address = record.get('local_address')
        self.timestamp_ms = timestamp_ms
        self.gateway_id = record['gateway_id']
        self.gateway_name = record.get('gateway_name')
        self.direction = record.get('direction')
        self.seq = record.get('seq')
        self.msg_type = record.get('msg_type')
        self.org = record.get('org')
        self.data = record.get('data')
        self.status = record.get('status')
        self.status_base = _status_base(record.get('status'))
        self.rp_count = record.get('rp_count')
        self.raw = record.get('raw')
        rssi = record.get('rssi_dbm')
        self.rssi_dbm = int(rssi) if isinstance(rssi, (int, float)) else None
        self.simulated = bool(record.get('simulated'))
        self.device_name = record.get('device_name')
        self.known = bool(record.get('known'))
        # what the telegram was read as: the profile and the values which came out of it
        self.eep = record.get('eep') or record.get('decoded_eep') or record.get('teach_in_profile')
        self.decoded = decoded_to_text(record.get('decoded'))

    @property
    def is_outgoing(self) -> bool:
        return self.direction == TelegramDirection.OUTGOING.value

    @property
    def payload_key(self) -> tuple:
        """What makes two receptions the *same* telegram.

        Deliberately without the status byte: a repeater sends the telegram again with an
        incremented hop count, and one gateway can receive both. Those two receptions belong
        to the same transmission - a *different* payload from the same gateway is a new one.
        """
        return (self.msg_type, self.org, self.data)


class _Member:
    """What one gateway made of one transmission."""

    __slots__ = ('reception', 'offset_ms', 'repeats', 'rp_count_max', 'rssi_min', 'rssi_max')

    def __init__(self, reception: _Reception, first_ms: int):
        self.reception = reception
        self.offset_ms = max(0, reception.timestamp_ms - first_ms)
        self.repeats = 0
        self.rp_count_max = reception.rp_count
        self.rssi_min = reception.rssi_dbm
        self.rssi_max = reception.rssi_dbm

    def note_repetition(self, reception: _Reception) -> None:
        """The same telegram again at the same gateway - a repeater sent it twice."""
        self.repeats += 1
        self.rp_count_max = max(self.rp_count_max or 0, reception.rp_count or 0)
        if reception.rssi_dbm is not None:
            self.rssi_min = reception.rssi_dbm if self.rssi_min is None \
                else min(self.rssi_min, reception.rssi_dbm)
            self.rssi_max = reception.rssi_dbm if self.rssi_max is None \
                else max(self.rssi_max, reception.rssi_dbm)

    def to_dict(self) -> dict:
        reception = self.reception
        return {
            'gateway_id': reception.gateway_id,
            'gateway_name': reception.gateway_name,
            'direction': reception.direction,
            'simulated': reception.simulated,
            'seq': reception.seq,
            'address': reception.address,
            'local_address': reception.local_address,
            # what this gateway made of the telegram
            'eep': reception.eep,
            'decoded': reception.decoded,
            'timestamp_ms': reception.timestamp_ms,
            # how much later than the first gateway this one reported the telegram
            'offset_ms': self.offset_ms,
            'msg_type': reception.msg_type,
            'org': reception.org,
            'data': reception.data,
            'status': reception.status,
            'status_base': reception.status_base,
            'rp_count': reception.rp_count,
            'rp_count_max': self.rp_count_max,
            'raw': reception.raw,
            'rssi_dbm': reception.rssi_dbm,
            'rssi_min': self.rssi_min,
            'rssi_max': self.rssi_max,
            'repeats': self.repeats,
        }


class _Burst:
    """All receptions of one transmission."""

    __slots__ = ('address', 'first_ms', 'members', 'device_name', 'known', 'eep')

    def __init__(self, reception: _Reception):
        self.address = reception.address
        self.first_ms = reception.timestamp_ms
        self.members: dict[Any, _Member] = {}
        self.device_name = None
        self.known = False
        self.eep = None

    def add(self, reception: _Reception) -> bool:
        """Add a reception. False if it is a new telegram of the same device instead."""
        member = self.members.get(reception.gateway_id)
        if member is not None:
            if reception.payload_key != member.reception.payload_key:
                return False
            member.note_repetition(reception)
            return True

        self.members[reception.gateway_id] = _Member(reception, self.first_ms)
        self._note_device(reception)
        return True

    def _note_device(self, reception: _Reception) -> None:
        # every reception carries it, but not necessarily completely - the first answer wins
        self.device_name = self.device_name or reception.device_name
        self.known = self.known or reception.known
        self.eep = self.eep or reception.eep

    def fits(self, reception: _Reception, window_ms: int) -> bool:
        """The window starts at the *first* reception, so a chain of repeated telegrams
        cannot keep a burst open forever."""
        return reception.timestamp_ms - self.first_ms <= window_ms

    def receivers(self) -> list[_Member]:
        """The gateways which *received* it - a telegram a gateway sent itself says nothing
        about its reception, it is only kept for the context (and so its own telegram is not
        counted as missed)."""
        return [member for member in self.sorted_members() if not member.reception.is_outgoing]

    def senders(self) -> list[Any]:
        return [member.reception.gateway_id for member in self.sorted_members()
                if member.reception.is_outgoing]

    def sorted_members(self) -> list[_Member]:
        return sorted(self.members.values(),
                      key=lambda member: (member.offset_ms, str(member.reception.gateway_id)))


### ---------------------------------------------------------------------------
### comparison of one burst
### ---------------------------------------------------------------------------

def compare(receivers: list[_Member]) -> dict:
    """Which of the compared fields are not identical between the receiving gateways."""
    values: dict[str, dict[str, list]] = {}
    differences: list[str] = []
    majority: dict[str, str] = {}
    tied: list[str] = []
    outliers: set = set()

    for field in ALL_COMPARED_FIELDS:
        attribute = 'status_base' if field == 'status' else field
        buckets: dict[str, list] = {}
        for member in receivers:
            buckets.setdefault(_text(getattr(member.reception, attribute)), []) \
                   .append(member.reception.gateway_id)
        values[field] = buckets
        if len(buckets) < 2:
            continue
        differences.append(field)

        # The value most of the gateways agree on. It needs a *strict* majority: with two
        # gateways reporting two different bytes there is nothing to vote on, and naming one of
        # them the truth would blame a gateway at random. Then there simply is no majority and
        # no outlier - the two values stand next to each other.
        ranked = sorted(buckets, key=lambda value: (-len(buckets[value]), value))
        if len(buckets[ranked[0]]) == len(buckets[ranked[1]]):
            tied.append(field)
            continue
        majority[field] = ranked[0]
        # only a real disagreement makes a gateway the odd one out. Hearing the telegram
        # through a repeater while the others heard it directly is not a fault of the gateway -
        # that one is counted as a hop instead.
        if field == HOP_FIELD:
            continue
        for value, gateway_ids in buckets.items():
            if value != ranked[0]:
                outliers.update(gateway_ids)

    first = receivers[0].reception if receivers else None
    return {
        'differences': differences,
        # what came out of the air was not the same. A different repeater hop count is normal
        # and the interpretation is a question of the configuration, so both are kept apart.
        'disagreement': [field for field in differences
                         if field in COMPARED_FIELDS and field != HOP_FIELD],
        # the bytes may well be identical: the gateways read them as different values, which
        # points at the device behind the address, not at the reception
        'interpretation': [field for field in differences if field in INTERPRETATION_FIELDS],
        'values': values,
        'majority': majority,
        # fields whose values are evenly split, so no gateway can be called wrong
        'tied': tied,
        # what the differing bytes are marked against in the web ui: the reception which came
        # in first. Independent of the majority, so a 1:1 difference is still visible as
        # "these two bytes are not the same".
        'reference': {
            'msg_type': first.msg_type if first else None,
            'org': first.org if first else None,
            'data': first.data if first else None,
            'status': first.status if first else None,
            'gateway_id': first.gateway_id if first else None,
        },
        'outlier_gateway_ids': sorted(outliers, key=str),
    }


def matches_filter(burst: dict, name: str) -> bool:
    """Whether a burst belongs to the selected view - see FILTERS."""
    if name in (None, '', 'all'):
        return True
    if name == 'identical':
        return burst['gateway_count'] > 1 and not burst['differences']
    if name == 'differing':
        return bool(burst['differences'])
    if name == 'disagreeing':
        return bool(burst['disagreement'])
    if name == 'interpreted':
        return bool(burst['interpretation'])
    if name == 'hops':
        return burst['differences'] == [HOP_FIELD]
    if name == 'missing':
        return bool(burst['missing_gateway_ids'])
    if name == 'single':
        return burst['gateway_count'] == 1
    if name == 'repeated':
        return any(member['repeats'] for member in burst['members'])
    return True


### ---------------------------------------------------------------------------
### statistics
### ---------------------------------------------------------------------------

class _GatewayStatistics:
    """What one gateway received over all bursts of the analysed window."""

    def __init__(self, gateway_id, name: str | None, first_burst_index: int):
        self.gateway_id = gateway_id
        self.name = name
        # bursts which had already been counted when this gateway showed up for the first
        # time. Without it a gateway which was added later would look like it missed
        # everything which happened before it existed.
        self.first_burst_index = first_burst_index
        self.received = 0           # bursts in which it received the telegram
        self.sent = 0               # bursts which it sent itself
        self.missed = 0             # bursts another gateway received and it did not
        self.first = 0              # bursts in which it was the first one to report
        self.alone = 0              # bursts only it received
        self.outlier = 0            # bursts in which it disagreed with the majority
        # bursts it took part in which the gateways did not agree about. With only two
        # gateways there is no majority and therefore no outlier (see compare()) - this is the
        # number which still says "you were part of a telegram which came in twice differently"
        self.differing = 0
        self.repeats = 0            # receptions of an already received telegram (repeaters)
        self.hops = 0               # receptions which came over at least one repeater
        # how the telegrams arrived: hop count -> receptions. 0 is the direct path.
        self.by_level: dict[int, int] = {}
        self.rssi_sum = 0.0
        self.rssi_count = 0
        self.rssi_min: int | None = None
        self.rssi_max: int | None = None

    def note_rssi(self, rssi: int | None) -> None:
        if rssi is None:
            return
        self.rssi_sum += rssi
        self.rssi_count += 1
        self.rssi_min = rssi if self.rssi_min is None else min(self.rssi_min, rssi)
        self.rssi_max = rssi if self.rssi_max is None else max(self.rssi_max, rssi)

    def to_dict(self, burst_count: int) -> dict:
        offered = max(0, burst_count - self.first_burst_index)
        return {
            'gateway_id': self.gateway_id,
            'gateway_name': self.name,
            'received': self.received,
            'sent': self.sent,
            'missed': self.missed,
            # how many bursts it could have received: everything since it showed up
            'offered': offered,
            'share': None if offered == 0 else round(self.received / offered, 4),
            'first': self.first,
            'alone': self.alone,
            'outlier': self.outlier,
            'differing': self.differing,
            'repeats': self.repeats,
            'hops': self.hops,
            'by_level': {str(level): count for level, count in sorted(self.by_level.items())},
            'rssi_min': self.rssi_min,
            'rssi_max': self.rssi_max,
            'rssi_avg': None if self.rssi_count == 0 else round(self.rssi_sum / self.rssi_count, 1),
            'rssi_count': self.rssi_count,
        }


class _AddressStatistics:
    """What the gateways made of one EnOcean address - the 'who receives what' table."""

    def __init__(self, address: str):
        self.address = address
        self.name: str | None = None
        self.known = False
        self.eep: str | None = None
        self.bursts = 0
        self.differing = 0
        self.disagreeing = 0        # differences other than the repeater hop count
        self.max_gateway_count = 0
        self.last_seen_ms = 0
        self.gateways: dict[Any, dict] = {}

    def _entry(self, gateway_id) -> dict:
        # -1: `bursts` already counts the burst which is being added, and that one does count
        # for a gateway which shows up in it
        return self.gateways.setdefault(gateway_id, {
            'count': 0, 'first_burst_index': max(0, self.bursts - 1), 'rssi_sum': 0.0,
            'rssi_count': 0, 'rssi_min': None, 'rssi_max': None, 'hops': 0,
            # which path the telegrams of this device took to this gateway: hop count -> count
            'by_level': {},
        })

    def add(self, burst: dict, receivers: list[dict], known_gateway_ids: list) -> None:
        self.bursts += 1
        self.last_seen_ms = burst['timestamp_ms']
        self.known = self.known or bool(burst.get('known'))
        self.name = self.name or burst.get('device_name')
        self.eep = self.eep or burst.get('eep')
        if burst['differences']:
            self.differing += 1
        if burst['disagreement']:
            self.disagreeing += 1
        self.max_gateway_count = max(self.max_gateway_count, len(receivers))

        for member in receivers:
            entry = self._entry(member['gateway_id'])
            entry['count'] += 1
            level = int(member.get('rp_count') or 0)
            entry['by_level'][level] = entry['by_level'].get(level, 0) + 1
            if level:
                entry['hops'] += 1
            rssi = member.get('rssi_dbm')
            if rssi is not None:
                entry['rssi_sum'] += rssi
                entry['rssi_count'] += 1
                entry['rssi_min'] = rssi if entry['rssi_min'] is None else min(entry['rssi_min'], rssi)
                entry['rssi_max'] = rssi if entry['rssi_max'] is None else max(entry['rssi_max'], rssi)

        # a gateway which never received this address at all still has to appear in its row -
        # "this device is not heard by that gateway" is exactly what the table is for
        for gateway_id in known_gateway_ids:
            self._entry(gateway_id)

    def to_dict(self) -> dict:
        gateways = {}
        for gateway_id, entry in self.gateways.items():
            offered = max(0, self.bursts - entry['first_burst_index'])
            levels = entry['by_level']
            gateways[str(gateway_id)] = {
                'count': entry['count'],
                'offered': offered,
                'missed': max(0, offered - entry['count']),
                'share': None if offered == 0 else round(entry['count'] / offered, 4),
                'hops': entry['hops'],
                # how this gateway hears this device: 0 = directly, 1 / 2 = over a repeater
                'by_level': {str(level): count for level, count in sorted(levels.items())},
                'direct': levels.get(0, 0),
                # the best path which was ever seen - a device which arrives directly at least
                # sometimes is in range, one which never does depends on the repeater
                'best_level': min(levels) if levels else None,
                'worst_level': max(levels) if levels else None,
                'rssi_min': entry['rssi_min'],
                'rssi_max': entry['rssi_max'],
                'rssi_avg': None if entry['rssi_count'] == 0
                            else round(entry['rssi_sum'] / entry['rssi_count'], 1),
            }
        return {
            'address': self.address,
            'name': self.name,
            'known': self.known,
            'eep': self.eep,
            'bursts': self.bursts,
            'differing': self.differing,
            'disagreeing': self.disagreeing,
            'max_gateway_count': self.max_gateway_count,
            'last_seen': _iso(self.last_seen_ms) if self.last_seen_ms else None,
            'gateways': gateways,
        }


class _FieldStatistics:
    """Where one kind of difference happens: on which device, and at which gateway.

    "The data bytes differed twelve times" is the beginning of the question, not the answer -
    the next one is always *which device* and *which gateway is the odd one out*, and without
    them the number is only a reason to scroll through the telegram list. Both are collected
    here so the page can say it in one line.

    A gateway is only named when it really is the odd one out: with two gateways reporting two
    different bytes there is no majority (see `compare()`), nobody can be blamed, and that case
    is counted as `tied` instead.
    """

    def __init__(self, field: str):
        self.field = field
        self.count = 0
        self.tied = 0               # bursts in which the values were evenly split
        self.last_ms = 0
        self.addresses: dict[str, dict] = {}
        self.gateways: dict[Any, dict] = {}

    def add(self, burst: dict, names: dict) -> None:
        self.count += 1
        self.last_ms = max(self.last_ms, burst['timestamp_ms'])

        address = self.addresses.get(burst['address'])
        if address is None:
            address = self.addresses[burst['address']] = {
                'address': burst['address'], 'name': burst.get('device_name'),
                'known': bool(burst.get('known')), 'count': 0}
        address['count'] += 1
        address['name'] = address['name'] or burst.get('device_name')
        address['known'] = address['known'] or bool(burst.get('known'))

        if self.field in (burst.get('tied') or ()):
            self.tied += 1
            return
        majority = (burst.get('majority') or {}).get(self.field)
        if majority is None:
            return
        for value, gateway_ids in ((burst.get('values') or {}).get(self.field) or {}).items():
            if value == majority:
                continue
            for gateway_id in gateway_ids:
                entry = self.gateways.get(gateway_id)
                if entry is None:
                    entry = self.gateways[gateway_id] = {
                        'gateway_id': gateway_id, 'gateway_name': names.get(gateway_id),
                        'count': 0}
                entry['count'] += 1
                entry['gateway_name'] = entry['gateway_name'] or names.get(gateway_id)

    def to_dict(self) -> dict:
        addresses = sorted(self.addresses.values(),
                           key=lambda entry: (-entry['count'], entry['address']))
        return {
            'field': self.field,
            'count': self.count,
            'tied': self.tied,
            'last_seen': _iso(self.last_ms) if self.last_ms else None,
            # the whole list can be long in a big installation - the page names the worst few
            # and says how many more there are
            'address_count': len(addresses),
            'addresses': addresses[:MAX_NAMED_ADDRESSES],
            'gateways': sorted(self.gateways.values(),
                               key=lambda entry: (-entry['count'], str(entry['gateway_id']))),
        }


class RadioComparison:
    """Records the receptions of radio telegrams and compares them on demand.

    `add()` is called from the thread which records the telegram (the serial bus thread of a
    gateway) and does nothing but append to a ring buffer; `get_report()` runs in the event
    loop and does the whole grouping and comparison for the window it is asked for. Both are
    guarded by one lock.
    """

    def __init__(self, buffer_size: int = DEFAULT_BUFFER_SIZE):
        self.buffer_size = max(int(buffer_size), 1)
        self._lock = threading.Lock()
        self._receptions: deque[_Reception] = deque(maxlen=self.buffer_size)
        self._dropped = 0
        self._started_at_ms = _now_ms()

    ### recording

    def add(self, record: dict) -> None:
        """Feed one recorded telegram (see EnOceanTelegramLogger.record_message)."""
        if not is_radio_telegram(record):
            return

        timestamp_ms = record.get('timestamp_ms')
        reception = _Reception(record, int(timestamp_ms) if timestamp_ms else _now_ms())
        with self._lock:
            if len(self._receptions) == self.buffer_size:
                self._dropped += 1
            self._receptions.append(reception)

    ### grouping

    def _group(self, window_ms: int, receptions: list[_Reception]) -> list[_Burst]:
        """The receptions of the buffer as bursts - one per transmission.

        Open bursts are only closed for the address which is currently being added (they are
        independent of each other), so this is one pass over the buffer.
        """
        open_bursts: dict[str, _Burst] = {}
        bursts: list[_Burst] = []

        for reception in receptions:
            burst = open_bursts.get(reception.address)
            if burst is not None and not burst.fits(reception, window_ms):
                burst = None                        # the window has passed
            if burst is not None and not burst.add(reception):
                # the same gateway reported a different payload: a new telegram of this device
                burst = None
            if burst is None:
                burst = _Burst(reception)
                burst.add(reception)
                open_bursts[reception.address] = burst
                bursts.append(burst)

        bursts.sort(key=lambda entry: entry.first_ms)
        return bursts

    ### queries used by the web ui

    def get_report(self, window_ms: int = DEFAULT_WINDOW_MS, limit: int = 50,
                   telegram_filter: str = DEFAULT_FILTER, gateway_ids: list = None,
                   address: str = None) -> dict:
        """Everything the radio page shows, computed for `window_ms`.

        `gateway_ids` and `address` narrow the *whole* analysis down: two gateways and one
        sender is the direct comparison of those two - "of the 84 telegrams of this button,
        which one did each of the two hear, and did they read them the same way?". Restricting
        the gateways changes what "missing" means, which is the point: a telegram the third
        gateway received is none of their business.

        `limit` and `telegram_filter` only apply to the list of single telegrams - the summary,
        the per gateway and the per address numbers always describe everything which is left
        after the restriction, so a filter cannot make a gateway look better than it is.
        """
        window_ms = max(MIN_WINDOW_MS, min(int(window_ms or DEFAULT_WINDOW_MS), MAX_WINDOW_MS))
        with self._lock:
            all_receptions = list(self._receptions)
            dropped = self._dropped
            started_at_ms = self._started_at_ms

        # what can be selected: everything the buffer holds, independent of the current
        # restriction - otherwise choosing one sender would empty the list of senders
        available = self._available(all_receptions)

        wanted_gateways = {str(gateway_id) for gateway_id in (gateway_ids or [])}
        wanted_address = str(address).upper() if address else None
        receptions = [reception for reception in all_receptions
                      if (not wanted_gateways or str(reception.gateway_id) in wanted_gateways)
                      and (wanted_address is None or reception.address == wanted_address)]

        bursts = [self._describe(burst) for burst in self._group(window_ms, receptions)]
        statistics = self._analyse(bursts)

        counts = {name: 0 for name in FILTERS}
        for burst in bursts:
            for name in FILTERS:
                if matches_filter(burst, name):
                    counts[name] += 1

        selected = [burst for burst in bursts if matches_filter(burst, telegram_filter)]
        summary = {
            'enabled': True,
            'window_ms': window_ms,
            'window_choices': list(WINDOW_CHOICES),
            'filter': telegram_filter if telegram_filter in FILTERS else DEFAULT_FILTER,
            'filters': dict(FILTERS),
            'filter_counts': counts,
            'started_at': _iso(started_at_ms),
            'telegram_count': len(receptions),
            'buffer_size': self.buffer_size,
            # receptions which fell out of the buffer: the numbers describe what is left
            'dropped_count': dropped,
            'covers_from': _iso(receptions[0].timestamp_ms) if receptions else None,
            'last_telegram': _iso(receptions[-1].timestamp_ms) if receptions else None,
            **statistics['summary'],
        }
        summary['available'] = available
        summary['selected_gateway_ids'] = sorted(wanted_gateways)
        summary['selected_address'] = wanted_address
        summary['hop_level_labels'] = {str(level): label
                                       for level, label in HOP_LEVEL_LABELS.items()}
        return {
            'summary': summary,
            'gateways': statistics['gateways'],
            'addresses': statistics['addresses'],
            # every pair of gateways head to head - see _compare_pairs
            'pairs': statistics['pairs'],
            # newest first - the same order as the live view
            'bursts': list(reversed(selected))[:limit],
            'selected_count': len(selected),
        }

    def _available(self, receptions: list[_Reception]) -> dict:
        """What can be selected: the gateways and the senders the buffer knows about."""
        gateways: dict[Any, dict] = {}
        addresses: dict[str, dict] = {}
        for reception in receptions:
            gateway = gateways.get(reception.gateway_id)
            if gateway is None:
                gateway = gateways[reception.gateway_id] = {
                    'gateway_id': reception.gateway_id, 'gateway_name': reception.gateway_name,
                    'count': 0}
            gateway['count'] += 1
            gateway['gateway_name'] = gateway['gateway_name'] or reception.gateway_name

            address = addresses.get(reception.address)
            if address is None:
                address = addresses[reception.address] = {
                    'address': reception.address, 'name': reception.device_name,
                    'known': reception.known, 'count': 0}
            address['count'] += 1
            address['name'] = address['name'] or reception.device_name
            address['known'] = address['known'] or reception.known

        return {
            'gateways': sorted(gateways.values(), key=lambda entry: str(entry['gateway_id'])),
            # the busiest sender first: that is the one somebody is watching while walking
            # around with a transmitter
            'addresses': sorted(addresses.values(), key=lambda entry: (-entry['count'],
                                                                      entry['address'])),
        }

    def _describe(self, burst: _Burst) -> dict:
        """One burst as the web ui reads it, including the comparison of its receptions."""
        members = burst.sorted_members()
        receivers = burst.receivers()
        rssi_values = [member.reception.rssi_dbm for member in receivers
                       if member.reception.rssi_dbm is not None]
        return {
            'address': burst.address,
            'device_name': burst.device_name,
            'known': burst.known,
            'eep': burst.eep,
            'timestamp_ms': burst.first_ms,
            'timestamp': _iso(burst.first_ms),
            'gateway_count': len(receivers),
            'sender_gateway_ids': burst.senders(),
            'span_ms': members[-1].offset_ms if members else 0,
            'members': [member.to_dict() for member in members],
            'rssi_min': min(rssi_values) if rssi_values else None,
            'rssi_max': max(rssi_values) if rssi_values else None,
            'rssi_spread': (max(rssi_values) - min(rssi_values)) if len(rssi_values) > 1 else None,
            # filled in by _analyse: which gateways existed at that point in time
            'known_gateway_ids': [],
            'missing_gateway_ids': [],
            **compare(receivers),
        }

    def _analyse(self, bursts: list[dict]) -> dict:
        """Per gateway and per address statistics over all bursts, oldest first.

        Chronological order matters: a gateway is only held responsible for the telegrams
        which happened after it showed up for the first time.
        """
        gateways: dict[Any, _GatewayStatistics] = {}
        addresses: dict[str, _AddressStatistics] = {}
        pairs: dict[tuple, dict] = {}
        by_gateway_count: dict[int, int] = {}
        by_field = {field: 0 for field in ALL_COMPARED_FIELDS}
        field_detail: dict[str, _FieldStatistics] = {}
        differing_bursts = 0
        disagreeing_bursts = 0
        interpreted_bursts = 0

        def statistics_of(gateway_id, name, index) -> _GatewayStatistics:
            entry = gateways.get(gateway_id)
            if entry is None:
                entry = gateways[gateway_id] = _GatewayStatistics(gateway_id, name, index)
            if name and not entry.name:
                entry.name = name
            return entry

        for index, burst in enumerate(bursts):
            members = burst['members']
            receivers = [member for member in members
                         if member['direction'] != TelegramDirection.OUTGOING.value]

            for member in members:
                statistics_of(member['gateway_id'], member['gateway_name'], index)
            known_gateway_ids = sorted(gateways, key=str)
            present = {member['gateway_id'] for member in members}
            missing = [gateway_id for gateway_id in known_gateway_ids
                       if gateway_id not in present
                       # a gateway which did not exist yet did not miss this telegram
                       and gateways[gateway_id].first_burst_index <= index]
            burst['known_gateway_ids'] = known_gateway_ids
            burst['missing_gateway_ids'] = missing

            by_gateway_count[len(receivers)] = by_gateway_count.get(len(receivers), 0) + 1
            names = {member['gateway_id']: member['gateway_name'] for member in members}
            for field in burst['differences']:
                by_field[field] = by_field.get(field, 0) + 1
                detail = field_detail.get(field)
                if detail is None:
                    detail = field_detail[field] = _FieldStatistics(field)
                detail.add(burst, names)
            if burst['differences']:
                differing_bursts += 1
            if burst['disagreement']:
                disagreeing_bursts += 1
            if burst['interpretation']:
                interpreted_bursts += 1
            self._compare_pairs(pairs, burst, receivers, known_gateway_ids, gateways, index)

            for member in receivers:
                entry = statistics_of(member['gateway_id'], member['gateway_name'], index)
                entry.received += 1
                entry.repeats += member['repeats']
                level = int(member.get('rp_count') or 0)
                entry.by_level[level] = entry.by_level.get(level, 0) + 1
                if level:
                    entry.hops += 1
                entry.note_rssi(member['rssi_dbm'])
                if len(receivers) == 1:
                    entry.alone += 1
                if burst['disagreement']:
                    entry.differing += 1
                if member['gateway_id'] in burst['outlier_gateway_ids']:
                    entry.outlier += 1
            # who was there first - only meaningful when there was a race to win. The winner is
            # usually the gateway closest to the device, so a gateway which is never first
            # while its reception rate is fine sits at the edge of the range of everything.
            if len(receivers) > 1:
                statistics_of(receivers[0]['gateway_id'], None, index).first += 1
            for gateway_id in burst['sender_gateway_ids']:
                statistics_of(gateway_id, None, index).sent += 1
            for gateway_id in missing:
                statistics_of(gateway_id, None, index).missed += 1

            address = addresses.get(burst['address'])
            if address is None:
                address = addresses[burst['address']] = _AddressStatistics(burst['address'])
            address.add(burst, receivers, known_gateway_ids)

        burst_count = len(bursts)
        gateway_rows = [entry.to_dict(burst_count) for entry in gateways.values()]
        gateway_rows.sort(key=lambda row: str(row['gateway_id']))
        address_rows = [entry.to_dict() for entry in addresses.values()]
        address_rows.sort(key=lambda row: (-row['disagreeing'], -row['bursts']))

        return {
            'summary': {
                'burst_count': burst_count,
                'differing_bursts': differing_bursts,
                'disagreeing_bursts': disagreeing_bursts,
                'interpreted_bursts': interpreted_bursts,
                'by_field': by_field,
                # the same counts with the answer to "where": which devices, which gateways
                'by_field_detail': {field: detail.to_dict()
                                    for field, detail in field_detail.items()},
                'by_gateway_count': {str(count): value
                                     for count, value in sorted(by_gateway_count.items())},
                'multi_gateway_bursts': sum(value for count, value in by_gateway_count.items()
                                            if count > 1),
                'single_gateway_bursts': by_gateway_count.get(1, 0),
                'gateway_count': len(gateways),
                'address_count': len(addresses),
                'compared_fields': list(COMPARED_FIELDS),
                'interpretation_fields': list(INTERPRETATION_FIELDS),
                'hop_field': HOP_FIELD,
            },
            'gateways': gateway_rows,
            'addresses': address_rows,
            'pairs': self._describe_pairs(pairs),
        }

    ### two gateways head to head

    def _compare_pairs(self, pairs: dict, burst: dict, receivers: list[dict],
                       known_gateway_ids: list, gateways: dict, index: int) -> None:
        """Every pair of gateways against each other, for this one transmission.

        The per gateway table says how much a gateway hears in total, which does not answer
        "which of these two is the better one *for this device*" - one of them may be counting
        telegrams the other one is not even in range of. A pair only counts the transmissions
        which happened while both of them existed, so the two columns are comparable.
        """
        by_gateway = {member['gateway_id']: member for member in receivers}
        for position, left in enumerate(known_gateway_ids):
            if gateways[left].first_burst_index > index:
                continue
            for right in known_gateway_ids[position + 1:]:
                if gateways[right].first_burst_index > index:
                    continue
                pair = pairs.get((left, right))
                if pair is None:
                    pair = pairs[(left, right)] = {
                        'gateway_a': left, 'gateway_b': right, 'together': 0, 'only_a': 0,
                        'only_b': 0, 'neither': 0, 'agreed': 0, 'disagreed': 0, 'hops': 0,
                        'interpreted': 0, 'delta_sum': 0.0, 'delta_count': 0,
                        'a_stronger': 0, 'b_stronger': 0,
                    }
                member_a = by_gateway.get(left)
                member_b = by_gateway.get(right)
                if member_a is None and member_b is None:
                    pair['neither'] += 1
                    continue
                if member_b is None:
                    pair['only_a'] += 1
                    continue
                if member_a is None:
                    pair['only_b'] += 1
                    continue

                pair['together'] += 1
                # the same fields the burst comparison uses, and the status byte the same way:
                # without the repeater counter, which is reported as 'hops' instead
                if any(_text(member_a.get(key)) != _text(member_b.get(key))
                       for key in ('status_base' if field == 'status' else field
                                   for field in COMPARED_FIELDS if field != HOP_FIELD)):
                    pair['disagreed'] += 1
                else:
                    pair['agreed'] += 1
                if _text(member_a.get(HOP_FIELD)) != _text(member_b.get(HOP_FIELD)):
                    pair['hops'] += 1
                if any(_text(member_a.get(field)) != _text(member_b.get(field))
                       for field in INTERPRETATION_FIELDS):
                    pair['interpreted'] += 1
                if member_a['rssi_dbm'] is not None and member_b['rssi_dbm'] is not None:
                    delta = member_a['rssi_dbm'] - member_b['rssi_dbm']
                    pair['delta_sum'] += delta
                    pair['delta_count'] += 1
                    if delta > 0:
                        pair['a_stronger'] += 1
                    elif delta < 0:
                        pair['b_stronger'] += 1

    def _describe_pairs(self, pairs: dict) -> list[dict]:
        result = []
        for pair in pairs.values():
            count = pair.pop('delta_count')
            total = pair.pop('delta_sum')
            offered = pair['together'] + pair['only_a'] + pair['only_b'] + pair['neither']
            result.append({
                **pair,
                'offered': offered,
                # how much stronger a hears the same telegram than b, on average
                'rssi_delta_avg': round(total / count, 1) if count else None,
                'rssi_delta_count': count,
                'share_a': round((pair['together'] + pair['only_a']) / offered, 4) if offered else None,
                'share_b': round((pair['together'] + pair['only_b']) / offered, 4) if offered else None,
            })
        result.sort(key=lambda entry: (-entry['disagreed'], -entry['together']))
        return result

    def clear(self) -> None:
        with self._lock:
            self._receptions.clear()
            self._dropped = 0
            self._started_at_ms = _now_ms()
