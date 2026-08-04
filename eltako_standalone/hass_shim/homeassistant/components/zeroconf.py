"""Zeroconf access mirroring homeassistant.components.zeroconf.

Returns a plain Zeroconf instance of the `zeroconf` package (which the
integration imports directly anyway). One shared instance per runtime.
"""

DATA_ZEROCONF = "zeroconf"


async def async_get_instance(hass):
    instance = hass.data.get(DATA_ZEROCONF)
    if instance is None:
        from zeroconf import Zeroconf
        instance = await hass.async_add_executor_job(Zeroconf)
        hass.data[DATA_ZEROCONF] = instance
    return instance
