#!/usr/bin/env python3
import argparse
from argparse import RawTextHelpFormatter
import asyncio
import sys
import functools

from termcolor import colored
import logging

from eltakobus import *
from ymalRepresentation import HaConfig

DEFAULT_SENDER_ADDRESS = 0x0000B000

async def create_busobject(bus, id):
    response = await bus.exchange(EltakoDiscoveryRequest(address=id), EltakoDiscoveryReply)

    assert id == response.reported_address, "Queried for ID %s, received %s" % (id, prettify(response))

    for o in sorted_known_objects:
        if response.model.startswith(o.discovery_name) and (o.size is None or o.size == response.reported_size):
            return o(response, bus=bus)
    else:
        return BusObject(response, bus=bus)

async def enumerate_bus(bus, *, limit_ids=None):
    """Search the bus for devices, yield bus objects for every match"""

    if limit_ids is None:
        limit_ids = range(1, 256)

    for i in limit_ids:
        try:
            yield await create_busobject(bus, i)
        except TimeoutError:
            continue

def buslocked(f):
    """Wraps a coroutine inside a bus locking and (finally) bus unlocking. The
    coroutine must take a bus as its first argument."""
    @functools.wraps(f)
    async def new_f(bus, *args, **kwargs):
        try:
            logging.debug("Sending a lock command onto the bus; its reply should tell us whether there's a FAM in the game.")
            await lock_bus(bus)
            return await f(bus, *args, **kwargs)
        finally:
            logging.debug("Unlocking the bus again")
            await unlock_bus(bus)
    return new_f

async def lock_bus(bus):
    logging.debug(await(locking.lock_bus(bus)))

async def unlock_bus(bus):
    logging.debug(await(locking.unlock_bus(bus)))

@buslocked
async def ha_config(bus, config: HaConfig):
    
    logging.info(colored("Start scanning for devices", 'red'))
    async for dev in enumerate_bus(bus):
        try:
            logging.info(colored(f"Found device: {dev}",'grey'))
            await config.add_device(dev)
        except TimeoutError:
            logging.error("Read error, skipping: Device %s announces %d memory but produces timeouts at reading" % (dev, dev.discovery_response.memory_size))
    logging.info(colored("Device scan finished.", 'red'))


async def listen(bus, config: HaConfig, ensure_unlocked):
    logging.info(colored(f"Listen for sensor events ...", 'red'))
    if ensure_unlocked:
        await lock_bus(bus)
        await unlock_bus(bus)

    seen_someone_polling = True
    seen_someone_force_polling = True

    while True:
        msg = await bus.received.get()
        msg = prettify(msg)

        await config.add_sensor(msg)

def main():

    p = argparse.ArgumentParser(
        formatter_class=RawTextHelpFormatter,
        description='''Eltako Decice and Sensor Discovery for Home Assistant Configuration: 
Detection of EnOcean Sensors and Eltako Devices mounted on Baureihe 14. 
Output format is compatible to Home Assistant configuration. 
In the output file EEPs for sensors need to be manually extend before copying the yaml into Home Assistent.''')

    
    p.add_argument('-v', '--verbose', 
                   action='count', 
                   default=0, 
                   help="enables debug logs")
    p.add_argument('-eb', '--eltakobus', 
                   required=True,
                   help="file at which a RS485 Eltako bus can be opened")
    p.add_argument('-osa', '--offset-sender-address', 
                   default=DEFAULT_SENDER_ADDRESS, 
                   help="offset address for unique sender address used to send messages to devices mounted on the bus")
    p.add_argument('-o', '--output', 
                   help="filename in which Home Assistant configuration will be stored", 
                   default="ha_conf.yaml")

    opts = p.parse_args()

    log_level = logging.INFO
    if opts.verbose > 0:
        log_level = logging.DEBUG
    logging.basicConfig(format='%(message)s', level=log_level)

    logging.info(colored('Generate Home Assistent configuration.', 'red'))

    loop = asyncio.new_event_loop()    
    asyncio.set_event_loop(loop)

    bus_ready = asyncio.Future(loop=loop)
    bus = RS485SerialInterface(opts.eltakobus)
    asyncio.ensure_future(bus.run(loop, conn_made=bus_ready), loop=loop)
    loop.run_until_complete(bus_ready)
    # cache_rawpart = opts.eltakobus.replace('/', '-')

    try:
        config = HaConfig(int(opts.offset_sender_address,16), save_debug_log_config=True)

        maintask = asyncio.Task( ha_config(bus, config), loop=loop )
        result = loop.run_until_complete(maintask)

        maintask = asyncio.Task( listen(bus, config, True), loop=loop )
        result = loop.run_until_complete(maintask)

    except KeyboardInterrupt as e:
        logging.info("Received keyboard interrupt, cancelling")
        maintask.cancel()
    finally:
        config.save_as_yaml_to_flie(opts.output)

    # if result is not None:
    #     logging.info(result)

if __name__ == "__main__":
    main()
