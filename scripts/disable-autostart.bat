@echo off
powershell -NoProfile -Command "Remove-Item -ErrorAction SilentlyContinue ([Environment]::GetFolderPath('Startup')+'\Madhurima Restaurant.lnk')"
echo Autostart disabled.
pause
