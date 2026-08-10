# Reception: finding a good place for a gateway

An EnOcean installation is not "working or not". A device which is received with -88 dBm works
today and stops working when a door is closed, a cupboard is moved or a person stands in the
wrong place. The *Reception* page of the [web ui](../web-ui/readme.md) (`/eltako#/reception`)
makes that reserve visible, and it is built to be **walked through the building** with.

## What it measures

Two numbers, both already part of every recorded telegram:

| | What it says |
| --- | --- |
| **Signal strength** (dBm) | How much reserve the link has. Reported by ESP3 transceivers &ndash; FAM-USB, USB300, LAN gateways. A FAM14 receives by radio too, but reports none; for it the counters and the repeater share are the measurement. |
| **Repeated** | The telegram arrived **through a repeater** instead of directly (`rp_count` &gt; 0). A link whose telegrams are mostly repeated is coverage which only exists as long as the repeater does &ndash; it looks fine until the repeater is unplugged. |

Only **radio** telegrams are surveyed. Everything a gateway read off its RS485 wire is left out: the
house keeping of the bus (polling, discovery, memory) as well as the telegrams of the actuators on
that bus, which are addressed relative to the base id of their gateway. A wire never fades, so
counting it would make every bus gateway the best receiver of the installation.

The signal strength is graded in the steps commissioning practice uses:

| dBm | | |
| --- | --- | --- |
| &ge; -60 | **excellent** | plenty of reserve |
| -61 &hellip; -75 | **good** | survives a closed door |
| -76 &hellip; -85 | **fair** | works, but without much reserve |
| &lt; -85 | **weak** | one obstacle more and it is gone |

## How to use it

The page needs the [telegram recording](../web-ui/readme.md#telegram-pages) &ndash; it reads what
was recorded, it does not send anything itself.

1. **Pick a window.** The default is the *last minute*: short enough that the reading follows
   you while you walk, long enough to catch a sensor which sends every 30 seconds. For judging
   a fixed position afterwards, 15 minutes or an hour say much more.
2. **Produce telegrams.** Press the button of the device you are interested in a few times, or
   wait for a sensor which sends by itself.
3. **Read the cards.** One per gateway: the average signal strength, the quality, how many
   transmitters it hears, and the share of telegrams which came through a repeater. Below them
   one row per **link** &ndash; one transmitter as heard by one gateway, with last/average/min/max.
4. **Save the spot** under a name (*"hallway"*, *"cellar door"*, *"next to the fuse box"*). The
   complete reading is kept, and the table at the bottom compares the spots. This is the point
   of the whole page: -72 dBm against -84 dBm is the difference between an installation which
   keeps working and one which needs a repeater, and nobody remembers that from one room to
   the next.
5. **Export as CSV** when the survey is done.

The saved spots live in the browser, so a reload does not lose them. They are per browser, not
per Home Assistant &ndash; a survey done on a phone stays on that phone.

### Two ways to walk

* **Carry the gateway.** A USB stick on a laptop, or a LAN gateway on a power bank: put it
  where it might be installed, press a device which stays where it is, save the spot, move on.
* **Carry the transmitter.** Leave the gateway where it will be installed and walk through the
  rooms pressing a button. Set the transmitter in the toolbar (*watch one transmitter*) &ndash; the
  survey then shows that one link only, and the rooms are the spots.

## Reading the result

* **A weak link is not a broken link.** It works. It has no reserve. Where a *weak* link is
  the only path to a device which matters, move the gateway, add a second one or accept a
  repeater.
* **A high repeater share is a warning even at a good signal strength.** The good value is what
  the *repeater* delivers; the device itself does not reach the gateway.
* **Nothing heard is a result too.** A gateway which reports no telegram of a device in a
  minute of button presses does not see that device.
* If the recording buffer is smaller than the selected window, the page says so &ndash; the numbers
  then describe less time than the window claims. `telegram_log_buffer_size` raises it.

## Where the numbers come from

[`observation/reception.py`](../../custom_components/eltako/observation/reception.py) aggregates
the telegram records of the ring buffer
([`observation/enocean_logger.py`](../../custom_components/eltako/observation/enocean_logger.py))
per link and per gateway; the page reads it through `eltako/reception/survey`
([websocket api](../architecture/websocket-api.md)). The aggregation is a pure function over
the records, so it is covered by [`tests/test_reception.py`](../../tests/test_reception.py)
without any hardware.

Related: the [*Radio* page](../web-ui/readme.md) compares what the gateways made of the **same**
transmission (who heard it, where the bytes differ), and the
[live telegrams](../web-ui/readme.md) show every single reception with its signal strength.
