import argparse
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

APP_NAME = "Meccha Mod Builder"
APP_VERSION = "1.2.0-dev"

MECCHA_APP_ID = "4704690"  # DO NOT CHANGE

def user_data_dir() -> Path:
    """
    Return a persistent, writable per-user data directory.

    Windows example:
    C:\\Users\\Username\\AppData\\Roaming\\Meccha Mod Builder
    """
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path.home() / ".config"

    app_dir = base / "Meccha Mod Builder"
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir


USER_DATA_DIR = user_data_dir()

SETTINGS_FILE = USER_DATA_DIR / "build_meccha_mod_gui_settings_v3.json"
PROFILES_DIR = USER_DATA_DIR / "build_profiles"

BUILD_HISTORY_DIR = USER_DATA_DIR / "build_history"
BUILD_LOGS_DIR = BUILD_HISTORY_DIR / "logs"
BUILD_HISTORY_FILE = BUILD_HISTORY_DIR / "history.json"

CACHE_DIR = USER_DATA_DIR / "cache"
RECENT_PROJECTS_FILE = CACHE_DIR / "recent_projects.json"
BUILD_STATISTICS_FILE = CACHE_DIR / "build_statistics.json"
UPDATE_SETTINGS_FILE = CACHE_DIR / "update_settings.json"

PREVIEWS_DIR = USER_DATA_DIR / "previews"

GUI_SETTINGS_VERSION = 3

def ensure_user_data_directories():
    """Create all persistent application directories if they do not exist."""
    directories = [
        USER_DATA_DIR,
        PROFILES_DIR,
        BUILD_HISTORY_DIR,
        BUILD_LOGS_DIR,
        CACHE_DIR,
        PREVIEWS_DIR,
    ]

    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)


ensure_user_data_directories()

def load_json_file(path: Path, default):
    """
    Safely load JSON data.

    Returns the supplied default value when the file is missing, unreadable,
    or contains invalid JSON.
    """
    try:
        if not path.exists():
            return default

        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Could not load JSON file '{path}': {exc}")
        return default


def save_json_file(path: Path, data):
    """
    Safely save JSON data using a temporary file before replacing the original.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    temporary_path = path.with_name(f"{path.name}.tmp")

    temporary_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    temporary_path.replace(path)

def current_local_timestamp() -> str:
    """Return the current local date and time in ISO format."""
    return datetime.now().astimezone().isoformat(timespec="seconds")

def create_build_id() -> str:
    """
    Create a sortable ID that is unique enough for local build history.

    Example:
        20260719_214530_482193
    """
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")

def load_build_history() -> list[dict]:
    """Load persistent build history from disk."""
    data = load_json_file(BUILD_HISTORY_FILE, [])

    if not isinstance(data, list):
        return []

    return [
        record
        for record in data
        if isinstance(record, dict)
    ]

def save_build_history(records: list[dict]) -> None:
    """
    Save build history while limiting the file to the newest 500 records.
    """
    limited_records = records[-500:]
    save_json_file(BUILD_HISTORY_FILE, limited_records)

def save_build_history(records: list[dict]) -> None:
    """
    Save build history while limiting the file to the newest 500 records.
    """
    limited_records = records[-500:]
    save_json_file(BUILD_HISTORY_FILE, limited_records)

def calculate_duration_seconds(started_at: datetime | None) -> float | None:
    """Calculate elapsed seconds from a datetime value."""
    if started_at is None:
        return None

    elapsed = datetime.now().astimezone() - started_at
    return round(max(0.0, elapsed.total_seconds()), 2)

def append_build_history_record(record: dict) -> None:
    """Add a new build-history record."""
    records = load_build_history()
    records.append(record)
    save_build_history(records)

def format_duration(seconds) -> str:
    """Format a duration as seconds, minutes, or hours."""
    if seconds is None:
        return "—"

    try:
        total_seconds = max(0, int(round(float(seconds))))
    except (TypeError, ValueError):
        return "—"

    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours:
        return f"{hours}h {minutes}m {seconds}s"

    if minutes:
        return f"{minutes}m {seconds}s"

    return f"{seconds}s"

def validation_result(level: str, title: str, details: str = "") -> dict:
    """
    Create a standardized preflight validation result.

    level must be:
        pass
        warning
        error
    """
    normalized_level = level.strip().lower()

    if normalized_level not in {"pass", "warning", "error"}:
        raise ValueError(f"Invalid validation level: {level}")

    return {
        "level": normalized_level,
        "title": title,
        "details": details,
    }


def count_validation_results(results: list[dict]) -> dict:
    """Return totals for each preflight result level."""
    return {
        "pass": sum(result["level"] == "pass" for result in results),
        "warning": sum(result["level"] == "warning" for result in results),
        "error": sum(result["level"] == "error" for result in results),
    }

def detect_unreal_version(run_uat_path: Path) -> str:
    """
    Attempt to determine the Unreal Engine version from the RunUAT path.

    Example:
        C:\\Program Files\\Epic Games\\UE_5.6\\Engine\\Build\\BatchFiles\\RunUAT.bat
        returns 5.6
    """
    path_text = str(run_uat_path)

    match = re.search(
        r"(?:UE[_-]?|UnrealEngine[_-]?)(\d+(?:\.\d+){1,2})",
        path_text,
        flags=re.IGNORECASE,
    )

    if match:
        return match.group(1)

    return ""

def inspect_json_descriptor(path: Path) -> tuple[dict | None, str]:
    """
    Load a JSON-based Unreal descriptor such as .uproject or .uplugin.

    Returns:
        (parsed_data, error_message)
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))

        if not isinstance(data, dict):
            return None, "Descriptor root must be a JSON object."

        return data, ""

    except OSError as exc:
        return None, f"Could not read descriptor: {exc}"

    except json.JSONDecodeError as exc:
        return None, (
            f"Invalid JSON at line {exc.lineno}, column {exc.colno}: "
            f"{exc.msg}"
        )

def find_map_candidates(
    project: Path,
    plugin_name: str,
    map_path: str,
) -> list[Path]:
    """
    Search likely project and plugin Content folders for a .umap whose filename
    matches the selected runtime map name.

    This is a filename-level check only. Runtime package remapping may mean the
    physical source location differs from the final /Game path.
    """
    map_name = map_path.rstrip("/").rsplit("/", 1)[-1].strip()

    if not map_name:
        return []

    project_root = project.parent

    search_roots = [
        project_root / "Content",
        project_root / "Plugins" / plugin_name / "Content",
    ]

    candidates = []

    for search_root in search_roots:
        if not search_root.exists():
            continue

        try:
            candidates.extend(search_root.rglob(f"{map_name}.umap"))
        except OSError:
            continue

    unique_candidates = {
        candidate.resolve()
        for candidate in candidates
        if candidate.is_file()
    }

    return sorted(unique_candidates, key=lambda path: str(path).lower())

def find_running_unreal_processes() -> list[str]:
    """
    Return the names of running Unreal Editor processes on Windows.

    Uses Windows tasklist so no additional dependency such as psutil is needed.
    """
    if os.name != "nt":
        return []

    known_processes = {
        "unrealeditor.exe",
        "ue4editor.exe",
        "unrealeditor-cmd.exe",
        "ue4editor-cmd.exe",
    }

    try:
        completed = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            shell=False,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []

    if completed.returncode != 0:
        return []

    running = set()

    for line in completed.stdout.splitlines():
        line = line.strip()

        if not line:
            continue

        # CSV output begins with the quoted process name.
        process_name = line.split(",", 1)[0].strip().strip('"')

        if process_name.lower() in known_processes:
            running.add(process_name)

    return sorted(running, key=str.lower)

def find_recent_unreal_recovery_files(
    project: Path,
    plugin_name: str = "",
    maximum_results: int = 20,
) -> list[Path]:
    """
    Locate recent Unreal autosave, backup, and temporary files.

    Finding these files does not prove that assets are currently unsaved.
    They are only used as a caution before starting a build.
    """
    project_root = project.parent

    search_roots = [
        project_root / "Saved" / "Autosaves",
        project_root / "Saved" / "Backup",
    ]

    if plugin_name:
        plugin_saved = project_root / "Plugins" / plugin_name / "Saved"

        search_roots.extend([
            plugin_saved / "Autosaves",
            plugin_saved / "Backup",
        ])

    candidate_suffixes = {
        ".autosave",
        ".tmp",
        ".temp",
    }

    candidates = []

    for search_root in search_roots:
        if not search_root.is_dir():
            continue

        try:
            for path in search_root.rglob("*"):
                if not path.is_file():
                    continue

                # Unreal autosave folders commonly contain .uasset and .umap
                # recovery copies in addition to explicitly temporary files.
                if (
                    path.suffix.lower() in candidate_suffixes
                    or path.suffix.lower() in {".uasset", ".umap"}
                ):
                    candidates.append(path)
        except OSError:
            continue

    def modified_time(path: Path) -> float:
        try:
            return path.stat().st_mtime
        except OSError:
            return 0.0

    candidates.sort(key=modified_time, reverse=True)

    return candidates[:maximum_results]

def describe_file_age(path: Path) -> str:
    """Return a short human-readable description of a file's age."""
    try:
        modified = datetime.fromtimestamp(path.stat().st_mtime)
    except OSError:
        return "unknown age"

    elapsed = datetime.now() - modified
    seconds = max(0, int(elapsed.total_seconds()))

    if seconds < 60:
        return "less than a minute ago"

    minutes = seconds // 60

    if minutes < 60:
        return f"{minutes} minute(s) ago"

    hours = minutes // 60

    if hours < 24:
        return f"{hours} hour(s) ago"

    days = hours // 24
    return f"{days} day(s) ago"

def resource_path(*parts: str) -> Path:
    """
    Return a resource path that works both as a normal Python script
    and when packaged with PyInstaller.
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base_dir = Path(sys._MEIPASS)
    else:
        base_dir = Path(__file__).resolve().parent

    return base_dir.joinpath(*parts)


WINDOW_ICON_PATH = resource_path("icon", "icon.ico")
HEADER_LOGO_PATH = resource_path("icon", "icon.png")

APP_ICON_FILE = WINDOW_ICON_PATH
APP_LOGO_FILE = HEADER_LOGO_PATH

def run(cmd, cwd=None):
    print("\n=== RUNNING ===")
    print(" ".join(f'"{c}"' if " " in str(c) else str(c) for c in cmd))
    result = subprocess.run(cmd, cwd=cwd, shell=False)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed with exit code {result.returncode}")


def require_file(path: Path, label: str):
    path = path.expanduser().resolve()
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Missing {label}: {path}")
    return path


def require_dir(path: Path, label: str):
    path = path.expanduser().resolve()
    if not path.exists() or not path.is_dir():
        raise FileNotFoundError(f"Missing {label}: {path}")
    return path


def ensure_dir(path: Path):
    path = path.expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def require_fresh_file(path: Path, label: str, build_started_at: datetime):
    path = require_file(path, label)
    modified = datetime.fromtimestamp(path.stat().st_mtime)
    if modified.timestamp() + 2 < build_started_at.timestamp():
        raise RuntimeError(
            f"{label} exists but was not updated by this build:\n"
            f"  File:          {path}\n"
            f"  Modified:      {modified}\n"
            f"  Build started: {build_started_at}\n\n"
            "This usually means the DLC/My Mod build failed, wrote somewhere "
            "else, or cooked the wrong plugin/map."
        )
    return path


def newest_files(root: Path, suffixes):
    files = []
    if root.exists():
        for file in root.rglob("*"):
            if file.is_file() and file.suffix.lower() in suffixes:
                files.append(file)
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)


def mark_interrupted_builds() -> int:
    """
    Mark unfinished records from previous sessions as interrupted.

    Returns the number of records changed.
    """
    records = load_build_history()
    changed = 0
    recovery_time = current_local_timestamp()

    for record in records:
        if record.get("status") == "running":
            record.update({
                "status": "interrupted",
                "finished_at": recovery_time,
                "error": (
                    "The application ended before this build recorded "
                    "a normal completion state."
                ),
            })
            changed += 1

    if changed:
        save_build_history(records)

    return changed

def to_vdf_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "\\\\")


def escape_vdf_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def write_vdf(vdf_path_out, appid, publishedfileid, contentfolder, previewfile,
              title, description, changenote, visibility):
    text = f'''\"workshopitem\"
{{
    \"appid\"                 \"{escape_vdf_value(appid)}\"
    \"publishedfileid\"       \"{escape_vdf_value(publishedfileid)}\"
    \"contentfolder\"         \"{to_vdf_path(contentfolder)}\"
    \"previewfile\"           \"{to_vdf_path(previewfile)}\"
    \"visibility\"            \"{escape_vdf_value(visibility)}\"
    \"title\"                 \"{escape_vdf_value(title)}\"
    \"description\"           \"{escape_vdf_value(description)}\"
    \"changenote\"            \"{escape_vdf_value(changenote)}\"
}}
'''
    vdf_path_out.write_text(text, encoding="utf-8")
    print(f"Wrote VDF: {vdf_path_out}")


def print_recent_payload_candidates(project_root: Path, plugin_name: str):
    print("\n=== Recent Pak/Registry Candidates ===")
    roots = [
        project_root / "Saved",
        project_root / "Plugins" / plugin_name / "Saved",
    ]
    files = []
    for root in roots:
        files.extend(newest_files(root, {".pak", ".ucas", ".utoc", ".bin"}))
    if not files:
        print("No .pak/.ucas/.utoc/.bin files found.")
        return
    for file in sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)[:40]:
        modified = datetime.fromtimestamp(file.stat().st_mtime)
        print(f"{modified:%Y-%m-%d %H:%M:%S}  {file.stat().st_size:>12,}  {file}")


def validate_map_path(map_path: str, plugin_name: str):
    if not map_path.startswith("/"):
        raise ValueError(
            f"Unreal map path must start with '/'. Got: {map_path}\n"
            "Example: /Game/Mods/UserMap01/MyCustomMap"
        )
    if map_path.endswith(".umap"):
        raise ValueError(
            f"Do not include '.umap': {map_path}\n"
            "Use: /Game/Mods/UserMap01/MyCustomMap"
        )
    if "." in map_path.rsplit("/", 1)[-1]:
        raise ValueError(
            f"Use package path only, not Object.Object syntax: {map_path}"
        )

    if map_path.startswith("/Game/Mods/UserMap01/"):
        print("\nMap path matches Meccha's confirmed runtime folder:")
        print(f"  {map_path}\n")
    elif map_path.startswith(f"/{plugin_name}/"):
        print("\nWARNING: map is inside the plugin.")
        print("Known reliable Meccha runtime path:")
        print("  /Game/Mods/UserMap01/MapName\n")
    else:
        print(f"\nWARNING: unusual map path: {map_path}")
        print("Known working example: /Game/Mods/UserMap01/MyCustomMap\n")


def validate_plugin(project_root: Path, plugin_name: str):
    plugin_root = require_dir(project_root / "Plugins" / plugin_name, "plugin folder")
    files = list(plugin_root.glob("*.uplugin"))
    if not files:
        raise FileNotFoundError(
            f"No .uplugin file found in:\n  {plugin_root}\n\n"
            "Select the exact plugin folder name."
        )
    if not any(p.stem == plugin_name for p in files):
        print("\nWARNING: plugin folder and .uplugin basename do not match.")
        print("Found:", ", ".join(p.name for p in files), "\n")
    return plugin_root


def build_full_game(ue, project, project_root, release):
    run([
        str(ue), "BuildCookRun", f"-project={project}", "-noP4",
        "-platform=Win64", "-clientconfig=Development", "-build", "-cook",
        "-stage", "-pak", "-compressed",
        f"-createReleaseVersion={release}", "-utf8output",
    ], cwd=project_root)


def build_mod_dlc(ue, project, project_root, plugin_name, release, map_path):
    run([
        str(ue), "BuildCookRun", f"-project={project}", "-noP4",
        "-platform=Win64", "-clientconfig=Development", "-build", "-cook",
        "-stage", "-pak", "-compressed", f"-dlcName={plugin_name}",
        f"-basedOnReleaseVersion={release}", "-DLCIncludeEngineContent",
        f"-map={map_path}", "-utf8output",
    ], cwd=project_root)


def find_expected_payload_paths(project: Path, plugin_name: str):
    project_root = project.parent
    project_name = project.stem
    plugin_root = project_root / "Plugins" / plugin_name

    staged_paks = (
        plugin_root / "Saved" / "StagedBuilds" / "Windows" / project_name
        / "Plugins" / plugin_name / "Content" / "Paks" / "Windows"
    )
    cooked_plugin = (
        plugin_root / "Saved" / "Cooked" / "Windows" / project_name
        / "Plugins" / plugin_name
    )
    prefix = f"{plugin_name}{project_name}-Windows"

    return {
        "plugin_root": plugin_root,
        "staged_paks": staged_paks,
        "cooked_plugin": cooked_plugin,
        "pak": staged_paks / f"{prefix}.pak",
        "ucas": staged_paks / f"{prefix}.ucas",
        "utoc": staged_paks / f"{prefix}.utoc",
        "registry": cooked_plugin / "AssetRegistry.bin",
    }


def discover_payload_fallback(project: Path, plugin_name: str, payload):
    project_root = project.parent
    project_name = project.stem
    plugin_saved = project_root / "Plugins" / plugin_name / "Saved"
    expected_stem = f"{plugin_name}{project_name}-Windows".lower()
    candidates = newest_files(plugin_saved, {".pak", ".ucas", ".utoc", ".bin"})

    for suffix, key in [(".pak", "pak"), (".ucas", "ucas"), (".utoc", "utoc")]:
        if payload[key].exists():
            continue
        matches = [
            p for p in candidates
            if p.suffix.lower() == suffix and p.stem.lower() == expected_stem
        ]
        if matches:
            payload[key] = matches[0]
            print(f"Fallback located {suffix}: {matches[0]}")

    if not payload["registry"].exists():
        matches = [
            p for p in candidates
            if p.name.lower() == "assetregistry.bin"
            and plugin_name.lower() in str(p).lower()
        ]
        if matches:
            payload["registry"] = matches[0]
            print(f"Fallback located AssetRegistry.bin: {matches[0]}")
    return payload


def clean_workshop_payload(workshop: Path, preview: Path):
    print("\n=== Cleaning Old Workshop Payload ===")
    keep = preview.resolve()
    for file in workshop.iterdir():
        if file.is_file() and file.resolve() != keep:
            if file.suffix.lower() in {".pak", ".ucas", ".utoc", ".bin", ".vdf"}:
                print(f"Deleting old payload: {file}")
                file.unlink()


def copy_payload_to_workshop(payload, workshop, preview):
    print("\n=== Copying Workshop Payload ===")
    required = [payload["pak"], payload["ucas"], payload["utoc"], payload["registry"]]
    copied = []
    for src in required:
        dst = workshop / src.name
        shutil.copy2(src, dst)
        copied.append(dst)
        print(f"Copied: {src.name}  ({src.stat().st_size:,} bytes)")

    preview_dst = workshop / preview.name
    if preview.resolve() != preview_dst.resolve():
        shutil.copy2(preview, preview_dst)
        print(f"Copied: {preview.name}  ({preview.stat().st_size:,} bytes)")
    else:
        print(f"Preview already in Workshop folder: {preview.name}")
    copied.append(preview_dst)
    return preview_dst, copied


def run_steamcmd(steamcmd, vdf_path, steam_login):
    if steam_login:
        cmd = [
            str(steamcmd), "+login", *steam_login.split(),
            "+workshop_build_item", str(vdf_path), "+quit",
        ]
    else:
        cmd = [str(steamcmd), "+workshop_build_item", str(vdf_path), "+quit"]
    run(cmd)


def make_parser():
    parser = argparse.ArgumentParser(
        description="Universal Meccha Chameleon Full Game + My Mod builder."
    )
    parser.add_argument("--gui", action="store_true")
    parser.add_argument("--ue")
    parser.add_argument("--project")
    parser.add_argument("--map", dest="map_path")
    parser.add_argument("--plugin")
    parser.add_argument("--release", default="1.0")
    parser.add_argument("--workshop")
    parser.add_argument("--preview")
    parser.add_argument("--appid", default=MECCHA_APP_ID)
    parser.add_argument("--publishedfileid", default="0")
    parser.add_argument("--visibility", default="2", choices=["0", "1", "2"])
    parser.add_argument("--title", default="Custom Meccha Map")
    parser.add_argument("--description", default="Custom map for Meccha Chameleon.")
    parser.add_argument("--changenote", default="Fresh UE 5.6.1 build")
    parser.add_argument("--skip-full-game", action="store_true")
    parser.add_argument("--skip-mod", action="store_true")
    parser.add_argument("--copy-only", action="store_true")
    parser.add_argument("--clean-workshop", action="store_true")
    parser.add_argument("--steamcmd")
    parser.add_argument("--upload", action="store_true")
    parser.add_argument("--steam-login")
    return parser


def main_cli(argv=None):
    parser = make_parser()
    args = parser.parse_args(argv)
    if args.gui:
        launch_gui()
        return

    for flag, value in [
        ("--ue", args.ue), ("--project", args.project), ("--map", args.map_path),
        ("--plugin", args.plugin), ("--workshop", args.workshop),
        ("--preview", args.preview),
    ]:
        if not value:
            parser.error(f"{flag} is required in CLI mode")

    build_started_at = datetime.now()
    ue = require_file(Path(args.ue), "RunUAT.bat")
    project = require_file(Path(args.project), "uproject")
    project_root = project.parent
    plugin_root = validate_plugin(project_root, args.plugin)
    workshop = ensure_dir(Path(args.workshop))
    preview = require_file(Path(args.preview), "preview image")
    validate_map_path(args.map_path, args.plugin)

    print("=== Meccha Mod Build ===")
    print(f"UE RunUAT:      {ue}")
    print(f"Project:        {project}")
    print(f"Project Root:   {project_root}")
    print(f"Plugin:         {args.plugin}")
    print(f"Plugin Root:    {plugin_root}")
    print(f"Map:            {args.map_path}")
    print(f"Release:        {args.release}")
    print(f"Workshop:       {workshop}")
    print(f"Preview:        {preview}")
    print(f"App ID:         {args.appid}")
    print(f"Published ID:   {args.publishedfileid}")
    print(f"Visibility:     {args.visibility}")

    if args.clean_workshop:
        clean_workshop_payload(workshop, preview)

    if not args.copy_only:
        if not args.skip_full_game:
            build_full_game(ue, project, project_root, args.release)
        else:
            print("\nSkipping Full Game build.")
        if not args.skip_mod:
            build_mod_dlc(
                ue, project, project_root, args.plugin, args.release, args.map_path
            )
        else:
            print("\nSkipping My Mod/DLC build.")
    else:
        print("\nCopy-only mode enabled. No build commands will run.")

    payload = discover_payload_fallback(
        project, args.plugin, find_expected_payload_paths(project, args.plugin)
    )

    print("\n=== Expected Payload Paths ===")
    print(f"Pak folder:      {payload['staged_paks']}")
    print(f"Cooked plugin:   {payload['cooked_plugin']}")
    print(f"Pak:             {payload['pak']}")
    print(f"UCAS:            {payload['ucas']}")
    print(f"UTOC:            {payload['utoc']}")
    print(f"AssetRegistry:   {payload['registry']}")

    try:
        checker = require_file if args.copy_only else (
            lambda p, label: require_fresh_file(p, label, build_started_at)
        )
        payload["pak"] = checker(payload["pak"], "mod .pak")
        payload["ucas"] = checker(payload["ucas"], "mod .ucas")
        payload["utoc"] = checker(payload["utoc"], "mod .utoc")
        payload["registry"] = checker(payload["registry"], "plugin AssetRegistry.bin")
    except Exception:
        print_recent_payload_candidates(project_root, args.plugin)
        raise

    preview_dst, _ = copy_payload_to_workshop(payload, workshop, preview)
    vdf_path = workshop / "my_item.vdf"
    write_vdf(
        vdf_path, args.appid, args.publishedfileid, workshop, preview_dst,
        args.title, args.description, args.changenote, args.visibility
    )

    print("\n=== Workshop Folder Ready ===")
    for file in sorted(workshop.iterdir()):
        if file.is_file():
            modified = datetime.fromtimestamp(file.stat().st_mtime)
            print(f"{modified:%Y-%m-%d %H:%M:%S}  {file.stat().st_size:>12,}  {file.name}")

    print("\nNext SteamCMD command:")
    print(f'workshop_build_item "{vdf_path}"')

    if args.upload:
        if not args.steamcmd:
            raise RuntimeError("--upload requires --steamcmd")
        steamcmd = require_file(Path(args.steamcmd), "steamcmd.exe")
        print("\n=== Uploading with SteamCMD ===")
        run_steamcmd(steamcmd, vdf_path, args.steam_login)

    print("\n=== DONE ===")



def launch_gui():
    import tkinter as tk
    from tkinter import filedialog, messagebox, scrolledtext, simpledialog, ttk

    try:
        from PIL import Image, ImageTk
        pillow_available = True
    except ImportError:
        Image = None
        ImageTk = None
        pillow_available = False

    class ToolTip:
        def __init__(self, widget, text):
            self.widget = widget
            self.text = text
            self.window = None
            widget.bind("<Enter>", self.show, add="+")
            widget.bind("<Leave>", self.hide, add="+")
            widget.bind("<ButtonPress>", self.hide, add="+")

        def show(self, _event=None):
            if self.window or not self.text:
                return
            x = self.widget.winfo_rootx() + 20
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
            self.window = tk.Toplevel(self.widget)
            self.window.wm_overrideredirect(True)
            self.window.wm_geometry(f"+{x}+{y}")
            tk.Label(
                self.window,
                text=self.text,
                justify="left",
                background="#fff7c7",
                foreground="#111111",
                relief="solid",
                borderwidth=1,
                padx=7,
                pady=5,
                wraplength=540,
            ).pack()

        def hide(self, _event=None):
            if self.window:
                self.window.destroy()
                self.window = None;
        window_icon_refs = {
            "photo": None,
        }


    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "Limbs.UniversalMecchaModBuilder.1"
        )
    except Exception:
        pass

    root = tk.Tk()
    root.title(f"Universal Meccha Mod Builder v{APP_VERSION}")

    interrupted_build_count = mark_interrupted_builds()


    def apply_window_icon():
        try:
            if WINDOW_ICON_PATH.is_file():
                root.iconbitmap(default=str(WINDOW_ICON_PATH.resolve()))
            else:
                print(f"ICO file does not exist: {WINDOW_ICON_PATH}")
        except Exception as exc:
            print(f"iconbitmap failed: {exc}")

    apply_window_icon()

    try:
        if WINDOW_ICON_PATH.exists():
            root.iconbitmap(default=str(WINDOW_ICON_PATH))
    except Exception as exc:
        print("Could not set initial window icon:", exc)

    branding_refs = {
    "window_icon": None,
    "header_logo": None,
}
    root.geometry("1060x760")
    root.minsize(820, 560)
    root.after_idle(apply_window_icon)
    root.after(250, apply_window_icon)

    PROFILES_DIR.mkdir(parents=True, exist_ok=True)

    style = ttk.Style(root)

    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    locals_ref = {}

    fields = {
        "ue": tk.StringVar(),
        "project": tk.StringVar(),
        "plugin": tk.StringVar(),
        "map": tk.StringVar(value="/Game/Mods/UserMap01/MyMap"),
        "release": tk.StringVar(value="1.0"),
        "workshop": tk.StringVar(),
        "preview": tk.StringVar(),
        "appid": tk.StringVar(value=MECCHA_APP_ID),
        "publishedfileid": tk.StringVar(value="0"),
        "visibility": tk.StringVar(value="2"),
        "title": tk.StringVar(value="My Custom Map"),
        "description": tk.StringVar(value="Custom map for Meccha Chameleon."),
        "changenote": tk.StringVar(value="Fresh UE 5.6.1 build"),
        "steamcmd": tk.StringVar(),
        "steam_login": tk.StringVar(),
        "theme": tk.StringVar(value="dark"),
    }

    flags = {
        "build_full": tk.BooleanVar(value=True),
        "build_mod": tk.BooleanVar(value=True),
        "copy_only": tk.BooleanVar(value=False),
        "clean_workshop": tk.BooleanVar(value=True),
        "upload": tk.BooleanVar(value=False),
    }

    hints = {
        "ue": r"Example: C:\Program Files\Epic Games\UE_5.6\Engine\Build\BatchFiles\RunUAT.bat",
        "project": r"Example: C:\MecchaCModKit_Load\MecchaCModKit_Load\MecchaCModKit_Load.uproject",
        "plugin": (
            "Exact plugin folder/.uplugin name containing this map's imported assets.\n"
            "Generic examples: MyMapUGC or CustomMapUGC.\n"
            "This value controls -dlcName and the package output location."
        ),
        "map": (
            "Unreal package path; no Windows path and no .umap extension.\n"
            "Known working Meccha example: /Game/Mods/UserMap01/MyMap"
        ),
        "workshop": r"Example: C:\Steam_Workshop\MyMapUGC",
        "preview": r"Example: C:\Steam_Workshop\MyMapUGC\preview.png",
        "profiles": f"Profiles are saved locally in:\n{PROFILES_DIR}",
        "publishedfileid": "0 creates a new item. An existing numeric ID updates that item.",
        "visibility": "0 = Public, 1 = Friends-only, 2 = Private.",
        "steamcmd": r"Example: C:\steamcmd\steamcmd.exe",
        "steam_login": "Example: username password. May be blank if SteamCMD is already logged in.",
        "clean_workshop": "Deletes old payload files before copying the fresh build.",
        "theme": "Switch between Dark and Light appearance.",
    }

    saved = load_json_file(
        SETTINGS_FILE,
        {
            "fields": {},
            "flags": {},
        },
    )

    for key, value in saved.get("fields", {}).items():
        if key in fields:
            fields[key].set(value)

    for key, value in saved.get("flags", {}).items():
        if key in flags:
            flags[key].set(bool(value))

    brand_image_ref = {"logo": None, "icon": None}

    COLORS = {
        "dark": {
            "bg": "#1f232a",
            "panel": "#2a2f38",
            "field": "#171a1f",
            "fg": "#f2f4f8",
            "muted": "#b9c0ca",
            "accent": "#4c8dff",
            "select": "#365f9d",
            "console_bg": "#0f1216",
            "console_fg": "#dbe7ff",
        },
        "light": {
            "bg": "#f2f3f5",
            "panel": "#ffffff",
            "field": "#ffffff",
            "fg": "#20242a",
            "muted": "#5f6874",
            "accent": "#2869c7",
            "select": "#b7d5ff",
            "console_bg": "#ffffff",
            "console_fg": "#1e2329",
        },
    }

    def apply_theme():
        mode = fields["theme"].get()
        c = COLORS.get(mode, COLORS["dark"])

        root.configure(background=c["bg"])
        style.configure(".", background=c["bg"], foreground=c["fg"])
        style.configure("TFrame", background=c["bg"])
        style.configure("TLabelframe", background=c["bg"], foreground=c["fg"])
        style.configure("TLabelframe.Label", background=c["bg"], foreground=c["fg"])
        style.configure("TLabel", background=c["bg"], foreground=c["fg"])
        style.configure("TButton", background=c["panel"], foreground=c["fg"], padding=5)
        style.map("TButton", background=[("active", c["accent"])])
        style.configure("TCheckbutton", background=c["bg"], foreground=c["fg"])
        style.map("TCheckbutton", background=[("active", c["bg"])])
        style.configure("TEntry", fieldbackground=c["field"], foreground=c["fg"])
        style.configure("TCombobox", fieldbackground=c["field"], foreground=c["fg"])
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", c["field"])],
            foreground=[("readonly", c["fg"])],
            selectbackground=[("readonly", c["select"])],
        )

        if "output_box" in locals_ref:
            locals_ref["output_box"].configure(
                background=c["console_bg"],
                foreground=c["console_fg"],
                insertbackground=c["fg"],
                selectbackground=c["select"],
            )

    def load_brand_image(path: Path, max_size):
        if not path.exists():
            return None

        if pillow_available:
            image = Image.open(path)
            image.thumbnail(max_size, Image.LANCZOS)
            return ImageTk.PhotoImage(image)

        image = tk.PhotoImage(file=str(path))
        factor = max(
            1,
            int(max(image.width() / max_size[0], image.height() / max_size[1]))
        )
        if factor > 1:
            image = image.subsample(factor, factor)
        return image

    icon_image_ref = {"image": None}
    header_image_ref = {"image": None}


    def apply_hardcoded_branding():
        try:
            if HEADER_LOGO_PATH.is_file():
                if pillow_available:
                    image = Image.open(HEADER_LOGO_PATH).convert("RGBA")
                    image.thumbnail((56, 56), Image.Resampling.LANCZOS)
                    header_photo = ImageTk.PhotoImage(image)
                else:
                    header_photo = tk.PhotoImage(
                        file=str(HEADER_LOGO_PATH.resolve())
                    )

                header_logo.configure(image=header_photo, text="")
                branding_refs["header_logo"] = header_photo
            else:
                print(f"Header logo not found: {HEADER_LOGO_PATH}")
        except Exception as exc:
            print(f"Could not apply header logo: {exc}")

    # The action bar is packed first at the bottom, so Build/Cancel stay visible
    # at every supported window size.
    action_host = ttk.Frame(root, padding=(10, 6))
    action_host.pack(side="bottom", fill="x")

    # All configuration/output content is scrollable.
    scroll_host = ttk.Frame(root)
    scroll_host.pack(side="top", fill="both", expand=True)

    canvas = tk.Canvas(scroll_host, highlightthickness=0, borderwidth=0)
    vertical_scroll = ttk.Scrollbar(scroll_host, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=vertical_scroll.set)

    vertical_scroll.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)

    outer = ttk.Frame(canvas, padding=10)
    canvas_window = canvas.create_window((0, 0), window=outer, anchor="nw")

    def update_scroll_region(_event=None):
        canvas.configure(scrollregion=canvas.bbox("all"))

    def match_canvas_width(event):
        canvas.itemconfigure(canvas_window, width=event.width)

    outer.bind("<Configure>", update_scroll_region)
    canvas.bind("<Configure>", match_canvas_width)

    def mousewheel(event):
        if event.delta:
            canvas.yview_scroll(int(-event.delta / 120), "units")

    canvas.bind_all("<MouseWheel>", mousewheel)

    header = ttk.Frame(outer)
    header.pack(fill="x", pady=(0, 8))

    header_logo = ttk.Label(
        header,
        text="MC",
        width=7,
        anchor="center",
        font=("Segoe UI", 14, "bold"),
    )
    header_logo.pack(side="left", padx=(0, 10))

    header_text = ttk.Frame(header)
    header_text.pack(side="left", fill="x", expand=True)

    ttk.Label(
        header_text,
        text="Universal Meccha Mod Builder",
        anchor="w",
        font=("Segoe UI", 16, "bold"),
    ).pack(fill="x")

    ttk.Label(
        header_text,
        text="Build, package, and publish custom Meccha Chameleon maps",
        anchor="w",
    ).pack(fill="x")

    form = ttk.LabelFrame(outer, text="Build configuration", padding=10)
    form.pack(fill="x")
    form.columnconfigure(1, weight=1)
    row = 0

    field_rows = {}

    def add_entry(label_text, key, browse=None):
        nonlocal row

        current_row = row
        widgets = []

        label = ttk.Label(form, text=label_text)
        label.grid(row=current_row, column=0, sticky="w", padx=(0, 8), pady=4)
        widgets.append(label)

        entry = ttk.Entry(form, textvariable=fields[key])
        entry.grid(row=current_row, column=1, sticky="ew", pady=4)
        widgets.append(entry)

        ToolTip(label, hints.get(key, ""))
        ToolTip(entry, hints.get(key, ""))

        if browse:
            button = ttk.Button(form, text="Browse…", command=browse)
            button.grid(row=current_row, column=2, padx=(8, 0), pady=4)
            ToolTip(button, hints.get(key, ""))
            widgets.append(button)

        field_rows[key] = widgets
        row += 1
        return entry

    def browse_ue():
        value = filedialog.askopenfilename(
            title="Select UE 5.6 RunUAT.bat",
            filetypes=[("RunUAT", "RunUAT.bat"), ("Batch", "*.bat"), ("All", "*.*")]
        )
        if value:
            fields["ue"].set(value)

    def browse_project():
        value = filedialog.askopenfilename(
            title="Select Meccha .uproject",
            filetypes=[("Unreal project", "*.uproject"), ("All", "*.*")]
        )
        if value:
            fields["project"].set(value)
            fields["plugin"].set("")
            refresh_plugins()

    def browse_workshop():
        value = filedialog.askdirectory(title="Select Workshop staging folder")
        if value:
            fields["workshop"].set(value)

    def browse_preview():
        value = filedialog.askopenfilename(
            title="Select preview image",
            filetypes=[("Images", "*.png *.jpg *.jpeg"), ("All", "*.*")]
        )
        if value:
            fields["preview"].set(value)

    def browse_steamcmd():
        value = filedialog.askopenfilename(
            title="Select steamcmd.exe",
            filetypes=[("SteamCMD", "steamcmd.exe"), ("Executables", "*.exe"), ("All", "*.*")]
        )
        if value:
            fields["steamcmd"].set(value)

    add_entry("UE RunUAT.bat", "ue", browse_ue)
    project_entry = add_entry("Meccha .uproject", "project", browse_project)

    plugin_label = ttk.Label(form, text="Asset plugin")
    plugin_label.grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)
    plugin_combo = ttk.Combobox(form, textvariable=fields["plugin"], state="readonly")
    plugin_combo.grid(row=row, column=1, sticky="ew", pady=4)
    refresh_button = ttk.Button(form, text="Refresh", command=lambda: refresh_plugins())
    refresh_button.grid(row=row, column=2, padx=(8, 0), pady=4)
    ToolTip(plugin_label, hints["plugin"])
    ToolTip(plugin_combo, hints["plugin"])
    row += 1

    add_entry("Runtime map path", "map")
    add_entry("Workshop folder", "workshop", browse_workshop)
    add_entry("Preview image", "preview", browse_preview)

    compact = ttk.Frame(form)
    compact.grid(row=row, column=0, columnspan=3, sticky="ew", pady=6)
    for i in range(8):
        compact.columnconfigure(i, weight=1)

    def small_field(col, label_text, key, values=None):
        label = ttk.Label(compact, text=label_text)
        label.grid(row=0, column=col * 2, sticky="w", padx=(0 if col == 0 else 12, 5))
        if values:
            widget = ttk.Combobox(
                compact, textvariable=fields[key], values=values,
                state="readonly", width=9
            )
        else:
            widget = ttk.Entry(compact, textvariable=fields[key], width=13)
        widget.grid(row=0, column=col * 2 + 1, sticky="ew")
        ToolTip(label, hints.get(key, ""))
        ToolTip(widget, hints.get(key, ""))

    small_field(0, "Release", "release")
    small_field(1, "App ID", "appid")
    small_field(2, "Published ID", "publishedfileid")
    small_field(3, "Visibility", "visibility", ["0", "1", "2"])
    row += 1

    add_entry("Workshop title", "title")
    add_entry("Description", "description")
    add_entry("Change note", "changenote")
    add_entry("SteamCMD.exe", "steamcmd", browse_steamcmd)
    add_entry("Steam login args", "steam_login")

    steam_login_warning = ttk.Label(
        form,
        text=(
            "LOCAL ONLY — OPTIONAL. Recommended: log in through SteamCMD beforehand, "
            "or upload the completed build manually with SteamCMD."
        ),
        foreground="#e05252",
        wraplength=720,
        justify="left",
    )

    steam_login_warning.grid(
        row=row,
        column=1,
        columnspan=2,
        sticky="w",
        pady=(0, 8),
    )

    row += 1

    def update_steamcmd_visibility():
        visible = flags["upload"].get()

        for key in ("steamcmd", "steam_login"):
            for widget in field_rows.get(key, []):
                if visible:
                    widget.grid()
                else:
                    widget.grid_remove()

        if visible:
            steam_login_warning.grid()
        else:
            steam_login_warning.grid_remove()

    theme_frame = ttk.Frame(form)
    theme_frame.grid(row=row, column=0, columnspan=3, sticky="w", pady=(4, 0))
    ttk.Label(theme_frame, text="Appearance").pack(side="left", padx=(0, 8))
    theme_combo = ttk.Combobox(
        theme_frame,
        textvariable=fields["theme"],
        values=["dark", "light"],
        width=10,
        state="readonly",
    )
    theme_combo.pack(side="left")
    theme_combo.bind("<<ComboboxSelected>>", lambda _e: apply_theme())
    ToolTip(theme_combo, hints["theme"])
    row += 1

    options = ttk.LabelFrame(outer, text="Build options", padding=8)
    options.pack(fill="x", pady=(10, 0))
    ttk.Checkbutton(options, text="Build Full Game", variable=flags["build_full"]).pack(side="left", padx=6)
    ttk.Checkbutton(options, text="Build My Mod / DLC", variable=flags["build_mod"]).pack(side="left", padx=6)
    ttk.Checkbutton(options, text="Copy only", variable=flags["copy_only"]).pack(side="left", padx=6)
    clean = ttk.Checkbutton(options, text="Clean Workshop first", variable=flags["clean_workshop"])
    clean.pack(side="left", padx=6)
    ToolTip(clean, hints["clean_workshop"])
    upload_checkbox = ttk.Checkbutton(
        options,
        text="Upload with SteamCMD",
        variable=flags["upload"],
        command=update_steamcmd_visibility,
    )

    upload_checkbox.pack(side="left", padx=6)

    profile_bar = ttk.LabelFrame(outer, text="Profiles", padding=8)
    profile_bar.pack(fill="x", pady=(8, 0))

    profile_var = tk.StringVar()
    profile_combo = ttk.Combobox(profile_bar, textvariable=profile_var, state="readonly", width=38)
    profile_combo.pack(side="left", padx=(0, 8))

    
    ToolTip(profile_combo, hints["profiles"])

    status_frame = ttk.Frame(outer)
    status_frame.pack(fill="x", pady=(10, 4))
    status_var = tk.StringVar(value="Ready")
    if interrupted_build_count:
        status_var.set(
            f"Recovered {interrupted_build_count} interrupted build record(s)"
        )

    ttk.Label(status_frame, textvariable=status_var).pack(side="left")
    progress = ttk.Progressbar(status_frame, mode="indeterminate", length=180)
    progress.pack(side="right")

    output_box = scrolledtext.ScrolledText(
        outer, height=12, wrap="word", font=("Consolas", 9), state="disabled"
    )
    output_box.pack(fill="both", expand=True)
    locals_ref["output_box"] = output_box

    buttons = action_host

    messages = queue.Queue()

    process_holder = {
        "process": None,
    }

    build_state = {
        "id": None,
        "log_path": None,
        "started_at": None,
        "cancel_requested": False,
        "record_active": False,
    }

    def redact_command_for_log(cmd: list[str]) -> list[str]:
        """
        Return a safe copy of the command with Steam credentials removed.
        """
        safe_cmd = [str(part) for part in cmd]

        for index, part in enumerate(safe_cmd):
            if part == "--steam-login" and index + 1 < len(safe_cmd):
                safe_cmd[index + 1] = "[REDACTED]"

        return safe_cmd

    def append_to_active_log(text: str) -> None:
        """Append text to the currently active build log."""
        log_path = build_state.get("log_path")

        if not build_state.get("record_active") or log_path is None:
            return

        try:
            Path(log_path).parent.mkdir(parents=True, exist_ok=True)

            with Path(log_path).open(
                "a",
                encoding="utf-8",
                errors="replace",
            ) as log_file:
                log_file.write(text)
                log_file.flush()

        except OSError as exc:
            # Avoid recursively calling log() here.
            print(f"Could not write build log '{log_path}': {exc}")

    def log(text):
        text = str(text)

        output_box.configure(state="normal")
        output_box.insert("end", text)
        output_box.see("end")
        output_box.configure(state="disabled")

        append_to_active_log(text)

    def create_build_snapshot() -> dict:
        """
        Capture the configuration used by a build.

        Steam login arguments are deliberately excluded.
        """
        return {
            "ue": fields["ue"].get().strip(),
            "project": fields["project"].get().strip(),
            "plugin": fields["plugin"].get().strip(),
            "map": fields["map"].get().strip(),
            "release": fields["release"].get().strip(),
            "workshop": fields["workshop"].get().strip(),
            "preview": fields["preview"].get().strip(),
            "appid": fields["appid"].get().strip(),
            "publishedfileid": fields["publishedfileid"].get().strip(),
            "visibility": fields["visibility"].get().strip(),
            "title": fields["title"].get(),
            "description": fields["description"].get(),
            "changenote": fields["changenote"].get(),
            "steamcmd": fields["steamcmd"].get().strip(),
            "flags": {
                key: bool(variable.get())
                for key, variable in flags.items()
            },
        }

    def begin_build_record(cmd: list[str]) -> Path:
        """Create the build-history record and its log file."""
        build_id = create_build_id()
        started_at = datetime.now().astimezone()

        plugin_name = fields["plugin"].get().strip() or "UnknownPlugin"
        safe_plugin_name = re.sub(
            r"[^A-Za-z0-9._-]+",
            "_",
            plugin_name,
        ).strip("._")

        if not safe_plugin_name:
            safe_plugin_name = "UnknownPlugin"

        log_filename = f"{build_id}_{safe_plugin_name}.log"
        log_path = BUILD_LOGS_DIR / log_filename

        build_state.update({
            "id": build_id,
            "log_path": log_path,
            "started_at": started_at,
            "cancel_requested": False,
            "record_active": True,
        })

        safe_command = redact_command_for_log(cmd)
        safe_command_text = subprocess.list2cmdline(safe_command)

        record = {
            "id": build_id,
            "app_version": APP_VERSION,
            "status": "running",
            "started_at": started_at.isoformat(timespec="seconds"),
            "finished_at": None,
            "duration_seconds": None,
            "exit_code": None,
            "error": "",
            "log_path": str(log_path),
            "command": safe_command_text,
            "configuration": create_build_snapshot(),
        }

        append_build_history_record(record)

        log_header = (
            "============================================================\n"
            f"{APP_NAME} Build Log\n"
            "============================================================\n"
            f"Build ID:       {build_id}\n"
            f"App Version:    {APP_VERSION}\n"
            f"Started:        {record['started_at']}\n"
            f"Plugin:         {record['configuration']['plugin']}\n"
            f"Map:            {record['configuration']['map']}\n"
            f"Release:        {record['configuration']['release']}\n"
            f"Workshop:       {record['configuration']['workshop']}\n"
            f"Published ID:   {record['configuration']['publishedfileid']}\n"
            "\n"
            "=== GUI COMMAND ===\n"
            f"{safe_command_text}\n\n"
        )

        append_to_active_log(log_header)

        return log_path

    def finish_build_record(
        status: str,
        exit_code: int | None = None,
        error: str = "",
    ) -> None:
        """Finish the active history record and close its logging lifecycle."""
        build_id = build_state.get("id")

        if not build_id or not build_state.get("record_active"):
            return

        finished_at = datetime.now().astimezone()
        duration_seconds = calculate_duration_seconds(
            build_state.get("started_at")
        )

        completion_text = (
            "\n"
            "============================================================\n"
            "BUILD FINISHED\n"
            "============================================================\n"
            f"Status:         {status}\n"
            f"Finished:       {finished_at.isoformat(timespec='seconds')}\n"
            f"Duration:       {format_duration(duration_seconds)}\n"
            f"Exit code:      "
            f"{exit_code if exit_code is not None else 'N/A'}\n"
        )

        if error:
            completion_text += f"Error:          {error}\n"

        append_to_active_log(completion_text)

        update_build_history_record(
            build_id,
            {
                "status": status,
                "finished_at": finished_at.isoformat(timespec="seconds"),
                "duration_seconds": duration_seconds,
                "exit_code": exit_code,
                "error": str(error),
            },
        )

        build_state["record_active"] = False

    def reset_active_build_state() -> None:
        """Clear transient build state after completion."""
        build_state.update({
            "id": None,
            "log_path": None,
            "started_at": None,
            "cancel_requested": False,
            "record_active": False,
        })

    def refresh_plugins():
        plugins = []
        project_text = fields["project"].get().strip()
        if project_text:
            plugin_dir = Path(project_text).parent / "Plugins"
            if plugin_dir.exists():
                plugins = sorted(
                    {p.stem for p in plugin_dir.glob("*/*.uplugin")},
                    key=str.lower
                )
        plugin_combo["values"] = plugins
        # Do not silently choose a plugin. Wrong plugin = wrong DLC output.
        if fields["plugin"].get() not in plugins:
            fields["plugin"].set("")
        status_var.set(f"Found {len(plugins)} plugin(s); select the asset plugin")

    def profile_payload():
        return {
            "fields": {k: v.get() for k, v in fields.items()},
            "flags": {k: v.get() for k, v in flags.items()},
        }

    def refresh_profiles():
        names = sorted(p.stem for p in PROFILES_DIR.glob("*.json"))
        profile_combo["values"] = names
        if profile_var.get() not in names:
            profile_var.set(names[0] if names else "")

    def save_profile():
        name = simpledialog.askstring("Save profile", "Profile name:")
        if not name:
            return
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
        if not safe:
            messagebox.showerror("Profile", "Profile name is invalid.")
            return
        path = PROFILES_DIR / f"{safe}.json"
        save_json_file(path, profile_payload())
        refresh_profiles()
        profile_var.set(safe)
        status_var.set(f"Saved profile: {safe}")

    def load_profile():
        name = profile_var.get().strip()
        if not name:
            messagebox.showwarning("Profiles", "Select a profile first.")
            return
        path = PROFILES_DIR / f"{name}.json"
        data = load_json_file(
            path,
            {
                "fields": {},
                "flags": {},
            },
        )
        for key, value in data.get("fields", {}).items():
            if key in fields:
                fields[key].set(value)
        for key, value in data.get("flags", {}).items():
            if key in flags:
                flags[key].set(bool(value))
        refresh_plugins()
        # Reapply plugin after refresh, provided it exists.
        wanted_plugin = data.get("fields", {}).get("plugin", "")
        if wanted_plugin in plugin_combo["values"]:
            fields["plugin"].set(wanted_plugin)
        apply_theme()
        update_steamcmd_visibility()
        status_var.set(f"Loaded profile: {name}")

    def delete_profile():
        name = profile_var.get().strip()
        if not name:
            return
        if messagebox.askyesno("Delete profile", f"Delete profile '{name}'?"):
            (PROFILES_DIR / f"{name}.json").unlink(missing_ok=True)
            refresh_profiles()

    ttk.Button(profile_bar, text="Save Current", command=save_profile).pack(side="left", padx=4)
    ttk.Button(profile_bar, text="Load", command=load_profile).pack(side="left", padx=4)
    ttk.Button(profile_bar, text="Delete", command=delete_profile).pack(side="left", padx=4)
    open_profiles_button = ttk.Button(
        profile_bar,
        text="Open Local Profiles Folder",
        command=lambda: os.startfile(PROFILES_DIR),
    )

    open_profiles_button.pack(side="left", padx=4)

    ToolTip(open_profiles_button, hints["profiles"])

    def save_settings():
        save_json_file(
            SETTINGS_FILE,
            profile_payload(),
        )

    def collect_preflight_results():
        results = []

        ue_text = fields["ue"].get().strip()
        project_text = fields["project"].get().strip()
        plugin_name = fields["plugin"].get().strip()
        map_path = fields["map"].get().strip()
        workshop_text = fields["workshop"].get().strip()
        preview_text = fields["preview"].get().strip()
        appid = fields["appid"].get().strip()
        publishedfileid = fields["publishedfileid"].get().strip()
        release = fields["release"].get().strip()

        # ---------------------------------------------------------
        # Unreal Engine / RunUAT
        # ---------------------------------------------------------
        if not ue_text:
            results.append(validation_result(
                "error",
                "Unreal Automation Tool path is missing",
                "Select UE 5.6 RunUAT.bat.",
            ))
        else:
            ue_path = Path(ue_text).expanduser()

            if not ue_path.is_file():
                results.append(validation_result(
                    "error",
                    "Unreal Automation Tool was not found",
                    str(ue_path),
                ))
            elif ue_path.name.lower() != "runuat.bat":
                results.append(validation_result(
                    "warning",
                    "Selected Unreal tool is not named RunUAT.bat",
                    str(ue_path),
                ))
            else:
                unreal_version = detect_unreal_version(ue_path)

                if unreal_version:
                    level = "pass" if unreal_version.startswith("5.6") else "warning"

                    results.append(validation_result(
                        level,
                        f"Unreal Engine {unreal_version} found",
                        str(ue_path),
                    ))

                    if not unreal_version.startswith("5.6"):
                        results.append(validation_result(
                            "warning",
                            "The Meccha Mod Kit expects Unreal Engine 5.6",
                            f"Selected installation appears to be Unreal Engine {unreal_version}.",
                        ))
                else:
                    results.append(validation_result(
                        "pass",
                        "Unreal Automation Tool found",
                        str(ue_path),
                    ))

                    results.append(validation_result(
                        "warning",
                        "Unreal version could not be identified from the path",
                        "Confirm that this RunUAT.bat belongs to Unreal Engine 5.6.",
                    ))

        # ---------------------------------------------------------
        # Unreal project
        # ---------------------------------------------------------
        project = None

        if not project_text:
            results.append(validation_result(
                "error",
                "Meccha project path is missing",
                "Select the Meccha .uproject file.",
            ))
        else:
            project = Path(project_text).expanduser()

            if not project.is_file():
                results.append(validation_result(
                    "error",
                    "Meccha project was not found",
                    str(project),
                ))
                project = None

            elif project.suffix.lower() != ".uproject":
                results.append(validation_result(
                    "error",
                    "Selected project is not a .uproject file",
                    str(project),
                ))
                project = None

            else:
                project_data, project_error = inspect_json_descriptor(project)

                if project_error:
                    results.append(validation_result(
                        "error",
                        "The .uproject descriptor is invalid",
                        project_error,
                    ))
                else:
                    results.append(validation_result(
                        "pass",
                        "Meccha project found",
                        str(project),
                    ))

                    engine_association = str(
                        project_data.get("EngineAssociation", "")
                    ).strip()

                    if engine_association:
                        results.append(validation_result(
                            "pass",
                            f"Project EngineAssociation: {engine_association}",
                        ))
                    else:
                        results.append(validation_result(
                            "warning",
                            "The project has no EngineAssociation value",
                            "This may be intentional for a source-built Unreal project.",
                        ))

        # ---------------------------------------------------------
        # Plugin
        # ---------------------------------------------------------
        plugin_root = None
        plugin_descriptor = None

        if not plugin_name:
            results.append(validation_result(
                "error",
                "Asset plugin is not selected",
                "Select the plugin containing the map assets.",
            ))

        elif project is not None:
            plugin_root = project.parent / "Plugins" / plugin_name

            if not plugin_root.is_dir():
                results.append(validation_result(
                    "error",
                    "Plugin folder was not found",
                    str(plugin_root),
                ))
            else:
                descriptors = sorted(plugin_root.glob("*.uplugin"))

                if not descriptors:
                    results.append(validation_result(
                        "error",
                        "Plugin descriptor was not found",
                        f"No .uplugin file exists in:\n{plugin_root}",
                    ))

                elif len(descriptors) > 1:
                    results.append(validation_result(
                        "warning",
                        "Multiple .uplugin descriptors were found",
                        "\n".join(str(path) for path in descriptors),
                    ))
                    plugin_descriptor = descriptors[0]

                else:
                    plugin_descriptor = descriptors[0]

                if plugin_descriptor is not None:
                    plugin_data, plugin_error = inspect_json_descriptor(
                        plugin_descriptor
                    )

                    if plugin_error:
                        results.append(validation_result(
                            "error",
                            "Plugin descriptor contains invalid JSON",
                            plugin_error,
                        ))
                    else:
                        results.append(validation_result(
                            "pass",
                            f"Plugin found: {plugin_name}",
                            str(plugin_root),
                        ))

                        if plugin_descriptor.stem != plugin_name:
                            results.append(validation_result(
                                "warning",
                                "Plugin folder and descriptor names differ",
                                (
                                    f"Folder: {plugin_name}\n"
                                    f"Descriptor: {plugin_descriptor.name}"
                                ),
                            ))
                        else:
                            results.append(validation_result(
                                "pass",
                                "Plugin folder and descriptor names match",
                                plugin_descriptor.name,
                            ))

                        can_contain_content = plugin_data.get(
                            "CanContainContent",
                            False,
                        )

                        if can_contain_content is True:
                            results.append(validation_result(
                                "pass",
                                "Plugin allows content",
                                "CanContainContent is enabled.",
                            ))
                        else:
                            results.append(validation_result(
                                "error",
                                "Plugin does not allow content",
                                (
                                    "CanContainContent is false or missing in the "
                                    ".uplugin descriptor."
                                ),
                            ))

        # ---------------------------------------------------------
        # Runtime map
        # ---------------------------------------------------------
        map_format_valid = True

        if not map_path:
            results.append(validation_result(
                "error",
                "Runtime map path is missing",
                "Example: /Game/Mods/UserMap01/MyMap",
            ))
            map_format_valid = False

        else:
            if not map_path.startswith("/"):
                results.append(validation_result(
                    "error",
                    "Runtime map path must begin with '/'",
                    map_path,
                ))
                map_format_valid = False

            if map_path.lower().endswith(".umap"):
                results.append(validation_result(
                    "error",
                    "Remove the .umap extension from the runtime map path",
                    map_path,
                ))
                map_format_valid = False

            map_leaf = map_path.rstrip("/").rsplit("/", 1)[-1]

            if "." in map_leaf:
                results.append(validation_result(
                    "error",
                    "Use a package path rather than Object.Object syntax",
                    map_path,
                ))
                map_format_valid = False

            if map_format_valid:
                if map_path.startswith("/Game/Mods/UserMap01/"):
                    results.append(validation_result(
                        "pass",
                        "Runtime map path uses Meccha's expected folder",
                        map_path,
                    ))
                else:
                    results.append(validation_result(
                        "warning",
                        "Runtime map path uses an unusual folder",
                        (
                            f"{map_path}\n\n"
                            "Known working Meccha location:\n"
                            "/Game/Mods/UserMap01/MapName"
                        ),
                    ))

                if project is not None and plugin_name:
                    map_candidates = find_map_candidates(
                        project,
                        plugin_name,
                        map_path,
                    )

                    if map_candidates:
                        shown_candidates = map_candidates[:5]
                        details = "\n".join(str(path) for path in shown_candidates)

                        if len(map_candidates) > len(shown_candidates):
                            details += (
                                f"\n...and "
                                f"{len(map_candidates) - len(shown_candidates)} more"
                            )

                        results.append(validation_result(
                            "pass",
                            "Matching .umap file found",
                            details,
                        ))
                    else:
                        results.append(validation_result(
                            "warning",
                            "No matching .umap filename was found",
                            (
                                "The build may still work if Meccha remaps or copies "
                                "the map to its runtime path.\n\n"
                                f"Searched for: {map_leaf}.umap"
                            ),
                        ))

        # ---------------------------------------------------------
        # Release
        # ---------------------------------------------------------
        if not release:
            results.append(validation_result(
                "error",
                "Release version is missing",
            ))
        elif not re.fullmatch(r"\d+(?:\.\d+)*", release):
            results.append(validation_result(
                "warning",
                "Release version uses an unusual format",
                release,
            ))
        else:
            results.append(validation_result(
                "pass",
                f"Release version is valid: {release}",
            ))

        # ---------------------------------------------------------
        # Workshop directory
        # ---------------------------------------------------------
        if not workshop_text:
            results.append(validation_result(
                "error",
                "Workshop folder is missing",
                "Select the staging folder for the Workshop payload.",
            ))
        else:
            workshop = Path(workshop_text).expanduser()

            if workshop.exists():
                if not workshop.is_dir():
                    results.append(validation_result(
                        "error",
                        "Workshop path is not a directory",
                        str(workshop),
                    ))
                elif not os.access(workshop, os.W_OK):
                    results.append(validation_result(
                        "error",
                        "Workshop folder is not writable",
                        str(workshop),
                    ))
                else:
                    results.append(validation_result(
                        "pass",
                        "Workshop folder is writable",
                        str(workshop),
                    ))
            else:
                existing_parent = workshop.parent

                while (
                    not existing_parent.exists()
                    and existing_parent != existing_parent.parent
                ):
                    existing_parent = existing_parent.parent

                if (
                    existing_parent.is_dir()
                    and os.access(existing_parent, os.W_OK)
                ):
                    results.append(validation_result(
                        "warning",
                        "Workshop folder does not exist yet",
                        (
                            f"{workshop}\n\n"
                            "The folder will be created when the build starts."
                        ),
                    ))
                else:
                    results.append(validation_result(
                        "error",
                        "Workshop folder cannot be created",
                        (
                            f"Target: {workshop}\n"
                            f"Nearest existing parent: {existing_parent}"
                        ),
                    ))

        # ---------------------------------------------------------
        # Preview image
        # ---------------------------------------------------------
        if not preview_text:
            results.append(validation_result(
                "error",
                "Workshop preview image is missing",
            ))
        else:
            preview = Path(preview_text).expanduser()

            if not preview.is_file():
                results.append(validation_result(
                    "error",
                    "Workshop preview image was not found",
                    str(preview),
                ))
            elif preview.suffix.lower() not in {
                ".png",
                ".jpg",
                ".jpeg",
                ".webp",
            }:
                results.append(validation_result(
                    "warning",
                    "Preview image uses an unusual format",
                    (
                        f"{preview.suffix or 'No extension'}\n"
                        "PNG, JPG, JPEG, or WEBP is recommended."
                    ),
                ))
            else:
                try:
                    size_bytes = preview.stat().st_size

                    if size_bytes <= 0:
                        results.append(validation_result(
                            "error",
                            "Preview image is empty",
                            str(preview),
                        ))
                    else:
                        results.append(validation_result(
                            "pass",
                            "Workshop preview image found",
                            (
                                f"{preview}\n"
                                f"Size: {size_bytes:,} bytes"
                            ),
                        ))
                except OSError as exc:
                    results.append(validation_result(
                        "error",
                        "Preview image could not be inspected",
                        str(exc),
                    ))

        # ---------------------------------------------------------
        # Steam Workshop identifiers
        # ---------------------------------------------------------
        if not appid:
            results.append(validation_result(
                "error",
                "Steam App ID is missing",
            ))
        elif not appid.isdigit():
            results.append(validation_result(
                "error",
                "Steam App ID must be numeric",
                appid,
            ))
        elif appid != MECCHA_APP_ID:
            results.append(validation_result(
                "warning",
                "Steam App ID differs from Meccha Chameleon",
                (
                    f"Selected: {appid}\n"
                    f"Expected: {MECCHA_APP_ID}"
                ),
            ))
        else:
            results.append(validation_result(
                "pass",
                f"Meccha Steam App ID confirmed: {appid}",
            ))

        if not publishedfileid:
            results.append(validation_result(
                "error",
                "Published File ID is missing",
            ))
        elif not publishedfileid.isdigit():
            results.append(validation_result(
                "error",
                "Published File ID must be numeric",
                publishedfileid,
            ))
        elif publishedfileid == "0":
            results.append(validation_result(
                "warning",
                "Published File ID is 0",
                "SteamCMD will create a new Workshop item.",
            ))
        else:
            results.append(validation_result(
                "pass",
                "Existing Workshop item will be updated",
                f"Published File ID: {publishedfileid}",
            ))

        # ---------------------------------------------------------
        # Build options
        # ---------------------------------------------------------
        if (
            not flags["copy_only"].get()
            and not flags["build_full"].get()
            and not flags["build_mod"].get()
        ):
            results.append(validation_result(
                "error",
                "No build operation is selected",
                (
                    "Enable Build Full Game, Build My Mod / DLC, "
                    "or choose Copy only."
                ),
            ))
        elif flags["copy_only"].get():
            results.append(validation_result(
                "warning",
                "Copy-only mode is enabled",
                "No Unreal build commands will run.",
            ))
        else:
            if flags["build_full"].get():
                results.append(validation_result(
                    "pass",
                    "Full-game build is enabled",
                ))
            else:
                results.append(validation_result(
                    "warning",
                    "Full-game build will be skipped",
                ))

            if flags["build_mod"].get():
                results.append(validation_result(
                    "pass",
                    "My Mod / DLC build is enabled",
                ))
            else:
                results.append(validation_result(
                    "warning",
                    "My Mod / DLC build will be skipped",
                ))

        # ---------------------------------------------------------
        # SteamCMD upload
        # ---------------------------------------------------------
        if flags["upload"].get():
            steamcmd_text = fields["steamcmd"].get().strip()

            if not steamcmd_text:
                results.append(validation_result(
                    "error",
                    "SteamCMD is required because upload is enabled",
                ))
            else:
                steamcmd = Path(steamcmd_text).expanduser()

                if not steamcmd.is_file():
                    results.append(validation_result(
                        "error",
                        "SteamCMD was not found",
                        str(steamcmd),
                    ))
                elif steamcmd.name.lower() != "steamcmd.exe":
                    results.append(validation_result(
                        "warning",
                        "Selected upload executable is not named steamcmd.exe",
                        str(steamcmd),
                    ))
                else:
                    results.append(validation_result(
                        "pass",
                        "SteamCMD found",
                        str(steamcmd),
                    ))

            if fields["steam_login"].get().strip():
                results.append(validation_result(
                    "warning",
                    "Steam login arguments are populated",
                    (
                        "Credentials may be visible in process arguments and logs.\n"
                        "Using an existing SteamCMD login is recommended."
                    ),
                ))
            else:
                results.append(validation_result(
                    "pass",
                    "No Steam credentials are stored in the build command",
                ))
        else:
            results.append(validation_result(
                "pass",
                "Automatic SteamCMD upload is disabled",
                "The Workshop payload will be prepared locally.",
            ))
        # ---------------------------------------------------------
        # Running Unreal Editor
        # ---------------------------------------------------------
        running_unreal_processes = find_running_unreal_processes()

        if running_unreal_processes:
            results.append(validation_result(
                "warning",
                "Unreal Editor is currently running",
                (
                    "Detected process(es):\n"
                    + "\n".join(
                        f"• {process_name}"
                        for process_name in running_unreal_processes
                    )
                    + "\n\nSave all assets before building. Closing Unreal "
                    "Editor is recommended before cooking or packaging."
                ),
            ))
        else:
            results.append(validation_result(
                "pass",
                "Unreal Editor is not running",
            ))

        # ---------------------------------------------------------
        # Possible Unreal autosave or recovery files
        # ---------------------------------------------------------
        if project is not None:
            recovery_files = find_recent_unreal_recovery_files(
                project,
                plugin_name,
            )

            if recovery_files:
                shown_files = recovery_files[:8]

                recovery_details = [
                    (
                        f"• {path.name} — {describe_file_age(path)}\n"
                        f"  {path}"
                    )
                    for path in shown_files
                ]

                if len(recovery_files) > len(shown_files):
                    recovery_details.append(
                        f"...and {len(recovery_files) - len(shown_files)} more"
                    )

                results.append(validation_result(
                    "warning",
                    "Potential Unreal recovery or autosave files were found",
                    (
                        "This does not necessarily mean assets are currently "
                        "unsaved. Save all work in Unreal before building.\n\n"
                        + "\n".join(recovery_details)
                    ),
                ))
            else:
                results.append(validation_result(
                    "pass",
                    "No Unreal autosave or recovery files were found",
                    (
                        "No recovery files were found in the project's standard "
                        "Saved\\Autosaves or Saved\\Backup folders."
                    ),
                ))

        return results

    def show_preflight_report(results):
        counts = count_validation_results(results)

        decision = {
            "approved": False,
        }

        report_window = tk.Toplevel(root)
        report_window.title("Build Validation Report")
        report_window.geometry("820x680")
        report_window.minsize(680, 480)
        report_window.transient(root)
        report_window.grab_set()

        try:
            if WINDOW_ICON_PATH.is_file():
                report_window.iconbitmap(
                    default=str(WINDOW_ICON_PATH.resolve())
                )
        except Exception:
            pass

        header_frame = ttk.Frame(report_window, padding=(14, 12))
        header_frame.pack(fill="x")

        ttk.Label(
            header_frame,
            text="Build Validation Report",
            font=("Segoe UI", 16, "bold"),
        ).pack(anchor="w")

        summary_text = (
            f"{counts['pass']} passed    "
            f"{counts['warning']} warning(s)    "
            f"{counts['error']} error(s)"
        )

        ttk.Label(
            header_frame,
            text=summary_text,
        ).pack(anchor="w", pady=(4, 0))

        if counts["error"]:
            readiness_text = (
                "Build blocked — resolve all errors before continuing."
            )
        elif counts["warning"]:
            readiness_text = (
                "Ready with warnings — review them before continuing."
            )
        else:
            readiness_text = "Ready to build."

        readiness_label = ttk.Label(
            header_frame,
            text=readiness_text,
            font=("Segoe UI", 10, "bold"),
        )
        readiness_label.pack(anchor="w", pady=(8, 0))

        report_box = scrolledtext.ScrolledText(
            report_window,
            wrap="word",
            font=("Segoe UI", 10),
            padx=12,
            pady=10,
            state="normal",
        )
        report_box.pack(
            fill="both",
            expand=True,
            padx=14,
            pady=(0, 10),
        )

        report_box.tag_configure(
            "pass",
            foreground="#2f9e44",
            font=("Segoe UI", 10, "bold"),
        )
        report_box.tag_configure(
            "warning",
            foreground="#d58b00",
            font=("Segoe UI", 10, "bold"),
        )
        report_box.tag_configure(
            "error",
            foreground="#d64545",
            font=("Segoe UI", 10, "bold"),
        )
        report_box.tag_configure(
            "details",
            lmargin1=28,
            lmargin2=28,
            spacing3=8,
        )

        symbols = {
            "pass": "✓",
            "warning": "⚠",
            "error": "✖",
        }

        for result in results:
            level = result["level"]
            symbol = symbols[level]

            report_box.insert(
                "end",
                f"{symbol} {result['title']}\n",
                level,
            )

            if result["details"]:
                report_box.insert(
                    "end",
                    f"{result['details']}\n",
                    "details",
                )

            report_box.insert("end", "\n")

        report_box.insert("end", "-" * 64 + "\n\n")

        if counts["error"]:
            report_box.insert(
                "end",
                "NOT READY — fix the blocking errors and validate again.\n",
                "error",
            )
        elif counts["warning"]:
            report_box.insert(
                "end",
                "READY WITH WARNINGS\n",
                "warning",
            )
        else:
            report_box.insert(
                "end",
                "READY TO BUILD\n",
                "pass",
            )

        report_box.configure(state="disabled")

        button_frame = ttk.Frame(report_window, padding=(14, 0, 14, 14))
        button_frame.pack(fill="x")

        def cancel():
            decision["approved"] = False
            report_window.destroy()

        def approve():
            decision["approved"] = True
            report_window.destroy()

        ttk.Button(
            button_frame,
            text="Cancel",
            command=cancel,
        ).pack(side="right")

        if counts["error"] == 0 and counts["warning"] > 0:
            ttk.Button(
                button_frame,
                text="Continue Anyway",
                command=approve,
            ).pack(side="right", padx=(0, 8))

        if counts["error"] == 0 and counts["warning"] == 0:
            ttk.Button(
                button_frame,
                text="Start Build",
                command=approve,
            ).pack(side="right", padx=(0, 8))

        if counts["error"] > 0:
            ttk.Button(
                button_frame,
                text="Fix Errors and Recheck",
                command=cancel,
            ).pack(side="right", padx=(0, 8))

        report_window.protocol("WM_DELETE_WINDOW", cancel)
        report_window.wait_window()

        return decision["approved"]

    def validate_only():
        results = collect_preflight_results()
        show_preflight_report(results)

    def build_command():
        if getattr(sys, "frozen", False):
            # Running as the packaged PyInstaller executable.
            cmd = [sys.executable]
        else:
            # Running directly from the Python source file.
            cmd = [
                sys.executable,
                str(Path(__file__).resolve()),
            ]

        cmd.extend([
            "--ue", fields["ue"].get().strip(),
            "--project", fields["project"].get().strip(),
            "--plugin", fields["plugin"].get().strip(),
            "--map", fields["map"].get().strip(),
            "--release", fields["release"].get().strip(),
            "--workshop", fields["workshop"].get().strip(),
            "--preview", fields["preview"].get().strip(),
            "--appid", fields["appid"].get().strip(),
            "--publishedfileid", fields["publishedfileid"].get().strip(),
            "--visibility", fields["visibility"].get().strip(),
            "--title", fields["title"].get(),
            "--description", fields["description"].get(),
            "--changenote", fields["changenote"].get(),
        ])

        if not flags["build_full"].get():
            cmd.append("--skip-full-game")

        if not flags["build_mod"].get():
            cmd.append("--skip-mod")

        if flags["copy_only"].get():
            cmd.append("--copy-only")

        if flags["clean_workshop"].get():
            cmd.append("--clean-workshop")

        if flags["upload"].get():
            cmd.extend([
                "--upload",
                "--steamcmd",
                fields["steamcmd"].get().strip(),
            ])

            if fields["steam_login"].get().strip():
                cmd.extend([
                    "--steam-login",
                    fields["steam_login"].get().strip(),
                ])

        return cmd

    def reader_thread(process):
        try:
            for line in iter(process.stdout.readline, ""):
                messages.put(("log", line))
            messages.put(("done", process.wait()))
        except Exception as exc:
            messages.put(("error", str(exc)))

    def start_build():
        results = collect_preflight_results()

        if not show_preflight_report(results):
            status_var.set("Build cancelled during validation")
            return

        save_settings()

        output_box.configure(state="normal")
        output_box.delete("1.0", "end")
        output_box.configure(state="disabled")

        cmd = build_command()
        log_path = begin_build_record(cmd)

        # Display the same safe header already written to the persistent log.
        safe_command = redact_command_for_log(cmd)

        log(
            "=== BUILD HISTORY ===\n"
            f"Build ID: {build_state['id']}\n"
            f"Log file: {log_path}\n\n"
            "=== GUI COMMAND ===\n"
            f"{subprocess.list2cmdline(safe_command)}\n\n"
        )

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
            )

        except Exception as exc:
            error_text = str(exc)

            finish_build_record(
                status="launch_error",
                exit_code=None,
                error=error_text,
            )

            reset_active_build_state()

            messagebox.showerror(
                "Failed to start",
                error_text,
            )
            return

        process_holder["process"] = process
        build_button.configure(state="disabled")
        validate_button.configure(state="disabled")
        cancel_button.configure(state="normal")
        progress.start(10)
        status_var.set("Building…")
        threading.Thread(target=reader_thread, args=(process,), daemon=True).start()

    def close_application():
        process = process_holder.get("process")

        if process and process.poll() is None:
            should_close = messagebox.askyesno(
                "Build in progress",
                (
                    "A build is currently running.\n\n"
                    "Closing the application will terminate it and mark the "
                    "build as cancelled.\n\n"
                    "Close anyway?"
                ),
            )

            if not should_close:
                return

            build_state["cancel_requested"] = True

            try:
                process.terminate()
            except Exception:
                pass

            finish_build_record(
                status="cancelled",
                exit_code=None,
                error="Application closed while the build was running.",
            )

        root.destroy()

    def cancel_build():
        process = process_holder["process"]

        if process and process.poll() is None:
            build_state["cancel_requested"] = True

            log(
                "\n=== CANCELLATION REQUESTED ===\n"
                f"{current_local_timestamp()}\n\n"
            )

            try:
                process.terminate()
                status_var.set("Stopping…")
                cancel_button.configure(state="disabled")

            except Exception as exc:
                build_state["cancel_requested"] = False
                log(f"Could not terminate build process: {exc}\n")

                messagebox.showerror(
                    "Cancel build",
                    f"Could not stop the build:\n\n{exc}",
                )

    def poll_queue():
        try:
            while True:
                kind, value = messages.get_nowait()
                if kind == "log":
                    log(value)
                elif kind == "done":
                    progress.stop()
                    build_button.configure(state="normal")
                    validate_button.configure(state="normal")
                    cancel_button.configure(state="disabled")
                    process_holder["process"] = None

                    was_cancelled = bool(
                        build_state.get("cancel_requested")
                    )

                    if was_cancelled:
                        finish_build_record(
                            status="cancelled",
                            exit_code=value,
                        )

                        status_var.set("Build cancelled")

                        messagebox.showwarning(
                            "Meccha builder",
                            "The build was cancelled.\n\n"
                            f"Log saved to:\n{build_state['log_path']}",
                        )

                    elif value == 0:
                        finish_build_record(
                            status="success",
                            exit_code=value,
                        )

                        status_var.set(
                            "Build completed successfully"
                        )

                        messagebox.showinfo(
                            "Meccha builder",
                            "Build completed successfully.\n\n"
                            f"Log saved to:\n{build_state['log_path']}",
                        )

                    else:
                        finish_build_record(
                            status="failed",
                            exit_code=value,
                            error=f"Process exited with code {value}",
                        )

                        status_var.set(
                            f"Build failed with exit code {value}"
                        )

                        messagebox.showerror(
                            "Meccha builder",
                            f"Build failed with exit code {value}.\n"
                            "Review the log.\n\n"
                            f"Log saved to:\n{build_state['log_path']}",
                        )

                    reset_active_build_state()

                elif kind == "error":
                    progress.stop()
                    build_button.configure(state="normal")
                    validate_button.configure(state="normal")
                    cancel_button.configure(state="disabled")
                    process_holder["process"] = None

                    error_text = str(value)
                    log_path = build_state.get("log_path")

                    finish_build_record(
                        status="failed",
                        exit_code=None,
                        error=error_text,
                    )

                    status_var.set("Build failed")

                    messagebox.showerror(
                        "Meccha builder",
                        f"{error_text}\n\n"
                        f"Log saved to:\n{log_path}",
                    )

                    reset_active_build_state()

        except queue.Empty:
            pass
        root.after(100, poll_queue)

    def open_path_in_windows(path: Path) -> None:
        """Open a file or folder using the Windows shell."""
        path = Path(path).expanduser()

        if not path.exists():
            messagebox.showwarning(
                "Open path",
                f"The path does not exist:\n\n{path}",
            )
            return

        try:
            os.startfile(str(path))
        except Exception as exc:
            messagebox.showerror(
                "Open path",
                f"Could not open:\n{path}\n\n{exc}",
            )

    def show_build_history():
        history_window = tk.Toplevel(root)
        history_window.title("Build History")
        history_window.geometry("1050x560")
        history_window.minsize(820, 420)
        history_window.transient(root)

        try:
            if WINDOW_ICON_PATH.is_file():
                history_window.iconbitmap(
                    default=str(WINDOW_ICON_PATH.resolve())
                )
        except Exception:
            pass

        header = ttk.Frame(
            history_window,
            padding=(12, 12, 12, 6),
        )
        header.pack(fill="x")

        ttk.Label(
            header,
            text="Build History",
            font=("Segoe UI", 16, "bold"),
        ).pack(side="left")

        history_count_var = tk.StringVar()
        ttk.Label(
            header,
            textvariable=history_count_var,
        ).pack(side="right")

        table_frame = ttk.Frame(
            history_window,
            padding=(12, 6),
        )
        table_frame.pack(fill="both", expand=True)

        columns = (
            "started",
            "status",
            "plugin",
            "release",
            "duration",
            "exit_code",
        )

        tree = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            selectmode="browse",
        )

        tree.heading("started", text="Started")
        tree.heading("status", text="Status")
        tree.heading("plugin", text="Plugin")
        tree.heading("release", text="Release")
        tree.heading("duration", text="Duration")
        tree.heading("exit_code", text="Exit Code")

        tree.column("started", width=190, anchor="w")
        tree.column("status", width=100, anchor="center")
        tree.column("plugin", width=220, anchor="w")
        tree.column("release", width=90, anchor="center")
        tree.column("duration", width=100, anchor="center")
        tree.column("exit_code", width=85, anchor="center")

        scrollbar = ttk.Scrollbar(
            table_frame,
            orient="vertical",
            command=tree.yview,
        )
        tree.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        tree.pack(side="left", fill="both", expand=True)

        record_lookup = {}

        def refresh_history_table():
            tree.delete(*tree.get_children())
            record_lookup.clear()

            records = load_build_history()
            newest_first = list(reversed(records))

            for record in newest_first:
                build_id = str(record.get("id", ""))

                if not build_id:
                    continue

                configuration = record.get("configuration", {})

                if not isinstance(configuration, dict):
                    configuration = {}

                started = str(record.get("started_at", ""))
                started_display = started.replace("T", " ")[:19]

                exit_code = record.get("exit_code")

                if exit_code is None:
                    exit_code_display = "—"
                else:
                    exit_code_display = str(exit_code)

                tree.insert(
                    "",
                    "end",
                    iid=build_id,
                    values=(
                        started_display,
                        str(record.get("status", "unknown")).title(),
                        configuration.get("plugin", ""),
                        configuration.get("release", ""),
                        format_duration(
                            record.get("duration_seconds")
                        ),
                        exit_code_display,
                    ),
                )

                record_lookup[build_id] = record

            history_count_var.set(
                f"{len(record_lookup)} build(s)"
            )

        def selected_record() -> dict | None:
            selection = tree.selection()

            if not selection:
                messagebox.showwarning(
                    "Build History",
                    "Select a build first.",
                    parent=history_window,
                )
                return None

            return record_lookup.get(selection[0])

        def open_selected_log():
            record = selected_record()

            if record is None:
                return

            log_path_text = str(record.get("log_path", "")).strip()

            if not log_path_text:
                messagebox.showwarning(
                    "Build History",
                    "This build does not have a log path.",
                    parent=history_window,
                )
                return

            open_path_in_windows(Path(log_path_text))

        def show_selected_details():
            record = selected_record()

            if record is None:
                return

            configuration = record.get("configuration", {})

            if not isinstance(configuration, dict):
                configuration = {}

            details = (
                f"Build ID: {record.get('id', '')}\n"
                f"Status: {record.get('status', '')}\n"
                f"Started: {record.get('started_at', '')}\n"
                f"Finished: {record.get('finished_at') or '—'}\n"
                f"Duration: "
                f"{format_duration(record.get('duration_seconds'))}\n"
                f"Exit code: "
                f"{record.get('exit_code') if record.get('exit_code') is not None else '—'}\n\n"
                f"Project:\n{configuration.get('project', '')}\n\n"
                f"Plugin:\n{configuration.get('plugin', '')}\n\n"
                f"Map:\n{configuration.get('map', '')}\n\n"
                f"Workshop:\n{configuration.get('workshop', '')}\n\n"
                f"Published ID:\n"
                f"{configuration.get('publishedfileid', '')}\n\n"
                f"Log:\n{record.get('log_path', '')}"
            )

            error_text = str(record.get("error", "")).strip()

            if error_text:
                details += f"\n\nError:\n{error_text}"

            messagebox.showinfo(
                "Build Details",
                details,
                parent=history_window,
            )

        button_frame = ttk.Frame(
            history_window,
            padding=(12, 6, 12, 12),
        )
        button_frame.pack(fill="x")

        ttk.Button(
            button_frame,
            text="Refresh",
            command=refresh_history_table,
        ).pack(side="left")

        ttk.Button(
            button_frame,
            text="Build Details",
            command=show_selected_details,
        ).pack(side="left", padx=(8, 0))

        ttk.Button(
            button_frame,
            text="Open Selected Log",
            command=open_selected_log,
        ).pack(side="left", padx=(8, 0))

        ttk.Button(
            button_frame,
            text="Open Logs Folder",
            command=lambda: open_path_in_windows(BUILD_LOGS_DIR),
        ).pack(side="left", padx=(8, 0))

        ttk.Button(
            button_frame,
            text="Close",
            command=history_window.destroy,
        ).pack(side="right")

        tree.bind(
            "<Double-1>",
            lambda _event: open_selected_log(),
        )

        refresh_history_table()

    def open_workshop():
        path = fields["workshop"].get().strip()
        if path and Path(path).exists():
            os.startfile(path)
        else:
            messagebox.showwarning("Workshop folder", "Workshop folder does not exist yet.")

    validate_button = ttk.Button(
        buttons,
        text="Validate",
        command=validate_only,
    )
    validate_button.pack(side="left", padx=(0, 8))
    build_button = ttk.Button(buttons, text="Build Mod", command=start_build)
    build_button.pack(side="left")
    cancel_button = ttk.Button(buttons, text="Cancel", command=cancel_build, state="disabled")
    cancel_button.pack(side="left", padx=8)
    ttk.Button(buttons, text="Open Workshop Folder", command=open_workshop).pack(side="left")
    ttk.Button(
        buttons,
        text="Build History",
        command=show_build_history,
    ).pack(side="left", padx=(8, 0))
    ttk.Button(buttons, text="Refresh Plugins", command=refresh_plugins).pack(side="left", padx=8)
    ttk.Button(
        buttons,
        text="Exit",
        command=close_application,
    ).pack(side="right")

    project_entry.bind("<FocusOut>", lambda _event: refresh_plugins(), add="+")
    refresh_profiles()
    refresh_plugins()
    apply_theme()
    apply_hardcoded_branding()
    update_steamcmd_visibility()
    poll_queue()

    root.protocol("WM_DELETE_WINDOW", close_application)
    root.mainloop()


if __name__ == "__main__":
    if len(sys.argv) == 1:
        launch_gui()
    else:
        main_cli()