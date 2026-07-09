from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RELEASES = ROOT / "releases"
REQUIRED_PATHS = [
    "RUN_SIMULATOR.bat",
    "suite_runtime.py",
    "stop_hidden.py",
    "requirements.txt",
    "runtime/runtime_manifest.json",
    "runtime/python/python.exe",
    "runtime/python/pythonw.exe",
    "wheels/wheelhouse_manifest.json",
    "wheels/wheelhouse_constraints.txt",
    "portal/portal_app.py",
    "portal/simulator_ui.html",
    "industrial_simulator/main.py",
    "industrial_simulator/app/api.py",
    "industrial_simulator/app/generators/polyester_fiber.py",
    "industrial_simulator/sample_data/Demo Data.xlsx",
    "industrial_logging.py",
]
REQUIRED_DIRS = [
    "runtime/python",
    "wheels",
    "industrial_simulator",
    "portal",
]
EXCLUDE_DIR_NAMES = {
    ".git",
    ".agents",
    ".codex",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "app_window_profile",
    "logs",
    "outputs",
    "releases",
}
EXCLUDE_FILE_NAMES = {
    "launcher.log",
    "runtime_pids.json",
    ".coverage",
}
EXCLUDE_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".tmp",
    ".ndjson",
}
EXCLUDE_PREFIXES = (
    ".git/",
    ".venv/",
    "logs/",
    "outputs/",
    "releases/",
    "app_window_profile/",
    "industrial_simulator/generated_data/datasets/",
    "industrial_simulator/generated_data/video/",
    "industrial_simulator/lakehouse/",
    "industrial_simulator/runtime_state/",
)
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


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fail(message: str) -> None:
    raise SystemExit(f"ERROR: {message}")


def validate_required_paths() -> None:
    missing = [rel for rel in REQUIRED_PATHS if not (ROOT / rel).exists()]
    missing_dirs = [rel for rel in REQUIRED_DIRS if not (ROOT / rel).is_dir()]
    if missing or missing_dirs:
        problems = [f"missing file: {item}" for item in missing]
        problems.extend(f"missing directory: {item}" for item in missing_dirs)
        fail("; ".join(problems))


def validate_runtime_manifest() -> None:
    runtime_manifest = json.loads((ROOT / "runtime/runtime_manifest.json").read_text(encoding="utf-8"))
    wheel_manifest = json.loads((ROOT / "wheels/wheelhouse_manifest.json").read_text(encoding="utf-8"))
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
        actual = sha256(wheel)
        if actual != file_info["sha256"]:
            fail(f"wheel hash mismatch: {file_info['name']}")


def validate_python_sources() -> None:
    targets = [
        ROOT / "suite_runtime.py",
        ROOT / "stop_hidden.py",
        ROOT / "build_release.py",
        ROOT / "industrial_logging.py",
        *sorted((ROOT / "portal").rglob("*.py")),
        *sorted((ROOT / "industrial_simulator").rglob("*.py")),
    ]
    for path in targets:
        try:
            source = path.read_text(encoding="utf-8-sig")
            compile(source, str(path), "exec")
        except SyntaxError as exc:
            fail(f"Python syntax validation failed: {path.relative_to(ROOT)}:{exc.lineno}: {exc.msg}")


def should_include(path: Path) -> bool:
    rel_parts = path.relative_to(ROOT).parts
    rel = str(path.relative_to(ROOT)).replace("\\", "/")
    if rel.startswith(EXCLUDE_PREFIXES):
        return False
    if any(part in EXCLUDE_DIR_NAMES for part in rel_parts[:-1]):
        return False
    if path.is_dir():
        return path.name not in EXCLUDE_DIR_NAMES
    if path.name.startswith("~$"):
        return False
    if path.name in EXCLUDE_FILE_NAMES:
        return False
    if path.suffix.lower() in EXCLUDE_SUFFIXES:
        return False
    return True


def iter_release_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if path.is_dir():
            continue
        if should_include(path):
            files.append(path)
    return sorted(files, key=lambda p: str(p.relative_to(ROOT)).lower())


def validate_artifact_exclusions(files: list[Path]) -> None:
    bad = []
    for path in files:
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        if rel.startswith(EXCLUDE_PREFIXES):
            bad.append(rel)
        if Path(rel).name.startswith("~$"):
            bad.append(rel)
        if rel.endswith((".pyc", ".pyo", ".tmp", ".ndjson")):
            bad.append(rel)
        if Path(rel).name in EXCLUDE_FILE_NAMES:
            bad.append(rel)
    if bad:
        fail("runtime/build artifacts would be included: " + ", ".join(bad[:20]))


def build_manifest(files: list[Path], package_name: str) -> dict:
    manifest_files = []
    for path in files:
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        include_hash = not rel.startswith("runtime/python/") and not (rel.startswith("wheels/") and path.suffix.lower() == ".whl")
        manifest_files.append(
            {
                "path": rel,
                "size": path.stat().st_size,
                "sha256": sha256(path) if include_hash else "",
            }
        )
    return {
        "package": package_name,
        "built_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "python": sys.version,
        "file_count": len(files),
        "runtime_file_count": sum(1 for path in files if str(path.relative_to(ROOT)).replace("\\", "/").startswith("runtime/python/")),
        "wheel_file_count": sum(1 for path in files if str(path.relative_to(ROOT)).replace("\\", "/").startswith("wheels/") and path.suffix.lower() == ".whl"),
        "files": manifest_files,
    }


def write_zip(files: list[Path], manifest: dict, package_name: str) -> Path:
    RELEASES.mkdir(exist_ok=True)
    zip_path = RELEASES / f"{package_name}.zip"
    tmp_zip_path = RELEASES / f"{package_name}.zip.tmp"
    manifest_path = RELEASES / f"{package_name}.manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    if tmp_zip_path.exists():
        tmp_zip_path.unlink()
    with zipfile.ZipFile(tmp_zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=3) as archive:
        for index, path in enumerate(files, start=1):
            rel = str(path.relative_to(ROOT)).replace("\\", "/")
            compress_type = zipfile.ZIP_STORED if path.suffix.lower() in STORE_SUFFIXES or rel.startswith("runtime/python/") else zipfile.ZIP_DEFLATED
            archive.write(path, rel, compress_type=compress_type)
            if index % 2500 == 0:
                log(f"Packaged {index}/{len(files)} files...")
        archive.writestr("release_manifest.json", json.dumps(manifest, indent=2))
    tmp_zip_path.replace(zip_path)
    return zip_path


def validate_zip(zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "r") as archive:
        names = set(archive.namelist())
        missing = [rel for rel in REQUIRED_PATHS if rel.replace("\\", "/") not in names]
        if missing:
            fail("release zip missing required files: " + ", ".join(missing))
        blocked = [
            name for name in names
            if name.startswith(EXCLUDE_PREFIXES)
            or Path(name).name.startswith("~$")
            or Path(name).name in EXCLUDE_FILE_NAMES
            or Path(name).suffix.lower() in EXCLUDE_SUFFIXES
        ]
        if blocked:
            fail("release zip contains blocked runtime artifacts: " + ", ".join(blocked[:20]))
        bad = archive.testzip()
        if bad:
            fail(f"release zip integrity check failed at {bad}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a complete offline simulator release ZIP.")
    parser.add_argument("--name", default="", help="Optional package name. Default includes current timestamp.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    package_name = args.name.strip() or f"Simulator-{time.strftime('%Y%m%d-%H%M%S')}"
    log("Validating required release files...")
    validate_required_paths()
    log("Validating bundled runtime and offline wheelhouse...")
    validate_runtime_manifest()
    log("Checking Python source syntax...")
    validate_python_sources()
    log("Collecting release files...")
    files = iter_release_files()
    validate_artifact_exclusions(files)
    log(f"Building release manifest for {len(files)} files...")
    manifest = build_manifest(files, package_name)
    log("Writing release ZIP...")
    zip_path = write_zip(files, manifest, package_name)
    log("Validating release ZIP...")
    validate_zip(zip_path)
    print(f"Release built: {zip_path}")
    print(f"Manifest: {RELEASES / (package_name + '.manifest.json')}")
    print(f"Files packaged: {len(files)}")
    print("Install: extract the ZIP on the target Windows machine and run RUN_SIMULATOR.bat.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
