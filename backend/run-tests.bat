@echo off
cd /d "%~dp0"

if exist ".venv-win\Scripts\python.exe" (
  ".venv-win\Scripts\python.exe" -m unittest discover tests
  exit /b %ERRORLEVEL%
)

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m unittest discover tests
  exit /b %ERRORLEVEL%
)

python -m unittest discover tests
