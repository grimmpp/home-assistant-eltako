# Testing with real hardware

How to point a real gateway at a development setup and check that the **automatic detection**
recognizes it - the serial port probe, the bus scan and the devices which come out of it
([plug & play](../plug-and-play/readme.md)).

Two ways lead there, and they are not equivalent:

| | [Standalone runtime](../standalone/readme.md) | [Dev container](../dev-container/readme.md) |
| --- | --- | --- |
| Access to the stick | **native** - the real serial port | only through a tcp bridge (macOS/Windows) or a device pass-through (Linux) |
| FAM14 / FGW14-USB (bus gateway) | **yes**, verified | Linux pass-through yes; over the bridge see [the limits](#what-the-bridge-cannot-do) |
| FAM-USB / USB300 (transceiver) | yes | yes, also over the bridge |
| Start-up | ~1 second | tens of seconds |

**If you only want to know whether your bus is detected, take the standalone runtime.** It runs
the same integration code Home Assistant runs, and it talks to the port directly, which removes
every question the bridge adds.

## The one rule that breaks everything else

**Exactly one process may hold a serial port.** Not one *connection* - one *process*.

On Linux pyserial takes an exclusive lock and a second opener fails loudly. On **macOS
`/dev/cu.*` is not exclusive**: a second process opens the same port happily, and from then on
the kernel hands each byte to whichever reader asks first. Nobody gets an error. What you get
instead:

* the gateway type is still detected (that test is short and survives losing bytes)
* but **no base id** - the answer went to the other reader
* and **no bus members and no memory** - the frames arrive torn apart

So before anything else:

```bash
lsof /dev/cu.usbserial-XXXX          # macOS
fuser -v /dev/ttyUSB0                # linux
```

Every line is a process holding the port. A running `serve`, a `pytest eltako_standalone/tests`
run against real hardware, an open PCT14, the EnOcean Device Manager, a forgotten
`bridge publish` - stop all but one. This is by far the most common reason for "it finds the
FAM14 but nothing else works".

## Way 1: standalone runtime (recommended)

Nothing to set up - the runtime reads the port of the machine it runs on.

```bash
python -m eltako_standalone scan       # which ports are there, what is behind them (passive)
python -m eltako_standalone detect     # open the free ports and ask: which gateway is this?
```

`scan` only reads usb descriptors and never opens a port. `detect` is the **active** probe, the
serial half of plug & play on its own - it creates nothing and reads no bus, so it is safe to
repeat. On a connected FAM14 it prints:

```console
$ python -m eltako_standalone detect
Probed 1 port(s): /dev/cu.usbserial-AQ028YCS
Skipped: /dev/cu.Bluetooth-Incoming-Port, /dev/cu.debug-console

/dev/cu.usbserial-AQ028YCS          fam14        FAM14  [detected]
                                    Answered the probe.
```

To run the **whole** chain (detect → read the bus → add the devices), configure the gateway and
switch plug & play on:

```yaml
# <config>/configuration.yaml
eltako:
  general_settings:
    plug_and_play: True
  gateway:
  - id: 1
    device_type: fam14
    base_id: 00-00-00-00            # queried from the hardware
    serial_path: /dev/cu.usbserial-AQ028YCS   # linux: /dev/ttyUSB0, windows: COM3
```

```bash
python -m eltako_standalone --config <folder> serve
```

A run against a real FAM14 with eight bus devices looks like this - the bus scan takes about a
minute, the devices are stored afterwards:

```text
[Plug & Play] Reading the bus of gateway 1 (this can take a few minutes)
[Bus Members] Paced bus scan of gateway 1 finished.
[Plug & Play] Collecting the devices which can be identified
[Device Config] Added 24 device(s) in one go: light 00-00-00-05, cover 00-00-00-06, ...
[Plug & Play] Finished: 0 gateway(s) and 24 device(s) added, 9 device(s) need a decision.
```

The nine which "need a decision" are the ones the detection refuses to guess - see
[plug & play](../plug-and-play/readme.md#3-which-devices-are-added). Reading the bus locks it
for minutes and happens **once**; the button *Detect + re-read all buses* does it again.

## Way 2: dev container

### Linux: pass the device through

The honest way - the container sees the real device node. Uncomment in
[`dev/docker-compose.yml`](../../dev/docker-compose.yml):

```yaml
    devices:
      - "/dev/ttyUSB0:/dev/ttyUSB0"
```

The detection works exactly as it does on the host: the node matches the `/dev/ttyUSB*` glob
and is probed. It carries no usb descriptor inside the container (sysfs is not passed through),
which is expected and explicitly allowed - see
[`ports_to_probe`](../../custom_components/eltako/tools/plug_and_play.py).

### macOS and Windows: bridge the port in

Docker runs in a linux vm without usb access, so `devices:` cannot forward a stick which the vm
never sees (measured in detail in the
[dev container docs](../dev-container/readme.md#macos-and-windows-publish-the-port-over-tcp)).
The port has to travel over tcp instead.

The integration ships that as a backend module,
[`tools/serial_bridge.py`](../../custom_components/eltako/tools/serial_bridge.py) - no socat
needed. It has two halves:

```bash
# 1. on the host, where the stick is plugged in
python -m eltako_standalone bridge publish /dev/cu.usbserial-AQ028YCS 57600 --port 5100

# 2. inside the container, where the gateway is expected
python -m eltako_standalone bridge attach host.docker.internal --port 5100 --link /dev/ttyUSB0
```

`attach` exposes the byte stream as a **pty** symlinked to `/dev/ttyUSB0`. That path is the
whole point: the detection globs `/dev/ttyUSB*`, so a bridged port is discovered like a real
one. Configuring the published port as a `lan-gw-esp2` network gateway also works and is fine
for *using* a transceiver - but then the gateway is declared by hand and the detection is not
what you tested.

Two details the module gets right and a naive `socat PTY,link=...` does not:

* the **pty survives its reader**. A probe opens and closes the port several times; a pty whose
  slave fd is not held open dies with its first reader and takes the symlink with it.
* the pty is put into **raw mode**. A fresh `pty.openpty()` is a terminal in canonical mode with
  echo on - it translates CR/LF and eats 0x11/0x13 as flow control, all of which occur inside a
  14 byte ESP2 frame. Without it the two halves disagree on how many bytes passed, which is what
  silent corruption looks like from the outside.

### What the bridge cannot do

A **transceiver** (FAM-USB, USB300) works over the bridge - it is a request/response device and
tolerates the added latency. This is verified with a FAM-USB.

A **bus gateway (FAM14)** is a different matter. RS485 is half duplex, so the adapter echoes back
what is written to it, and that echo is exactly how a FAM14 is recognized and how the library
decides to suppress its own traffic. Echo detection, the base id query and the paced bus scan are
all timing sensitive, and a tcp hop plus a pty in between changes that timing. Expect the type
detection to work and the base id and bus scan to be unreliable.

**For FAM14 bus work use the standalone runtime or a Linux host with a real pass-through.**
The bridge is for the web ui, the configuration pages and a transceiver - not for reading a bus.

## The backend entry points

Everything above is integration code, not shell scripts, so the same logic is reachable from the
CLI, from the web ui and from a REST client.

| What | Function | CLI | Websocket |
| --- | --- | --- | --- |
| List the ports (passive) | `gateway_scan.scan_serial_ports()` | `scan` | `eltako/gateways/scan` |
| Detect only, create nothing | `plug_and_play.async_detect_gateways()` | `detect` | `eltako/plug_and_play/probe` |
| The full run (bus + devices) | `plug_and_play.async_run()` | &ndash; (web ui) | `eltako/plug_and_play/run` |
| Publish a port over tcp | `serial_bridge.start_bridge('publish', ...)` | `bridge publish` | `eltako/bridge/start` |
| Attach a published port as a pty | `serial_bridge.start_bridge('attach', ...)` | `bridge attach` | `eltako/bridge/start` |
| Which bridges run, stop one | `bridge_status()` / `stop_bridge(name)` | Ctrl+C | `eltako/bridge/list` / `/stop` |

`start_bridge`, `stop_bridge` and `bridge_status` take and return plain json-able dicts and raise
`SerialBridgeError` for everything a caller can fix, so a REST endpoint is a thin adapter over
them - the same one the websocket commands are. `serial_bridge` itself imports nothing from Home
Assistant and works in a plain python process.

## When it does not work

In this order - the first two cover almost everything:

1. **Is the port held by someone else?** `lsof` / `fuser`, see [above](#the-one-rule-that-breaks-everything-else).
   The signature is: type detected, no base id, no bus members.
2. **Is it the right port?** A FAM-USB registers **two** (`...600` / `...601`) and only the second
   carries the telegrams. `scan` says so in its hint.
3. **Is the baud rate right?** 9600 for a FAM-USB, 57600 for FAM14, FGW14-USB and ESP3 sticks.
   Over a bridge it is set on the **publishing** side, not in the gateway form.
4. **Was the bus already read?** A bus is scanned once, also across a restart. Use *Detect +
   re-read all buses* to force it.
5. **Is the gateway an FGW14-USB?** It cannot be proven - every reachable, silent serial device
   looks like one - so it is only *suggested* and never created automatically. Confirm the type
   by hand.

On macOS use the **`cu.*`** device, never `tty.*`: the latter blocks until DCD.
