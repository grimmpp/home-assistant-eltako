from unittest import IsolatedAsyncioTestCase
import os
from custom_components.eltako.config_helpers import async_get_home_assistant_config
from custom_components.eltako.schema import CONFIG_SCHEMA
from custom_components.eltako.gateway import *
from custom_components.eltako.const import *
from homeassistant.const import CONF_DEVICE, Platform

import yaml

async def get_config(filename: str) -> str:
    full_path = os.path.join( os.path.dirname(__file__), 'test_configs', filename)
    with open(full_path) as f:
        return yaml.safe_load( f )

async def get_config_basic_fam14(hass, domain):
    return await get_config('basic_fam14.yaml')

async def get_ha_config(hass, domain):
    return await get_config(os.path.join('..', '..', 'ha.yaml'))

class TestIdComparison(IsolatedAsyncioTestCase):

    async def test_config(self):
        config = await async_get_home_assistant_config(None, CONFIG_SCHEMA, get_config_basic_fam14)
        
        self.assertTrue(CONF_GERNERAL_SETTINGS in config)
        self.assertTrue(not config[CONF_GERNERAL_SETTINGS][CONF_FAST_STATUS_CHANGE])

        self.assertTrue(CONF_GATEWAY in config)
        self.assertTrue(config[CONF_GATEWAY][CONF_DEVICE] == GatewayDeviceTypes.GatewayEltakoFAM14)
        self.assertTrue(config[CONF_GATEWAY][CONF_BASE_ID] == 'FF-BC-C8-00')

        self.assertTrue(Platform.LIGHT in config)

    async def test_config_example(self):
        config = await async_get_home_assistant_config(None, CONFIG_SCHEMA, get_ha_config)
        pass
