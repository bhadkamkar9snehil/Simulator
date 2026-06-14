@echo off
setlocal
cd /d %~dp0
if exist data\studio.db del data\studio.db
echo Database reset. Run setup_and_run.bat to recreate seed data.
