# Reacting on Incoming Telegrams in Automations

Every telegram the integration receives is fired as a **Home Assistant event** on the event bus.
Automations can subscribe to it, no matter whether a matching device is configured or not. This is
the general counterpart of the button events (`F6-02-01`/`F6-02-02`), which only exist for
configured rocker switches.

Event name: **`eltako_global_event_bus`**

## Event data

```yaml
gateway:
  name: EnOcean Gateway - fgw14usb (Id: 10)
  id: 10
msg:
  msg_type: EltakoWrappedRPS     # class name of the telegram
  address: FF-E7-C1-85           # sender address, always the external (wireless) address
  local_address: 00-00-00-05     # only for bus devices: address as it appears on the RS485 bus
  org: 5                         # telegram type (0x05 RPS, 0x06 1BS, 0x07 4BS)
  data: 0x70                     # payload, depends on the telegram type
  payload: ...
```

The address is always reported as **external address**: local bus addresses (`00-00-XX-XX` of a
FAM14/FGW14-USB) are converted with the base id of the gateway before the event is fired, the
original address stays available as `local_address`. Depending on the telegram type further fields
are present (`reported_address`, `memory_size`, `model`, ... for bus/discovery messages).

Discovery requests (`EltakoDiscoveryRequest`) are not forwarded. Events are only fired once the
base id of the gateway is known.

## Example: invalidating the position of a cover moved by a wall switch

An FSB14 has no absolute position feedback. If the cover is moved by a physical switch, the
position Home Assistant calculated is not reliable anymore. The automation below listens for the
sender address of that switch and marks the position as unknown.

```yaml
alias: cover moved externally
trigger:
  - platform: event
    event_type: eltako_global_event_bus
    event_data:
      msg:
        address: FF-E7-C1-85       # the wall switch which moves the cover
action:
  - service: homeassistant.update_entity
    target:
      entity_id: cover.eltako_gw10_00_00_00_01
mode: single
```

## Example: logging every telegram of one gateway

```yaml
alias: log eltako telegrams
trigger:
  - platform: event
    event_type: eltako_global_event_bus
condition:
  - condition: template
    value_template: "{{ trigger.event.data.gateway.id == 10 }}"
action:
  - service: logbook.log
    data:
      name: EnOcean
      message: >-
        {{ trigger.event.data.msg.msg_type }} from
        {{ trigger.event.data.msg.address }}: {{ trigger.event.data.msg.data }}
```

## Related interfaces

* **Button events** of configured rocker switches: [Automations triggered by Wall-Mounted EnOcean
  Switches](../rocker_switch/readme.md) - contain the pressed buttons and how long they were
  pressed, which is what dimming automations need.
* **Telegram recording** into a log file or a timeseries database:
  [Analysing telegrams](../telegram-analysis/readme.md)
* **Sending** arbitrary telegrams: [Send Message Service](../service-send-message/readme.md)
