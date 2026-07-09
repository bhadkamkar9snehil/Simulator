@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "BUNDLED_PY=%CD%\runtime\python\python.exe"
if not exist "%BUNDLED_PY%" (
  echo ERROR: Bundled Python runtime was not found.
  echo Expected: %BUNDLED_PY%
  exit /b 1
)

"%BUNDLED_PY%" "%CD%\build_release.py" %*
exit /b %ERRORLEVEL%
