import asyncio
import logging
import itertools

from homeassistant.const import CONF_DEVICE
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers import discovery
from homeassistant.util import slugify

from homeassistant.components.light import LightEntity, SUPPORT_BRIGHTNESS, ATTR_BRIGHTNESS
from homeassistant.components.switch import SwitchEntity
from homeassistant.components.cover import CoverEntity, CoverEntityFeature
from homeassistant.helpers.entity import Entity

REQUIREMENTS = ['eltakobus[serial] == 0.0.8']
DEVELOPMENT_MODE = True
if DEVELOPMENT_MODE:
    import sys
    # quick hack to allow local overrides during development
    sys.path.insert(0, __file__[:__file__.rfind('/')])
    import eltakobus
    logging.warning("Development mode; Using eltakobus module from %s", eltakobus.__file__)
try:
    from eltakobus.serial import RS485SerialInterface
    from eltakobus.util import b2a
    from eltakobus import device
    from eltakobus import message
    from eltakobus import locking
    from eltakobus.eep import EEP, ProfileExpression, AddressExpression
    from eltakobus.error import TimeoutError, ParseError, UnrecognizedUpdate
except ImportError:
    # Not fully failing here b/c the module needs to be loaded successfully
    # even when its REQUIREMENTS are not yet satisfied.
    #
    # As even a test where all eltakobus modules were imported at function
    # level failed with import errors, so far this is accepting an "Invalid
    # config" error after the first attempt to load the module; the second
    # attempt (ie. when home assistant is restarted) should succede then, when
    # the requirements are already present.
    #
    # Alternatively, run `pip3 install 'eltakobus[serial] == 0.0.3' --target
    # /config/deps/lib/python3.6/site-packages` beforehand in a hass.io SSH
    # session.

    # These are necssary because Python < 3.7 is supported, and they are used
    # in function signatures.
    ProfileExpression = AddressExpression = None

DOMAIN = 'eltako'

logger = logging.getLogger('eltako')
# To make other log levels than warn/error visible, set this in configuration.yml
#
# logger:
#   default: warning
#   logs:
#     eltako: debug
del logging # just to make sure nobody accidentally `logging.warning`s something

def into_entity_id_part(s):
    """Filter out anything that wouldn't pass by is_valid_entity_id and replace
    it with underscores. This does not take care of having a dot somewhere in
    it.

    Also make it lowercase -- otherwise there'd be very difficult to debug
    situations in which home assistant would be looking for switch.ttyusb0_4
    and find nothing because it announces itself as switch.ttyUSB0_4.
    """
    return slugify(s.lower())

# Passing the futures around in a global rather than in discovery_info because
# recorder would try to serialize discovery_info and die from it. (Showing a
# "Object of type 'Future' is not JSON serializable" error, nothing else bad
# happens at first, but I suspect that history is unavailable when that
# happened.)
platforms = {}

async def async_setup(hass, config):
    # Just make sure there's an import error even though the module-level one
    # needs to be caught
    import eltakobus

    loop = asyncio.get_event_loop()

    global platforms
    assert platforms == {}
    platforms = {k: asyncio.Future() for k in ('light', 'switch', 'sensor', 'cover')}
    for platform, f in platforms.items():
        await discovery.async_load_platform(
                hass,
                platform,
                DOMAIN,
                {},
                config
                )

    ctrl = EltakoBusController(hass, loop, config, platforms)

    return True

class EltakoBusController:
    def __init__(self, hass, loop, config, platforms):
        self.loop = loop
        self.hass = hass
        self.config = config
        self._main_task = asyncio.ensure_future(self.wrapped_main(platforms), loop=loop)
        self._bus_task = None
        self.entities_for_status = {}

    async def initialize_bus_task(self, run):
        """Call bus.run in a task that takes down main if it crashes, and is
        properly shut down as well"""
        if self._bus_task is not None:
            self._bus_task.cancel()

        conn_made = asyncio.Future()
        self._bus_task = asyncio.ensure_future(run(self.loop, conn_made=conn_made))
        def bus_done(bus_future, _main=self._main_task):
            self._bus_task = None
            try:
                result = bus_future.result()
            except Exception as e:
                logger.error("Bus task terminated with %s, removing main task", bus_future.exception())
                logger.exception(e)
            else:
                logger.error("Bus task terminated with %s (it should have raised an exception instead), removing main task", result)
            _main.cancel()
        self._bus_task.add_done_callback(bus_done)
        await conn_made

    async def wrapped_main(self, *args):
        try:
            await self.main(*args)
        except Exception as e:
            logger.exception(e)
            # FIXME should I just restart with back-off?

        if self._bus_task is not None:
            self._bus_task.cancel()

    async def wait_for_platforms(self, platforms):
        """Wait for the futures originally dealt out to the various platforms
        to come back, so that at the end there is a .platforms property that
        contains all the add_entities callbacks"""
        logger.debug("Waiting for platforms to register")
        for p in platforms:
            platforms[p] = await platforms[p]
        logger.debug("Platforms registered")
        self.platforms = platforms

    async def setup_from_configuration(self, bus, config):
        for k, v in config.items():
            logger.info("Trying to process config for %s", k)
            
            try:
                address_expression = AddressExpression.parse(k)
                address = address_expression.plain_address()
                item_config = v
            except ValueError:
                logger.error('Invalid configuration entry %s: %s -- expected format is "01-23-45-67" for addresses.', k, v)
                continue
            
            if address is None or item_config is None:
                logger.error("The configuration for item %s is wrong.", k)
                continue
            
            type = item_config.get('type', None)
            
            if type is None:
                logger.error("Type is missing for %s.", k)
                continue
            
            bus_object = await device.create_busobject(bus, address, type)
            
            programming_config = item_config.get('programming', None)
            
            if programming_config is not None:
                programming = self.parse_programming(programming_config)
                bus_object.programming = programming
                
            eep_config = item_config.get('eep', None)
            
            if eep_config is not None:
                eep = self.parse_eep(eep_config)
                bus_object.eep = eep
                
            self.create_entity(bus_object)
            
    def parse_programming(self, config):
        programming = {}
        
        for k, v in config.items():
            try:
                function = k
                address = AddressExpression.parse(v)
            except ValueError:
                logger.error('Invalid configuration entry %s: %s -- expected format is 32 for function and "01-23-45-67" (or "01-23-45-67 left") for addresses.', k, v)
                continue
            else:
                programming[function] = address
        
        return programming
    
    def parse_eep(self, config):
        try:
            profile = ProfileExpression.parse(v)
        except ValueError:
            logger.error('Invalid configuration entry %s -- expected format is "a5-02-16".', config)
            return None
        
        try:
            eep = EEP.find(profile)
        except KeyError:
            logger.warning("Unknown profile %s, not processing any further", profile)
        else:
            return eep
    
    def create_entity(self, bus_object):
        if isinstance(bus_object, device.DimmerStyle):
            entity = DimmerEntity(bus_object, self.bus_id_part)
            self.platforms['light']([entity])
            self.entities_for_status[bus_object.address] = [entity]
            logger.info("Created dimmer entity for %s", bus_object)
        elif isinstance(bus_object, device.FSR14):
            entity = FSR14Entity(bus_object, self.bus_id_part)
            self.platforms['switch']([entity])
            self.entities_for_status[bus_object.address] = [entity]
            logger.info("Created FSR14 entity for %s", bus_object)
        elif isinstance(bus_object, device.FSB14):
            entity = FSB14Entity(bus_object, self.bus_id_part)
            self.platforms['cover']([entity])
            self.entities_for_status[bus_object.address] = [entity]
            logger.info("Created FSB14 entity for %s", bus_object)
        else:
            logger.info("Device %s is not implemented for Home Assistant, not adding.", bus_object)

    async def main(self, platforms):
        await self.wait_for_platforms(platforms)

        serial_dev = self.config['eltako'].get(CONF_DEVICE)
        items = self.config['eltako'].get('items', {})
        
        bus = RS485SerialInterface(serial_dev, log=logger.getChild('serial'))
        self.bus_id_part = into_entity_id_part(serial_dev.replace('/dev/', ''))

        await self.initialize_bus_task(bus.run)

        logger.info("Serial device detected and ready. Settings things up according to configuration.")

        await self.setup_from_configuration(bus, items)

        logger.info("Configuration read. Bus ready.")

        while True:
            await self.step(bus)

    async def step(self, bus):
        """Process a single bus message"""
        msg = await bus.received.get()

        try:
            msg = message.EltakoWrappedRPS.parse(msg.serialize())
        except ParseError:
            pass
        else:
            await self.pass_message_to_entities(msg.address, msg)
            return
            
        try:
            msg = message.EltakoWrapped4BS.parse(msg.serialize())
        except ParseError:
            pass
        else:
            await self.pass_message_to_entities(msg.address, msg)
            return
            
        # so it's not an eltakowrapped message... maybe regular 4bs/rps?
#        try:
#            msg = message.RPSMessage.parse(msg.serialize())
#        except ParseError as e:
#            pass
#        else:
#            teachins.feed_rps(msg)
#            return

#        try:
#            msg = message.Regular4BSMessage.parse(msg.serialize())
#        except ParseError:
#            pass
#        else:
#            self.pass_message_to_entities(msg.address, msg)
#            return

#        try:
#            msg = message.TeachIn4BSMessage2.parse(msg.serialize())
#        except ParseError:
#            pass
#        else:
#            teachins.feed_4bs(msg)
#            return
    
        # It's for debug only, prettify is OK here
        msg = message.prettify(msg)
        if type(msg) not in (message.EltakoPoll, message.EltakoPollForced):
            logger.debug("Discarding message %s", message.prettify(msg))

    async def pass_message_to_entities(self, address, msg):
        if address in self.entities_for_status:
            for entity in self.entities_for_status[address]:
                try:
                    await entity.process_message(msg)
                except UnrecognizedUpdate as e:
                    logger.error("Update to %s could not be processed: %s", entity, msg)
                    logger.exception(e)
        else:
            # It's for debug only, prettify is OK here
            msg = message.prettify(msg)
            if type(msg) not in (message.EltakoPoll, message.EltakoPollForced):
                logger.debug("Discarding message %s", message.prettify(msg))

class EltakoEntity:
    should_poll = False

    entity_id = None # set in constructor
    name = property(lambda self: self._name)

class DimmerEntity(EltakoEntity, LightEntity):
    def __init__(self, busobject, bus_id_part):
        self.busobject = busobject
        self.entity_id = "light.%s_%s" % (bus_id_part, busobject.address.hex())
        self._name = "%s [%s]" % (type(busobject).__name__, busobject.address.hex('-'))
        self._state = None

        # would need to do that outside, and even then
        # self._writable = await self.busobject.find_direct_command_address() is not None

    @property
    def is_on(self):
        return self._state != 0

    @property
    def supported_features(self):
        return SUPPORT_BRIGHTNESS

    @property
    def brightness(self):
        if self._state is None:
            # see assumed_state
            return 0
        return self._state * 255 / 100

    @property
    def assumed_state(self):
        return self._state is None

    @property
    def state_attributes(self):
        base = super().state_attributes or {}
        return {**base,
                'eltako-bus-address': self.busobject.address.hex('-'),
                }

    async def process_message(self, msg, notify=True):
        processed = self.busobject.interpret_status_update(msg)

        if 'dim' in processed:
            self._state = processed['dim']
            logger.debug("Read brightness as %s", self._state)
            if notify:
                self.async_schedule_update_ha_state(False)

    async def async_turn_on(self, **kwargs):
        if ATTR_BRIGHTNESS in kwargs:
            brightness = kwargs[ATTR_BRIGHTNESS]
        else:
            brightness = 255
        brightness = brightness * 100 / 255
        logger.debug("Setting brightness to %s", brightness)
        await self.busobject.set_state(brightness)

    async def async_turn_off(self, **kwargs):
        await self.busobject.set_state(0)

class FSR14Entity(EltakoEntity, SwitchEntity):
    def __init__(self, busobject, bus_id_part):
        self.busobject = busobject
        self.entity_id = "switch.%s_%s" % (bus_id_part, busobject.address.hex())
        self._name = "%s [%s]" % (type(busobject).__name__, busobject.address.hex('-'))
        self._state = None

    @property
    def is_on(self):
        return self._state

    @property
    def assumed_state(self):
        return self._state is None

    @property
    def state_attributes(self):
        base = super().state_attributes or {}
        return {**base,
                'eltako-bus-address': self.busobject.address.hex('-'),
                }

    async def process_message(self, msg, notify=True):
        processed = self.busobject.interpret_status_update(msg)
        self._state = processed["state"]
        if notify:
            self.async_schedule_update_ha_state(False)

    async def async_turn_on(self, **kwargs):
        await self.busobject.set_state(True)

    async def async_turn_off(self, **kwargs):
        await self.busobject.set_state(False)

class BusSensorEntity(EltakoEntity, Entity):
    # no I don't want to implement a property right now; the first two also
    # serve as default values
    state = None
    assumed_state = True
    unit_of_measurement = None

    def __init__(self, name, entity_id, unit, update_to_state_key, additional_state, busobject):
        self.entity_id = entity_id
        self._name = name
        self.unit_of_measurement = unit
        self.update_to_state_key = update_to_state_key
        self.additional_state = additional_state
        self.busobject = busobject

    @property
    def state_attributes(self):
        base = super().state_attributes or {}
        return {**base,
                **self.additional_state,
                'eltako-bus-address': self.busobject.address.hex('-'),
                }

    async def process_message(self, msg, notify=True):
        processed = self.busobject.interpret_status_update(msg)
        if not processed:
            return
        energy = processed.pop(self.update_to_state_key, None)
        if energy is not None:
            self.assumed_state = False
            self.state = energy
            self.async_schedule_update_ha_state(False)

class FSB14Entity(EltakoEntity, CoverEntity):
    assumed_state = True
    device_class = 'window'
    supported_features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE

    def __init__(self, busobject, bus_id_part):
        self.busobject = busobject
        self.entity_id = "cover.%s_%s" % (bus_id_part, busobject.address.hex())
        self._name = "%s [%s]" % (type(busobject).__name__, busobject.address.hex('-'))
        self._state = None # compatible with current_cover_position: None is unknown, 0 is closed, 100 is open

    async def process_message(self, msg, notify=True):
        processed = self.busobject.interpret_status_update(msg)
        if processed is None:
            return

        state = processed["state"]

        if state == 'top':
            self._state = 100
        elif state == 'bottom':
            self._state = 0
        else:
            # Not trying to make anythign of the others -- after a bottom
            # there'd come an "up" movement, and we'd never know when the
            # movement stopped for now.
            return

        self.assumed_state = False
        if notify:
            self.async_schedule_update_ha_state(False)

    @property
    def current_cover_position(self):
        return self._state

    @property
    def is_closed(self):
        if self._state is None:
            return None
        return self._state == 0

    async def async_open_cover(self):
        # Setting _state to None basically to make both arrows usable after one
        # was pressed.
        #
        # Scheduling state as we updated it.
        self._state = None
        self.async_schedule_update_ha_state(False)
        await self.busobject.set_state(True)

    async def async_close_cover(self):
        self._state = None
        self.async_schedule_update_ha_state(False)
        await self.busobject.set_state(False)

    # might be able to implement stop cover too -- but that's hard to tell
