from unittest import TestCase
from unittest import mock
from mocks import *
from homeassistant.helpers.entity import Entity
from custom_components.eltako.cover import EltakoCover
from custom_components.eltako.device import EltakoEntity
from eltakobus import *
from custom_components.eltako.gateway import *

# mock update of Home Assistant
Entity.schedule_update_ha_state = mock.Mock(return_value=None)
# EltakoEntity.send_message = mock.Mock(return_value=None)


class Test_GatewayTypes(TestCase):

    def test_gateway_types(self):
        for t in GatewayDeviceType:
            
            if t in [GatewayDeviceType.EnOceanUSB300, GatewayDeviceType.GatewayEltakoFAMUSB]:
                self.assertTrue(GatewayDeviceType.is_transceiver(t))
            else:
                self.assertFalse(GatewayDeviceType.is_transceiver(t))

