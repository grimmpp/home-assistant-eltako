"""The runtime spine: what runs, what connects, what every entity is built on.

    integration.py               async_setup / async_setup_entry, teardown, panel registration
    gateway.py                   EnOceanGateway - the only thing that touches a serial port
    virtual_network_gateway.py   an EnOceanGateway that bridges ESP2 over the network
    entity.py                    EltakoEntity - the base class of every entity platform
    websocket.py                 the shared part of the eltako/* websocket api

Everything here may be imported by any other subpackage. integration.py is the wiring point
and therefore reaches into all of them; the rest of core/ only imports const, config and
observation.
"""
