from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from app.models import SavedConfig, ConfigSummary, utc_now_iso

def get_base_dir() -> Path:
    if os.environ.get("ITS_BASE_DIR"):
        return Path(os.environ["ITS_BASE_DIR"]).resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent

ROOT = get_base_dir()
CONFIG_DIR = ROOT / "configs"


def ensure_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def safe_name(name: str) -> str:
    base = os.path.basename(name.strip())
    if not base or base in {".", ".."} or ".." in base or "/" in base or "\\" in base or "\x00" in base:
        raise ValueError("Unsafe config name.")
    if base.endswith(".json"):
        base = base[:-5]
    return base


def path_for(name: str) -> Path:
    ensure_dir()
    return CONFIG_DIR / f"{safe_name(name)}.json"


def list_configs() -> list[ConfigSummary]:
    ensure_dir()
    out: list[ConfigSummary] = []
    for path in sorted(CONFIG_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            out.append(ConfigSummary(name=data.get("name", path.stem), description=data.get("description", ""), created_at=data.get("created_at"), modified_at=data.get("modified_at")))
        except Exception:
            continue
    return out


def save_config(config: SavedConfig) -> SavedConfig:
    ensure_dir()
    now = utc_now_iso()
    existing = None
    path = path_for(config.name)
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            existing = None
    config.created_at = config.created_at or (existing or {}).get("created_at") or now
    config.modified_at = now
    path.write_text(config.model_dump_json(indent=2), encoding="utf-8")
    return config


def load_config(name: str) -> SavedConfig:
    path = path_for(name)
    if not path.exists():
        raise FileNotFoundError("Config not found.")
    return SavedConfig.model_validate_json(path.read_text(encoding="utf-8"))


def delete_config(name: str) -> dict[str, bool]:
    path = path_for(name)
    if not path.exists():
        raise FileNotFoundError("Config not found.")
    path.unlink()
    return {"deleted": True}
