import os
from homeassistant.core import HomeAssistant

# optionally do not load Home Assistant when used as a library
if not os.environ.get('SKIPP_IMPORT_HOME_ASSISTANT'):
    from .eltako_integration_init import *

async def async_setup(hass: HomeAssistant, config: dict):
    """Set up Eltako integration asynchronously."""
    # Asynchrone Einrichtung
    await hass.async_add_executor_job(initialize_device)
    # Weitere asynchrone Initialisierung von Geräten, etc.
