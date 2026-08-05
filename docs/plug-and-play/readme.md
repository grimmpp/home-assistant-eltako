# Plug & Play

How does the integration notice that a **new device was connected**? Plug & play answers that in
three steps and only ever uses information which is unambiguous:

1. **Gateway** &ndash; the serial ports are probed and the network is listened to (mDNS).
2. **Bus** &ndash; a new bus gateway (FAM14, FGW14-USB) gets its RS485 bus read.
3. **Devices** &ndash; everything which was identified beyond doubt is added to the configuration.

Everything which stays ambiguous is **listed with its reason** instead of being guessed - it remains
a manual decision on the *Devices* page.

Implementation: [`custom_components/eltako/plug_and_play.py`](../../custom_components/eltako/plug_and_play.py)

## It runs once when the integration is installed

**Adding the integration is the whole setup**: *Settings &rarr; Devices & services &rarr; Add integration
&rarr; Eltako* and pick the first option. Nothing is asked for - no gateway, no serial port, no yaml.
The entry which is created carries no gateway at all; it is the integration itself, and it starts one
detection run right away. Every gateway which is found beyond doubt gets its own entry a few seconds
later, and the [web ui](../web-ui/readme.md) shows the run while it happens.

That first run is a one-off. It is not repeated on the next restart, because reading an RS485 bus
locks it for minutes. Whether the detection keeps running afterwards is the setting below.

> A gateway which cannot be identified - an FGW14-USB looks like any other serial adapter, and a LAN
> gateway which does not announce itself cannot be found at all - is **added by hand on the overview
> page** of the web ui ("+ add gateway"): type, serial port or host, done. The ports of a scan are
> offered as suggestions.

## Keeping it on

Either with the checkbox **Plug & play enabled** in the settings of the web ui (group *Plug & Play*)
or in `configuration.yaml`:

```yaml
eltako:
  general_settings:
    plug_and_play: True            # detect and add automatically
    plug_and_play_interval: 1440   # default: once a day. 60 = hourly, 0 = only by button
```

The check runs **once a day** by default, plus once a minute after Home Assistant started. That is
enough: a gateway is plugged in rarely, and every run opens the free serial ports and listens on the
network. Whenever you actually plug something in, press the button instead of waiting.

The switch of the configuration sits as a **push button on the overview page** of the web ui, next to
the three stages of a run:

| Button | What it does |
|---|---|
| **Plug & Play on/off** | Stores the setting (like the checkbox) and starts a detection run right away when it is switched on. |
| **Detect now** | One single run without changing the setting. |
| **Detect + re-read all buses** | Additionally reads the bus of *every* bus gateway again - also of those which were read before. The bus is locked while it is read. |

A run happens in the background (reading a bus takes minutes). The overview page draws the three
stages as a flow: the stage which is running is highlighted, the ones behind it already show their
result, and the report of the last run (new gateways, added devices, what needs a decision, warnings)
sits below it.

## 1. Which gateway is there?

Two sources: the serial ports are probed **actively**, and LAN gateways which announce themselves via
**mDNS** are picked up. Both tables are ported from the `SerialPortDetector` and the
`LanServiceDetector` of the [EnOcean Device Manager](https://github.com/grimmpp/enocean-device-manager)
(same author, MIT), so both tools find the same gateways.

### Serial ports

Every port which is **not** used by one of the configured gateways is opened and asked:

| Gateway | How it is recognized | Created automatically |
|---|---|---|
| **FAM14** | only its adapter echoes back what is written to it | yes |
| **USB300 / ESP3 stick** | answers an ESP3 base id request (57600 baud) | yes |
| **FAM-USB** | answers an ESP2 base id request (9600 baud) | yes |
| **FGW14-USB** | the port is reachable and does not echo | **no** - only suggested |

An FGW14-USB cannot be *proven*: every serial device which is reachable and does not echo behaves
exactly like one. Such a port is therefore reported with a "+ add" button which opens the gateway
wizard prefilled - the type is confirmed by a human.

A gateway which was created gets its config entry as well, so its entities exist a few seconds later.
The base id stays `00-00-00-00`: a FAM14 and the ESP3 sticks report their own base id after connecting
and it is stored automatically.

### What is never touched

* a port which one of our gateways uses (running or configured but not set up yet)
* a port whose usb descriptor is known but fits no Eltako/EnOcean gateway - Home Assistant
  installations usually carry more sticks (Zigbee, Z-Wave, ...) and those belong to another
  integration. A port **without** a usb descriptor is probed, because inside a container only the
  device nodes are passed through and the descriptor of a FAM14 cannot be read there.
* a port which another program holds open - it cannot be opened a second time, so the probe skips it
  by itself

### LAN gateways which announce themselves (mDNS)

Yes &ndash; a LAN gateway which publishes an mDNS/bonjour service is picked up in **every** run, no
probing involved. The browsed service types and the names behind them:

| Service | Name contains | Gateway type | Created automatically |
|---|---|---|---|
| `_bsc-sc-socket._tcp` | `SmartConn` | `lan` (ESP3 over TCP) | yes |
| `_tcm515._tcp` | `EUL` | `eul_lan` | yes |
| `_bsc-sc-socket._tcp` | `Virtual-Network-Gateway-Adapter` | `lan-gw-esp2` | **no** - only suggested |

A service which states its own type *and* name identifies itself, which is a far better proof than the
FGW14-USB test - therefore those gateways are created with their ip address and port. The reverse
bridge is the exception: **this integration publishes it itself**
([`virtual_network_gateway.py`](../../custom_components/eltako/virtual_network_gateway.py)) so that the
EnOcean Device Manager can connect to Home Assistant. Creating a gateway for it would connect Home
Assistant to itself, so it is only offered with a "+ add" button (for the case that it belongs to
another installation).

A gateway which is already configured with that address (or host name) and port is skipped, so a run
never creates it twice. The browser listens for a few seconds and uses the Zeroconf instance of Home
Assistant - no second socket is opened.

> A gateway which does **not** announce itself (a plain ESP2/ESP3 TCP bridge, socat, a MGW with mDNS
> switched off) cannot be found this way. Add it once with **+ Add gateway** - host name and port are
> all it needs.

## 2. Reading the bus

A bus gateway gets the discovery of every position plus the complete memory of every device - the same
paced scan the button *scan bus & read memory* of the device page runs
([`bus_members.py`](../../custom_components/eltako/bus_members.py)).

Reading the memory **locks the bus for minutes**, therefore it happens **once**: the periodic check
skips a bus which was already scanned (also across a restart - the memory images are persisted).
Reading it again is the explicit button *Detect + re-read all buses*.

## 3. Which devices are added?

Only devices whose profile is certain. Three sources, in decreasing order of certainty:

| Source | Why it is unambiguous |
|---|---|
| **Bus position** | the discovery reply names the model, the model maps to exactly one device class and the [device catalog](../../custom_components/eltako/device_catalog.py) knows its platform and EEP. A multi channel device (e.g. an FSR14-4x) becomes one device per channel; the sender ids follow the convention of the EnOcean Device Manager (`00-00-B0-<bus position>`). |
| **Device memory** | a sender which is taught into a bus actuator - its key function names the EEP (e.g. `..._ACCORDING_EEP_A5_10_06_...`, push buttons `F6-02-01`). |
| **Teach-in telegram** | an address which sent a 4BS teach-in telegram: the telegram *states* the EEP (confidence `confirmed`). Needs the telegram recording to be enabled. |

Everything else lands in **"needs a decision"** with its reason, e.g.

* the position did not answer the discovery yet - its model is unknown
* the model is used by several device classes (FSR14_1x / FSR14_2x) - please pick one
* the EEP is only a guess (derived from the message type or the data bytes) - it has to be confirmed
* the device is an actuator which needs a sender address to be taught in

Take those over on the *Devices* page, where every candidate is listed with its possible EEPs and
device models.

## After the detection

* Added devices are stored **like devices created in the web ui**: their attributes (name, area, EEP,
  sender, device class, travel times, ...) can be **changed** on the *Devices* page and they can be
  removed again. A device declared in `configuration.yaml` is never shadowed or modified.
* **Nothing is written into any device.** An added actuator only works once the sender id of Home
  Assistant is taught into it - use the button *check & teach in HA senders* of its bus, or PCT14.
* All devices of one gateway are stored in one go, so the gateway is reloaded once and not once per
  device.

## Websocket api

| Command | Result |
|---|---|
| `eltako/plug_and_play/status` | enabled, interval, whether a run is active, its current stage/step and the report (of the running or of the last run) |
| `eltako/plug_and_play/run` | starts a run in the background. `enable: true/false` additionally switches the setting on/off, `rescan_bus: true` reads every bus again |

## Tests

* [`tests/test_plug_and_play.py`](../../tests/test_plug_and_play.py) - which detection result leads to
  which device, which port is probed, and the periodic check. Everything that *decides* is a pure
  function.
* [`eltako_standalone/tests/test_plug_and_play.py`](../../eltako_standalone/tests/test_plug_and_play.py) -
  a whole run on a booted runtime: bus positions &rarr; devices &rarr; entities, editing and removing an
  added device, and that a second run adds nothing twice.
