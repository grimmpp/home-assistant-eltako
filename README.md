Eltako bus support for home assistant
=====================================

(While this is not integrated into home assistant's repositories, this can be
installed by copying over the eltako directory from this repository ino your
home assistant's ``/config/custom_components`` directory.

When installed like this, an "Invalid config" error may show at the first start
of home assistant with the module active; a restart fixes that, as by then all
dependencies will be installed.)

To enable this component, add lines like the following to your config.yaml:

~~~~~~~~
eltako:
  device: /dev/ttyS0
~~~~~~~~

Devices on the bus will be integrated automatically.

Devices that are not on the bus can be made to send teach-in telegrams. As soon
as the teach-in telegrams are received, its sensor values are added to home
assistant. As those additions are not permanent, a notice is shown on the home
screen on how to make those devices available across reboots without sending
teach-in messsages again.

Various sensors can be persisted simply by adding their teach-in messages to
the configuration in a "teach-in" section as shown in the notification. As
switches without attached lights have no direct useful representation in home
assistant, you might want to register them at supported devices (currently
FUD14 and FSR14 series). For that purpose, write their lines into a
"programming" section in in a subsection with the eltako-busaddress of the
respective actuator. Again, the notification message will guide this. On the
next home assistant reload, that configuration will be applied to the
respective actuator if it is not already present.

If you have switches in the network that are not to be programmed into any
actuator (eg. because they are taught into an actuator not on the bus), they
can be set to ignore by taking down their lines in the teach-in section.

A full configuration can thus look like this:

~~~~~~~~
eltako:
  device: /dev/ttyUSB0
  teach-in:
    "05-11-fe-94": "a5-02-14"        # a temperature sensor
    "05-11-fa-7b": "a5-02-14"        # another temperature sensor
    "00-21-64-12 left": "f6-02-01"   # a pair of switch buttons we chose to ignore
    "00-21-64-12 right": "f6-02-01"  #
  programming:
    5:
      "00-21-63-44 left": "f6-02-01"  # A half switch that controls the FUD14 on bus address 5
    7:
      "00-21-63-44 right": "f6-02-01" # The other half of this switch controls an FSR14 on address 7
~~~~~~~~

Features
========

Recognized on the bus:

* as dimmable lights:
  * FUD14 (also the 800W version)
  * FSG14 1-10V (as dimmable lights)
  * FDG14
* as switches:
  * FSR14 with 1, 2, or 4 slots (as switches)
  * FSR14-LED
* as covers:
  * FSB14 (due to the limited feedback the devices give, they are only shown as
    full-up or full-down whenever end stops are reached, and as unknown while
    being actuated from home assistant; no attempt is made to recover state
    from timing.)
* as meters:
  * FWZ14-65A

Recognized over the air:

* Various temperature sensors (A5-02-01 to A5-02-1B)
* Various humidity sensors (A5-04-01 and A5-05-02)
* Direcional buttons (RPS)

  Those are not exposed as sensors as they are in practice taught into actuators, would only clutter the display, and just because home assistant received a telegram from them doesn't mean that any of its recipient devices actually got the message).

  Note that devices like the FTS14EM appear just as such devices because they do not fully participate on the bus, and send regular radio telegrams from their own address space.

* FGW14MS

  Those devices participate on the bus, but report their status only using telegrams whose ID depends on the switch state which can be read from the bus. For the purpose of reading it, the FGW14MS on the bus is a no-op entity, and has to be taught in like any other radio object.

Credits
=======
Credits for this code goes to chrysn (https://gitlab.com/chrysn) who made this code publicly available on his Gitlab repo, and shared it in the Home Assistant community. This repository here on Github is meant to keep the Eltako integration alive, make it work again with the latest Home Asssistant Core and potentially add functionalities.
