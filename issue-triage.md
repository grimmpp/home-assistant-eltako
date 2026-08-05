# Issue Triage

Status of the open GitHub issues checked against the code of version 2.2.0. Only issues whose
state can be decided from the code are listed - everything else needs a log or the reporter.

The comments below are meant to be posted before closing, so nobody has to guess why an issue
disappeared.

## Fixed in 2.2.0 - can be closed

### [#175](https://github.com/grimmpp/home-assistant-eltako/issues/175) ValueError when restoring electricity_cumulative sensor state if value is a float

Fixed. `sensor.py` no longer casts the restored state to `int` directly: states are strings and a
counter can contain decimals, so the value is parsed as a number and only narrowed to `int` if it
has no fractional part (`config_helpers.parse_number_state`). Applies to `measurement`, `total`
and `total_increasing`. A non-numeric state (e.g. `open` of a window handle) no longer raises
either. Tests: `tests/test_sensor_state_restore.py`.

### [#203](https://github.com/grimmpp/home-assistant-eltako/issues/203) False-positive device ID warnings for gateway and metadata entities

Fixed, along the lines suggested in the issue. Entities which do not represent a configured
device (gateway diagnostics, static info fields, event listener fields, repeater mode, connection
state, the gateway buttons) are marked with `_attr_is_actuator_entity = False` and skipped by
`validate_actuators_dev_and_sender_id()`.

Two more points from the issue are implemented:

* The warnings name the offending address, the gateway and the expected format:
  `Device ID FF-AA-BB-CC is not a local bus address; gateway '... (fgw14usb)' is a bus gateway and
  expects 00-00-XX-XX.`
* The sender id is not validated while the base id of the gateway is still unknown (it is queried
  from the hardware after connecting) - otherwise every correct sender id looked wrong.

On the way a related gap was closed: the sender ids of actuators were never validated at all,
because light/switch/cover/climate store them as `_sender_id` while the check only looked for
`sender_id`. A sender id outside the base id range of a transceiver - the gateway silently drops
those telegrams - now produces a warning.

Tests: `tests/test_id_validation.py` (local ids of a bus gateway, gateway-level zero ids, base
ids, real invalid formats, sender id outside the base id range).

### [#194](https://github.com/grimmpp/home-assistant-eltako/issues/194) gateway_1_send_message fails: sender_id is always None

Fixed. The service read the field `id` only, so the natural guess `sender_id` ended up as
`No valid sender id defined. (Given sender id: None)`. It now accepts `id`, `sender_id`, `sender`
and `address`, as string (`FF-A7-96-82`) as well as number (`0xFFA79682`, which is what the yaml
editor produces for an unquoted value).

Two follow-up problems of the same call were fixed too: a wrong `eep` reported a misleading
message about the sender id, and values which do not fit the eep aborted the service call with a
traceback. In addition a sender id outside the base id range of the gateway is now reported as a
warning - that is the usual reason for "the service runs but the stick does not blink", because a
transceiver only transmits sender ids of its own base id range.

Documentation: [docs/service-send-message](docs/service-send-message/readme.md).
Tests: `tests/test_send_message_service.py`.

### [#103](https://github.com/grimmpp/home-assistant-eltako/issues/103) Cover is driving all the way up or down if a small position correction is needed

Fixed. The runtime calculation uses `max(1, min(..., 255))` as suggested, so a small correction no
longer results in a runtime of 0 (which the actuator interprets as "drive to the end position").

The second suggestion (`time = 0` for position 0/100) was not taken over literally: those
positions are driven with the full runtime + 1 s, which reaches the end position and recalibrates
the cover just as well, without relying on the special meaning of 0. That runtime is capped at 255
now (the telegram carries one byte - with `time_opens: 255` encoding the telegram failed).
Setting an intermediate position while the position is unknown is rejected with a clear warning
instead of a `TypeError`. Tests: `tests/test_cover_G5_3F_7F.py`.

### [#95](https://github.com/grimmpp/home-assistant-eltako/issues/95) Tilt feature for shutters

Implemented. Configure `time_tilts` (in 0.1 s) for a cover and Home Assistant offers
`SET_TILT_POSITION`; the position of the slats is tracked from the runtime the actuator reports.
The wait between the move and the stop telegram is asynchronous now, so tilting does not block
Home Assistant. Tests: `tests/test_cover_G5_3F_7F.py::TestCoverTilt`.

### [#201](https://github.com/grimmpp/home-assistant-eltako/issues/201) Proposal: expose incoming gateway telegrams as a Home Assistant event

Already available - it was only undocumented. Every incoming telegram is fired on the Home
Assistant event bus as `eltako_global_event_bus` with the gateway (id, name) and the telegram
(type, address, payload). The address is the external one: local bus addresses are converted with
the base id before firing, the original stays available as `local_address` - which is exactly what
the FSB14 use case in the issue needs.

Documentation incl. the automation for a cover moved by a wall switch:
[docs/telegram-events](docs/telegram-events/readme.md). Tests: `tests/test_telegram_event.py`.

### [#202](https://github.com/grimmpp/home-assistant-eltako/issues/202) Invalid gateway-level entity ID will stop working in Home Assistant 2027.2

Fixed. The entity id is derived from the unique id through `config_helpers.sanitize_object_id()`,
which collapses repeated and strips leading/trailing underscores - `select.eltako_gw_10_` became
`select.eltako_gw_10`. The unique id itself is unchanged, so the entity registry keeps its
identity and existing installations are not duplicated. Test:
`tests/test_device_entity.py::test_entity_id_of_a_gateway_level_entity_is_valid`.

### [#114](https://github.com/grimmpp/home-assistant-eltako/issues/114) GatewayReceivedMessagesInActiveSession sets an invalid suggested_unit_of_measurement

Fixed. A free unit is only accepted as `native_unit_of_measurement` and only without a device
class; `suggested_unit_of_measurement` is validated against the units of the device class, which
made Home Assistant reject the whole entity. The sensor uses `native_unit_of_measurement` now.

### [#118](https://github.com/grimmpp/home-assistant-eltako/issues/118) Allow overriding delay_message for gateway serial communication

Implemented. `message_delay` is a per-gateway setting in `configuration.yaml` (default 0.01 s):

```yaml
gateway:
  - id: 1
    device_type: fgw14usb
    message_delay: 0.05
```

### [#61](https://github.com/grimmpp/home-assistant-eltako/issues/61) CONSTANT_X was used from eltako, deprecated constant

Fixed. No deprecated Home Assistant constant is used anymore (`TEMP_CELSIUS`, `DEVICE_CLASS_*`,
`ENERGY_KILO_WATT_HOUR`, `POWER_WATT`, `VOLUME_*`, ... - all replaced by the `UnitOf*` enums).

### [#121](https://github.com/grimmpp/home-assistant-eltako/issues/121) Allow specifying serial device path manually

Implemented. The path can be entered by hand in the config flow ("Custom path") as well as in
`configuration.yaml`, and an ESP2 gateway published over tcp (e.g. with ser2net/socat) is
supported as `device_type: lan-gw-esp2`. In addition the stick is searched by its usb serial
number if the kernel renumbered `/dev/ttyUSB*`.

## Needs the reporter / cannot be decided from the code

* [#204](https://github.com/grimmpp/home-assistant-eltako/issues/204),
  [#185](https://github.com/grimmpp/home-assistant-eltako/issues/185),
  [#96](https://github.com/grimmpp/home-assistant-eltako/issues/96) - `Cannot convert to esp2
  message (0x02 ...)` on ESP3 gateways (USB300, MGW-LAN). `0x02` is an ESP3 RESPONSE packet which
  does not have to be convertible at all, so it is log spam rather than an error - the log level
  belongs into `esp2-gateway-adapter`. #204 additionally runs on Python 3.14 and reports a
  blocking `open()` of `EEP.xml` in `esp3_tcp_com.py`. Should be tracked in the adapter repository.
* [#197](https://github.com/grimmpp/home-assistant-eltako/issues/197),
  [#191](https://github.com/grimmpp/home-assistant-eltako/issues/191) - state not synchronized
  after a Home Assistant core update. Needs a telegram log (the web ui records them) to tell a
  missing telegram from a wrong state handling.
* [#170](https://github.com/grimmpp/home-assistant-eltako/issues/170),
  [#138](https://github.com/grimmpp/home-assistant-eltako/issues/138) - CPU load. Never measured;
  a reproducible benchmark (telegrams/s -> cpu time) in the standalone runtime would make this
  decidable.
* EEP requests: [#199](https://github.com/grimmpp/home-assistant-eltako/issues/199) (A5-02-05),
  [#183](https://github.com/grimmpp/home-assistant-eltako/issues/183) (FHMB/FRWB/FRW),
  [#192](https://github.com/grimmpp/home-assistant-eltako/issues/192) (F6-05-02, A5-07-01,
  A5-38-08), [#174](https://github.com/grimmpp/home-assistant-eltako/issues/174) (A5-07-03),
  [#184](https://github.com/grimmpp/home-assistant-eltako/issues/184) (FRGBW71L),
  [#190](https://github.com/grimmpp/home-assistant-eltako/issues/190) (FDG14),
  [#181](https://github.com/grimmpp/home-assistant-eltako/issues/181) (F4HK14 modes),
  [#182](https://github.com/grimmpp/home-assistant-eltako/issues/182) (virtual rocker with several
  positions). Most of them need a change in `eltakobus` as well. #192 offers to contribute - a
  documented "how to add an EEP" walkthrough would unblock that.
