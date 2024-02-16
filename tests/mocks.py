from typing import Any

from custom_components.eltako.config_helpers import *
from custom_components.eltako.gateway import EnOceanGateway
class BusMock():

    def __init__(self):
        self.fired_events = list()

    def fire(self, 
                event_type: str,
                event_data: dict[str, Any] | None = None,
                origin = None,
                context = None,
                ) -> None:
        
        self.fired_events.append({
            'event_type': event_type,
            'event_data': event_data,
            'origin': origin,
            'context': context
        })

class HassMock():
        
    def __init__(self) -> None:
        self.bus = BusMock()
        
class ConfigEntryMock():

    def __init__(self):
        self.entry_id = "entity_id"

class GatewayMock(EnOceanGateway):

    def __init__(self, general_settings:dict=DEFAULT_GENERAL_SETTINGS, dev_id: int=123, base_id:AddressExpression=AddressExpression.parse('FF-AA-80-00')):
        hass = HassMock()
        gw_type = GatewayDeviceType.GatewayEltakoFAM14

        super().__init__(general_settings, hass, dev_id, gw_type, 'SERIAL_PATH', 56700, base_id, "MyFAM14", ConfigEntryMock())

    def set_status_changed_handler(self):
        pass

class LatestStateMock():
    def __init__(self, state:str=None, attributes:dict[str:str]={}):
        self.state = state
        self.attributes = attributes
        
