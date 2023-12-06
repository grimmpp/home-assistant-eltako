"""Representation of an Eltako device."""
from eltakobus.message import ESP2Message, EltakoWrappedRPS, EltakoWrapped1BS, EltakoWrapped4BS, RPSMessage, Regular4BSMessage, Regular1BSMessage
from eltakobus.error import ParseError
from eltakobus.util import AddressExpression
from eltakobus.eep import EEP

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import DATA_ENTITY_PLATFORM
from homeassistant.const import Platform

from homeassistant.helpers.dispatcher import async_dispatcher_connect, dispatcher_send
from homeassistant.helpers.entity import Entity

from .const import *
from .gateway import EltakoGateway
from .config_helpers import *


class EltakoEntity(Entity):
    """Parent class for all entities associated with the Eltako component."""
    _attr_has_entity_name = True

    def __init__(self, gateway: EltakoGateway, dev_id: AddressExpression, dev_name: str="Device", dev_eep: EEP=None):
        """Initialize the device."""
        self.gateway = gateway
        self.general_settings = self.gateway.general_settings
        self.dev_id = dev_id
        self.dev_name = get_device_name(dev_name, dev_id, self.general_settings)
        self.dev_eep = dev_eep
        self.listen_to_addresses = []
        self.listen_to_addresses.append(self.dev_id.plain_address())

    async def async_added_to_hass(self):
        """Register callbacks."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIGNAL_RECEIVE_MESSAGE, self._message_received_callback
            )
        )

    def _message_received_callback(self, msg: ESP2Message) -> None:
        """Handle incoming messages."""
        
        # Eltako wrapped RPS
        try:
            msg = EltakoWrappedRPS.parse(msg.serialize())
        except ParseError:
            pass
        else:
            if msg.address in self.listen_to_addresses:
                self.value_changed(msg)
            return
        
        # Eltako wrapped 1BS
        try:
            msg = EltakoWrapped1BS.parse(msg.serialize())
        except ParseError:
            pass
        else:
            if msg.address in self.listen_to_addresses:
                self.value_changed(msg)
            return

        # Eltako wrapped 4BS
        try:
            msg = EltakoWrapped4BS.parse(msg.serialize())
        except ParseError:
            pass
        else:
            if msg.address in self.listen_to_addresses:
                self.value_changed(msg)
            return
    
        # RPS
        try:
            msg = RPSMessage.parse(msg.serialize())
        except ParseError:
            pass
        else:
            if msg.address in self.listen_to_addresses:
                self.value_changed(msg)
            return

        # 1BS
        try:
            msg = Regular1BSMessage.parse(msg.serialize())
        except ParseError:
            pass
        else:
            if msg.address in self.listen_to_addresses:
                self.value_changed(msg)
            return

        # 4BS
        try:
            msg = Regular4BSMessage.parse(msg.serialize())
        except ParseError:
            pass
        else:
            if msg.address in self.listen_to_addresses:
                self.value_changed(msg)
            return

    def value_changed(self, msg: ESP2Message):
        """Update the internal state of the device when a message arrives."""
    
    def send_message(self, msg: ESP2Message):
        # TODO: check if gateway is available
        dispatcher_send(self.hass, SIGNAL_SEND_MESSAGE, msg)


class EltakoActuatorEntity(EltakoEntity):
    """ """

    def __init__(self, gateway: EltakoGateway, dev_id: AddressExpression, dev_name: str="Device", dev_eep: EEP=None):
        super(EltakoActuatorEntity,self).__init__(gateway, dev_id, dev_name, dev_eep)
        
        self.gateway.validate_dev_id(self.dev_id, self.dev_name)
        self.gateway.validate_sender_id(self.sender_id, self.dev_name)
        

def log_entities_to_be_added(entities:[EltakoEntity], platform:Platform) -> None:
    for e in entities:
        LOGGER.debug(f"Add entity {e.dev_name} (id: {e.dev_id}, eep: {e.dev_eep.eep_string}) of platform type {platform} to Home Assistant.")

def get_entity_from_hass(hass: HomeAssistant, domain:Platform, dev_id: AddressExpression) -> bool:
    entity_platforms = hass.data[DATA_ENTITY_PLATFORM][DOMAIN]
    for platform in entity_platforms:
        if platform.domain == domain:
            for entity in platform.entities.values():
                LOGGER.debug(f"checking entity type: {type(entity)}, dev_eep: {entity.dev_eep.eep_string}, dev_id: {entity.dev_id}")
                if entity.dev_id == dev_id:
                    return entity
    return None