from unittest import TestCase, mock
from tests.mocks import *
from eltakobus import *
from custom_components.eltako.gateway import *
from custom_components.eltako import config_helpers
import yaml

# mock update of Home Assistant
EnOceanGateway._register_device = mock.Mock(return_value=None)
EnOceanGateway._init_bus = mock.Mock(return_value=None)
RS485SerialInterface.__init__ = mock.Mock(return_value=None)
asyncio.get_event_loop = mock.Mock(return_value=None)

class TestGateway(TestCase):

    def test_gateway_types(self):
        for t in GatewayDeviceType:
            
            if t in [GatewayDeviceType.GatewayEltakoFAMUSB, GatewayDeviceType.EnOceanUSB300, GatewayDeviceType.USB300, GatewayDeviceType.ESP3]:
                self.assertTrue(GatewayDeviceType.is_transceiver(t))
            else:
                self.assertFalse(GatewayDeviceType.is_transceiver(t))


    def test_gateway_creation(self):
        sub_type = GatewayDeviceType.GatewayEltakoFAM14
        baud_rate = BAUD_RATE_DEVICE_TYPE_MAPPING[sub_type]
        conf = ConfigEntry(version=1, minor_version=0, domain=DOMAIN, title="gateway", data={}, source=None, options=None, unique_id=None)
        gw = EnOceanGateway(DEFAULT_GENERAL_SETTINGS, HassMock(), 
                              dev_id=123, dev_type=sub_type, serial_path="serial_path",  baud_rate=baud_rate, port=None, base_id=AddressExpression.parse('FF-AA-00-00'), dev_name="GW", 
                              config_entry=conf)
        
        self.assertEqual(gw.identifier, basename(normpath('serial_path')))
        self.assertEqual(gw.general_settings, DEFAULT_GENERAL_SETTINGS)
        self.assertEqual(gw.model, "EnOcean Gateway - FAM14")
        self.assertEqual(gw.dev_id, 123)
        self.assertEqual(gw.dev_type, sub_type)
        self.assertEqual(gw.dev_name, 'GW - fam14 (Id: 123, BaseId: FF-AA-00-00)')

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
          id: 00-00-B0-01
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

    def test_gateway_list(self):
        config = yaml.safe_load(self.config_str)

        g_list:dict = config_helpers.get_list_of_gateway_descriptions(config)
        self.assertEqual(len(g_list), 2)
        self.assertEqual(list(g_list.values())[0] ,'GW1 - fgw14usb (Id: 1, BaseId: FF-AA-00-00)')
        self.assertEqual(list(g_list.values())[1] ,'GW2 - fam-usb (Id: 2, BaseId: FF-BB-00-00)')

    def test_get_id_from_name(self):
      self.assertEqual(1, config_helpers.get_id_from_name('GW1 - fgw14usb (Id: 1, BaseId: FF-AA-00-00)'))
      self.assertEqual(87126, config_helpers.get_id_from_name('GW1 - fgw14usb (Id: 87126, BaseId: FF-AA-00-00)'))

    def test_get_gateway_from_config(self):
        config = yaml.safe_load(self.config_str)

        g_id = 99
        g_config = config_helpers.find_gateway_config_by_id(config, g_id)
        self.assertEqual(g_config, None)

        for i in range(1,3):
          g_config = config_helpers.find_gateway_config_by_id(config, i)
          self.assertEqual(g_config[CONF_ID], i)