# Industrial Dual Protocol Tag Simulator

## Windows start

Start the simulator from the suite root:

```text
RUN_SIMULATOR.bat
```

The suite launcher provides the bundled runtime, offline dependency setup, API Studio, and the portal. This folder is not intended to be launched directly anymore.


One local simulator for OPC UA and MQTT, with separate protocol plans for running different CSV/XLSX files at the same time.

## Features

- One web UI for OPC UA and MQTT.
- Protocol modes:
  - OPC UA only
  - MQTT only
  - OPC UA + MQTT together
- Protocol plans in BOTH mode:
  - **Shared / Both**: the selected files feed both OPC UA and MQTT.
  - **OPC UA Plan**: these files feed only OPC UA.
  - **MQTT Plan**: these files feed only MQTT.
- Multiple `.xlsx` and `.csv` files can run in each plan.
- Automatic tag mapping from file headers.
- Manual single-file tag mapping remains available.
- OPC UA exposes one common `TagSimulator` root folder with unique variables per file.
- MQTT publishes:
  - individual tag topics: `<topic-prefix>/<node-id>`
  - rich aggregate: `<topic-prefix>/all`
  - flat JSON for dashboards/StreamPipes: `<topic-prefix>/flat`
  - flat JSON duplicate topic: `<topic-prefix>/streampipes`
- Runtime status and current values are visible in the UI.

## Component-only development

From the extracted folder:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python run_desktop.py
```

Then open:

```text
http://127.0.0.1:8000
```

Alternative backend command:

```powershell
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## Run OPC UA and MQTT with different files

1. Open **2. Files**.
2. Upload or use existing CSV/XLSX files.
3. Tick one or more files under **OPC UA Plan**.
4. Tick different files under **MQTT Plan**.
5. Open **3. Replay**.
6. Set **Protocol** to **OPC UA + MQTT together**.
7. Configure OPC UA and MQTT settings.
8. Click **Apply Selected Protocol Plans**.
9. Click **Start**.

Example:

```text
OPC UA Plan: opcua_plan_demo.csv
MQTT Plan:   mqtt_plan_demo.csv
```

OPC UA variables will come from the OPC UA Plan. MQTT topics will publish only data from the MQTT Plan.

## Run the same files on both protocols

1. Tick files under **Shared / Both**.
2. Set **Protocol** to **OPC UA + MQTT together**.
3. Click **Apply Selected Protocol Plans**.
4. Click **Start**.

Shared files are automatically included in both the OPC UA Plan and the MQTT Plan.

## Default endpoints

- OPC UA endpoint: `opc.tcp://localhost:4840/simulator`
- MQTT broker default: `localhost:1883`
- MQTT topic prefix default: `industrial-tag-simulator`


## UaExpert OPC UA connection note

This build auto-generates and loads a local OPC UA server certificate in `configs/opcua_certs`, while exposing only the simple test endpoint:

```text
Security Policy: None
Message Security Mode: None
Authentication: Anonymous
Endpoint: opc.tcp://localhost:4840/simulator
```

Use the `None / None` endpoint in UaExpert. If UaExpert still shows an older cached connection, delete the old server entry and add it again manually with the endpoint above.

## MQTT topics to use in StreamPipes

Use one of these topics for flat JSON data:

```text
industrial-tag-simulator/streampipes
industrial-tag-simulator/flat
```

Avoid using `/all` for StreamPipes unless you specifically want nested JSON. The `/streampipes` and `/flat` topics publish simple field/value JSON.

If StreamPipes runs in Docker Desktop on Windows and Mosquitto runs on Windows, use this broker address in StreamPipes:

```text
tcp://host.docker.internal:1883
```

If Mosquitto runs in the same Docker network as StreamPipes, use the Mosquitto container/service name instead, for example:

```text
tcp://mosquitto:1883
```

## Excel / CSV format

The first row must contain column names. Each supported data column becomes a simulated tag. Columns such as `timestamp`, `scenario`, `phase`, and label/alarm columns are loaded but disabled by default in auto-mapping where appropriate.

## OPC UA address space behavior

OPC UA creates one common root only:

```text
Objects
  TagSimulator
    TagSimulator_sample_pipeline_normal_pressure_inlet_bar
    TagSimulator_sample_pipeline_normal_pressure_outlet_bar
    TagSimulator_sample_pipeline_small_leak_pressure_inlet_bar
```

It does not create a duplicate `TagSimulator` folder for every CSV/XLSX file.


## StreamPipes MQTT field values

For StreamPipes, subscribe to:

```text
industrial-tag-simulator/streampipes
```

This topic publishes a flat JSON object. In protocol-plan mode it includes both:

- file-prefixed field names, useful when multiple files are replayed
- original CSV/XLSX column names, useful for StreamPipes adapters created from the source file schema

Do not use `industrial-tag-simulator/all` for StreamPipes data tables. The `/all` topic is nested JSON intended for custom clients.

## v8: Separate OPC UA and MQTT tag plans

Protocol-plan replay now includes a tag preview step before Start.

Recommended workflow:

1. Go to **Files / Assignment**.
2. Select files under **OPC UA Plan** and **MQTT Plan** separately.
3. Go to **Replay OPC UA / MQTT**.
4. Click **Build / Refresh Tag Preview**.
5. Review **OPC UA Tag Plan** and **MQTT Tag Plan**.
6. Uncheck tags that should not run.
7. Click **Apply Selected Protocol Plans**.
8. Click **Start**.

Only tags listed under **Will Run** are exposed on OPC UA or published on MQTT. Tags listed under **Not Run / Unselected** are ignored.
