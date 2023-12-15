import unittest
import os
from mocks import *
from unittest import mock, IsolatedAsyncioTestCase, TestCase
from custom_components.eltako.config_helpers import async_get_home_assistant_config
from custom_components.eltako.schema import CONFIG_SCHEMA, GatewaySchema
from custom_components.eltako.gateway import *
from custom_components.eltako.const import *
from custom_components.eltako import config_helpers
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
        self.assertTrue(config[CONF_GATEWAY][CONF_DEVICE] == GatewayDeviceType.GatewayEltakoFAM14)
        self.assertTrue(config[CONF_GATEWAY][CONF_BASE_ID] == 'FF-BC-C8-00')

        self.assertTrue(Platform.LIGHT in config)

    async def test_config_example(self):
        config = await async_get_home_assistant_config(None, CONFIG_SCHEMA, get_ha_config)
        pass

class TestDeviceConfig(TestCase):

    CONFIG1 = {
        CONF_ID: "FF-AA-80-01",
        CONF_EEP: "A5-10-06",
        CONF_NAME: "My Device",
        CONF_GATEWAY_ID: 123123,
        CONF_MAX_TARGET_TEMPERATURE: 25,
        CONF_MIN_TARGET_TEMPERATURE: 16,
    }

    CONFIG2 = {
        CONF_ID: "FF-AA-80-01",
        CONF_EEP: "A5-10-06",
    }

    CONFIG3 = {
        CONF_ID: "FF-AA-80-01",
        CONF_EEP: "A5-10-06",
        CONF_MAX_TARGET_TEMPERATURE: 25,
        CONF_MIN_TARGET_TEMPERATURE: 16,
    }

    CONFIG_GW = {
        CONF_ID: 123123,
        CONF_DEVICE_TYPE: GatewayDeviceType.GatewayEltakoFAMUSB.value,
        CONF_BASE_ID: "FF-BB-80-00",
    }

    def test_device_config1_1(self):
        CONFIG = self.CONFIG1
        dev_config = DeviceConf(CONFIG, [CONF_MAX_TARGET_TEMPERATURE, CONF_MIN_TARGET_TEMPERATURE])

        for k in [CONF_ID, CONF_EEP, CONF_NAME, CONF_GATEWAY_ID, CONF_MAX_TARGET_TEMPERATURE, CONF_MIN_TARGET_TEMPERATURE]:
            self.assertTrue(k in dev_config)
            self.assertEquals(CONFIG[k], dev_config[k])
            self.assertTrue(hasattr(dev_config, k))
            self.assertEquals(CONFIG[k], dev_config.get(k))

        self.assertEquals(CONFIG[CONF_ID], str(dev_config.id).upper())
        self.assertEquals(CONFIG[CONF_EEP], dev_config.eep.eep_string)
        self.assertEquals(CONFIG[CONF_NAME], dev_config.name)
        self.assertEquals(CONFIG[CONF_GATEWAY_ID], dev_config.gateway_id)
        self.assertEquals(CONFIG[CONF_MAX_TARGET_TEMPERATURE], dev_config.max_target_temperature)
        self.assertEquals(CONFIG[CONF_MIN_TARGET_TEMPERATURE], dev_config.min_target_temperature)

    def test_device_config1_2(self):
        CONFIG = self.CONFIG1
        dev_config = DeviceConf(CONFIG)

        for k in [CONF_ID, CONF_EEP, CONF_NAME, CONF_GATEWAY_ID]:
            self.assertTrue(k in dev_config)
            self.assertEquals(CONFIG[k], dev_config[k])
            self.assertTrue(hasattr(dev_config, k))
            self.assertEquals(CONFIG[k], dev_config.get(k))

        self.assertTrue(CONF_MAX_TARGET_TEMPERATURE in dev_config)
        self.assertTrue(CONF_MIN_TARGET_TEMPERATURE in dev_config)

        self.assertFalse(hasattr(dev_config, CONF_MAX_TARGET_TEMPERATURE))
        self.assertFalse(hasattr(dev_config, CONF_MIN_TARGET_TEMPERATURE))

        self.assertEquals(CONFIG[CONF_MAX_TARGET_TEMPERATURE], dev_config[CONF_MAX_TARGET_TEMPERATURE])
        self.assertEquals(CONFIG[CONF_MIN_TARGET_TEMPERATURE], dev_config[CONF_MIN_TARGET_TEMPERATURE])

        self.assertEquals(CONFIG[CONF_ID], str(dev_config.id).upper())
        self.assertEquals(CONFIG[CONF_EEP], dev_config.eep.eep_string)
        self.assertEquals(CONFIG[CONF_NAME], dev_config.name)
        self.assertEquals(CONFIG[CONF_GATEWAY_ID], dev_config.gateway_id)

    def test_device_config2_1(self):
        CONFIG = self.CONFIG2
        dev_config = DeviceConf(CONFIG, [CONF_MAX_TARGET_TEMPERATURE, CONF_MIN_TARGET_TEMPERATURE])

        for k in [CONF_ID, CONF_EEP]:
            self.assertTrue(k in dev_config)
            self.assertEquals(CONFIG[k], dev_config[k])
            self.assertTrue(hasattr(dev_config, k))
            self.assertEquals(CONFIG[k], dev_config.get(k))

        for k in [CONF_NAME, CONF_BASE_ID, CONF_MAX_TARGET_TEMPERATURE, CONF_MIN_TARGET_TEMPERATURE]:
            self.assertFalse(k in dev_config)
            self.assertFalse(hasattr(dev_config, k))
            self.assertEquals(None, dev_config.get(k))

        self.assertEquals(CONFIG[CONF_ID], str(dev_config.id).upper())
        self.assertEquals(CONFIG[CONF_EEP], dev_config.eep.eep_string)

    def test_device_configGW(self):
        CONFIG = self.CONFIG_GW
        dev_config = DeviceConf(CONFIG, [CONF_MAX_TARGET_TEMPERATURE, CONF_MIN_TARGET_TEMPERATURE])

        for k in [CONF_ID, CONF_BASE_ID, CONF_DEVICE_TYPE]:
            self.assertTrue(k in dev_config)
            self.assertEquals(CONFIG[k], dev_config[k])
            self.assertTrue(hasattr(dev_config, k))
            self.assertEquals(CONFIG[k], dev_config.get(k))

        for k in [CONF_NAME, CONF_EEP, CONF_MAX_TARGET_TEMPERATURE, CONF_MIN_TARGET_TEMPERATURE]:
            self.assertFalse(k in dev_config)
            self.assertFalse(hasattr(dev_config, k))
            self.assertEquals(None, dev_config.get(k))

        self.assertEquals(CONFIG[CONF_ID], dev_config.id)
        self.assertEquals(CONFIG[CONF_BASE_ID], str(dev_config.base_id).upper())
        self.assertEquals(CONFIG[CONF_DEVICE_TYPE], dev_config.device_type)

    def test_device_config3_1(self):
        CONFIG = self.CONFIG3
        dev_config = DeviceConf(CONFIG, [CONF_MAX_TARGET_TEMPERATURE, CONF_MIN_TARGET_TEMPERATURE])

        for k in [CONF_ID, CONF_EEP]:
            self.assertTrue(k in dev_config)
            self.assertEquals(CONFIG[k], dev_config[k])
            self.assertTrue(hasattr(dev_config, k))
            self.assertEquals(CONFIG[k], dev_config.get(k))

        for k in [CONF_NAME, CONF_BASE_ID]:
            self.assertFalse(k in dev_config)
            self.assertFalse(hasattr(dev_config, k))
            self.assertEquals(None, dev_config.get(k))

        for k in [CONF_MAX_TARGET_TEMPERATURE, CONF_MIN_TARGET_TEMPERATURE]:
            self.assertTrue(k in dev_config)
            self.assertEquals(CONFIG[k], dev_config[k])
            self.assertTrue(hasattr(dev_config, k))
            self.assertEquals(CONFIG[k], dev_config.get(k))

        self.assertEquals(CONFIG[CONF_ID], str(dev_config.id).upper())
        self.assertEquals(CONFIG[CONF_EEP], dev_config.eep.eep_string)

    config_str = """
general_settings:
  fast_status_change: False
  show_dev_id_in_dev_name: True
gateway:
  - id: 1
    device_type: fgw14usb
    base_id: FF-AA-00-00
    name: GW1
    devices:
      light:
      - id: 00-00-00-01
        eep: M5-38-08
        name: "FSR14_4x - 1"
        sender:
          id: 00-00-B1-01
          eep: A5-38-08

  - id: 2
    device_type: fam-usb
    base_id: FF-BB-00-00
    name: GW2
    devices:
    sensor:
    - id: 05-1E-83-15
      eep: A5-13-01
      name: "Weather Station"
"""

    def test_config_validation(self):
        config = yaml.safe_load(self.config_str)
        CONFIG_SCHEMA(config)

    def test_config_validation_example_file(self):
        filename = os.path.join(os.getcwd(), 'ha.yaml')
        with open(filename, 'r') as file:
            config = yaml.safe_load(file)
            CONFIG_SCHEMA(config[DOMAIN])

        self.assertTrue(config_helpers.config_check_gateway(config[DOMAIN]))

        g_conf = config_helpers.find_gateway_config_by_id(config[DOMAIN], 1)
        GatewaySchema.ENTITY_SCHEMA(g_conf)
