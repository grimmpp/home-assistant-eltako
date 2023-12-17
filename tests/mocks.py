from typing import Any

from custom_components.eltako.config_helpers import *
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

class GatewayMock():

    def __init__(self, general_settings:dict=DEFAULT_GENERAL_SETTINGS, dev_id: int=123, base_id:AddressExpression=AddressExpression.parse('FF-AA-80-00')):
        self.general_settings = general_settings
        self.base_id = base_id
        self.dev_id = dev_id
