# Migration from v1.x to v2.2.x

This guide describes how to migrate the Eltako integration from v1.x to v2.2.x.

## Summary

Installing the new version is not always the only required step. The v2
configuration is not fully compatible with every v1 configuration. The hardware
configuration in the Eltako bus remains intact, but the Home Assistant
configuration—especially virtual HA senders—must be checked.

An update alone is sufficient only when:

* the v1 configuration already follows the v2 schema,
* exactly one integration accesses each EnOcean adapter,
* every controllable device has a matching `sender` and EEP, and
* that sender is taught into the actuator or programmed into its memory.

In all other cases, a short migration is required. The devices do not generally
need to be taught in again; missing or incorrect HA senders do need to be fixed.

## Before updating

1. Create a Home Assistant backup.
2. Back up `configuration.yaml` and the current Eltako configuration.
3. Check which process accesses each EnOcean adapter. USB300, FGW14-USB or
   another adapter must not be opened simultaneously by the official EnOcean
   integration, EnOceanMQTT and the Eltako integration. During migration, only
   the Eltako integration should be active.
   See the [FAQ](./faq.md) if the adapter receives telegrams but does not send.
4. Record or export the gateway type, gateway ID, Base ID, device address, device
   EEP, HA sender address, sender EEP and the senders taught into each actuator.

## Installation and configuration

Recommended order:

1. Update or install v2.2.x through HACS.
2. Restart Home Assistant.
3. Under **Eltako → Overview/Settings**, verify one gateway first.
4. Restore the devices through the web interface or YAML.
5. Add additional gateways only after the first gateway works correctly.

The web interface is the simplest option for a new or mixed configuration. A
minimal YAML configuration can look like this:

```yaml
eltako:
  gateway:
    - id: 1
      name: FAM14
      device_type: fam14
      serial_path: /dev/serial/by-id/...
      devices:
        light:
          - id: 00-00-00-01
            name: Ceiling light
            eep: M5-38-08
            sender:
              id: 00-00-B0-01
              eep: A5-38-08
```

See the [gateway documentation](./gateways/readme.md), [supported devices and
EEPs](./supported-devices.md) and the v2 schema for the supported values. Do not
copy old v1 examples blindly. With multiple gateways, devices must be assigned
to the correct gateway and use the sender of that gateway.

## FAM14, wireless gateways and senders

Two tasks must be distinguished in an Eltako bus installation:

* A FAM14 can scan RS485 bus devices and write sender addresses to their memory.
* An FGW14-USB, USB300 or another wireless gateway transmits telegrams into the
  EnOcean radio network. A wireless actuator must accept the sender through its
  teach-in mode.

The gateway Home Assistant uses to switch an actuator must match the `sender`
configuration. For bus actuators, the sender address is written into the actuator;
for wireless actuators, an Eltako teach-in telegram is sent through the wireless
gateway while the actuator is in teach-in mode.

The v2 web interface supports **check & teach in configured senders** and the
device action **teach in**. A FAM14 must be connected for a bus actuator. A
wireless actuator must be put into teach-in mode manually. See [Teach-in
Buttons](./teach_in_buttons/readme.md) and [Gateway usage](./gateway_usage/readme.md).

Important: A wireless gateway's Base ID and derived sender addresses are not
automatically known by every Eltako actuator. A gateway can receive and transmit
telegrams even though an actuator does not accept the sender. This is a teach-in
or addressing problem, not automatically a version-migration bug.
See [Why is an actuator visible but does not switch?](./faq.md#why-is-an-actuator-visible-but-does-not-switch).

## Heating and thermostats

For climate devices, the actuator address, actuator EEP, HA sender address and
sender EEP must be correct. An optional physical thermostat is configured
separately through `room_thermostat`; a Home Assistant room sensor through
`room_sensor`.

* `room_sensor` only supplies the room temperature from a Home Assistant entity.
* `room_thermostat` describes a physical EnOcean thermostat whose telegrams are
  received and evaluated.
* `sender` is the address Home Assistant uses to control the heating actuator.

A FAM14 may receive wireless telegrams or pass them on through the bus, but this
does not automatically mean that a target-temperature change is forwarded to a
specific wireless thermostat. The climate device, sender EEP and transmission
path must be supported and taught in correctly. See [Heating and
Cooling](./heating-and-cooling/readme.md).

## Verification after migration

Start with one device:

1. Does the device appear in the device and telegram views?
2. Is the actuator EEP correct?
3. Is the address of the actual HA sender configured under `sender`?
4. Is that sender taught into the actuator?
5. Is an outgoing telegram logged through the expected gateway when switching?
6. Does the actuator react to the same telegram in a manual test?

If an outgoing telegram is visible but the actuator does not react, the sender
address, sender EEP, teach-in, Base ID or gateway assignment is typically wrong.
If no outgoing telegram appears, the cause is usually the configuration,
platform/EEP or competing access to the adapter.

### Can actuators stop switching after migration?

Yes, this can happen, but it is not a general v2 migration effect. Common causes
are:

* the v1 sender was not transferred to the v2 `sender` field;
* the sender address changed but was not taught into the actuator;
* the sender EEP does not match the actuator;
* the device is assigned to the wrong gateway or Base ID;
* FAM14 and wireless gateway roles are being confused;
* another EnOcean integration opens the same adapter;
* an old YAML declaration overrides the web UI setting.

The v2 integration provides a teach-in action and displays known senders. YAML
devices must still be changed in YAML; web UI values do not override a YAML
declaration.

## Further troubleshooting

General troubleshooting and the findings generalized from the forum discussion
are maintained in the [FAQ](./faq.md). It covers sender teach-in, gateway ranges,
FAM14/FGW14-USB/USB300 roles, Hold wiring, Docker, climate EEPs and competing
EnOcean integrations.

The v2.2 feature list is maintained centrally in the [Change Log](../changes.md)
and is not duplicated here.

## Conclusion

For many installations, migration means an update plus a configuration check; it
is not guaranteed to be a file-only update. Bus devices normally do not need to
be fully reprogrammed. The important points are that v2 uses the same sender
addresses and EEPs that are taught into the actuators, and that only one EnOcean
process accesses each adapter.
