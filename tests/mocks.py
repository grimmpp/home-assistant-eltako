import asyncio
from typing import Any

from custom_components.eltako.config_helpers import *
from custom_components.eltako.gateway import EnOceanGateway
class BusMock():

    def __init__(self):
        self.fired_events = list()
        self.listeners = list()

    def async_listen_once(self, event_type: str, listener):
        self.listeners.append((event_type, listener))
        return lambda: None

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
        try:
            self.loop = asyncio.get_event_loop()
        except RuntimeError:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)

    # def async_create_task(self, async_call):
    #     asyncio.run( async_call )
        
class ConfigEntryMock():

    def __init__(self):
        self.entry_id = "entity_id"

class EltakoBusMock():

    def __init__(self):
        self._is_active = True

    def is_active(self):
        return self._is_active

class EventMock():
    def __init__(self, service:str, data:dict) -> None:
        self.service = service
        self.data = data
class GatewayMock(EnOceanGateway):

    def __init__(self, general_settings:dict=DEFAULT_GENERAL_SETTINGS, dev_id: int=123, base_id:AddressExpression=AddressExpression.parse('FF-AA-80-00')):
        hass = HassMock()
        gw_type = GatewayDeviceType.GatewayEltakoFAM14

        super().__init__(general_settings, hass, dev_id, gw_type, 'SERIAL_PATH', 56700, 5100, base_id, "MyFAM14", auto_reconnect=True, message_delay=0.01, config_entry=ConfigEntryMock())

        self._bus = EltakoBusMock()

        # test_gateway.py replaces EnOceanGateway._init_bus for the whole process, so the
        # attributes which are normally initialized there have to be provided here.
        self._received_message_count = 0

    def set_status_changed_handler(self):
        pass

    def _register_device(self) -> None:
        pass

    def _fire_connection_state_changed_event(self, status):
        pass

    def add_connection_state_changed_handler(self, handler):
        pass


class LatestStateMock():
    def __init__(self, state:str=None, attributes:dict[str:str]={}):
        self.state = state
        self.attributes = attributes
        
