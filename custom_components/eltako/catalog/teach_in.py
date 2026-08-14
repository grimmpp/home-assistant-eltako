"""Compatibility adapter for Eltako teach-in support in ``eltako14bus`` v1.0.0."""

from eltakobus.teach_in import (  # noqa: F401
    EEP_WITH_TEACH_IN_BUTTONS,
    build_teach_in_message,
    get_teach_in_payload,
    supports_teach_in_button,
    teach_in_button_eep_names,
    teach_in_devices,
    teach_in_profiles_for_device,
)
