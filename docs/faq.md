# Frequently Asked Questions

This FAQ collects recurring setup and troubleshooting questions from the Eltako
community, GitHub issue reports and the [forum discussion about Eltako and Weber
Haus](https://community.simon42.com/t/enocean-steuerung-mit-eltako-weber-haus/4696?page=21).
For migration-specific questions, see [Migration from v1.x to
v2.2.x](./migration-v1-to-v2.2.md).

## Why is an actuator visible but does not switch?

An Eltako actuator only reacts to senders that are stored in its memory. Check
all of the following:

1. The actuator address and actuator EEP are correct.
2. The configured `sender.id` is the address Home Assistant actually transmits.
3. The configured `sender.eep` matches the command profile expected by the actuator.
4. The sender is taught into the actuator.
5. The sender belongs to the Base ID range of the selected wireless gateway.

For a bus actuator, use a connected FAM14 to write the sender into the actuator
memory. For a wireless actuator, put the actuator into teach-in mode and send the
Eltako teach-in telegram through the selected wireless gateway. The integration's
device teach-in action and sender check can guide this process.

## The gateway receives telegrams, but switching does not work. Is that a bug?

Not necessarily. Receiving proves that the adapter and receive path work, but it
does not prove that the transmitted sender is valid for the actuator. First check
the sender address, sender EEP, Base ID range and teach-in state. A command can be
visible in the log and still be ignored by the actuator because its sender is not
stored there.

## Why does a wireless gateway silently reject a sender?

Wireless transceivers only transmit sender addresses from their own 128-address
range: `Base ID` through `Base ID + 127`. A sender outside that range is not a
valid sender for that gateway. Use the configured gateway Base ID to derive the
sender, or select the gateway that owns the sender address.

The configuration checker reports this situation. The send-message service also
validates the sender and EEP instead of sending a misleading telegram.

## What is the difference between FAM14, FGW14-USB and USB300?

* **FAM14** is the bus master and can read and write actuator memory.
* **FGW14-USB** is a wired bus gateway. It can communicate with bus devices and
  can also provide the bus/radio path depending on the installation.
* **USB300** is an ESP3 wireless transceiver with its own Base ID range. It cannot
  write the memory of an RS485 actuator.

The gateway used for everyday operation must use sender addresses that the
actuators know. If operation is moved from a FAM14 to a wireless gateway, program
the wireless gateway's sender addresses into the bus actuators while the FAM14 is
still connected. See [Gateway usage](./gateway_usage/readme.md).

## Does the FGW14 need a Hold connection?

Yes. The Hold line must be connected reliably for FGW14 and FGW14-USB setups. The
termination resistor and bus wiring must also match the installation. A gateway
may be detected while bus communication is still unreliable if the Hold line or
bus termination is incorrect.

## Why is the USB300 detected but no telegram is sent?

Check the sender field name and format first. The service accepts `id`,
`sender_id`, `sender` or `address`, as a string such as `FF-A7-96-82` or a numeric
address such as `0xFFA79682`. Also verify that the sender is inside the USB300's
Base ID range and that the selected EEP can be encoded.

The symptom “the USB300 receives but does not transmit” has also been reported in
[GitHub issue #194](https://github.com/grimmpp/home-assistant-eltako/issues/194).
When reporting a similar problem, include the gateway type, Base ID, exact action
data and the relevant log entry.

## Can the official EnOcean integration run in parallel?

No, not on the same adapter. The official EnOcean integration, EnOceanMQTT and the
Eltako integration must not open the same USB300, FGW14-USB or other serial
adapter at the same time. This can cause dependency errors, missing telegrams,
or a setup that receives but cannot send reliably.

Disable the competing integration, remove stale configuration if necessary, then
restart Home Assistant before testing again. This is a setup conflict, not a
protocol-level migration bug.

## Why is the gateway not visible in a Docker installation?

The serial device must be passed through to the Home Assistant container and the
container user must have permission to access it. Check the host with `dmesg` or
the device path, then verify that the same path exists inside the container. A
YAML entry alone cannot make an adapter available if Docker has not passed through
the USB device.

## Why do climate entities show 0 °C, -1000 °C or 40 °C?

First verify the EEP against the actual device and raw telegram. `A5-10-06` and
`A5-10-12` are not interchangeable profiles. A wrong profile can decode valid
bytes into implausible temperatures or humidity values. Test the profile which is
actually used by the device and inspect the telegram log.

If the values are correct through a wired gateway but wrong through USB300, check
the ESP3-to-ESP2 conversion path and the gateway-specific logs. A working teach-in
does not prove that every climate data telegram is decoded correctly.

The following settings have different purposes:

* `room_sensor` is a Home Assistant entity supplying the current room temperature.
* `room_thermostat` is a physical EnOcean thermostat whose telegrams are received.
* `sender` is the address used by Home Assistant to control the heating actuator.

See [Heating and Cooling](./heating-and-cooling/readme.md) for the supported
climate configuration.

## Why does a target-temperature change reach the gateway but not the thermostat?

A FAM14 may receive radio telegrams and communicate with bus devices, but this
does not automatically make it a complete wireless thermostat gateway. The
configured climate sender, its EEP, the selected gateway and the thermostat's
teach-in state must all match. Check the outgoing telegram and whether the target
device is in learn mode when teaching the sender.

The forum reports cases where light and dimmer control worked while F4HK14/FUTH
climate values were wrong or target temperatures were not applied. These symptoms
should be isolated as a climate-profile or gateway-path problem rather than
treated as proof that all actuator control is broken.

## Why do devices configured in YAML differ from devices created in the web UI?

YAML remains the authoritative source for a YAML device. Web UI values do not
override an existing YAML declaration. A YAML device must be changed in
`configuration.yaml` and Home Assistant must be restarted or the configuration
reloaded as appropriate.

## What information should be included in a bug report?

Include:

* integration version and Home Assistant version;
* gateway type, Base ID, connection type and whether it is wired or wireless;
* device address and device EEP;
* sender address and sender EEP;
* whether the sender is taught into the actuator;
* one incoming and, if available, one outgoing raw telegram;
* the relevant log lines with `eltako` logging enabled;
* whether another EnOcean integration accesses the same adapter.

This distinguishes configuration, teach-in, wiring, gateway-range, decoding and
software defects without guessing from the user interface symptom alone.
