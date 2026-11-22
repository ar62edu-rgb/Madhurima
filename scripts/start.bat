@echo off
rem Starts the restaurant app (waits for Docker Desktop if it is still starting) and opens the browser.
cd /d "%~dp0.."
title Madhurima Restaurant
set /a tries=0
:waitdocker
docker version >nul 2>&1 && goto :up
if %tries%==0 (
  echo Starting Docker Desktop...
  start "" "%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
)
set /a tries+=1
if %tries% gtr 90 (
  echo Docker Desktop did not start. Open it manually and try again.
  timeout /t 15
  exit /b 1
)
timeout /t 2 /nobreak >nul
goto :waitdocker
:up
docker compose up -d
call "%~dp0wait-and-open.bat"
