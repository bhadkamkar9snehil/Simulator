from __future__ import annotations
import json
import os
from pathlib import Path


def env_port(name: str, default: int) -> int:
    raw = str(os.environ.get(name, "")).strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


frontend = Path(__file__).resolve().parent / "frontend"
frontend.mkdir(exist_ok=True)
config = {
    "industrial_web_port": env_port("INDUSTRIAL_WEB_PORT", 8000),
    "opcua_port": env_port("OPCUA_PORT", 4840),
    "mqtt_port": env_port("MQTT_BROKER_PORT", env_port("MQTT_PORT", 1883)),
    "mqtt_host": os.environ.get("MQTT_HOST", "localhost"),
    "api_studio_port": env_port("API_STUDIO_PORT", 5050),
    "portal_port": env_port("PORTAL_PORT", 8001),
}
(frontend / "launcher-config.js").write_text(
    "window.SIMULATOR_LAUNCHER_CONFIG = " + json.dumps(config, indent=2) + ";\n",
    encoding="utf-8",
)
print("Wrote frontend launcher-config.js with selected ports:", config)
