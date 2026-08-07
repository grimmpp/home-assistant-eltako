"""Extras around the integration - useful, never required to operate a device.

    gateway_scan.py   which serial ports look like a gateway
    plug_and_play.py  detect gateways, read the bus, add unambiguous devices
    device_tests.py   burst test, cover travel times - tests against real hardware
    grafana_sync.py   upload the shipped dashboards to a Grafana instance

Nothing in core/, config/, catalog/ or observation/ may import from here.
"""
