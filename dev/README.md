# Home Assistant dev container

A ready-to-use Home Assistant with the ELTAKO integration and example data - one command,
no onboarding, no manual setup.

> Full documentation: **[docs/dev-container](../docs/dev-container/readme.md)** - incl. how to
> use a real USB gateway on macOS/Windows and the Grafana dashboards.

## Start

```bash
cd dev
./start.sh              # home assistant only          (windows: start.bat)
./start.sh analytics    # + InfluxDB and Grafana for the timeseries export
```

Then open **<http://localhost:8123>** and log in with **admin / admin**.

## What is prepared

* **No onboarding**: an admin user (`admin`/`admin`) and the finished onboarding are seeded
  into the config volume on the first start.
* **ELTAKO integration is already set up**: the config entry for the demo gateway exists,
  the *ELTAKO* panel is in the sidebar right away.
* **Example configuration**: the repository file [`ha.yaml`](../ha.yaml) is included as a
  Home Assistant package - one FGW14-USB bus gateway with example devices for every
  platform (lights, dimmer, switches, covers, climate, sensors, wired and wireless
  binary sensors), several areas, telegram recording and the web ui switched on.
* **Example telegram history**: `enocean_telegrams.jsonl` contains 24 h of demo telegrams
  (temperature curve, weather station, switching cycles, an unknown wall button) for the
  pandas examples in [docs/telegram-analysis](../docs/telegram-analysis/readme.md) and for
  the timeseries backfill service.
* **Live code**: `custom_components/eltako` is mounted from the repository. After a code
  change: `docker compose restart homeassistant`.

There is no physical gateway in the container, so the serial connection keeps retrying and
the demo devices stay unavailable / "never reported" - the configuration pages, the device
catalog, the hierarchy and the web ui are fully usable anyway.

## Timeseries export (InfluxDB + Grafana)

```bash
./start.sh analytics
```

```bash
./start-analytics.sh     # only InfluxDB + Grafana, without Home Assistant
```

| Service | URL | Login |
| --- | --- | --- |
| InfluxDB 2 | <http://localhost:8086> | `admin` / `eltako-dev` (org `home`, bucket `eltako`, token `eltako-dev-token`) |
| Grafana | <http://localhost:3000> | `admin` / `admin` (InfluxDB datasource preconfigured) |

Two dashboards are provisioned into the folder *ELTAKO* (tag `eltako`), the overview is the
home dashboard:

* **ELTAKO - Telegram overview** - telegram rate by direction and gateway, most active
  addresses, distribution over message type and EEP, table of the unconfigured addresses
* **ELTAKO - Device analysis** - any decoded EEP value over time, switching states, when each
  address was heard from last, telegrams per hour and area, average repeater level

They live in `grafana/provisioning/dashboards/eltako/*.json` and are editable in Grafana
(`allowUiUpdates`). The **standalone runtime** enables the export by default and links to
these dashboards from its web ui - see [eltako_standalone/README.md](../eltako_standalone/README.md).

Enable the export in the ELTAKO web ui (*Settings* page, group *Timeseries export*):

| Setting | Value |
| --- | --- |
| Export telegrams to InfluxDB | on |
| InfluxDB URL | `http://influxdb:8086` |
| API token | `eltako-dev-token` |
| Organization | `home` |
| Bucket | `eltako` |

To import the seeded 24 h history call the service
`eltako.export_telegram_log_to_timeseries` (Developer tools → Actions), then explore the
measurement `eltako_telegram` in Grafana.

## Windows, macOS, Linux

The container itself is a Linux container and identical on every host - only the Docker
runtime and the serial pass-through differ:

| | Linux | macOS | Windows |
| --- | --- | --- | --- |
| Docker runtime | native (`docker.io` / Docker Desktop) | Docker Desktop or [Colima](https://github.com/abiosoft/colima) (`brew install colima && colima start`) | Docker Desktop (WSL2 backend) |
| Start/stop scripts | `start.sh` / `stop.sh` | `start.sh` / `stop.sh` | `start.bat` / `stop.bat` |
| Use a USB gateway | pass it through: `devices: ["/dev/ttyUSB0:/dev/ttyUSB0"]` | publish it over tcp: `./share-serial.sh <device> <baud> 5100` + gateway type `lan-gw-esp2` | same tcp bridge, or [usbipd-win](https://github.com/dorssel/usbipd-win) into WSL2 |

Notes:

* `docker compose` (v2, with a space) is required. If `docker compose` reports an unknown
  command, link the compose plugin: `mkdir -p ~/.docker/cli-plugins && ln -s "$(brew --prefix)/opt/docker-compose/bin/docker-compose" ~/.docker/cli-plugins/docker-compose` (macOS/brew)
  or install `docker-compose-plugin` (Linux).
* On macOS a plain `brew install docker` installs the **client only** - without Docker
  Desktop or Colima there is no daemon and every command fails with
  `cannot connect to /var/run/docker.sock`.
* Docker cannot access a usb serial device on macOS/Windows. `./share-serial.sh` publishes
  the port with socat and the integration connects to it as `lan-gw-esp2` - verified with a
  FAM-USB. Details: [docs/dev-container](../docs/dev-container/readme.md#using-a-real-gateway-usb).
  Alternatively run the **standalone runtime**
  ([eltako_standalone/](../eltako_standalone/README.md)) directly on the host, it accesses
  the serial port natively (`COM3`, `/dev/cu.usbserial-*`).
* SELinux hosts (Fedora & co): bind mounts may need the `:z` suffix.

## Housekeeping

```bash
./stop.sh                               # stop, keep the data          (windows: stop.bat)
./stop.sh reset                         # stop and reset everything (users, storage, history)
docker compose logs -f homeassistant    # follow the log
docker compose restart homeassistant   # reload after code changes
```

The seed in `dev/seed/config` is only copied into the config volume when the volume is
empty (first start or after `down -v`) - a running installation is never overwritten.
