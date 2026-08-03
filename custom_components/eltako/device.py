"""Representation of an Eltako device."""
from datetime import datetime

from eltakobus.message import ESP2Message, EltakoWrappedRPS, EltakoWrapped1BS, EltakoWrapped4BS, RPSMessage, Regular4BSMessage, Regular1BSMessage, prettify
from eltakobus.util import AddressExpression, b2s
from eltakobus.eep import EEP

from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.entity_platform import DATA_ENTITY_PLATFORM
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect, dispatcher_send
from homeassistant.helpers.entity import Entity
from homeassistant.helpers import area_registry as ar, device_registry as dr
from homeassistant.const import Platform

from .const import *
from .gateway import EnOceanGateway
from . import config_helpers


class EltakoEntity(Entity):
    """Parent class for all entities associated with the Eltako component."""
    
    
    def __init__(self, platform: str, gateway: EnOceanGateway, dev_id: AddressExpression, dev_name: str="Device", dev_eep: EEP=None, description_key:str=None, dev_area: str=None):
        """Initialize the device."""
        self._attr_has_entity_name = True
        self._attr_should_poll = True

        self._attr_ha_platform = platform
        self._attr_gateway = gateway
        self.hass = self.gateway.hass
        self.general_settings = self.gateway.general_settings
        self._attr_dev_id = dev_id
        self._attr_dev_name = config_helpers.get_device_name(dev_name, dev_id, self.general_settings)
        self._attr_dev_eep = dev_eep
        self._attr_dev_area = dev_area
        self.listen_to_addresses = []
        
        # calculate external address
        if self.dev_id.is_local_address():
            self._external_dev_id = self.dev_id.add(self.gateway.base_id)
        else:
            self._external_dev_id = self.dev_id

        self.listen_to_addresses.append( self._external_dev_id[0] )

        self.description_key = description_key
        self._attr_unique_id = config_helpers.get_device_id(gateway.dev_id, self.dev_id, self._get_description_key())
        # The unique id is the identity in the entity registry and must not be changed. It can
        # however end with '_' (e.g. gateway entities without description key), which is not a
        # valid object id, so it is only sanitized for the entity id.
        self.entity_id = f"{self._attr_ha_platform}.{config_helpers.sanitize_object_id(self._attr_unique_id)}"

        LOGGER.debug(f"[{self._attr_ha_platform} {self.dev_id}] Added entity {self.dev_name} ({type(self).__name__}).")

    def _get_description_key(self, description_key:str=None):
        if description_key is not None:
            self.description_key = description_key

        if hasattr(self, 'entity_description') and self.entity_description is not None:
            if self.description_key is None:
                self.description_key = self.entity_description.key
                
        return self.description_key

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={
                (DOMAIN, b2s(self.dev_id) )
            },
            name=self.dev_name,
            manufacturer=MANUFACTURER,
            model=self.dev_eep.eep_string,
            via_device=(DOMAIN, self.gateway.serial_path),
            suggested_area=self._attr_dev_area,
        )
    

    async def async_added_to_hass(self) -> None:
        """Call when entity about to be added to hass."""
        await super().async_added_to_hass()

        # Register callbacks.
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, ELTAKO_GLOBAL_EVENT_BUS_ID, self._message_received_callback
            )
        )

        # Force-assign the device to the configured area. suggested_area on
        # DeviceInfo is only honored on initial device creation, so for
        # devices that already exist in the registry we update them here.
        if self._attr_dev_area:
            self._assign_device_to_area(self._attr_dev_area)

        # load initial value
        if isinstance(self, RestoreEntity):
            # check if value is not set
            is_value_available = getattr(self, '_attr_native_value', None)
            if is_value_available is None:
                is_value_available = getattr(self, '_attr_is_on', None)

            # update values
            if is_value_available is None:
                latest_state:State = await self.async_get_last_state()
                if latest_state is not None:
                    try:
                        self.load_value_initially(latest_state)
                    except Exception as e:
                        # Restoring the last state must never prevent the entity from being added.
                        # Otherwise Home Assistant aborts the registration and the entity stays
                        # unavailable until the next restart. (e.g. attributes of the old state are missing)
                        LOGGER.warning(f"[{self._attr_ha_platform} {self.dev_id}] Cannot restore last state "
                                       f"'{latest_state.state}' of {self.dev_name}: {e}", exc_info=True)

    def _assign_device_to_area(self, area_name: str) -> None:
        """Ensure the configured area exists and link this entity's device to it."""
        area_reg = ar.async_get(self.hass)
        area = area_reg.async_get_area_by_name(area_name)
        if area is None:
            area = area_reg.async_create(area_name)

        device_reg = dr.async_get(self.hass)
        device = device_reg.async_get_device(identifiers={(DOMAIN, b2s(self.dev_id))})
        if device is not None and device.area_id != area.id:
            device_reg.async_update_device(device.id, area_id=area.id)
            LOGGER.debug(f"[{self._attr_ha_platform} {self.dev_id}] Assigned device to area '{area_name}' (id={area.id}).")


    def load_value_initially(self, latest_state:State):
        """This function is implemented in the concrete devices classes"""
        LOGGER.warning(f"[{self._attr_ha_platform} {self.dev_id}] DOES NOT HAVE AN IMPLEMENTATION FOR: load_value_initially()")
        LOGGER.debug(f"[{self._attr_ha_platform} {self.dev_id}] latest state - state: {latest_state.state}")
        LOGGER.debug(f"[{self._attr_ha_platform} {self.dev_id}] latest state - attributes: {latest_state.attributes}")
        

    def validate_dev_id(self) -> bool:
        return self.gateway.validate_dev_id(self.dev_id, self.dev_name)


    def validate_sender_id(self, sender_id=None) -> bool:
        
        if sender_id is None:
            if hasattr(self, "sender_id"):
                sender_id = self.sender_id

        if sender_id is not None:
            return self.gateway.validate_sender_id(self.sender_id, self.dev_name)
        return True

    @property
    def external_dev_id(self) -> str:
        return b2s(self._external_dev_id)

    @property
    def dev_name(self) -> str:
        """Return the name of device."""
        return self._attr_dev_name

    @property
    def dev_eep(self):
        """Return the eep of device."""
        return self._attr_dev_eep
    
    @property
    def dev_id(self) -> AddressExpression:
        """Return the id of device."""
        return self._attr_dev_id
    
    @property
    def gateway(self) -> EnOceanGateway:
        """Return the supporting gateway of device."""
        return self._attr_gateway

    @property
    def dev_id(self) -> AddressExpression:
        """Return the id of device."""
        return self._attr_dev_id
    
    @property
    def unique_id(self) -> str:
        """Return the unique id of device"""
        return self._attr_unique_id

    def _message_received_callback(self, data: dict) -> None:
        """Handle incoming messages."""
        msg = data['esp2_msg']

        msg_types = [EltakoWrappedRPS, EltakoWrapped1BS, EltakoWrapped4BS, RPSMessage, Regular1BSMessage, Regular4BSMessage]

        if type(msg) in msg_types:
            adr = AddressExpression((msg.address, None))
            if adr.is_local_address():
                adr = adr.add(self.gateway.base_id)

            # LOGGER.debug(f"[{self.platform} {self.dev_id}] check if message address {b2s(msg.address)} is in registered list {', '.join([b2s(a) for a in self.listen_to_addresses])}")
            if adr[0] in self.listen_to_addresses:
                ## TODO: filter out message sent twice through other gateways
                self.value_changed(msg)


    def value_changed(self, msg: ESP2Message):
        """Update the internal state of the device when a message arrives."""
    
    def send_message(self, msg: ESP2Message):
        """Put message on RS485 bus. First the message is put onto HA event bus so that other automations can react on messages."""
        event_id = config_helpers.get_bus_event_type(self.gateway.dev_id, SIGNAL_SEND_MESSAGE)
        dispatcher_send(self.hass, event_id, msg)
        

def validate_actuators_dev_and_sender_id(entities:list[EltakoEntity]):
    """Only call it for actuators."""
    for e in entities:
        e.validate_dev_id()
        e.validate_sender_id()

def log_entities_to_be_added(entities:list[EltakoEntity], platform:Platform) -> None:
    for e in entities:
        temp_eep = ""
        if e.dev_eep:
             temp_eep = f"eep: {e.dev_eep.eep_string}),"
        LOGGER.debug(f"[{platform} {e.dev_id}] Add entity {e.dev_name} (id: {e.dev_id},{temp_eep} gw: {e.gateway.dev_name}) to Home Assistant.")

def get_entity_from_hass(hass: HomeAssistant, domain:Platform, dev_id: AddressExpression) -> bool:
    entity_platforms = hass.data[DATA_ENTITY_PLATFORM][DOMAIN]
    for platform in entity_platforms:
        if platform.domain == domain:
            for entity in platform.entities.values():
                LOGGER.debug(f"checking entity type: {type(entity)}, dev_eep: {entity.dev_eep.eep_string}, dev_id: {entity.dev_id}")
                if entity.dev_id == dev_id:
                    return entity
    return None