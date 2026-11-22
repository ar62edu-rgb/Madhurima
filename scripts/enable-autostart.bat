@echo off
rem Adds a shortcut to the current user's Startup folder so the app starts (minimised) when Windows starts.
set TARGET=%~dp0start.bat
powershell -NoProfile -Command ^
  "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Startup')+'\Madhurima Restaurant.lnk');" ^
  "$s.TargetPath='%TARGET%'; $s.WorkingDirectory='%~dp0..'; $s.WindowStyle=7; $s.Description='Start Madhurima Family Restaurant'; $s.Save()"
echo Autostart enabled. The app will start after you log in to Windows.
echo Also enable Docker Desktop: Settings ^> General ^> "Start Docker Desktop when you sign in".
pause
