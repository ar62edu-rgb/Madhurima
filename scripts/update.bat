@echo off
rem Rebuilds the app container after code changes. Database and backups are untouched.
cd /d "%~dp0.."
docker compose up -d --build app
call "%~dp0wait-and-open.bat"
pause
