@echo off
rem ===== Madhurima Family Restaurant - one-time installation (Docker) =====
cd /d "%~dp0"
title Madhurima Restaurant - Install

docker version >nul 2>&1
if errorlevel 1 (
  echo Docker Desktop is not running. Start Docker Desktop, wait until it says "Engine running", then run install.bat again.
  pause
  exit /b 1
)

if not exist ".env" (
  echo Creating .env with random passwords...
  powershell -NoProfile -Command "$r={-join((48..57)+(65..90)+(97..122)|Get-Random -Count 40|%%{[char]$_})}; \"POSTGRES_PASSWORD=$(& $r)`r`nSECRET_KEY=$(& $r)$(& $r)`r`nAPP_PORT=8090\" | Set-Content -Encoding ascii .env"
)
if not exist "backups" mkdir backups

echo Building and starting the application (first time takes a few minutes)...
docker compose up -d --build
if errorlevel 1 (
  echo Installation failed. See the messages above.
  pause
  exit /b 1
)

call "%~dp0scripts\wait-and-open.bat"
echo.
echo Installed. Run scripts\enable-autostart.bat to start the app automatically when Windows starts.
pause
