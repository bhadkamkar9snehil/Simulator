from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RELEASES = ROOT / "releases"

# Release packaging is allowlist-only. Development/reference material cannot
# enter a production ZIP unless it is intentionally added here.
REQUIRED_FILES = {
    "RUN_SIMULATOR.bat",
    "suite_runtime.py",
    "stop_hidden.py",
    "requirements.txt",
    "industrial_logging.py",
    "runtime/runtime_manifest.json",
    "portal/portal_app.py",
    "portal/simulator_ui.html",
    "portal/ui/index.html",
    "portal/ui/styles.css",
    "portal/ui/api.js",
    "portal/ui/model.js",
    "portal/ui/render.js",
    "portal/ui/app.js",
    "industrial_simulator/main.py",
    "industrial_simulator/app/sql_server_helper.ps1",
}

ALLOWED_DIRS = {
    "runtime/python",
    "wheels",
    "portal/ui",
    "industrial_simulator/app",
    "industrial_simulator/frontend",
    "industrial_simulator/sample_data",
}

OPTIONAL_FILES = {
    "README.md",
    "LICENSE",
}

STORE_SUFFIXES = {
    ".7z",
    ".cab",
    ".dll",
    ".exe",
    ".msi",
    ".pyd",
    ".pyz",
    ".whl",
    ".zip",
}


def log(message: str) -> None:
    print(message, flush=True)


def fail(message: str) -> None:
    raise SystemExit(f"ERROR: {message}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_required_files() -> None:
    missing = sorted(rel for rel in REQUIRED_FILES if not (ROOT / rel).is_file())
    missing_dirs = sorted(rel for rel in ALLOWED_DIRS if not (ROOT / rel).is_dir())
    if missing or missing_dirs:
        details = [f"missing file: {rel}" for rel in missing]
        details.extend(f"missing directory: {rel}" for rel in missing_dirs)
        fail("; ".join(details))


def validate_runtime_manifest() -> None:
    runtime_manifest_path = ROOT / "runtime/runtime_manifest.json"
    wheel_manifest_path = ROOT / "wheels/wheelhouse_manifest.json"
    runtime_manifest = json.loads(runtime_manifest_path.read_text(encoding="utf-8"))
    wheel_manifest = json.loads(wheel_manifest_path.read_text(encoding="utf-8"))

    if runtime_manifest.get("python_exe") != "runtime/python/python.exe":
        fail("runtime manifest does not point at runtime/python/python.exe")
    if wheel_manifest.get("runtime", {}).get("python_tag") != runtime_manifest.get("python_tag"):
        fail("wheelhouse Python tag does not match runtime manifest")

    for file_info in wheel_manifest.get("files", []):
        wheel = ROOT / "wheels" / file_info["name"]
        if not wheel.exists():
            fail(f"wheel listed in manifest is missing: {file_info['name']}")
        if wheel.stat().st_size != int(file_info["size"]):
            fail(f"wheel size mismatch: {file_info['name']}")
        if sha256(wheel) != file_info["sha256"]:
            fail(f"wheel hash mismatch: {file_info['name']}")


def iter_allowed_files() -> list[Path]:
    files: set[Path] = {ROOT / rel for rel in REQUIRED_FILES}
    files.update(ROOT / rel for rel in OPTIONAL_FILES if (ROOT / rel).is_file())

    for rel in ALLOWED_DIRS:
        base = ROOT / rel
        files.update(path for path in base.rglob("*") if path.is_file())

    return sorted(files, key=lambda path: str(path.relative_to(ROOT)).lower())


def validate_allowlist(files: list[Path]) -> None:
    blocked_fragments = (
        "/tests/",
        "/__pycache__/",
        "/generated_data/",
        "/lakehouse/",
        "/runtime_state/",
        "/uploads/",
        "/outputs/",
        "/releases/",
    )
    blocked_suffixes = {".pyc", ".pyo", ".tmp", ".ndjson", ".bak"}

    violations: list[str] = []
    for path in files:
        rel = "/" + str(path.relative_to(ROOT)).replace("\\", "/")
        if any(fragment in rel for fragment in blocked_fragments):
            violations.append(rel.lstrip("/"))
        elif path.suffix.lower() in blocked_suffixes:
            violations.append(rel.lstrip("/"))
        elif path.name.startswith("~$"):
            violations.append(rel.lstrip("/"))

    if violations:
        fail("allowlist contains runtime/development artifacts: " + ", ".join(violations[:20]))


def validate_python_sources(files: list[Path]) -> None:
    for path in files:
        if path.suffix.lower() != ".py":
            continue
        try:
            compile(path.read_text(encoding="utf-8-sig"), str(path), "exec")
        except SyntaxError as exc:
            fail(f"Python syntax validation failed: {path.relative_to(ROOT)}:{exc.lineno}: {exc.msg}")


def build_manifest(files: list[Path], package_name: str) -> dict:
    manifest_files = []
    for path in files:
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        skip_hash = rel.startswith("runtime/python/") or (rel.startswith("wheels/") and path.suffix.lower() == ".whl")
        manifest_files.append({
            "path": rel,
            "size": path.stat().st_size,
            "sha256": "" if skip_hash else sha256(path),
        })

    return {
        "package": package_name,
        "built_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "python": sys.version,
        "file_count": len(files),
        "runtime_file_count": sum(1 for item in manifest_files if item["path"].startswith("runtime/python/")),
        "wheel_file_count": sum(1 for item in manifest_files if item["path"].startswith("wheels/") and item["path"].endswith(".whl")),
        "files": manifest_files,
    }


def write_zip(files: list[Path], manifest: dict, package_name: str) -> Path:
    RELEASES.mkdir(exist_ok=True)
    zip_path = RELEASES / f"{package_name}.zip"
    tmp_path = RELEASES / f"{package_name}.zip.tmp"
    manifest_path = RELEASES / f"{package_name}.manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    if tmp_path.exists():
        tmp_path.unlink()

    with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=3) as archive:
        for path in files:
            rel = str(path.relative_to(ROOT)).replace("\\", "/")
            stored = path.suffix.lower() in STORE_SUFFIXES or rel.startswith("runtime/python/")
            archive.write(path, rel, compress_type=zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED)
        archive.writestr("release_manifest.json", json.dumps(manifest, indent=2))

    tmp_path.replace(zip_path)
    return zip_path


def validate_zip(zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "r") as archive:
        names = set(archive.namelist())
        missing = sorted(rel for rel in REQUIRED_FILES if rel not in names)
        if missing:
            fail("release ZIP missing required files: " + ", ".join(missing))
        if "api_studio/app.py" in names:
            fail("release ZIP unexpectedly contains retired API Studio")
        bad = archive.testzip()
        if bad:
            fail(f"release ZIP integrity check failed at {bad}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the offline Simulator runtime ZIP.")
    parser.add_argument("--name", default="", help="Optional package name.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    package_name = args.name.strip() or f"Simulator-{time.strftime('%Y%m%d-%H%M%S')}"

    log("Validating runtime release allowlist...")
    validate_required_files()
    validate_runtime_manifest()

    files = iter_allowed_files()
    validate_allowlist(files)
    validate_python_sources(files)

    manifest = build_manifest(files, package_name)
    log(f"Packaging {len(files)} allowlisted runtime files...")
    zip_path = write_zip(files, manifest, package_name)
    validate_zip(zip_path)

    print(f"Release built: {zip_path}")
    print(f"Manifest: {RELEASES / (package_name + '.manifest.json')}")
    print("Install: extract on the target Windows machine and run RUN_SIMULATOR.bat.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
