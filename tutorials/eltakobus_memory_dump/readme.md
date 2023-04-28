# Create a memory dump of Eltakobus and all its actors

In this example I use an Ubuntu machine connected via USB to FAM14 (BA=2, Auto=1) and [eltakotool](https://github.com/michaelpiron/eltako14bus). On the bus is a FSNT (Power Supply), FMA14 (radio transmitter), FGW14-USB (gateway - no relevance for this example), FSR14-4x (4x Relays in one box), FUD14 (dimmer). We are interested in getting the memory of the relays and the dimmer.

Keep in mind you will require administrative rights to use USB port. Just have a look for the owning group and add your user.
```
sudo su
# ls -la /dev/ttyUSB1
crw-rw---- 1 root dialout 188, 1 Apr 25 13:10 /dev/ttyUSB1
adduser YOUR_USERNAME dialout
exit
```
When executing the following command you wil receive a list of all actors and their memory.
```
sudo ./eltakotool.py --eltakobus /dev/ttyUSB1 dump -filename bus.yaml
```
bus.yaml:
```
1: # <FSR14_4x at 1 size 4 version (7, 2, 0, 0)>
    0:       01 04 7f 08 04 01 72 00
    1:       00 00 00 00 00 00 00 00
    #        R0 R1 R2 R3             -- (bool)Rn = 'restore channel n on power-up
    2:       00 00 00 00 00 00 00 00
    3:       00 00 00 00 03 e8 03 e8
    4:       03 e8 03 e8 00 00 00 00
    5:       00 00 00 00 64 64 64 64
    6:       0a 0a 0a 0a 00 00 00 00
    7:       00 00 00 00 00 00 00 00
    # ------ function group 1
    8-11:    00 00 00 00 00 00 00 00
    # ------ function group 2
    #        AD DR ES S, KY FN CH 00 -- key (5 = left, 6 = right), function (3 = bottom enable, 2 = upper enable), ch = affected channels as bits
    12:      fe db b6 40 03 17 01 00
    13:      00 00 b1 01 00 33 01 00
    14-127:  00 00 00 00 00 00 00 00

5: # <FUD14 at 5 size 1 version (4, 2, 0, 0)>
    0:       05 01 7f 0c 04 04 42 00
    1:       00 c8 96 64 32 c8 00 30
    2:       64 00 64 64 00 64 ff 50
    3:       1e 02 02 02 fa 00 ff 03
    4:       01 02 02 01 01 00 00 00
    5:       00 06 02 00 00 00 01 00
    6:       00 01 64 00 01 00 00 00
    7:       01 00 00 00 00 00 00 00
    # ------ function group 1
    8:       00 00 00 00 00 00 00 00
    # ------ function group 2
    9-11:    00 00 00 00 00 00 00 00
    # ------ function group 3
    #        AD DR ES S, KY FN SP %% -- key (5 = left, 6 = right), function (eg. 32 = A5-38-08), speed, percent
    12-15:   00 00 00 00 00 00 00 00
    16:      fe db da 04 03 01 01 00
    17-127:  00 00 00 00 00 00 00 00

255: # <FAM14 at 255 size 1 version (1, 9, 0, 0)>
    0:       ff 01 7f 00 07 ff 19 00
    #        AD DR ES S, -- -- -- -- -- Base address
    1:       ff a2 24 00 00 00 00 00
    2-127:   00 00 00 00 00 00 00 00


```

