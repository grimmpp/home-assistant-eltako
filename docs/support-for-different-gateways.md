# Support for different gateways

There are two types of gateways supported:
1. Eltako gateways based on RS485 bus which are **Eltako FAM14** and **Eltako FGW14-USB**
2. Enocean gateways based on UART which is **EnOcean USB300**

Per default Eltako FGW14-USB will be used.

If you want to change the gateway you need to add the following part into the eltako configuration:
```
eltako:
  gateway:
    device: fgw14usb    # allowed values: fam14, fgw14usb, enocean-usb300
 ...
```