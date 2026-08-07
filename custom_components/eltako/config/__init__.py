"""Where a configuration comes from, and whether it is valid.

    schema.py            voluptuous schemas - the authority on which EEP a platform accepts
    config_helpers.py    reading and merging the configuration, address and name helpers
    device_config.py     devices from configuration.yaml and from the web ui
    gateway_config.py    gateways created in the web ui, in their own Store
    general_settings.py  the editable settings, their defaults and their overrides
    config_import.py     import from PCT14 and EnOcean Device Manager exports
    config_check.py      everything verifiable without sending a telegram

The override rule: a value stored by the web ui wins over configuration.yaml, which wins over
the default.
"""
