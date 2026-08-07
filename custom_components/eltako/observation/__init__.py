"""Everything that only listens. None of it can influence a device.

    enocean_logger.py        every telegram: file log, statistics, live stream to the web ui
    bus_members.py           which devices sit on the bus, plus their memory images
    device_activity.py       which addresses have ever reported, how often, when last
    timeseries.py            export into InfluxDB for the Grafana dashboards
    telegram_suggestions.py  which EEP and which device could an unknown address be?

They subscribe to the same dispatcher signals as the entities. Switching any of them off must
not change how the lights behave.
"""
