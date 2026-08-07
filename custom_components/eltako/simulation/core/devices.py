"""One virtual device: what it is, what it reports and which telegram it sends."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from eltakobus.message import ESP2Message

from .addressing import normalize_address
from .constants import (ACTUATOR_PLATFORMS, MAX_INTERVAL_SECONDS, MIN_INTERVAL_SECONDS,
                        SIMULATED_PLATFORMS)
from .errors import SimulationError
from .telegrams import (default_state, eep_fields, encode_state_telegram,
                        encode_teach_in_telegram, has_teach_in_telegram, public_state,
                        teach_in_description, teach_in_kind)


def _validated_taught_in(entries, platform: str) -> list:
    """The senders which were taught into a device: [{'id', 'eep', 'name'}].

    Only an actuator has a memory - a sensor is never sent to, so teaching something into it
    would do nothing. A duplicate address is dropped instead of stored twice.
    """
    if not entries:
        return []
    if platform not in ACTUATOR_PLATFORMS:
        raise SimulationError(f"A {platform} is not controlled by anybody - nothing can be "
                              f"taught into it.")

    result = []
    seen = set()
    for entry in entries:
        if isinstance(entry, str):
            entry = {'id': entry}
        address = normalize_address((entry or {}).get('id'))
        if address in seen:
            continue
        eep = str((entry or {}).get('eep') or '').upper()
        if eep:
            eep_fields(eep)             # raises for an unknown EEP
        seen.add(address)
        result.append({'id': address, 'eep': eep or None,
                       'name': str((entry or {}).get('name') or '') or None})
    return result


def _validated_interval(value) -> int:
    """Seconds between two telegrams a device sends on its own. 0 (or nothing) = off."""
    if value in (None, "", False):
        return 0
    try:
        seconds = int(float(value))
    except (TypeError, ValueError):
        raise SimulationError(f"'{value}' is no number of seconds.") from None
    if seconds < 0:
        raise SimulationError("An interval cannot be negative.")
    if seconds and not MIN_INTERVAL_SECONDS <= seconds <= MAX_INTERVAL_SECONDS:
        raise SimulationError(f"An interval has to be between {MIN_INTERVAL_SECONDS} and "
                              f"{MAX_INTERVAL_SECONDS} seconds (0 switches it off).")
    return seconds


@dataclass
class SimulatedDevice:
    """A device which does not exist: an address, a profile and the values it reports.

    Everything a real device would tell the automation system is derived from these fields, so
    a simulated device is defined by exactly the same information a configured device needs -
    which is why the detection can take it over unchanged.
    """

    address: str
    platform: str
    eep: str
    name: str = ""
    sender_id: str | None = None        # the address the automation system controls it with
    sender_eep: str | None = None
    hw_type: str | None = None          # device of the catalog it imitates, e.g. 'FSR14_4x'
    area: str | None = None
    # Senders which were taught into this device, like the memory of a real actuator: every
    # entry is {'id': address, 'eep': sender EEP, 'name': what it is}. A real wall switch, a
    # simulated one or another automation system can all be taught in here - the device reacts
    # to every one of them, not only to the sender of Home Assistant.
    taught_in: list = field(default_factory=list)
    state: dict = field(default_factory=dict)
    # seconds between two telegrams the device sends on its own (0 = only when triggered).
    # A real sensor repeats its measurement - this is what makes statistics, the telegram rate
    # and "has this device reported lately?" testable.
    interval: int = 0
    last_sent: str | None = None
    sent_count: int = 0

    ### ------------------------------------------------------------- construction

    @classmethod
    def create(cls, **values) -> 'SimulatedDevice':
        """Build a validated device. Raises SimulationError for anything which cannot work."""
        known = {name: values.get(name) for name in cls.__dataclass_fields__}
        unknown = set(values) - set(cls.__dataclass_fields__)
        if unknown:
            raise SimulationError(f"A simulated device has no field(s) {', '.join(sorted(unknown))}.")

        platform = str(known.get('platform') or '')
        if platform not in SIMULATED_PLATFORMS:
            raise SimulationError(f"'{platform}' cannot be simulated. Known platforms: "
                                  f"{', '.join(sorted(SIMULATED_PLATFORMS))}.")
        if not known.get('eep'):
            raise SimulationError("A simulated device needs an EEP, e.g. A5-04-02.")

        eep = str(known['eep']).upper()
        eep_fields(eep)             # raises for an unknown EEP

        sender_id = known.get('sender_id')
        sender_eep = known.get('sender_eep')
        if platform in ACTUATOR_PLATFORMS:
            if not sender_eep:
                raise SimulationError(f"A {platform} is controlled by the automation system and "
                                      f"needs a sender EEP.")
            if not sender_id:
                raise SimulationError(f"A {platform} needs the sender address the automation "
                                      f"system controls it with.")
            sender_eep = str(sender_eep).upper()
            eep_fields(sender_eep)
            sender_id = normalize_address(sender_id)
        else:
            sender_id = None        # a sensor is never sent to
            sender_eep = None

        device = cls(
            address=normalize_address(known.get('address')),
            platform=platform,
            eep=eep,
            name=str(known.get('name') or '') or f"Simulated {platform}",
            sender_id=sender_id,
            sender_eep=sender_eep,
            hw_type=known.get('hw_type') or None,
            area=known.get('area') or None,
            taught_in=_validated_taught_in(known.get('taught_in'), platform),
            state={**default_state(eep), **(known.get('state') or {})},
            interval=_validated_interval(known.get('interval')),
            last_sent=known.get('last_sent') or None,
            sent_count=int(known.get('sent_count') or 0),
        )
        return device

    ### ------------------------------------------------------------------ queries

    @property
    def is_actuator(self) -> bool:
        return self.platform in ACTUATOR_PLATFORMS

    @property
    def has_teach_in(self) -> bool:
        """True if this profile can announce itself at all (4BS, 1BS or RPS)."""
        return has_teach_in_telegram(self.eep)

    @property
    def teach_in_kind(self) -> str | None:
        """'4bs', '1bs' or 'rps' - which kind of announcement its profile family has."""
        return teach_in_kind(self.eep)

    @property
    def teach_in_description(self) -> str:
        return teach_in_description(self.eep)

    @property
    def is_repeating(self) -> bool:
        """True if the device sends on its own instead of only when it is triggered."""
        return int(self.interval or 0) > 0

    @property
    def senders(self) -> list[dict]:
        """Every sender this device reacts to: the one of Home Assistant plus the taught-in ones.

        Same order a real actuator would answer in: its 'own' sender first (that is the one the
        configuration of Home Assistant uses), then whatever was taught in later.
        """
        senders = []
        if self.sender_id:
            senders.append({'id': self.sender_id, 'eep': self.sender_eep,
                            'name': "Home Assistant", 'role': 'ha_sender'})
        for entry in self.taught_in or []:
            senders.append({**entry, 'role': 'taught_in',
                            # without an own EEP the one of the automation system is assumed
                            'eep': entry.get('eep') or self.sender_eep})
        return senders

    def find_sender(self, address) -> dict | None:
        """The sender entry for this address, or None if this device does not know it."""
        try:
            wanted = normalize_address(address)
        except SimulationError:
            return None
        return next((sender for sender in self.senders if sender['id'] == wanted), None)

    def knows_sender(self, address) -> bool:
        return self.find_sender(address) is not None

    def teach_in(self, address, eep: str = None, name: str = None) -> dict:
        """Take a sender into the memory of this device. Returns the stored entry."""
        if not self.is_actuator:
            raise SimulationError(f"A {self.platform} is not controlled by anybody - nothing can "
                                  f"be taught into it.")
        entry = {'id': normalize_address(address), 'eep': str(eep).upper() if eep else None,
                 'name': name or None}
        if entry['eep']:
            eep_fields(entry['eep'])
        if entry['id'] == self.sender_id:
            raise SimulationError(f"{entry['id']} is already the sender Home Assistant controls "
                                  f"this device with.")
        self.taught_in = [existing for existing in self.taught_in
                          if existing['id'] != entry['id']] + [entry]
        return entry

    def forget_sender(self, address) -> bool:
        """Remove a taught-in sender. The sender of Home Assistant cannot be removed here."""
        wanted = normalize_address(address)
        before = len(self.taught_in)
        self.taught_in = [entry for entry in self.taught_in if entry['id'] != wanted]
        return len(self.taught_in) != before

    @property
    def fields(self) -> list[str]:
        """Names of the values its telegram carries - a ui renders one input per field."""
        try:
            return eep_fields(self.eep)
        except SimulationError:
            return []

    def public_state(self) -> dict:
        """The reported values without the keys the simulation keeps for itself."""
        return public_state(self.state)

    ### ----------------------------------------------------------------- changing

    def apply_state(self, values: dict, reset: bool = False) -> dict:
        """Take over reported values. `reset` starts from the defaults of the EEP again."""
        base = default_state(self.eep) if reset else dict(self.state)
        base.update(values or {})
        self.state = base
        return self.state

    def note_sent(self, when: str = None) -> None:
        self.last_sent = when or datetime.now(timezone.utc).isoformat(timespec='seconds')
        self.sent_count = int(self.sent_count or 0) + 1

    ### ---------------------------------------------------------------- telegrams

    def state_telegram(self, state: dict = None) -> ESP2Message:
        """The telegram this device sends for its current (or the given) values."""
        return encode_state_telegram(self.address, self.eep,
                                     self.state if state is None else state)

    def teach_in_telegrams(self) -> list[ESP2Message]:
        """What it sends when its teach-in button is pressed - see encode_teach_in_telegram."""
        return encode_teach_in_telegram(self.address, self.eep)

    def telegrams(self, kind: str = 'state') -> list[ESP2Message]:
        """The telegram(s) of one action. 'state' is always one, 'teach_in' can be two (RPS)."""
        if kind == 'teach_in':
            return self.teach_in_telegrams()
        if kind != 'state':
            raise SimulationError(f"'{kind}' is no known telegram kind - use 'state' or 'teach_in'.")
        return [self.state_telegram()]

    ### ------------------------------------------------------------ serialization

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'SimulatedDevice':
        return cls.create(**(data or {}))

    def describe(self) -> dict:
        """The device plus what a ui needs to render and trigger it."""
        return {**self.to_dict(), 'fields': self.fields, 'actuator': self.is_actuator,
                'senders': self.senders,
                'teach_in': self.has_teach_in, 'teach_in_kind': self.teach_in_kind,
                'teach_in_description': self.teach_in_description,
                'repeating': self.is_repeating}
