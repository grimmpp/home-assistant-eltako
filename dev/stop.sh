#!/bin/sh
# Stop the Home Assistant dev container (incl. InfluxDB/Grafana if they run).
#   ./stop.sh           stop - all data (users, storage, history) is kept
#   ./stop.sh reset     stop and DELETE all data - the next start seeds everything freshly
cd "$(dirname "$0")"

if [ "$1" = "reset" ]; then
    docker compose --profile analytics down -v
    echo
    echo "Stopped and reset. The next ./start.sh seeds a fresh installation (admin/admin)."
else
    docker compose --profile analytics down
    echo
    echo "Stopped. All data is kept - ./start.sh continues where you left off."
    echo "To start over with a fresh installation: ./stop.sh reset"
fi
