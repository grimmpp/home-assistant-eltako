"""What kind of device sent a telegram? EEP and device candidates for unknown addresses.

An address which is not configured yet only reveals itself through its telegrams. This module
derives candidates from them, so the web ui can offer them instead of letting the user guess:

1. a 4BS **teach-in** telegram carries the EEP of the device - that is a fact, not a guess
2. the **message type** limits the possible EEPs (RPS cannot be A5-04-02)
3. the **data bytes** decide between the remaining ones: every candidate EEP is decoded and
   the result is checked for plausibility (a humidity of 300% rules A5-04-02 out)
4. the **address** narrows it further (a local 00-00-.. id below 0x1500 is an FTS14EM input)

The device candidates come from the central device catalog (device_catalog.py) - the same
source the device form uses, so the web ui never carries its own device knowledge.
"""

from __future__ import annotations

from eltakobus.eep import EEP

from ..const import LOGGER
from ..catalog.device_catalog import DEVICE_CATALOG

LOG_PREFIX_SUGGEST = "Telegram Suggestions"

def _known_profiles() -> list[type[EEP]]:
    """Return every concrete profile registered by eltako14bus."""
    registry = getattr(EEP, '_EEP__sublasses_by_string', {})
    return [registry[key] for key in sorted(registry) if registry.get(key)]


def _profiles_by_message_type() -> dict[str, list[str]]:
    """Build transport candidates from the library's EEP metadata."""
    families = {0x05: 'RPS', 0x06: '1BS', 0x07: '4BS'}
    result = {'RPS': [], '1BS': [], '4BS': []}
    for profile in _known_profiles():
        # M5/H5 are actuator command/sender profiles. They are valid EEPs, but are not
        # useful candidates when identifying an unknown incoming sensor telegram.
        if profile.eep_string[:2] not in {'A5', 'D5', 'F6'}:
            continue
        family = families.get(profile.get_metadata().org)
        if family:
            result[family].append(profile.eep_string)
    preferred = {
        'RPS': ['F6-02-01', 'F6-02-02', 'F6-01-01', 'F6-05-01', 'F6-05-02', 'F6-10-00'],
        '1BS': ['D5-00-01'],
        '4BS': ['A5-04-02', 'A5-04-01', 'A5-04-03', 'A5-08-01', 'A5-06-01', 'A5-07-01',
                'A5-10-03', 'A5-10-06', 'A5-10-12', 'A5-12-01', 'A5-12-02', 'A5-12-03',
                'A5-13-01', 'A5-30-01', 'A5-30-03', 'A5-09-04', 'A5-09-05', 'A5-09-0C'],
    }
    for family, profiles in result.items():
        order = {eep: index for index, eep in enumerate(preferred[family])}
        profiles.sort(key=lambda eep: (order.get(eep, len(order)), eep))
    return result


# The library registry and its ``org`` metadata are the source of truth. This includes new
# profiles automatically and avoids a second, drifting EEP list in the integration.
EEP_BY_MESSAGE_TYPE = _profiles_by_message_type()


def _message_family(msg_type: str) -> str | None:
    """Message class name of the library -> RPS / 1BS / 4BS."""
    name = str(msg_type or '')
    if 'RPS' in name:
        return 'RPS'
    if '1BS' in name:
        return '1BS'
    if '4BS' in name:
        return '4BS'
    return None


def devices_for_eep(eep: str) -> list[dict]:
    """Devices of the catalog which speak this EEP."""
    if not eep:
        return []
    result = []
    seen = set()
    for entry in DEVICE_CATALOG:
        if str(entry.get('eep', '')).upper() != str(eep).upper():
            continue
        if entry['hw_type'] in seen:
            continue
        seen.add(entry['hw_type'])
        result.append({
            'hw_type': entry['hw_type'],
            'brand': entry.get('brand'),
            'description': entry.get('description'),
            'platform': entry.get('platform'),
            'bus_device': bool(entry.get('bus_device')),
        })
    return result


def _decode(eep_string: str, data: bytes, status: int):
    """Decode raw 4 byte data with an EEP. None if it does not fit."""
    from eltakobus.eep import EEP
    from eltakobus.message import Regular1BSMessage, Regular4BSMessage, RPSMessage

    try:
        eep = EEP.find(eep_string)
    except Exception:   # noqa: BLE001 - an EEP without class is simply no candidate
        return None

    family = eep_string[:2].upper()
    address = b'\x00\x00\x00\x00'
    try:
        if family == 'A5':
            message = Regular4BSMessage(address=address, status=status, data=data[:4])
        elif family == 'D5':
            message = Regular1BSMessage(address=address, status=status, data=data[:1])
        elif family == 'F6':
            message = RPSMessage(address=address, status=status, data=data[:1])
        else:
            return None
        return eep.decode_message(message)
    except Exception:   # noqa: BLE001 - not decodable with this profile
        return None


def _decoded_values(decoded) -> dict | None:
    """Everything a profile makes of the telegram, as a plain dict (or None)."""
    if decoded is None:
        return None
    from .enocean_logger import decoded_eep_to_dict

    try:
        return decoded_eep_to_dict(decoded)
    except Exception:   # noqa: BLE001 - a broken property is no reason to drop the candidate
        return None


def _profile_metadata(eep_string: str) -> dict | None:
    """Return JSON-safe metadata for a candidate profile."""
    try:
        return EEP.find(eep_string).get_metadata().as_dict()
    except Exception:  # noqa: BLE001 - unknown EEPs are expected in diagnostics
        return None


def _plausibility(eep_string: str, decoded) -> tuple[bool, list[str]]:
    """Check decoded values against ranges declared by eltako14bus metadata.

    Returns (plausible, list of 'name=value' of the checked values). A profile without any
    checkable value stays a candidate - it just gets no confirmation from the data.
    """
    if decoded is None:
        return False, []

    values = []
    try:
        fields = EEP.find(eep_string).get_metadata().fields
    except Exception:  # noqa: BLE001 - a missing profile has no evidence
        return False, []
    for field in fields:
        if not field.value_range:
            continue
        name = field.name
        if not hasattr(decoded, name):
            continue
        try:
            value = getattr(decoded, name)
        except Exception:   # noqa: BLE001 - a broken property is no evidence
            continue
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        minimum, maximum = field.value_range
        if not minimum <= value <= maximum:
            return False, []
        values.append(f"{name}={round(value, 2)}")
    return True, values


def suggest(msg_types=None, data: str = None, status: str = None, address: str = None,
            teach_in_profile: str = None, limit: int = 4) -> list[dict]:
    """EEP candidates for one unknown address, best first.

    `msg_types` is the dict of the statistics (message type -> count), `data` and `status` are
    the hex fields of the last telegram ('12-34-56-78' / '0x30'). Every candidate carries why
    it was suggested and which devices of the catalog speak it.
    """
    candidates: list[dict] = []
    families = {family for family in (_message_family(name) for name in (msg_types or {}))
                if family}

    raw = _parse_hex(data)
    status_value = _parse_status(status)
    local_id = _local_bus_id(address)

    # 1) a teach-in telegram states the EEP - highest confidence, independent of the data
    if teach_in_profile:
        profile = str(teach_in_profile).upper()
        metadata = _profile_metadata(profile)
        candidate = {'eep': profile,
                     'confidence': 'confirmed' if metadata else 'unknown',
                     'reason': ('reported by the 4BS teach-in telegram of the device'
                                if metadata else 'reported EEP is not known to eltako14bus'),
                     'values': [], 'metadata': metadata, 'decoded': None}
        candidate['devices'] = devices_for_eep(profile)
        # A 4BS teach-in contains the sender's actual EEP. It is authoritative, so do not
        # dilute that fact with data-based guesses for other profiles in the UI.
        return [candidate][:limit]

    # 2) the message type limits the possible profiles
    possible: list[str] = []
    for family in sorted(families):
        possible.extend(EEP_BY_MESSAGE_TYPE.get(family, []))
    if not possible and raw:
        possible = EEP_BY_MESSAGE_TYPE['4BS'] if len(raw) >= 4 else EEP_BY_MESSAGE_TYPE['RPS']

    for eep in possible:
        if any(existing['eep'] == eep for existing in candidates):
            continue
        # 3) the data bytes decide: decode and check the values
        if raw:
            decoded = _decode(eep, raw, status_value)
            plausible, values = _plausibility(eep, decoded)
            if decoded is None:
                continue
            if not plausible:
                continue
            candidates.append({
                'eep': eep,
                'confidence': 'likely' if values else 'possible',
                'reason': (f"decodes the data plausibly ({', '.join(values)})" if values
                           else f"fits the {'/'.join(sorted(families)) or 'telegram'} type"),
                'values': values,
                # what this telegram *means* read as this profile. The range check above only
                # looks at the few physical values it knows; this is everything the profile
                # decodes, and it is what lets a human decide which candidate is the right
                # one ("22.4 °C, 41 %" against "button B pressed").
                'decoded': _decoded_values(decoded),
                'metadata': _profile_metadata(eep),
            })
        else:
            candidates.append({'eep': eep, 'confidence': 'possible',
                               'reason': f"fits the {'/'.join(sorted(families))} type",
                               'values': [], 'decoded': None, 'metadata': _profile_metadata(eep)})

    # 4) a wired FTS14EM input is recognizable by its low local address
    if local_id is not None and local_id < 0x1500:
        for candidate in candidates:
            if candidate['eep'] in ('F6-02-01', 'F6-02-02'):
                candidate['confidence'] = 'likely'
                candidate['reason'] = ("wired input: local bus address below 0x1500 - "
                                       "an FTS14EM channel")

    for candidate in candidates:
        candidate['devices'] = devices_for_eep(candidate['eep'])

    # Confidence first, then profiles with concrete catalog evidence. Within those groups the
    # stable metadata-derived profile order keeps the suggestions predictable.
    order = {'confirmed': 0, 'likely': 1, 'possible': 2}
    candidates.sort(key=lambda candidate: (order.get(candidate['confidence'], 3),
                                           0 if candidate['devices'] else 1))
    return candidates[:limit]


def suggest_for_record(device: dict, limit: int = 4) -> list[dict]:
    """Convenience wrapper for one entry of the telegram statistics."""
    try:
        return suggest(msg_types=device.get('msg_types'), data=device.get('last_data'),
                       status=device.get('last_status'), address=device.get('address'),
                       teach_in_profile=device.get('teach_in_profile'), limit=limit)
    except Exception as e:  # noqa: BLE001 - a suggestion must never break the statistics
        LOGGER.debug(f"[{LOG_PREFIX_SUGGEST}] Cannot suggest for {device.get('address')}: {e}")
        return []


def best_candidate(suggestions: list[dict]) -> dict:
    """The candidate to prefill a device form with. `suggest` returns them best first."""
    candidate = (suggestions or [])[0] if suggestions else None
    if not candidate:
        return {'eep': None, 'platform': None, 'hw_type': None,
                'confidence': None, 'reason': None}
    model = (candidate.get('devices') or [{}])[0]
    return {
        'eep': candidate['eep'],
        'platform': model.get('platform'),
        'hw_type': model.get('hw_type'),
        'confidence': candidate.get('confidence'),
        'reason': candidate.get('reason'),
    }


def yaml_snippet(device: dict, suggestions: list[dict] = None) -> str:
    """configuration.yaml lines for one unknown address, ready to paste under `devices:`.

    Lives here and not in the web ui: indentation and key names are configuration knowledge of
    the integration, and the same snippet is offered by the ui, a future service and the CLI.
    """
    best = best_candidate(suggestions if suggestions is not None else device.get('suggestions'))
    comment = f"{best['platform'] or 'sensor'}: seen {device.get('count', 0)} time(s), " \
              f"last data {device.get('last_data') or '-'}"
    if best['hw_type']:
        comment += f", e.g. {best['hw_type']}"
    if best['confidence']:
        comment += f" ({best['confidence']})"
    return (f"      # {comment}\n"
            f"      - id: {device.get('address')}\n"
            f"        eep: {best['eep'] or '<EEP>'}\n"
            f"        name: \"New device {device.get('address')}\"\n")


def enrich_unknown(device: dict, limit: int = 4) -> dict:
    """Add everything the web ui needs for one unknown address - in place.

    `suggestions` (all candidates incl. their devices), `suggested` (the one to prefill a form
    with) and `yaml` (the configuration.yaml snippet). The web ui only renders these fields, it
    derives nothing itself.
    """
    suggestions = suggest_for_record(device, limit=limit)
    device['suggestions'] = suggestions
    device['suggested'] = best_candidate(suggestions)
    device['yaml'] = yaml_snippet(device, suggestions)
    return device


### ---------------------------------------------------------------------------
### helpers
### ---------------------------------------------------------------------------

def _parse_hex(value: str | None) -> bytes | None:
    """'12-34-56-78' or '12345678' -> bytes."""
    if not value:
        return None
    try:
        return bytes.fromhex(str(value).replace('-', '').replace(' ', ''))
    except ValueError:
        return None


def _parse_status(value: str | None) -> int:
    if value is None:
        return 0
    try:
        return int(str(value), 16) if str(value).lower().startswith('0x') else int(value)
    except ValueError:
        return 0


def _local_bus_id(address: str | None) -> int | None:
    """Local bus address 00-00-xx-yy -> its numeric id, None for a wireless address."""
    text = str(address or '').upper()
    if not text.startswith('00-00-'):
        return None
    try:
        return int(text.replace('-', ''), 16)
    except ValueError:
        return None
