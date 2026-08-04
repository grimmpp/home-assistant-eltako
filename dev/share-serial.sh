#!/bin/sh
# Publish a serial gateway over TCP so the dev container can use it.
#
# Docker on macOS (Colima/Docker Desktop) and Windows runs in a linux VM and cannot pass a USB
# serial device through to a container. Instead the port is published on the host with socat,
# and the integration connects to it as a LAN gateway - `RS485SerialInterfaceV2` accepts a
# pyserial url, so `socket://host.docker.internal:<port>` speaks ESP2 over TCP.
#
#   ./share-serial.sh /dev/cu.usbserial-FTAMHS601 9600 [5000]
#
# Then configure the gateway (web ui or ha.yaml) as:
#   - id: 1
#     device_type: lan-gw-esp2
#     base_id: 00-00-00-00                       # queried from the hardware
#     serial_path: socket://host.docker.internal:5000
#
# On a LINUX host none of this is needed - pass the device through instead, see
# docker-compose.yml ('devices:').

DEVICE="${1:?usage: share-serial.sh <device> <baud> [tcp-port]}"
BAUD="${2:?usage: share-serial.sh <device> <baud> [tcp-port]}"
PORT="${3:-5000}"

if ! command -v socat >/dev/null 2>&1; then
    echo "socat is required:  brew install socat   (macOS)  /  apt install socat  (linux)" >&2
    exit 1
fi
if [ ! -e "$DEVICE" ]; then
    echo "$DEVICE does not exist. Available:" >&2
    ls /dev/cu.* /dev/ttyUSB* 2>/dev/null >&2
    exit 1
fi

echo "Publishing $DEVICE (${BAUD} baud) on tcp port $PORT"
echo "  container url:  socket://host.docker.internal:$PORT"
echo "  device type:    lan-gw-esp2"
echo "Ctrl+C stops sharing."
echo

# raw + no echo/flow control: the ESP2 frames must pass through byte for byte.
# 'fork' lets home assistant reconnect after a restart without restarting socat.
# ispeed/ospeed instead of the shorthand b<rate>: socat 1.8 does not accept the latter for a
# device address anymore ("unknown option b9600").
exec socat -d -d \
    TCP-LISTEN:"$PORT",reuseaddr,fork \
    "$DEVICE",ispeed="$BAUD",ospeed="$BAUD",raw,echo=0,crtscts=0
