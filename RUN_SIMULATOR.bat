@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "BUNDLED_PY=%CD%\runtime\python\python.exe"
set "BUNDLED_PYW=%CD%\runtime\python\pythonw.exe"

if not exist "%BUNDLED_PY%" (
  echo ERROR: Bundled Python runtime was not found.
  echo Expected: %BUNDLED_PY%
  pause
  exit /b 1
)

if not exist "%BUNDLED_PYW%" (
  echo ERROR: Bundled Python runtime is incomplete.
  echo Expected: %BUNDLED_PYW%
  pause
  exit /b 1
)

echo Starting simulator suite...
"%BUNDLED_PY%" "%CD%\suite_runtime.py" ensure-env
if errorlevel 1 (
  echo.
  echo ERROR: Startup preparation failed. Check launcher.log.
  pause
  exit /b 1
)

start "" "%BUNDLED_PYW%" "%CD%\suite_runtime.py" start-hidden
echo Simulator launch requested.
echo Portal will open automatically when the services are ready.
timeout /t 2 /nobreak >nul
exit /b 0
