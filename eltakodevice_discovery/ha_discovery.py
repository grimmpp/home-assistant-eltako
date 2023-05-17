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
from eltakobus.locking import buslocked

DEFAULT_SENDER_ADDRESS = 0x0000B000

async def create_busobject(bus: RS485SerialInterface, id: int) -> BusObject:
    response = await bus.exchange(EltakoDiscoveryRequest(address=id), EltakoDiscoveryReply)

    assert id == response.reported_address, "Queried for ID %s, received %s" % (id, prettify(response))

    for o in sorted_known_objects:
        if response.model.startswith(o.discovery_name) and (o.size is None or o.size == response.reported_size):
            return o(response, bus=bus)
    else:
        return BusObject(response, bus=bus)

async def enumerate_bus(bus: RS485SerialInterface) -> Iterator[BusObject]:
    """Search the bus for devices, yield bus objects for every match"""

    for i in range(1, 256):
        try:
            yield await create_busobject(bus, i)
        except TimeoutError:
            continue

async def lock_bus(bus):
    logging.debug(await(locking.lock_bus(bus)))


async def unlock_bus(bus):
    logging.debug(await(locking.unlock_bus(bus)))


@buslocked
async def ha_config(bus: RS485SerialInterface, config: HaConfig, offset_address:bytes, write_sender_address_to_mem:bool) -> None:
    
    logging.info(colored("Start scanning for devices", 'red'))
    async for dev in enumerate_bus(bus):
        try:
            logging.info(colored(f"Found device: {dev}",'grey'))
            await config.add_device(dev)

            if write_sender_address_to_mem:
                if isinstance(dev, HasProgrammableRPS) or isinstance(dev, DimmerStyle):
                    for i in range(0,dev.size):
                        sender_address = (int(offset_address, 16) + dev.address).to_bytes(4, 'big')
                        await dev.ensure_programmed(i, AddressExpression((sender_address, None)), A5_38_08)

        except TimeoutError:
            logging.error("Read error, skipping: Device %s announces %d memory but produces timeouts at reading" % (dev, dev.discovery_response.memory_size))
    logging.info(colored("Device scan finished.", 'red'))


async def listen(bus: RS485SerialInterface, config: HaConfig, ensure_unlocked) -> None:
    logging.info(colored(f"Listen for sensor events ...", 'red'))

    # if ensure_unlocked:
    #     await lock_bus(bus)
    #     await unlock_bus(bus)

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
In the output file EEPs for sensors need to be manually extend before copying the yaml into Home Assistant.''')

    
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
    p.add_argument('-wsa', '--write_sender_address_to_device', 
                   action=argparse.BooleanOptionalAction,
                   help="Writes the sender address for Home Assistant into memory of devices if not exists.", 
                   default=False)

    opts = p.parse_args()

    log_level = logging.INFO
    if opts.verbose > 0:
        log_level = logging.DEBUG
    logging.basicConfig(format='%(message)s', level=log_level)

    logging.info(colored('Generate Home Assistant configuration.', 'red'))

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    bus_ready = asyncio.Future(loop=loop)
    bus = RS485SerialInterface(opts.eltakobus)
    asyncio.ensure_future(bus.run(loop, conn_made=bus_ready), loop=loop)
    loop.run_until_complete(bus_ready)
    # cache_rawpart = opts.eltakobus.replace('/', '-')

    try:
        config = HaConfig(int(opts.offset_sender_address,16), save_debug_log_config=True)

        maintask = asyncio.Task( ha_config(bus, config, opts.offset_sender_address, opts.write_sender_address_to_device), loop=loop )
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
