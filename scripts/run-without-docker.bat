@echo off
rem Alternative: run directly on Windows with Python 3.12+ and Node 20+ installed. Uses SQLite in backend\data.
cd /d "%~dp0..\backend"
if not exist ".venv" (
  python -m venv .venv || (echo Python is not installed. & pause & exit /b 1)
  .venv\Scripts\pip install -r requirements.txt
)
if not exist "..\frontend\dist\index.html" (
  pushd ..\frontend
  call npm ci && call npm run build
  popd
)
start "" http://localhost:8000
.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
