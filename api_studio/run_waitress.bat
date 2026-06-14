@echo off
setlocal
cd /d %~dp0
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat
set PORT=5050
waitress-serve --listen=0.0.0.0:5050 app:app
