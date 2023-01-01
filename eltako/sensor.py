DEPENDENCIES = ['eltako']

from . import platforms

async def async_setup_platform(hass, config, add_entities, discovery_info=None):
    platforms['sensor'].set_result(add_entities)
