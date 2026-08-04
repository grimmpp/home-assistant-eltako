#!/bin/sh
# Start the Home Assistant dev container for the Eltako integration.
#   ./start.sh              home assistant only
#   ./start.sh analytics    additionally InfluxDB + Grafana (timeseries export)
cd "$(dirname "$0")"

if [ "$1" = "analytics" ]; then
    docker compose --profile analytics up -d
else
    docker compose up -d
fi

echo
echo "Home Assistant:  http://localhost:8123   (admin / admin)"
if [ "$1" = "analytics" ]; then
    echo "InfluxDB:        http://localhost:8086   (admin / eltako-dev, token: eltako-dev-token)"
    echo "Grafana:         http://localhost:3000   (admin / admin)"
fi
echo
echo "Logs:            docker compose logs -f homeassistant"
echo "Restart HA:      docker compose restart homeassistant   (after code changes)"
echo "Stop:            ./stop.sh          (keeps the data)"
echo "Reset all data:  ./stop.sh reset"
