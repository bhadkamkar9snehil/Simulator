# Simulator

Single entry surface:

`RUN_SIMULATOR.bat`

What it does:

- uses the bundled Python runtime in `runtime/python`
- validates or recreates `.venv`
- installs only from the bundled offline wheelhouse
- starts Industrial, API Studio, and Portal hidden
- opens the portal automatically

Notes:

- stop the suite from the portal UI
- startup logs are written to `launcher.log`
- saved ports live in `simulator_ports.json`
