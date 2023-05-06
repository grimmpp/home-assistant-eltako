#!/usr/bin/env python3
import asyncio
import sys
import functools

from termcolor import colored

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
            print("Sending a lock command onto the bus; its reply should tell us whether there's a FAM in the game.")
            await lock_bus(bus)
            return await f(bus, *args, **kwargs)
        finally:
            print("Unlocking the bus again")
            await unlock_bus(bus)
    return new_f

async def lock_bus(bus):
    print(await(locking.lock_bus(bus)))

async def unlock_bus(bus):
    print(await(locking.unlock_bus(bus)))

@buslocked
async def ha_config(bus, config: HaConfig):
    
    print(colored("Start scanning for devices", 'red'))
    async for dev in enumerate_bus(bus):
        try:
            print(colored(f"Found device: {dev}",'grey'))
            await config.add_device(dev)
        except TimeoutError:
            print("Read error, skipping: Device %s announces %d memory but produces timeouts at reading" % (dev, dev.discovery_response.memory_size))
    print(colored("Device scan finished.", 'red'))


async def listen(bus, config, ensure_unlocked):
    print(colored(f"Listen for sensor events ...", 'red'))
    if ensure_unlocked:
        await lock_bus(bus)
        await unlock_bus(bus)

    seen_someone_polling = True
    seen_someone_force_polling = True

    while True:
        msg = await bus.received.get()
        msg = prettify(msg)

        if isinstance(msg, EltakoPoll):
            if not seen_someone_polling:
                seen_someone_polling = True
                print("There is a device on the bus that polls for messages.")
            continue

        if isinstance(msg, EltakoPollForced):
            if not seen_someone_force_polling:
                seen_someone_force_polling = True
                print("There is a device on the bus that force-polls for messages.")
            continue

        await config.add_sensor(msg)

def main():
    print(colored('Generate Home Assistent configuration.', 'red'))

    eltakobus = "/dev/ttyUSB1"
    if len(sys.argv) > 0:
        eltakobus = sys.argv[1] 

    filename = "ha.yaml"
    if len(sys.argv) > 1:
        filename = sys.argv[2]

    loop = asyncio.get_event_loop()

    bus_ready = asyncio.Future()
    bus = RS485SerialInterface(eltakobus)
    asyncio.ensure_future(bus.run(loop, conn_made=bus_ready), loop=loop)
    loop.run_until_complete(bus_ready)
    cache_rawpart = eltakobus.replace('/', '-')

    try:
        config = HaConfig(DEFAULT_SENDER_ADDRESS, save_debug_log_config=True)

        maintask = asyncio.Task( ha_config(bus, config) )
        result = loop.run_until_complete(maintask)

        maintask = asyncio.Task( listen(bus, config, True) )
        result = loop.run_until_complete(maintask)

    except KeyboardInterrupt as e:
        print("Received keyboard interrupt, cancelling", file=sys.stderr)
        maintask.cancel()
    finally:
        config.save_as_yaml_to_flie(filename)

    # if result is not None:
    #     print(result)

if __name__ == "__main__":
    main()
