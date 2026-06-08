@echo off
cd /d "%~dp0"

if exist ".venv-win\Scripts\python.exe" (
  ".venv-win\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
  exit /b %ERRORLEVEL%
)

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
  exit /b %ERRORLEVEL%
)

python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
