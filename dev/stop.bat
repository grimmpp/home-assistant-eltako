@echo off
rem Stop the Home Assistant dev container (incl. InfluxDB/Grafana if they run).
rem   stop.bat           stop - all data (users, storage, history) is kept
rem   stop.bat reset     stop and DELETE all data - the next start seeds everything freshly
cd /d "%~dp0"

if "%1"=="reset" (
    docker compose --profile analytics down -v
    echo.
    echo Stopped and reset. The next start.bat seeds a fresh installation ^(admin/admin^).
) else (
    docker compose --profile analytics down
    echo.
    echo Stopped. All data is kept - start.bat continues where you left off.
    echo To start over with a fresh installation: stop.bat reset
)
