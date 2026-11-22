@echo off
rem Waits for the app to answer, then opens it in the default browser.
set PORT=8090
for /f "tokens=2 delims==" %%a in ('findstr /b "APP_PORT=" "%~dp0..\.env" 2^>nul') do set PORT=%%a
echo Waiting for http://localhost:%PORT% ...
for /l %%i in (1,1,90) do (
  powershell -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 http://localhost:%PORT%/api/health | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1 && goto :ready
  timeout /t 2 /nobreak >nul
)
echo The app did not respond yet. Check "docker compose logs app".
exit /b 1
:ready
echo Madhurima Restaurant is running at http://localhost:%PORT%
start "" http://localhost:%PORT%
exit /b 0
