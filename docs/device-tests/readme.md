# Device Tests

Functional tests against the real hardware. They run on the gateways of the running integration
(no own serial connection) and are available in two places:

* **Web ui**: page **Tests** (shown when the general setting `enable_test_page` is on)
* **Command line**: `python -m eltako_standalone devicetest <test>` &ndash; the same code, no web
  ui needed. `devicetest list` prints what is available.

Only one test runs at a time. Every test streams its log live and ends with a result table; the
command line exits with `0` when the test succeeded, `1` when it failed and `2` when it could not
even start (e.g. gateway not connected).

| Test | Sends telegrams | Answers the question |
|------|-----------------|----------------------|
| [`config`](#configuration-check) | no | Is my configuration able to work at all? |
| [`actuator`](#actuator--teach-in-test) | yes, switches | Does the actuator obey Home Assistant? |
| [`burst`](#bus-burst-test) | yes, test addresses | Is the link reliable? |
| [`cover`](#cover-travel-time-test) | yes, drives covers | How long does my cover really run? |

Start with `config` &ndash; it costs nothing and finds most problems.

## Configuration check

Checks the configuration against everything the integration already knows and **sends nothing**:

* the address of a device fits its gateway (a local `00-00-XX-XX` bus address cannot be reached
  by a wireless transceiver; a wireless actuator on a bus gateway only works if a FAM14 transmits
  it by radio)
* every actuator has a sender, and that sender lies inside the base id range of its gateway
  &ndash; a foreign sender id is dropped by the gateway **silently**, which is the most invisible
  configuration mistake there is
* the same address is not configured twice, a sender which is shared by several devices is
  reported as a hint
* the bus position really answered on the RS485 bus, and the model which answered fits the
  configured EEP (needs the passive bus detection / a bus scan)
* the sender of Home Assistant is in the memory of the actuator (needs a memory read-out:
  "scan bus & read memory")
* the device has ever been heard from (recorded activity)
* a cover has `time_opens` and `time_closes`

Findings have three severities: `error` (cannot work), `warning` (very probably broken) and
`info` (worth knowing). Hints alone still count as success.

```bash
# everything
python -m eltako_standalone devicetest config

# only one gateway, only real problems, as json for a script
python -m eltako_standalone devicetest config --gateway 1 --severity warning
python -m eltako_standalone devicetest config --json
```

## Actuator / teach-in test

The answer to *"Home Assistant sends but nothing happens"*: the test switches every selected
switch or light with the sender of the configuration and waits for the status telegram of the
actuator. An Eltako actuator only answers a command whose sender is **taught into** it, so an
answer proves the whole chain - configuration, gateway, radio/bus, teach-in - and the round trip
time comes along for free (a value far above ~0.5 s points at an overloaded bus).

> The actuators really switch. With the default command sequence (`on_off`) every tested device
> ends up switched off.

Covers are not part of this test (a stop telegram of a standing cover is not answered) - they
have their own test below.

```bash
# every configured switch and light of gateway 1: on, then off
python -m eltako_standalone devicetest actuator --gateway 1

# only two of them, only switch on, wait longer for the answer
python -m eltako_standalone devicetest actuator --gateway 1 \
    --devices 00-00-00-01,00-00-00-02 --command on --timeout 5
```

`--command` takes `on_off` (default), `off_on`, `on` or `off`.

If a device does not answer, check its sender id and teach it in - with the button
"check & teach in HA senders" on the devices page or with PCT14. A wrong device address looks
exactly the same; the configuration check names both.

## Bus burst test

Sends a burst of telegrams through one gateway and verifies that a second gateway receives every
single one. That measures the reliability of the link and whether `message_delay` is big enough:
if telegrams get lost, increase the delay.

Both gateways have to sit **on the RS485 bus** (FAM14, FGW14-USB). The test uses the fixed
addresses `FF-00-00-01..` of the EnOcean Device Manager, which lie outside every base id range -
a wireless transceiver would not transmit them at all.

```bash
python -m eltako_standalone devicetest burst --gateway1 1 --gateway2 2 --count 44 --delay 0.01
python -m eltako_standalone devicetest burst --gateway1 1 --gateway2 2 --runs 10   # flaky link?
```

## Cover travel time test

Drives the selected covers with a movement sequence, records their status telegrams and measures
the real travel times - the base for `time_opens` and `time_closes` of an FSB actuator. The
result lists the measured time next to the configured one and suggests a value.

```bash
# the configured covers of gateway 1 with the derived default sequence
python -m eltako_standalone devicetest cover --gateway 1

# an actuator which is not configured yet (calibration), with an explicit sender
python -m eltako_standalone devicetest cover --gateway 1 \
    --covers 00-00-00-09 --senders 00-00-B0-09 --sequence 'up:30,pause:2,down:30'
```

The sequence understands `up`, `down`, `stop` and `pause`, each with seconds
(`up:25,pause:2,down:25`). Actuator and sender addresses are paired by position; a single sender
is applied to all actuators.

## Where the results come from

Backend: [`custom_components/eltako/device_tests.py`](../../custom_components/eltako/device_tests.py)
and [`config_check.py`](../../custom_components/eltako/config_check.py). Both are part of the
integration, so the tests work in Home Assistant and in the
[standalone runtime](../standalone/readme.md) alike - the web ui talks to them through the
websocket commands `eltako/device_tests/*`, the CLI calls the same runners directly.
