"""The Eltako integration.

Home Assistant expects the setup functions in this file, so it only re-exports them from
:mod:`core.integration`. Where everything lives:

    const.py         the shared vocabulary - constants, signals, websocket command names
    config_flow.py   the "add integration" dialog (Home Assistant loads it by this name)
    <platform>.py    one entity platform each, e.g. light.py - Home Assistant loads them by
                     name too, which is why they stay next to this file

    core/            the runtime spine: startup, gateway, entity base class, websocket api
    config/          where a configuration comes from and whether it is valid
    catalog/         what this integration knows about devices, and the help built from it
    observation/     everything that only listens: telegram log, bus members, activity, export
    simulation/      gateways and devices without any hardware
    tools/           discovery, device tests and other extras
    frontend/        the web ui - plain ES modules, no build step
    grafana/         dashboards shipped for the InfluxDB export

See docs/architecture/readme.md for the guided tour.
"""
import os

# Optionally do not load the integration init: when using e.g. const as a library in a different
# project, the whole of Home Assistant would be loaded because it expects the setup functions in
# this file. To avoid loading Home Assistant - which also crashes the event loop - this opt out
# is placed here.
if not os.environ.get('SKIPP_IMPORT_HOME_ASSISTANT'):
    from .core.integration import *
