"""Which sender EEPs can be taught into an actuator, and with which telegram.

A teach-in button sends one 4BS telegram whose payload tells the actuator what kind of sender
it is being taught. The payload is a property of the EEP, not of the button entity, which is why
this table lives here and not in `button.py`: the button platform builds the entities from it,
and everything else that needs to know whether an EEP can be taught in - config checks, the
help page, the web ui - asks the helpers below instead of repeating the knowledge.
"""
from __future__ import annotations

from eltakobus.eep import A5_10_06, A5_10_12, A5_38_08, EEP, H5_3F_7F

#: sender EEP -> the data bytes of its teach-in telegram
EEP_WITH_TEACH_IN_BUTTONS = {
    A5_10_06: b'\x40\x30\x0D\x85',  # climate
    A5_10_12: b'\x40\x90\x0D\x80',  # climate
    A5_38_08: b'\xE0\x40\x0D\x80',  # light
    H5_3F_7F: b'\xFF\xF8\x0D\x80',  # cover
    # F6_02_01  # What button to take?
    # F6_02_02
}


def _resolve(eep) -> type | None:
    """Accept an EEP class as well as its name ('A5-10-06', 'a5_10_06')."""
    if eep is None:
        return None
    if isinstance(eep, type):
        return eep
    try:
        return EEP.find(str(eep).upper())
    except Exception:   # noqa: BLE001 - no teach-in payload for this profile
        return None


def supports_teach_in_button(eep) -> bool:
    """Can a device with this sender EEP be taught in with a button?"""
    return _resolve(eep) in EEP_WITH_TEACH_IN_BUTTONS


def get_teach_in_payload(eep) -> bytes | None:
    """The data bytes of the teach-in telegram of this sender EEP, None if it has none."""
    return EEP_WITH_TEACH_IN_BUTTONS.get(_resolve(eep))


def teach_in_button_eep_names() -> list[str]:
    """The supported sender EEPs as strings ('A5-10-06'), for catalogs and the web ui."""
    return sorted(getattr(eep, 'eep_string', None) or eep.__name__.replace('_', '-')
                  for eep in EEP_WITH_TEACH_IN_BUTTONS)
