@echo off
rem Start the Home Assistant dev container for the Eltako integration.
rem   start.bat              home assistant only
rem   start.bat analytics    additionally InfluxDB + Grafana (timeseries export)
cd /d "%~dp0"

if "%1"=="analytics" (
    docker compose --profile analytics up -d
) else (
    docker compose up -d
)

echo.
echo Home Assistant:  http://localhost:8123   (admin / admin)
if "%1"=="analytics" (
    echo InfluxDB:        http://localhost:8086   (admin / eltako-dev, token: eltako-dev-token)
    echo Grafana:         http://localhost:3000   (admin / admin)
)
echo.
echo Logs:            docker compose logs -f homeassistant
echo Restart HA:      docker compose restart homeassistant   (after code changes)
echo Stop:            stop.bat           (keeps the data)
echo Reset all data:  stop.bat reset
