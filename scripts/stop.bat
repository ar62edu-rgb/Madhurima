@echo off
rem Stops the restaurant app. Data is kept in Docker volumes.
cd /d "%~dp0.."
docker compose stop
echo Stopped.
timeout /t 3
