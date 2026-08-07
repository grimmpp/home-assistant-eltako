# Version 2.2 — Introducing Version 2

## ELTAKO Bus Integration (RS485 &ndash; EnOcean) for Home Assistant

**Version 2.2 is the release of version 2.** It is the first generally available edition of the
second generation of this integration. This page shows, at feature level, what version 2 brings —
measured against the last version 1 (1.5.9). The details are in the linked documentation, the
complete list of changes in [changes.md](../changes.md).

---

## A yaml file becomes a user interface

**Version 1** was an integration for people who already understood EnOcean: know the gateway type,
find the serial port, look up the base id, write every device with its address and EEP into
`configuration.yaml` by hand — and restart Home Assistant after every change.

**Version 2** asks nothing at all when it is set up. Add the integration — that is all.

| | **Version 1.5.9** | **Version 2.2.0** |
| --- | --- | --- |
| Setup | Gateway type, port and base id in a dialog | **Nothing** — gateways detect themselves |
| Adding devices | By hand in `configuration.yaml` | Suggested and added with one click, or imported |
| After a change | Restart Home Assistant | Takes effect right away |
| User interface | None (separate package, optional) | The web ui is part of the integration |
| Troubleshooting | Read the Home Assistant log | Live telegrams, statistics, bus scan, device tests |
| Configuring without yaml | Not possible | Entirely possible |
| Testing without hardware | Not possible | Simulation of complete installations |
| Shortest yaml | ~30 lines for one device | `eltako:` — one line, or none at all |

---

## What is new

### Plug & play — analyse, suggest, add with one click

**EnOcean does not allow devices to be discovered.** The protocol has no such thing: a device
cannot be asked what it is, and a telegram does not say which product sent it. All that arrives
over the air is an address, a message type and a few data bytes — a 4BS teach-in telegram is the
one exception which really states its profile. That is a property of the standard, not a gap in
this integration, and no software can talk it away.

So version 2 does what can be done instead:

* **Gateways are detected** — serial ports are probed and LAN gateways are picked up via mDNS.
  Those identify themselves, so they can be created outright.
* **The RS485 bus is read.** Wired ELTAKO series 14 devices *can* be enumerated: the bus reports
  model and size, and the memory of every actuator reveals which senders are taught into it. This
  is the one place where devices are genuinely known rather than guessed.
* **Everything else is analysed and suggested.** Telegrams are evaluated — the message type, the
  data bytes, a plausibility check of every candidate profile — and the result is a ranked
  suggestion of EEP and product, not a claim.
* **Whatever is unambiguous is added by itself.** Whatever is not, is **listed automatically**:
  every address that has sent something but is not configured yet appears in the device list with
  its suggestions and a **"+ add"** button, which opens the form already filled in.

Nothing is created behind your back on a guess. The remaining step is a click on a suggestion,
not a search through data sheets.

&rarr; [docs/plug-and-play](plug-and-play/readme.md)

### Web ui — part of the integration, not a second package

The **ELTAKO** panel in the sidebar, in two views: **simple** (devices as cards grouped by room,
switch them, rename them) and **expert** (overview, devices, telegrams, statistics, tests,
settings). Gateways, devices and all settings are maintained there — no restart, no file.

&rarr; [docs/web-ui](web-ui/readme.md)

### Insight into the bus

Live telegrams, statistics per address, passively detected bus members in a hierarchical view, an
active bus scan which reads the memory of every device (which sender is taught in where), and
long term activity per address.

&rarr; [docs/telegram-analysis](telegram-analysis/readme.md) ·
[docs/logging](logging/readme.md)

### Functional tests against the real installation

A configuration check (sends nothing, finds the silent mistakes), an actuator/teach-in test (the
answer to "Home Assistant sends but nothing happens") and a cover travel time measurement — in the
web ui and on the command line.

&rarr; [docs/device-tests](device-tests/readme.md)

### Simulation — test without any hardware

Complete installations of virtual gateways and devices which answer commands and send on their
own. Real and simulated hardware can be mixed, and everything simulated is marked as such
everywhere.

&rarr; [docs/simulation](simulation/readme.md)

### Import a configuration instead of typing it

`.eodm` projects of the EnOcean Device Manager, **PCT14 xml exports** and an existing `eltako:`
yaml — with a preview before anything is applied. Importing the same file twice changes nothing.

&rarr; [docs/web-ui](web-ui/readme.md)

### Telegram analysis and Grafana

A rotating telegram log file, export into a timeseries database (InfluxDB) and five Grafana
dashboards which ship with the integration and can be pushed into your own instance from the
web ui.

&rarr; [docs/grafana](grafana/readme.md) ·
[docs/telegram-analysis](telegram-analysis/readme.md)

### Multiple gateways, properly supported

Several gateways on one bus and devices taught into more than one gateway. Gateways can also be
used as repeaters.

&rarr; [docs/multiple-gateway-support](multiple-gateway-support/readme.md) ·
[docs/gateways](gateways/readme.md)

### Around everyday operation

Send arbitrary telegrams from the web ui, log levels per telegram category, button events carrying
time information (dimming via blueprint, for Zigbee or Hue lamps as well), a central device
catalog which prefills EEP and sender, and a base id which is queried automatically.

&rarr; [docs/service-send-message](service-send-message/readme.md) ·
[docs/telegram-events](telegram-events/readme.md) ·
[docs/teach_in_buttons](teach_in_buttons/readme.md)

### For developers

Architecture documentation, a ready to use dev container and a standalone runtime which runs the
integration without Home Assistant.

&rarr; [docs/architecture](architecture/readme.md) ·
[docs/dev-container](dev-container/readme.md) ·
[docs/standalone](standalone/readme.md)

### And roughly 40 fixed bugs

Among them sensors which never updated, covers which were not added at all, meter readings with
decimals which dropped the entity, tilting slats which blocked Home Assistant, and several
reported issues.

&rarr; [changes.md](../changes.md)

---

## What to keep in mind when upgrading

* **Button event ids have changed** — automations reacting on button events need to be adjusted.
  In return the events now carry time information.
  &rarr; [docs/telegram-events](telegram-events/readme.md)
* **Entity ids of gateways have changed** — the base id is no longer part of them.
* **The yaml keeps working unchanged** and still wins over the web ui. Existing configurations
  continue to run without any migration.

---

## Try it

```text
Settings → Devices & services → Add integration → ELTAKO
```

Nothing else is asked. The panel opens itself the first time. For those who prefer files, one line
does the same job:

```yaml
eltako:
```

Installed through [HACS](https://hacs.xyz/) — the integration is not part of the Home Assistant
core repositories.
&rarr; [Getting started](01_getting_started/readme.md) ·
[All supported devices and EEPs](supported-devices.md) ·
[Documentation overview](readme.md)

*The integration is not limited to ELTAKO hardware — it speaks the EnOcean standard. ELTAKO devices
are just the ones named as examples throughout the documentation.*
