#!/bin/sh
# Start ONLY InfluxDB + Grafana - without Home Assistant.
#
# For the standalone runtime (python -m eltako_standalone serve), which enables the telegram
# recording and the InfluxDB export by default and expects the stack under these urls.
cd "$(dirname "$0")"

docker compose --profile analytics up -d influxdb grafana

echo
echo "InfluxDB:  http://localhost:8086   (admin / eltako-dev, token: eltako-dev-token)"
echo "Grafana:   http://localhost:3000   (admin / admin)"
echo "           dashboards 'Eltako - Telegram overview' and 'Eltako - Device analysis'"
echo "           are provisioned, the overview is the home dashboard."
echo
echo "Standalone: python -m eltako_standalone serve    (export is on by default)"
echo "Stop:       ./stop.sh"
