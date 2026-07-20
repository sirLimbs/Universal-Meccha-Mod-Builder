# =============================================================================
# Imports
# =============================================================================

import argparse
import json
import os
import platform
import queue
import re
import shutil
import subprocess
import sys
import threading
import webbrowser
import zipfile
from datetime import datetime
from pathlib import Path

# =============================================================================
# Application constants and persistent paths
# =============================================================================

APP_NAME = "Meccha Mod Builder"
APP_VERSION = "1.2.0-dev"

MECCHA_APP_ID = "4704690"  # DO NOT CHANGE

GITHUB_REPOSITORY_URL = "https://github.com/sirLimbs/Universal-Meccha-Mod-Builder"
LICENSE_NAME = "N/A"
MECCHA_DISCLAIMER = (
    "This is an independent community tool and is not affiliated with or "
    "endorsed by the developers or publishers of Meccha Chameleon."
)


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


# =============================================================================
# Build history and timing statistics
# =============================================================================


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

    return [record for record in data if isinstance(record, dict)]


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


def update_build_history_record(
    build_id: str,
    updates: dict,
) -> bool:
    """
    Update an existing build-history record.

    Returns True when the record was found.
    """
    records = load_build_history()
    record_found = False

    for record in records:
        if record.get("id") == build_id:
            record.update(updates)
            record_found = True
            break

    if record_found:
        save_build_history(records)

    return record_found


def classify_build_mode(configuration: dict) -> str:
    """
    Return a stable key describing the selected build workflow.

    Examples:
        full_mod
        full_only
        mod_only
        copy_only
        full_mod_upload
    """
    if not isinstance(configuration, dict):
        return "unknown"

    flags = configuration.get("flags", {})

    if not isinstance(flags, dict):
        flags = {}

    build_full = bool(flags.get("build_full"))
    build_mod = bool(flags.get("build_mod"))
    copy_only = bool(flags.get("copy_only"))
    upload = bool(flags.get("upload"))

    if copy_only:
        base_mode = "copy_only"
    elif build_full and build_mod:
        base_mode = "full_mod"
    elif build_full:
        base_mode = "full_only"
    elif build_mod:
        base_mode = "mod_only"
    else:
        base_mode = "no_build"

    if upload:
        return f"{base_mode}_upload"

    return base_mode


def describe_build_mode(mode: str) -> str:
    """Convert an internal build mode key into a readable label."""
    labels = {
        "full_mod": "Full Game + My Mod",
        "full_only": "Full Game only",
        "mod_only": "My Mod only",
        "copy_only": "Copy only",
        "no_build": "No Unreal build",
        "full_mod_upload": "Full Game + My Mod + Upload",
        "full_only_upload": "Full Game + Upload",
        "mod_only_upload": "My Mod + Upload",
        "copy_only_upload": "Copy only + Upload",
        "no_build_upload": "Upload only",
        "unknown": "Unknown",
    }

    return labels.get(mode, mode.replace("_", " ").title())


def default_build_statistics() -> dict:
    """Return the initial build-statistics structure."""
    return {
        "version": 1,
        "updated_at": None,
        "modes": {},
    }


def load_build_statistics() -> dict:
    """Load persisted build timing statistics."""
    data = load_json_file(
        BUILD_STATISTICS_FILE,
        default_build_statistics(),
    )

    if not isinstance(data, dict):
        return default_build_statistics()

    if not isinstance(data.get("modes"), dict):
        data["modes"] = {}

    data.setdefault("version", 1)
    data.setdefault("updated_at", None)

    return data


def save_build_statistics(statistics: dict) -> None:
    """Save build timing statistics."""
    statistics["updated_at"] = current_local_timestamp()
    save_json_file(BUILD_STATISTICS_FILE, statistics)


def calculate_median(values: list[float]) -> float | None:
    """Return the median of numeric values without external dependencies."""
    cleaned = []

    for value in values:
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            continue

        if numeric_value > 0:
            cleaned.append(numeric_value)

    if not cleaned:
        return None

    cleaned.sort()
    count = len(cleaned)
    midpoint = count // 2

    if count % 2:
        return cleaned[midpoint]

    return (cleaned[midpoint - 1] + cleaned[midpoint]) / 2


def rebuild_build_statistics() -> dict:
    """
    Recalculate timing statistics from successful build-history records.

    Only the newest 20 successful durations per build mode are retained.
    """
    records = load_build_history()
    durations_by_mode = {}

    for record in records:
        if record.get("status") != "success":
            continue

        duration = record.get("duration_seconds")

        try:
            duration = float(duration)
        except (TypeError, ValueError):
            continue

        if duration <= 0:
            continue

        configuration = record.get("configuration", {})
        mode = classify_build_mode(configuration)

        durations_by_mode.setdefault(mode, []).append(duration)

    statistics = default_build_statistics()

    for mode, durations in durations_by_mode.items():
        recent_durations = durations[-20:]
        median_duration = calculate_median(recent_durations)

        statistics["modes"][mode] = {
            "sample_count": len(recent_durations),
            "median_seconds": (
                round(median_duration, 2) if median_duration is not None else None
            ),
            "minimum_seconds": round(min(recent_durations), 2),
            "maximum_seconds": round(max(recent_durations), 2),
            "recent_durations": [round(value, 2) for value in recent_durations],
        }

    save_build_statistics(statistics)
    return statistics


def get_build_time_estimate(
    configuration: dict,
) -> dict:
    """
    Return an estimate for the supplied configuration.

    A minimum of two successful comparable builds is required before showing
    an estimated total.
    """
    mode = classify_build_mode(configuration)
    statistics = load_build_statistics()
    mode_statistics = statistics.get("modes", {}).get(mode, {})

    sample_count = mode_statistics.get("sample_count", 0)
    median_seconds = mode_statistics.get("median_seconds")

    try:
        sample_count = int(sample_count)
    except (TypeError, ValueError):
        sample_count = 0

    try:
        median_seconds = float(median_seconds)
    except (TypeError, ValueError):
        median_seconds = None

    if sample_count < 2 or not median_seconds or median_seconds <= 0:
        return {
            "available": False,
            "mode": mode,
            "mode_label": describe_build_mode(mode),
            "sample_count": sample_count,
            "estimated_seconds": None,
        }

    return {
        "available": True,
        "mode": mode,
        "mode_label": describe_build_mode(mode),
        "sample_count": sample_count,
        "estimated_seconds": median_seconds,
    }


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


# =============================================================================
# Preflight validation and Unreal project inspection
# =============================================================================


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
            f"Invalid JSON at line {exc.lineno}, column {exc.colno}: " f"{exc.msg}"
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
        candidate.resolve() for candidate in candidates if candidate.is_file()
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

        search_roots.extend(
            [
                plugin_saved / "Autosaves",
                plugin_saved / "Backup",
            ]
        )

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
                if path.suffix.lower() in candidate_suffixes or path.suffix.lower() in {
                    ".uasset",
                    ".umap",
                }:
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


# =============================================================================
# Resource paths and general filesystem helpers
# =============================================================================


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


RESOURCES_DIR = resource_path("resources")
ICON_DIR = RESOURCES_DIR / "icon"
CURSOR_DIR = RESOURCES_DIR / "cursor"
SPINNER_DIR = RESOURCES_DIR / "spinner"

WINDOW_ICON_PATH = ICON_DIR / "icon.ico"
HEADER_LOGO_PATH = ICON_DIR / "header_icon.png"
ICON_IMAGE_PATH = ICON_DIR / "icon_source.png"
GIT_LOGO_PATH = ICON_DIR / "github_icon.png"

# cursor.png remains the editable source artwork. Tk requires a real .cur file
# for a native Windows cursor, so cursor.cur is used automatically when present.
CURSOR_SOURCE_PATH = CURSOR_DIR / "cursor.png"
CURSOR_FILE_PATH = CURSOR_DIR / "cursor.cur"
GENERATED_CURSOR_PATH = CACHE_DIR / "meccha_cursor.cur"

# Retained as packaged artwork. The active spinner uses Tk only.
SPINNER_SVG_PATH = SPINNER_DIR / "spinner.svg"

APP_ICON_FILE = WINDOW_ICON_PATH
APP_LOGO_FILE = HEADER_LOGO_PATH


def read_image_dimensions(path: Path) -> tuple[int, int] | None:
    """
    Read PNG, GIF, or JPEG dimensions using only the Python standard library.

    Returns None when the format is unsupported or the image cannot be parsed.
    """
    path = Path(path)

    try:
        with path.open("rb") as stream:
            header = stream.read(32)

            # PNG: width and height are stored in the IHDR chunk.
            if header.startswith(b"\x89PNG\r\n\x1a\n") and len(header) >= 24:
                width = int.from_bytes(header[16:20], "big")
                height = int.from_bytes(header[20:24], "big")
                return width, height

            # GIF87a / GIF89a: little-endian logical screen dimensions.
            if header[:6] in {b"GIF87a", b"GIF89a"} and len(header) >= 10:
                width = int.from_bytes(header[6:8], "little")
                height = int.from_bytes(header[8:10], "little")
                return width, height

            # JPEG: scan markers until a Start Of Frame marker is found.
            if header.startswith(b"\xff\xd8"):
                stream.seek(2)

                while True:
                    marker_prefix = stream.read(1)

                    if not marker_prefix:
                        break

                    if marker_prefix != b"\xff":
                        continue

                    marker = stream.read(1)

                    while marker == b"\xff":
                        marker = stream.read(1)

                    if not marker:
                        break

                    marker_value = marker[0]

                    # Standalone markers with no length field.
                    if marker_value in {0x01, *range(0xD0, 0xD9)}:
                        continue

                    length_data = stream.read(2)

                    if len(length_data) != 2:
                        break

                    segment_length = int.from_bytes(length_data, "big")

                    if segment_length < 2:
                        break

                    if marker_value in {
                        0xC0, 0xC1, 0xC2, 0xC3,
                        0xC5, 0xC6, 0xC7,
                        0xC9, 0xCA, 0xCB,
                        0xCD, 0xCE, 0xCF,
                    }:
                        frame_data = stream.read(5)

                        if len(frame_data) != 5:
                            break

                        height = int.from_bytes(frame_data[1:3], "big")
                        width = int.from_bytes(frame_data[3:5], "big")
                        return width, height

                    stream.seek(segment_length - 2, 1)

    except OSError:
        return None

    return None


def format_file_size(size_bytes: int) -> str:
    """Format a file size using binary units."""
    size = float(max(0, size_bytes))

    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024

    return f"{size_bytes} B"


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
            record.update(
                {
                    "status": "interrupted",
                    "finished_at": recovery_time,
                    "error": (
                        "The application ended before this build recorded "
                        "a normal completion state."
                    ),
                }
            )
            changed += 1

    if changed:
        save_build_history(records)

    return changed


# =============================================================================
# Steam Workshop VDF and payload helpers
# =============================================================================


def to_vdf_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "\\\\")


def escape_vdf_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def build_vdf_text(
    appid,
    publishedfileid,
    contentfolder,
    previewfile,
    title,
    description,
    changenote,
    visibility,
) -> str:
    """Return the exact Steam Workshop VDF content used for uploads."""
    return f"""\"workshopitem\"
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
"""


def read_published_file_id_from_vdf(vdf_path: Path) -> str:
    """Return a non-zero Published File ID written into a Workshop VDF."""
    try:
        text = Path(vdf_path).read_text(encoding="utf-8-sig")
    except OSError:
        return ""

    match = re.search(
        r'"publishedfileid"\s+"(\d+)"',
        text,
        flags=re.IGNORECASE,
    )

    if not match:
        return ""

    published_file_id = match.group(1)
    return published_file_id if published_file_id != "0" else ""


def write_vdf(
    vdf_path_out,
    appid,
    publishedfileid,
    contentfolder,
    previewfile,
    title,
    description,
    changenote,
    visibility,
):
    text = build_vdf_text(
        appid,
        publishedfileid,
        contentfolder,
        previewfile,
        title,
        description,
        changenote,
        visibility,
    )
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
        raise ValueError(f"Use package path only, not Object.Object syntax: {map_path}")

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


# =============================================================================
# Unreal build and payload discovery
# =============================================================================


def build_full_game(ue, project, project_root, release):
    run(
        [
            str(ue),
            "BuildCookRun",
            f"-project={project}",
            "-noP4",
            "-platform=Win64",
            "-clientconfig=Development",
            "-build",
            "-cook",
            "-stage",
            "-pak",
            "-compressed",
            f"-createReleaseVersion={release}",
            "-utf8output",
        ],
        cwd=project_root,
    )


def build_mod_dlc(ue, project, project_root, plugin_name, release, map_path):
    run(
        [
            str(ue),
            "BuildCookRun",
            f"-project={project}",
            "-noP4",
            "-platform=Win64",
            "-clientconfig=Development",
            "-build",
            "-cook",
            "-stage",
            "-pak",
            "-compressed",
            f"-dlcName={plugin_name}",
            f"-basedOnReleaseVersion={release}",
            "-DLCIncludeEngineContent",
            f"-map={map_path}",
            "-utf8output",
        ],
        cwd=project_root,
    )


def find_expected_payload_paths(project: Path, plugin_name: str):
    project_root = project.parent
    project_name = project.stem
    plugin_root = project_root / "Plugins" / plugin_name

    staged_paks = (
        plugin_root
        / "Saved"
        / "StagedBuilds"
        / "Windows"
        / project_name
        / "Plugins"
        / plugin_name
        / "Content"
        / "Paks"
        / "Windows"
    )
    cooked_plugin = (
        plugin_root
        / "Saved"
        / "Cooked"
        / "Windows"
        / project_name
        / "Plugins"
        / plugin_name
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
            p
            for p in candidates
            if p.suffix.lower() == suffix and p.stem.lower() == expected_stem
        ]
        if matches:
            payload[key] = matches[0]
            print(f"Fallback located {suffix}: {matches[0]}")

    if not payload["registry"].exists():
        matches = [
            p
            for p in candidates
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
            str(steamcmd),
            "+login",
            *steam_login.split(),
            "+workshop_build_item",
            str(vdf_path),
            "+quit",
        ]
    else:
        cmd = [str(steamcmd), "+workshop_build_item", str(vdf_path), "+quit"]
    run(cmd)


# =============================================================================
# Command-line interface
# =============================================================================


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
        ("--ue", args.ue),
        ("--project", args.project),
        ("--map", args.map_path),
        ("--plugin", args.plugin),
        ("--workshop", args.workshop),
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
            print("=== PIPELINE:BUILD_FULL ===", flush=True)
            build_full_game(ue, project, project_root, args.release)
        else:
            print("\nSkipping Full Game build.")
        if not args.skip_mod:
            print("=== PIPELINE:BUILD_MOD ===", flush=True)
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
        checker = (
            require_file
            if args.copy_only
            else (lambda p, label: require_fresh_file(p, label, build_started_at))
        )
        payload["pak"] = checker(payload["pak"], "mod .pak")
        payload["ucas"] = checker(payload["ucas"], "mod .ucas")
        payload["utoc"] = checker(payload["utoc"], "mod .utoc")
        payload["registry"] = checker(payload["registry"], "plugin AssetRegistry.bin")
    except Exception:
        print_recent_payload_candidates(project_root, args.plugin)
        raise

    print("=== PIPELINE:COPY_FILES ===", flush=True)
    preview_dst, _ = copy_payload_to_workshop(payload, workshop, preview)
    vdf_path = workshop / "my_item.vdf"
    write_vdf(
        vdf_path,
        args.appid,
        args.publishedfileid,
        workshop,
        preview_dst,
        args.title,
        args.description,
        args.changenote,
        args.visibility,
    )

    print("\n=== Workshop Folder Ready ===")
    for file in sorted(workshop.iterdir()):
        if file.is_file():
            modified = datetime.fromtimestamp(file.stat().st_mtime)
            print(
                f"{modified:%Y-%m-%d %H:%M:%S}  {file.stat().st_size:>12,}  {file.name}"
            )

    print("\nNext SteamCMD command:")
    print(f'workshop_build_item "{vdf_path}"')

    if args.upload:
        if not args.steamcmd:
            raise RuntimeError("--upload requires --steamcmd")
        steamcmd = require_file(Path(args.steamcmd), "steamcmd.exe")
        print("\n=== Uploading with SteamCMD ===")
        print("=== PIPELINE:UPLOAD ===", flush=True)
        run_steamcmd(steamcmd, vdf_path, args.steam_login)

    print("=== PIPELINE:DONE ===", flush=True)
    print("\n=== DONE ===")


# =============================================================================
# Tkinter graphical interface
# =============================================================================


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
                self.window = None

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
    root.withdraw()

    splash_refs = {"logo": None}

    def show_startup_splash():
        """
        Show a lightweight splash while startup initialization continues.

        The splash is time-limited and never waits before allowing the main
        window to initialize.
        """
        splash = tk.Toplevel(root)
        splash.title(APP_NAME)
        splash.overrideredirect(True)
        splash.attributes("-topmost", True)

        splash_frame = ttk.Frame(splash, padding=(24, 18))
        splash_frame.pack(fill="both", expand=True)

        if ICON_IMAGE_PATH.is_file():
            try:
                if pillow_available:
                    image = Image.open(ICON_IMAGE_PATH).convert("RGBA")
                    image.thumbnail((72, 72), Image.Resampling.LANCZOS)
                    splash_photo = ImageTk.PhotoImage(image)
                else:
                    splash_photo = tk.PhotoImage(
                        file=str(ICON_IMAGE_PATH.resolve())
                    )

                splash_refs["logo"] = splash_photo
                ttk.Label(
                    splash_frame,
                    image=splash_photo,
                ).pack(side="left", padx=(0, 16))
            except Exception as exc:
                print(f"Could not load splash logo: {exc}")

        splash_text = ttk.Frame(splash_frame)
        splash_text.pack(side="left", fill="both", expand=True)

        ttk.Label(
            splash_text,
            text="Meccha Mod Builder",
            font=("Segoe UI", 16, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            splash_text,
            text=f"v{APP_VERSION}",
        ).pack(anchor="w", pady=(2, 6))
        ttk.Label(
            splash_text,
            text="Loading profiles and project tools...",
        ).pack(anchor="w")

        splash.update_idletasks()

        width = splash.winfo_reqwidth()
        height = splash.winfo_reqheight()
        screen_width = splash.winfo_screenwidth()
        screen_height = splash.winfo_screenheight()
        x = max(0, (screen_width - width) // 2)
        y = max(0, (screen_height - height) // 2)
        splash.geometry(f"{width}x{height}+{x}+{y}")
        splash.update()

        def close_splash():
            if splash.winfo_exists():
                splash.destroy()
            root.deiconify()
            root.lift()
            root.focus_force()

        root.after(700, close_splash)
        return splash

    startup_splash = show_startup_splash()

    interrupted_build_count = mark_interrupted_builds()
    rebuild_build_statistics()

    branding_refs = {
        "header_logo": None,
        "window_icon_targets": {},
    }

    def apply_window_icon(window, *, remember_key=None):
        """
        Apply icon.ico to the root window and all child windows.

        icon.png is reserved exclusively for the large header branding image.
        """
        if not WINDOW_ICON_PATH.is_file():
            print(f"ICO file does not exist: {WINDOW_ICON_PATH}")
            return

        icon_path = str(WINDOW_ICON_PATH.resolve())

        try:
            # The direct form applies the icon to the current window.
            window.iconbitmap(icon_path)
        except Exception as exc:
            print(f"iconbitmap failed for {window}: {exc}")

        try:
            # The default form helps newly created Tk/Toplevel windows inherit it.
            window.iconbitmap(default=icon_path)
        except Exception:
            pass

        if remember_key:
            branding_refs["window_icon_targets"][remember_key] = window

    # Apply the ICO immediately. No delayed PNG override is used.
    apply_window_icon(root, remember_key="root")
    root.geometry("1060x760")
    root.minsize(820, 560)

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
            "console_muted": "#8d98a8",
            "console_info": "#7fb3ff",
            "console_success": "#72d597",
            "console_warning": "#f2c66d",
            "console_error": "#ff7f87",
            "console_heading": "#c7a7ff",
            "danger": "#b93f4a",
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
            "console_muted": "#6d7682",
            "console_info": "#1f64b5",
            "console_success": "#237a43",
            "console_warning": "#9a6500",
            "console_error": "#b4232c",
            "console_heading": "#6741a5",
            "danger": "#b83843",
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
        style.configure(
            "TButton",
            background=c["panel"],
            foreground=c["fg"],
            padding=5,
        )
        style.map(
            "TButton",
            background=[("active", c["accent"])],
        )
        style.configure(
            "Primary.TButton",
            background=c["accent"],
            foreground="#ffffff",
            padding=(12, 7),
            font=("Segoe UI", 9, "bold"),
        )
        style.map(
            "Primary.TButton",
            background=[
                ("disabled", c["panel"]),
                ("pressed", c["select"]),
                ("active", c["select"]),
            ],
            foreground=[("disabled", c["muted"])],
        )
        style.configure(
            "Danger.TButton",
            background=c["danger"],
            foreground="#ffffff",
            padding=(10, 6),
        )
        style.map(
            "Danger.TButton",
            background=[
                ("disabled", c["panel"]),
                ("active", c["danger"]),
            ],
            foreground=[("disabled", c["muted"])],
        )
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
            console = locals_ref["output_box"]
            console.configure(
                background=c["console_bg"],
                foreground=c["console_fg"],
                insertbackground=c["fg"],
                selectbackground=c["select"],
            )
            console.tag_configure("timestamp", foreground=c["console_muted"])
            console.tag_configure("normal", foreground=c["console_fg"])
            console.tag_configure("info", foreground=c["console_info"])
            console.tag_configure("success", foreground=c["console_success"])
            console.tag_configure("warning", foreground=c["console_warning"])
            console.tag_configure("error", foreground=c["console_error"])
            console.tag_configure(
                "heading",
                foreground=c["console_heading"],
                font=("Consolas", 9, "bold"),
            )
            console.tag_configure(
                "command",
                foreground=c["console_info"],
                font=("Consolas", 9, "bold"),
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
            1, int(max(image.width() / max_size[0], image.height() / max_size[1]))
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
                    image.thumbnail((96, 96), Image.Resampling.LANCZOS)
                    header_photo = ImageTk.PhotoImage(image)
                else:
                    header_photo = tk.PhotoImage(file=str(HEADER_LOGO_PATH.resolve()))

                header_logo.configure(image=header_photo, text="")
                branding_refs["header_logo"] = header_photo
            else:
                print(f"Header logo not found: {HEADER_LOGO_PATH}")
        except Exception as exc:
            print(f"Could not apply header logo: {exc}")

    # The footer is packed first so it stays at the absolute bottom.
    footer_host = ttk.Frame(root, padding=(10, 4))
    footer_host.pack(side="bottom", fill="x")

    # The action bar remains directly above the footer at all window sizes.
    action_host = ttk.Frame(root, padding=(10, 6))
    action_host.pack(side="bottom", fill="x")

    # All configuration/output content is scrollable.
    scroll_host = ttk.Frame(root)
    scroll_host.pack(side="top", fill="both", expand=True)

    canvas = tk.Canvas(scroll_host, highlightthickness=0, borderwidth=0)
    vertical_scroll = ttk.Scrollbar(
        scroll_host, orient="vertical", command=canvas.yview
    )
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

    title_row = ttk.Frame(header_text)
    title_row.pack(fill="x")

    ttk.Label(
        title_row,
        text="Universal Meccha Mod Builder",
        font=("Segoe UI", 16, "bold"),
    ).pack(side="left")

    ttk.Label(
        title_row,
        text="by Limbs",
        font=("Segoe UI", 9, "italic"),
        foreground="#888888",
    ).pack(side="left", padx=(10, 0), pady=(7, 0))

    ttk.Label(
        header_text,
        text="Build, package, and publish custom Meccha Chameleon maps",
        anchor="w",
    ).pack(fill="x")

    # Profile area
    profile_bar = ttk.Frame(header, padding=6)
    profile_bar.pack(
        side="right",
        padx=(12, 0),
        pady=(26, 0),   # moves the profile area downward
        anchor="n",
    )

    profile_var = tk.StringVar()

    # Profile icon
    profile_icon = ttk.Label(
        profile_bar,
        text="👤",
        font=("Segoe UI Emoji", 12),
        cursor="hand2",
    )
    profile_icon.grid(
        row=0,
        column=0,
        padx=(0, 6),
        pady=(0, 5),
        sticky="w",
    )

    ToolTip(profile_icon, "Profile")

    # Profile dropdown
    profile_combo = ttk.Combobox(
        profile_bar,
        textvariable=profile_var,
        state="readonly",
        width=28,
    )
    profile_combo.grid(
        row=0,
        column=1,
        columnspan=4,
        sticky="ew",
        pady=(0, 5),
    )

    ToolTip(profile_combo, hints["profiles"])

    form = ttk.LabelFrame(outer, text="Build configuration", padding=10)
    form.pack(fill="x")
    form.columnconfigure(1, weight=1)
    row = 0

    field_rows = {}
    path_control_buttons = {}

    def copy_field_value(key: str) -> None:
        """Copy a field value and report it through the non-blocking status area."""
        value = fields[key].get().strip()

        if not value:
            status_var.set("Nothing to copy")
            return

        root.clipboard_clear()
        root.clipboard_append(value)
        root.update_idletasks()
        status_var.set("Copied to clipboard")

    def resolve_field_directory(key: str) -> Path | None:
        """Resolve the directory represented by a main configuration field."""
        value = fields[key].get().strip()

        if key == "plugin":
            project_value = fields["project"].get().strip()
            plugin_name = value

            if not project_value or not plugin_name:
                return None

            project_path = Path(project_value).expanduser()
            project_root = (
                project_path.parent
                if project_path.suffix.lower() == ".uproject"
                else project_path
            )
            plugin_path = project_root / "Plugins" / plugin_name
            return plugin_path if plugin_path.is_dir() else None

        if key == "map":
            project_value = fields["project"].get().strip()
            plugin_name = fields["plugin"].get().strip()

            if not project_value or not plugin_name or not value:
                return None

            project_path = Path(project_value).expanduser()

            if not project_path.is_file():
                return None

            candidates = find_map_candidates(project_path, plugin_name, value)
            return candidates[0].parent if candidates else None

        if not value:
            return None

        path = Path(value).expanduser()

        if key in {"ue", "project"}:
            return path.parent if path.is_file() else None

        if key == "workshop":
            return path if path.is_dir() else None

        return path.parent if path.is_file() else (path if path.is_dir() else None)

    def open_field_directory(key: str) -> None:
        """Open the resolved directory for a configuration field."""
        directory = resolve_field_directory(key)

        if directory is None:
            status_var.set("No valid folder could be resolved")
            return

        open_path_in_windows(directory)

    def update_path_control_states(*_args) -> None:
        """Enable folder controls only when their destination can be resolved."""
        for key, controls in path_control_buttons.items():
            folder_button = controls.get("folder")

            if folder_button is None:
                continue

            state = "normal" if resolve_field_directory(key) else "disabled"
            folder_button.configure(state=state)

    def add_entry(label_text, key, browse=None, *, browse_tooltip=None):
        nonlocal row

        current_row = row
        widgets = []

        label = ttk.Label(form, text=label_text)
        label.grid(row=current_row, column=0, sticky="w", padx=(0, 8), pady=4)
        widgets.append(label)

        entry = ttk.Entry(form, textvariable=fields[key])
        entry.grid(row=current_row, column=1, sticky="ew", pady=4)
        entry.bind(
            "<Double-Button-1>",
            lambda _event, field_key=key: copy_field_value(field_key),
            add="+",
        )
        widgets.append(entry)

        ToolTip(label, hints.get(key, ""))
        ToolTip(entry, f"{hints.get(key, '')}\n\nDouble-click to copy.".strip())

        controls = ttk.Frame(form)
        controls.grid(row=current_row, column=2, padx=(8, 0), pady=4)
        widgets.append(controls)

        browse_button = ttk.Button(
            controls,
            text="🔍",
            width=3,
            command=browse if browse else None,
            state="normal" if browse else "disabled",
            cursor="hand2",
        )
        browse_button.pack(side="left")
        ToolTip(
            browse_button,
            browse_tooltip or hints.get(key, "") or "Browse or select a value.",
        )

        folder_button = ttk.Button(
            controls,
            text="📂",
            width=3,
            command=lambda field_key=key: open_field_directory(field_key),
            state="disabled",
            cursor="hand2",
        )
        folder_button.pack(side="left", padx=(4, 0))
        ToolTip(folder_button, "Open the resolved folder for this field.")

        path_control_buttons[key] = {
            "browse": browse_button,
            "folder": folder_button,
        }
        field_rows[key] = widgets
        row += 1
        return entry

    def browse_ue():
        value = filedialog.askopenfilename(
            title="Select UE 5.6 RunUAT.bat",
            filetypes=[("RunUAT", "RunUAT.bat"), ("Batch", "*.bat"), ("All", "*.*")],
        )
        if value:
            fields["ue"].set(value)

    def browse_project():
        value = filedialog.askopenfilename(
            title="Select Meccha .uproject",
            filetypes=[("Unreal project", "*.uproject"), ("All", "*.*")],
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
            filetypes=[("Images", "*.png *.jpg *.jpeg"), ("All", "*.*")],
        )
        if value:
            fields["preview"].set(value)

    def browse_steamcmd():
        value = filedialog.askopenfilename(
            title="Select steamcmd.exe",
            filetypes=[
                ("SteamCMD", "steamcmd.exe"),
                ("Executables", "*.exe"),
                ("All", "*.*"),
            ],
        )
        if value:
            fields["steamcmd"].set(value)

    add_entry(
        "UE RunUAT.bat",
        "ue",
        browse_ue,
        browse_tooltip="Select RunUAT.bat.",
    )
    project_entry = add_entry(
        "Meccha .uproject",
        "project",
        browse_project,
        browse_tooltip="Select the Meccha Unreal project.",
    )

    plugin_label = ttk.Label(form, text="Asset plugin")
    plugin_label.grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)

    plugin_combo = ttk.Combobox(
        form,
        textvariable=fields["plugin"],
        state="readonly",
    )
    plugin_combo.grid(row=row, column=1, sticky="ew", pady=4)
    plugin_combo.bind(
        "<Double-Button-1>",
        lambda _event: copy_field_value("plugin"),
        add="+",
    )

    plugin_controls = ttk.Frame(form)
    plugin_controls.grid(row=row, column=2, padx=(8, 0), pady=4)

    refresh_button = ttk.Button(
        plugin_controls,
        text="🔍",
        width=3,
        command=lambda: refresh_plugins(),
        cursor="hand2",
    )
    refresh_button.pack(side="left")

    plugin_folder_button = ttk.Button(
        plugin_controls,
        text="📂",
        width=3,
        command=lambda: open_field_directory("plugin"),
        state="disabled",
        cursor="hand2",
    )
    plugin_folder_button.pack(side="left", padx=(4, 0))

    path_control_buttons["plugin"] = {
        "browse": refresh_button,
        "folder": plugin_folder_button,
    }

    ToolTip(plugin_label, hints["plugin"])
    ToolTip(plugin_combo, f"{hints['plugin']}\n\nDouble-click to copy.")
    ToolTip(refresh_button, "Refresh and select from detected project plugins.")
    ToolTip(plugin_folder_button, "Open the selected plugin folder.")
    row += 1

    add_entry(
        "Runtime map path",
        "map",
        browse=None,
        browse_tooltip=(
            "Runtime package paths are selected inside Unreal. "
            "The folder button opens a matching .umap location when found."
        ),
    )
    add_entry(
        "Workshop folder",
        "workshop",
        browse_workshop,
        browse_tooltip="Select the Workshop staging folder.",
    )

    for traced_key in ("ue", "project", "plugin", "map", "workshop"):
        fields[traced_key].trace_add("write", update_path_control_states)

    root.after_idle(update_path_control_states)

    release_frame = ttk.Frame(form)
    release_frame.grid(row=row, column=0, columnspan=3, sticky="ew", pady=6)
    release_frame.columnconfigure(1, weight=1)

    release_label = ttk.Label(release_frame, text="Release")
    release_label.grid(row=0, column=0, sticky="w", padx=(0, 8))
    release_entry = ttk.Entry(
        release_frame,
        textvariable=fields["release"],
        width=16,
    )
    release_entry.grid(row=0, column=1, sticky="w")
    ToolTip(release_label, "Release version used by Unreal's DLC build.")
    ToolTip(release_entry, "Release version used by Unreal's DLC build.")
    row += 1

    workshop_summary_var = tk.StringVar()

    def update_workshop_summary():
        published_id = fields["publishedfileid"].get().strip()
        mode_text = (
            "Create new item"
            if not published_id or published_id == "0"
            else f"Update item {published_id}"
        )
        visibility_labels = {
            "0": "Public",
            "1": "Friends-only",
            "2": "Private",
        }
        visibility_text = visibility_labels.get(
            fields["visibility"].get().strip(),
            "Unknown visibility",
        )
        upload_text = "SteamCMD upload enabled" if flags["upload"].get() else "Local package only"
        workshop_summary_var.set(
            f"{mode_text}  •  {visibility_text}  •  {upload_text}"
        )

    def open_workshop_manager():
        dialog = tk.Toplevel(root)
        dialog.title("Workshop Manager")
        dialog.geometry("680x920")
        dialog.minsize(680, 580)
        dialog.transient(root)
        dialog.grab_set()

        apply_window_icon(dialog, remember_key="workshop_manager")

        original_published_id = fields["publishedfileid"].get().strip()
        remembered_published_id = (
            original_published_id
            if original_published_id and original_published_id != "0"
            else ""
        )

        mode_var = tk.StringVar(
            value=(
                "create"
                if not original_published_id or original_published_id == "0"
                else "update"
            )
        )
        workshop_var = tk.StringVar(value=fields["workshop"].get())
        preview_var = tk.StringVar(value=fields["preview"].get())
        appid_var = tk.StringVar(value=fields["appid"].get() or MECCHA_APP_ID)
        published_id_var = tk.StringVar(
            value=original_published_id or "0"
        )
        visibility_var = tk.StringVar(value=fields["visibility"].get() or "2")
        title_var = tk.StringVar(value=fields["title"].get())
        changenote_var = tk.StringVar(value=fields["changenote"].get())
        steamcmd_var = tk.StringVar(value=fields["steamcmd"].get())
        steam_login_var = tk.StringVar(value=fields["steam_login"].get())
        upload_var = tk.BooleanVar(value=flags["upload"].get())
        action_refs = {}

        container = ttk.Frame(dialog, padding=14)
        container.pack(fill="both", expand=True)
        container.columnconfigure(1, weight=1)
        container.rowconfigure(3, weight=1)

        ttk.Label(
            container,
            text="Steam Workshop Settings",
            font=("Segoe UI", 16, "bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(
            container,
            text=(
                "Configure the item metadata and optional SteamCMD upload without "
                "crowding the main build screen."
            ),
            wraplength=700,
            justify="left",
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 14))

        mode_frame = ttk.LabelFrame(container, text="Workshop item mode", padding=10)
        mode_frame.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(0, 10))

        def sync_mode():
            if mode_var.get() == "create":
                published_id_var.set("0")
                published_id_entry.configure(state="disabled")
            else:
                if published_id_var.get().strip() in {"", "0"}:
                    published_id_var.set(remembered_published_id)
                published_id_entry.configure(state="normal")

            update_workshop_action_state()

        ttk.Radiobutton(
            mode_frame,
            text="Create new item",
            variable=mode_var,
            value="create",
            command=sync_mode,
        ).pack(side="left", padx=(0, 18))
        ttk.Radiobutton(
            mode_frame,
            text="Update existing item",
            variable=mode_var,
            value="update",
            command=sync_mode,
        ).pack(side="left")

        details_frame = ttk.LabelFrame(
            container,
            text="Workshop item details",
            padding=(0, 6, 0, 0),
        )
        details_frame.grid(
            row=3,
            column=0,
            columnspan=3,
            sticky="nsew",
            pady=(0, 10),
        )
        details_frame.columnconfigure(0, weight=1)
        details_frame.rowconfigure(0, weight=1)

        details_canvas = tk.Canvas(
            details_frame,
            height=300,
            highlightthickness=0,
            borderwidth=0,
        )
        details_scrollbar = ttk.Scrollbar(
            details_frame,
            orient="vertical",
            command=details_canvas.yview,
        )
        details_canvas.configure(yscrollcommand=details_scrollbar.set)

        details_canvas.grid(row=0, column=0, sticky="nsew")
        details_scrollbar.grid(row=0, column=1, sticky="ns")

        details_content = ttk.Frame(details_canvas, padding=(10, 4, 10, 10))
        details_content.columnconfigure(1, weight=1)
        details_window = details_canvas.create_window(
            (0, 0),
            window=details_content,
            anchor="nw",
        )

        def update_details_scroll_region(_event=None):
            details_canvas.configure(scrollregion=details_canvas.bbox("all"))

        def match_details_canvas_width(event):
            details_canvas.itemconfigure(details_window, width=event.width)

        details_content.bind("<Configure>", update_details_scroll_region)
        details_canvas.bind("<Configure>", match_details_canvas_width)

        def scroll_details(event):
            if event.delta:
                details_canvas.yview_scroll(int(-event.delta / 120), "units")
                return "break"
            return None

        def bind_details_mousewheel(_event=None):
            details_canvas.bind_all("<MouseWheel>", scroll_details)

        def unbind_details_mousewheel(_event=None):
            details_canvas.unbind_all("<MouseWheel>")

        details_canvas.bind("<Enter>", bind_details_mousewheel)
        details_canvas.bind("<Leave>", unbind_details_mousewheel)
        details_content.bind("<Enter>", bind_details_mousewheel)
        details_content.bind("<Leave>", unbind_details_mousewheel)

        def add_dialog_entry(
            row_index,
            label_text,
            variable,
            browse_command=None,
            *,
            readonly=False,
        ):
            ttk.Label(details_content, text=label_text).grid(
                row=row_index,
                column=0,
                sticky="w",
                padx=(0, 8),
                pady=4,
            )
            entry = ttk.Entry(
                details_content,
                textvariable=variable,
                state="readonly" if readonly else "normal",
            )
            entry.grid(row=row_index, column=1, sticky="ew", pady=4)
            if browse_command:
                ttk.Button(
                    details_content,
                    text="Browse…",
                    command=browse_command,
                    cursor="hand2",
                ).grid(row=row_index, column=2, padx=(8, 0), pady=4)
            return entry

        def choose_workshop_folder():
            value = filedialog.askdirectory(
                parent=dialog,
                title="Select Workshop staging folder",
                initialdir=workshop_var.get() or None,
            )
            if value:
                workshop_var.set(value)

        def choose_preview_image():
            value = filedialog.askopenfilename(
                parent=dialog,
                title="Select preview image",
                filetypes=[("Images", "*.png *.jpg *.jpeg"), ("All", "*.*")],
            )
            if value:
                preview_var.set(value)

        def choose_steamcmd():
            value = filedialog.askopenfilename(
                parent=dialog,
                title="Select steamcmd.exe",
                filetypes=[
                    ("SteamCMD", "steamcmd.exe"),
                    ("Executables", "*.exe"),
                    ("All", "*.*"),
                ],
            )
            if value:
                steamcmd_var.set(value)

        add_dialog_entry(0, "Workshop folder", workshop_var, choose_workshop_folder)
        add_dialog_entry(1, "Preview image", preview_var, choose_preview_image)
        add_dialog_entry(2, "Steam App ID", appid_var, readonly=True)
        published_id_entry = add_dialog_entry(
            3,
            "Published File ID",
            published_id_var,
        )

        ttk.Label(details_content, text="Visibility").grid(
            row=4,
            column=0,
            sticky="w",
            padx=(0, 8),
            pady=4,
        )
        visibility_combo = ttk.Combobox(
            details_content,
            textvariable=visibility_var,
            values=["0", "1", "2"],
            state="readonly",
        )
        visibility_combo.grid(row=4, column=1, sticky="ew", pady=4)

        add_dialog_entry(5, "Workshop title", title_var)

        ttk.Label(details_content, text="Description").grid(
            row=6,
            column=0,
            sticky="nw",
            padx=(0, 8),
            pady=4,
        )
        description_text = tk.Text(
            details_content,
            height=4,
            wrap="word",
            font=("Segoe UI", 10),
        )
        description_text.grid(
            row=6,
            column=1,
            columnspan=2,
            sticky="ew",
            pady=4,
        )
        description_text.insert("1.0", fields["description"].get())

        add_dialog_entry(7, "Change note", changenote_var)

        upload_frame = ttk.LabelFrame(container, text="SteamCMD upload", padding=10)
        upload_frame.grid(row=4, column=0, columnspan=3, sticky="ew")
        upload_frame.columnconfigure(1, weight=1)

        upload_check = ttk.Checkbutton(
            upload_frame,
            text="Upload automatically after packaging",
            variable=upload_var,
        )
        upload_check.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))

        ttk.Label(upload_frame, text="SteamCMD.exe").grid(
            row=1, column=0, sticky="w", padx=(0, 8), pady=4
        )
        steamcmd_entry = ttk.Entry(upload_frame, textvariable=steamcmd_var)
        steamcmd_entry.grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Button(
            upload_frame,
            text="Browse…",
            command=choose_steamcmd,
            cursor="hand2",
        ).grid(row=1, column=2, padx=(8, 0), pady=4)

        ttk.Label(upload_frame, text="Login arguments").grid(
            row=2, column=0, sticky="w", padx=(0, 8), pady=4
        )
        ttk.Entry(upload_frame, textvariable=steam_login_var).grid(
            row=2, column=1, columnspan=2, sticky="ew", pady=4
        )
        ttk.Label(
            upload_frame,
            text=(
                "Optional and stored locally. Logging in through SteamCMD beforehand "
                "is recommended so credentials are not stored in settings."
            ),
            foreground="#e05252",
            wraplength=620,
            justify="left",
        ).grid(row=3, column=0, columnspan=3, sticky="w", pady=(4, 0))

        readiness_frame = ttk.LabelFrame(
            container,
            text="Workshop readiness",
            padding=10,
        )
        readiness_frame.grid(
            row=5,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=(10, 0),
        )
        readiness_frame.columnconfigure(1, weight=1)

        preview_thumbnail_ref = {"image": None}

        preview_thumbnail = ttk.Label(
            readiness_frame,
            text="No preview",
            anchor="center",
            width=18,
        )
        preview_thumbnail.grid(
            row=0,
            column=0,
            rowspan=2,
            sticky="nsw",
            padx=(0, 12),
        )

        readiness_status_var = tk.StringVar(value="Not checked")
        ttk.Label(
            readiness_frame,
            textvariable=readiness_status_var,
            font=("Segoe UI", 10, "bold"),
        ).grid(row=0, column=1, sticky="w")

        readiness_details_var = tk.StringVar(
            value="Choose Refresh Readiness to inspect the current settings."
        )
        ttk.Label(
            readiness_frame,
            textvariable=readiness_details_var,
            justify="left",
            wraplength=600,
        ).grid(row=1, column=1, sticky="ew", pady=(4, 0))

        readiness_results = {
            "errors": [],
            "warnings": [],
            "passes": [],
        }

        def update_preview_thumbnail(preview_path: Path | None) -> None:
            preview_thumbnail_ref["image"] = None
            preview_thumbnail.configure(image="", text="No preview")

            if preview_path is None or not preview_path.is_file():
                return

            if pillow_available:
                try:
                    image = Image.open(preview_path).convert("RGBA")
                    image.thumbnail((128, 96), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(image)
                    preview_thumbnail.configure(image=photo, text="")
                    preview_thumbnail_ref["image"] = photo
                    return
                except Exception:
                    pass

            dimensions = read_image_dimensions(preview_path)
            label = preview_path.name

            if dimensions:
                label += f"\n{dimensions[0]} × {dimensions[1]}"

            preview_thumbnail.configure(text=label)

        def collect_workshop_readiness() -> dict:
            results = {
                "errors": [],
                "warnings": [],
                "passes": [],
            }

            workshop_text = workshop_var.get().strip()
            preview_text = preview_var.get().strip()
            title = title_var.get().strip()
            description = description_text.get("1.0", "end-1c").strip()
            changenote = changenote_var.get().strip()
            published_id = published_id_var.get().strip()

            # Workshop folder
            if not workshop_text:
                results["errors"].append("Workshop folder is not selected.")
            else:
                workshop_path = Path(workshop_text).expanduser()

                if workshop_path.exists() and not workshop_path.is_dir():
                    results["errors"].append(
                        "Workshop path exists but is not a folder."
                    )
                elif workshop_path.is_dir():
                    results["passes"].append("Workshop folder is accessible.")

                    try:
                        existing_payload = [
                            path
                            for path in workshop_path.iterdir()
                            if path.is_file()
                            and path.suffix.lower()
                            in {".pak", ".ucas", ".utoc", ".bin", ".vdf"}
                        ]
                    except OSError:
                        existing_payload = []

                    if existing_payload:
                        results["passes"].append(
                            f"{len(existing_payload)} existing payload file(s) found."
                        )
                    else:
                        results["warnings"].append(
                            "No packaged payload files are currently present."
                        )
                else:
                    parent = workshop_path.parent

                    if parent.is_dir():
                        results["warnings"].append(
                            "Workshop folder does not exist yet but can be created."
                        )
                    else:
                        results["errors"].append(
                            "Workshop folder parent does not exist."
                        )

            # Preview image
            preview_path = Path(preview_text).expanduser() if preview_text else None
            update_preview_thumbnail(preview_path)

            if preview_path is None:
                results["errors"].append("Preview image is not selected.")
            elif not preview_path.is_file():
                results["errors"].append("Preview image was not found.")
            else:
                suffix = preview_path.suffix.lower()

                if suffix not in {".png", ".jpg", ".jpeg", ".gif"}:
                    results["errors"].append(
                        f"Unsupported preview format: {suffix or 'none'}."
                    )
                else:
                    results["passes"].append(
                        f"Preview format is {suffix.lstrip('.').upper()}."
                    )

                try:
                    preview_size = preview_path.stat().st_size
                except OSError:
                    preview_size = 0

                if preview_size > 8 * 1024 * 1024:
                    results["warnings"].append(
                        f"Preview is large ({format_file_size(preview_size)})."
                    )
                elif preview_size:
                    results["passes"].append(
                        f"Preview size is {format_file_size(preview_size)}."
                    )

                dimensions = read_image_dimensions(preview_path)

                if dimensions:
                    width, height = dimensions
                    results["passes"].append(
                        f"Preview dimensions: {width} × {height}."
                    )

                    if width < 256 or height < 256:
                        results["warnings"].append(
                            "Preview is smaller than 256 pixels on one side."
                        )

                    aspect_ratio = width / height if height else 0

                    if aspect_ratio and not 0.75 <= aspect_ratio <= 1.8:
                        results["warnings"].append(
                            "Preview has an unusually narrow or wide aspect ratio."
                        )
                else:
                    results["warnings"].append(
                        "Preview dimensions could not be read."
                    )

            # Metadata
            if not title:
                results["errors"].append("Workshop title is empty.")
            elif len(title) < 3:
                results["warnings"].append("Workshop title is very short.")
            else:
                results["passes"].append(
                    f"Workshop title contains {len(title)} characters."
                )

            if not description:
                results["errors"].append("Workshop description is empty.")
            elif len(description) < 20:
                results["warnings"].append(
                    "Workshop description is shorter than 20 characters."
                )
            else:
                results["passes"].append(
                    f"Description contains {len(description)} characters."
                )

            if not changenote:
                results["warnings"].append("Change note is empty.")
            else:
                results["passes"].append("Change note is present.")

            # IDs and upload configuration
            if mode_var.get() == "create":
                results["passes"].append(
                    "Create mode will use Published File ID 0."
                )
            elif not published_id.isdigit() or published_id == "0":
                results["errors"].append(
                    "Update mode requires a non-zero numeric Published File ID."
                )
            else:
                results["passes"].append(
                    f"Published File ID {published_id} is valid."
                )

            if upload_var.get():
                steamcmd_path = Path(steamcmd_var.get().strip()).expanduser()

                if not steamcmd_var.get().strip():
                    results["errors"].append(
                        "Automatic upload is enabled but SteamCMD is not selected."
                    )
                elif not steamcmd_path.is_file():
                    results["errors"].append("SteamCMD executable was not found.")
                else:
                    results["passes"].append("SteamCMD executable was found.")
            else:
                results["passes"].append(
                    "Automatic upload is disabled; local packaging only."
                )

            return results

        def refresh_workshop_readiness(*_args) -> dict:
            results = collect_workshop_readiness()
            readiness_results.clear()
            readiness_results.update(results)

            error_count = len(results["errors"])
            warning_count = len(results["warnings"])
            pass_count = len(results["passes"])

            if error_count:
                readiness_status_var.set(
                    f"Not ready — {error_count} error(s), "
                    f"{warning_count} warning(s)"
                )
            elif warning_count:
                readiness_status_var.set(
                    f"Ready with {warning_count} warning(s)"
                )
            else:
                readiness_status_var.set("Ready for Workshop packaging")

            detail_lines = []

            for message in results["errors"]:
                detail_lines.append(f"✖ {message}")

            for message in results["warnings"]:
                detail_lines.append(f"⚠ {message}")

            for message in results["passes"][:4]:
                detail_lines.append(f"✓ {message}")

            if pass_count > 4:
                detail_lines.append(f"✓ {pass_count - 4} more check(s) passed.")

            readiness_details_var.set("\n".join(detail_lines))
            return results

        def open_local_workshop_folder():
            path = Path(workshop_var.get().strip()).expanduser()
            if path.is_dir():
                os.startfile(path)
            else:
                messagebox.showwarning(
                    "Workshop folder",
                    "The selected Workshop folder does not exist.",
                    parent=dialog,
                )

        mode_status_var = tk.StringVar()

        def current_workshop_url() -> str:
            published_id = published_id_var.get().strip()

            if not published_id.isdigit() or published_id == "0":
                return ""

            return (
                "https://steamcommunity.com/sharedfiles/filedetails/?id="
                + published_id
            )

        def update_workshop_action_state(*_args):
            workshop_url = current_workshop_url()
            button_state = "normal" if workshop_url else "disabled"

            if "open_page_button" in action_refs:
                action_refs["open_page_button"].configure(state=button_state)
                action_refs["copy_url_button"].configure(state=button_state)

            if mode_var.get() == "create":
                mode_status_var.set(
                    "A new Workshop item will be created during upload. "
                    "The Published File ID will be recovered afterward when SteamCMD "
                    "writes it into the VDF."
                )
            elif workshop_url:
                mode_status_var.set(
                    f"Builds will update Workshop item {published_id_var.get().strip()}."
                )
            else:
                mode_status_var.set(
                    "Enter a non-zero numeric Published File ID to update an item."
                )

        def open_workshop_page():
            workshop_url = current_workshop_url()

            if not workshop_url:
                messagebox.showwarning(
                    "Workshop page",
                    "Enter an existing numeric Published File ID first.",
                    parent=dialog,
                )
                return

            webbrowser.open(workshop_url)

        def copy_workshop_url():
            workshop_url = current_workshop_url()

            if not workshop_url:
                messagebox.showwarning(
                    "Workshop page",
                    "Enter an existing numeric Published File ID first.",
                    parent=dialog,
                )
                return

            dialog.clipboard_clear()
            dialog.clipboard_append(workshop_url)
            dialog.update_idletasks()
            status_var.set("Workshop URL copied to clipboard")

        def preview_vdf():
            workshop_text = workshop_var.get().strip()
            preview_text = preview_var.get().strip()

            if not workshop_text or not preview_text:
                messagebox.showwarning(
                    "VDF Preview",
                    "Select both a Workshop folder and preview image first.",
                    parent=dialog,
                )
                return

            workshop_path = Path(workshop_text).expanduser()
            preview_source = Path(preview_text).expanduser()
            preview_destination = workshop_path / preview_source.name

            preview_text_value = build_vdf_text(
                appid_var.get().strip() or MECCHA_APP_ID,
                "0" if mode_var.get() == "create" else published_id_var.get().strip(),
                workshop_path,
                preview_destination,
                title_var.get(),
                description_text.get("1.0", "end-1c"),
                changenote_var.get(),
                visibility_var.get().strip() or "2",
            )

            preview_window = tk.Toplevel(dialog)
            preview_window.title("Workshop VDF Preview")
            preview_window.geometry("760x540")
            preview_window.minsize(620, 420)
            preview_window.transient(dialog)
            preview_window.grab_set()

            try:
                if WINDOW_ICON_PATH.is_file():
                    preview_window.iconbitmap(
                        default=str(WINDOW_ICON_PATH.resolve())
                    )
            except Exception:
                pass

            preview_container = ttk.Frame(preview_window, padding=14)
            preview_container.pack(fill="both", expand=True)

            ttk.Label(
                preview_container,
                text="Generated Workshop VDF",
                font=("Segoe UI", 15, "bold"),
            ).pack(anchor="w")
            ttk.Label(
                preview_container,
                text=(
                    "Read-only preview of the exact metadata that will be written "
                    "to my_item.vdf."
                ),
                wraplength=700,
                justify="left",
            ).pack(anchor="w", pady=(4, 10))

            preview_box = scrolledtext.ScrolledText(
                preview_container,
                wrap="none",
                font=("Consolas", 10),
                padx=10,
                pady=10,
            )
            preview_box.pack(fill="both", expand=True)
            preview_box.insert("1.0", preview_text_value)
            preview_box.configure(state="disabled")

            ttk.Button(
                preview_container,
                text="Close",
                command=preview_window.destroy,
                cursor="hand2",
            ).pack(anchor="e", pady=(10, 0))

            preview_window.bind(
                "<Escape>",
                lambda _event: preview_window.destroy(),
            )
            apply_interactive_cursors(preview_window)
            preview_window.wait_window()

        def save_workshop_settings():
            results = refresh_workshop_readiness()

            if results["errors"]:
                messagebox.showerror(
                    "Workshop Manager",
                    "Workshop settings contain blocking errors.\n\n"
                    + "\n".join(f"• {message}" for message in results["errors"]),
                    parent=dialog,
                )
                return

            published_id = published_id_var.get().strip()
            if mode_var.get() == "create":
                published_id = "0"
            elif not published_id.isdigit() or published_id == "0":
                messagebox.showerror(
                    "Workshop Manager",
                    "Update mode requires a non-zero numeric Published File ID.",
                    parent=dialog,
                )
                return

            appid = appid_var.get().strip()
            if not appid.isdigit():
                messagebox.showerror(
                    "Workshop Manager",
                    "Steam App ID must be numeric.",
                    parent=dialog,
                )
                return

            if upload_var.get() and not steamcmd_var.get().strip():
                messagebox.showerror(
                    "Workshop Manager",
                    "Select steamcmd.exe or disable automatic upload.",
                    parent=dialog,
                )
                return

            fields["workshop"].set(workshop_var.get().strip())
            fields["preview"].set(preview_var.get().strip())
            fields["appid"].set(appid)
            fields["publishedfileid"].set(published_id)
            fields["visibility"].set(visibility_var.get().strip())
            fields["title"].set(title_var.get())
            fields["description"].set(description_text.get("1.0", "end-1c"))
            fields["changenote"].set(changenote_var.get())
            fields["steamcmd"].set(steamcmd_var.get().strip())
            fields["steam_login"].set(steam_login_var.get())
            flags["upload"].set(bool(upload_var.get()))

            update_workshop_summary()
            save_settings()
            status_var.set("Workshop settings saved")
            dialog.destroy()

        ttk.Label(
            container,
            textvariable=mode_status_var,
            wraplength=700,
            justify="left",
        ).grid(
            row=6,
            column=0,
            columnspan=3,
            sticky="w",
            pady=(10, 0),
        )

        button_frame = ttk.Frame(container)
        button_frame.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(12, 0))

        ttk.Button(
            button_frame,
            text="Refresh Readiness",
            command=refresh_workshop_readiness,
            cursor="hand2",
        ).pack(side="left")

        ttk.Button(
            button_frame,
            text="Open Folder",
            command=open_local_workshop_folder,
            cursor="hand2",
        ).pack(side="left", padx=(8, 0))

        open_page_button = ttk.Button(
            button_frame,
            text="Open Page",
            command=open_workshop_page,
            cursor="hand2",
        )
        open_page_button.pack(side="left", padx=(8, 0))

        copy_url_button = ttk.Button(
            button_frame,
            text="Copy URL",
            command=copy_workshop_url,
            cursor="hand2",
        )
        copy_url_button.pack(side="left", padx=(8, 0))

        ttk.Button(
            button_frame,
            text="Preview VDF",
            command=preview_vdf,
            cursor="hand2",
        ).pack(side="left", padx=(8, 0))

        ttk.Button(
            button_frame,
            text="Cancel",
            command=dialog.destroy,
            cursor="hand2",
        ).pack(side="right")

        ttk.Button(
            button_frame,
            text="Save Settings",
            command=save_workshop_settings,
            style="Primary.TButton",
            cursor="hand2",
        ).pack(side="right", padx=(0, 8))

        action_refs["open_page_button"] = open_page_button
        action_refs["copy_url_button"] = copy_url_button

        published_id_var.trace_add("write", update_workshop_action_state)
        mode_var.trace_add("write", update_workshop_action_state)

        for readiness_variable in (
            workshop_var,
            preview_var,
            published_id_var,
            title_var,
            changenote_var,
            steamcmd_var,
            upload_var,
            mode_var,
        ):
            readiness_variable.trace_add(
                "write",
                lambda *_args: dialog.after_idle(refresh_workshop_readiness),
            )

        description_text.bind(
            "<KeyRelease>",
            lambda _event: dialog.after_idle(refresh_workshop_readiness),
        )

        sync_mode()
        refresh_workshop_readiness()
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        apply_interactive_cursors(dialog)
        dialog.wait_window()

    workshop_manager_frame = ttk.LabelFrame(
        form,
        text="Steam Workshop",
        padding=8,
    )
    workshop_manager_frame.grid(
        row=row,
        column=0,
        columnspan=3,
        sticky="ew",
        pady=(6, 4),
    )
    workshop_manager_frame.columnconfigure(0, weight=1)

    ttk.Label(
        workshop_manager_frame,
        textvariable=workshop_summary_var,
    ).grid(row=0, column=0, sticky="w")
    workshop_manager_button = ttk.Button(
        workshop_manager_frame,
        text="Workshop Manager…",
        command=open_workshop_manager,
        cursor="hand2",
    )
    workshop_manager_button.grid(row=0, column=1, padx=(10, 0))
    ToolTip(
        workshop_manager_button,
        "Configure Workshop metadata, visibility, item ID, and SteamCMD upload.",
    )
    row += 1

    def update_steamcmd_visibility():
        update_workshop_summary()

    options = ttk.LabelFrame(outer, text="Build options", padding=8)
    options.pack(fill="x", pady=(10, 0))
    ttk.Checkbutton(options, text="Build Full Game", variable=flags["build_full"]).pack(
        side="left", padx=6
    )
    ttk.Checkbutton(
        options, text="Build My Mod / DLC", variable=flags["build_mod"]
    ).pack(side="left", padx=6)
    ttk.Checkbutton(options, text="Copy only", variable=flags["copy_only"]).pack(
        side="left", padx=6
    )
    clean = ttk.Checkbutton(
        options, text="Clean Workshop first", variable=flags["clean_workshop"]
    )
    clean.pack(side="left", padx=6)
    ToolTip(clean, hints["clean_workshop"])
    upload_checkbox = ttk.Checkbutton(
        options,
        text="Upload with SteamCMD",
        variable=flags["upload"],
        command=update_steamcmd_visibility,
    )

    upload_checkbox.pack(side="left", padx=6)
    ToolTip(
        upload_checkbox,
        "Enable automatic SteamCMD upload using settings from Workshop Manager.",
    )

    update_workshop_summary()

    output_frame = ttk.LabelFrame(
        outer,
        text="Build output",
        padding=8,
    )
    output_frame.pack(fill="both", expand=True, pady=(10, 0))

    status_frame = ttk.Frame(output_frame)
    status_frame.pack(fill="x", pady=(0, 6))

    status_left = ttk.Frame(status_frame)
    status_left.pack(side="left", fill="x", expand=True)

    status_var = tk.StringVar(value="Ready")
    if interrupted_build_count:
        status_var.set(
            f"Recovered {interrupted_build_count} interrupted build record(s)"
        )

    status_title_row = ttk.Frame(status_left)
    status_title_row.pack(anchor="w", fill="x")

    spinner_state = {
        "job": None,
        "frame": 0,
        "active": False,
    }
    spinner_frames = ("◐", "◓", "◑", "◒")

    spinner_label = ttk.Label(
        status_title_row,
        text="",
        width=2,
        anchor="center",
    )
    spinner_label.pack(side="left", padx=(0, 4))

    ttk.Label(
        status_title_row,
        textvariable=status_var,
    ).pack(side="left")

    timing_var = tk.StringVar(value="Elapsed: —    Estimate: —")
    ttk.Label(
        status_left,
        textvariable=timing_var,
    ).pack(anchor="w", pady=(2, 0))

    progress = ttk.Progressbar(
        status_frame,
        mode="indeterminate",
        length=180,
    )
    progress.pack(side="right")

    def animate_busy_spinner() -> None:
        """Advance the small dependency-free Tk spinner."""
        if not spinner_state["active"]:
            spinner_label.configure(text="")
            spinner_state["job"] = None
            return

        index = spinner_state["frame"] % len(spinner_frames)
        spinner_label.configure(text=spinner_frames[index])
        spinner_state["frame"] += 1
        spinner_state["job"] = root.after(110, animate_busy_spinner)

    def set_busy_indicator(active: bool) -> None:
        """Start or stop the Tk spinner and indeterminate progress bar."""
        active = bool(active)

        if active == spinner_state["active"]:
            return

        spinner_state["active"] = active

        if active:
            progress.start(10)
            spinner_state["frame"] = 0
            animate_busy_spinner()
        else:
            progress.stop()

            if spinner_state["job"] is not None:
                try:
                    root.after_cancel(spinner_state["job"])
                except tk.TclError:
                    pass

            spinner_state["job"] = None
            spinner_label.configure(text="")

    pipeline_frame = ttk.LabelFrame(
        output_frame,
        text="Build pipeline",
        padding=(8, 6),
    )
    pipeline_frame.pack(fill="x", pady=(0, 8))

    pipeline_definitions = [
        ("validate", "Validate configuration"),
        ("build_full", "Build Full Game"),
        ("build_mod", "Build My Mod / DLC"),
        ("copy_files", "Copy Workshop files"),
        ("upload", "Upload to Steam Workshop"),
    ]

    pipeline_status_vars = {}
    pipeline_labels = {}
    pipeline_state = {
        "enabled": set(),
        "active": None,
    }

    for pipeline_row, (stage_key, stage_title) in enumerate(pipeline_definitions):
        stage_var = tk.StringVar(value=f"○  {stage_title}")
        stage_label = ttk.Label(
            pipeline_frame,
            textvariable=stage_var,
            anchor="w",
        )
        stage_label.grid(
            row=pipeline_row,
            column=0,
            sticky="w",
            pady=1,
        )
        pipeline_status_vars[stage_key] = stage_var
        pipeline_labels[stage_key] = stage_label

    pipeline_frame.columnconfigure(0, weight=1)

    def pipeline_stage_title(stage_key: str) -> str:
        for key, title in pipeline_definitions:
            if key == stage_key:
                return title
        return stage_key.replace("_", " ").title()

    def set_pipeline_stage(stage_key: str, state: str) -> None:
        """Update one build-pipeline row without relying on external assets."""
        if stage_key not in pipeline_status_vars:
            return

        symbols = {
            "pending": "○",
            "active": "⏳",
            "complete": "✓",
            "skipped": "—",
            "failed": "✗",
            "cancelled": "■",
        }
        symbol = symbols.get(state, "○")
        title = pipeline_stage_title(stage_key)
        pipeline_status_vars[stage_key].set(f"{symbol}  {title}")

        if state == "active":
            pipeline_state["active"] = stage_key
        elif pipeline_state.get("active") == stage_key:
            pipeline_state["active"] = None

    def configure_build_pipeline() -> None:
        """Prepare pipeline rows from the currently selected build options."""
        enabled = {"validate", "copy_files"}

        if not flags["copy_only"].get():
            if flags["build_full"].get():
                enabled.add("build_full")
            if flags["build_mod"].get():
                enabled.add("build_mod")

        if flags["upload"].get():
            enabled.add("upload")

        pipeline_state["enabled"] = enabled
        pipeline_state["active"] = None

        for stage_key, _stage_title in pipeline_definitions:
            set_pipeline_stage(
                stage_key,
                "pending" if stage_key in enabled else "skipped",
            )

    def activate_pipeline_stage(stage_key: str) -> None:
        """Complete the previous active stage and activate the next stage."""
        previous = pipeline_state.get("active")

        if previous and previous != stage_key:
            set_pipeline_stage(previous, "complete")

        if stage_key in pipeline_state.get("enabled", set()):
            set_pipeline_stage(stage_key, "active")

    def finish_pipeline_successfully() -> None:
        """Mark every enabled pipeline stage as completed."""
        for stage_key, _stage_title in pipeline_definitions:
            if stage_key in pipeline_state.get("enabled", set()):
                set_pipeline_stage(stage_key, "complete")

        pipeline_state["active"] = None

    def finish_pipeline_with_state(state: str) -> None:
        """Mark the current stage as failed or cancelled."""
        active_stage = pipeline_state.get("active")

        if active_stage:
            set_pipeline_stage(active_stage, state)

        pipeline_state["active"] = None

    configure_build_pipeline()

    console_toolbar = ttk.Frame(output_frame)
    console_toolbar.pack(fill="x", pady=(0, 4))

    auto_scroll_var = tk.BooleanVar(value=True)

    ttk.Label(
        console_toolbar,
        text="Live build log",
        font=("Segoe UI", 9, "bold"),
    ).pack(side="left")

    ttk.Checkbutton(
        console_toolbar,
        text="Auto-scroll",
        variable=auto_scroll_var,
    ).pack(side="right")

    output_box = scrolledtext.ScrolledText(
        output_frame,
        height=12,
        wrap="word",
        font=("Consolas", 9),
        state="disabled",
    )
    output_box.pack(fill="both", expand=True)
    locals_ref["output_box"] = output_box

    console_menu = tk.Menu(output_box, tearoff=False)
    console_menu.add_command(
        label="Copy",
        command=lambda: output_box.event_generate("<<Copy>>"),
    )
    console_menu.add_command(
        label="Select All",
        command=lambda: (
            output_box.tag_add("sel", "1.0", "end-1c"),
            output_box.mark_set("insert", "1.0"),
            output_box.see("insert"),
        ),
    )
    console_menu.add_separator()
    console_menu.add_command(
        label="Clear",
        command=lambda: (
            output_box.configure(state="normal"),
            output_box.delete("1.0", "end"),
            output_box.configure(state="disabled"),
        ),
    )

    def show_console_menu(event):
        try:
            console_menu.tk_popup(event.x_root, event.y_root)
        finally:
            console_menu.grab_release()

    output_box.bind("<Button-3>", show_console_menu)

    apply_theme()

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
        "estimated_seconds": None,
        "estimate_sample_count": 0,
        "mode": None,
        "configuration": None,
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

    def classify_console_line(line: str) -> str:
        """Return the display tag used for one console line."""
        stripped = line.strip()
        lowered = stripped.lower()

        if not stripped:
            return "normal"

        if stripped.startswith("===") and stripped.endswith("==="):
            return "heading"

        if lowered.startswith(("error", "fatal", "exception", "traceback")):
            return "error"

        if any(
            token in lowered
            for token in (
                " error:",
                "error c",
                "failed",
                "failure",
                "could not",
                "missing ",
                "not found",
                "recursionerror",
            )
        ):
            return "error"

        if lowered.startswith(("warning", "warn")) or " warning:" in lowered:
            return "warning"

        if any(
            token in lowered
            for token in (
                "completed successfully",
                "build succeeded",
                "success",
                "copied:",
                "wrote vdf:",
                "fallback located",
            )
        ):
            return "success"

        if stripped.startswith(("python ", '"')) or " --" in stripped:
            return "command"

        if lowered.startswith(
            (
                "build id:",
                "log file:",
                "elapsed:",
                "estimated",
                "skipping ",
                "copy-only mode",
            )
        ):
            return "info"

        return "normal"

    def log(text):
        """
        Append raw text to the persistent log and a timestamped, color-classified
        representation to the visible console.
        """
        text = str(text)
        append_to_active_log(text)

        output_box.configure(state="normal")

        for line in text.splitlines(keepends=True):
            has_newline = line.endswith(("\n", "\r"))
            visible_line = line.rstrip("\r\n")
            timestamp = datetime.now().strftime("[%H:%M:%S] ")

            output_box.insert("end", timestamp, ("timestamp",))
            output_box.insert(
                "end",
                visible_line,
                (classify_console_line(visible_line),),
            )

            if has_newline:
                output_box.insert("end", "\n", ("normal",))

        if text and not text.endswith(("\n", "\r")):
            # Preserve the old behavior for partial messages without forcing a
            # newline that was not present in the source stream.
            pass

        if auto_scroll_var.get():
            output_box.see("end")

        output_box.configure(state="disabled")

    def update_build_timing_display():
        """Refresh elapsed, estimated, and remaining build time."""
        process = process_holder.get("process")
        started_at = build_state.get("started_at")

        if process is None or process.poll() is not None or started_at is None:
            return

        elapsed_seconds = calculate_duration_seconds(started_at)

        if elapsed_seconds is None:
            timing_var.set("Elapsed: —    Estimate: —")
            return

        estimated_seconds = build_state.get("estimated_seconds")

        if estimated_seconds:
            remaining_seconds = max(
                0,
                float(estimated_seconds) - elapsed_seconds,
            )

            timing_var.set(
                f"Elapsed: {format_duration(elapsed_seconds)}    "
                f"Estimated total: {format_duration(estimated_seconds)}    "
                f"Remaining: ~{format_duration(remaining_seconds)}"
            )
        else:
            timing_var.set(
                f"Elapsed: {format_duration(elapsed_seconds)}    "
                "Estimate: learning from build history"
            )

        root.after(1000, update_build_timing_display)

    def show_finished_timing(
        status: str,
        duration_seconds,
    ) -> None:
        """Show the final elapsed duration after a build ends."""
        timing_var.set(
            f"Elapsed: {format_duration(duration_seconds)}    " f"Result: {status}"
        )

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
            "flags": {key: bool(variable.get()) for key, variable in flags.items()},
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

        build_state.update(
            {
                "id": build_id,
                "log_path": log_path,
                "started_at": started_at,
                "cancel_requested": False,
                "record_active": True,
            }
        )

        safe_command = redact_command_for_log(cmd)
        safe_command_text = subprocess.list2cmdline(safe_command)

        configuration = create_build_snapshot()
        estimate = get_build_time_estimate(configuration)

        build_state.update(
            {
                "estimated_seconds": estimate.get("estimated_seconds"),
                "estimate_sample_count": estimate.get("sample_count", 0),
                "mode": estimate.get("mode"),
                "configuration": configuration,
            }
        )

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
            "configuration": configuration,
            "estimate": {
                "mode": estimate.get("mode"),
                "mode_label": estimate.get("mode_label"),
                "sample_count": estimate.get("sample_count", 0),
                "estimated_seconds": estimate.get("estimated_seconds"),
            },
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
            f"Build Mode:     {estimate.get('mode_label', 'Unknown')}\n"
            f"Estimate:       "
            f"{format_duration(estimate.get('estimated_seconds'))}\n"
            f"Estimate Data:  "
            f"{estimate.get('sample_count', 0)} successful build(s)\n"
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
        duration_seconds = calculate_duration_seconds(build_state.get("started_at"))

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
        build_state.update(
            {
                "id": None,
                "log_path": None,
                "started_at": None,
                "cancel_requested": False,
                "record_active": False,
                "estimated_seconds": None,
                "estimate_sample_count": 0,
                "mode": None,
                "configuration": None,
            }
        )

    def refresh_plugins():
        plugins = []
        project_text = fields["project"].get().strip()
        if project_text:
            plugin_dir = Path(project_text).parent / "Plugins"
            if plugin_dir.exists():
                plugins = sorted(
                    {p.stem for p in plugin_dir.glob("*/*.uplugin")}, key=str.lower
                )
        plugin_combo["values"] = plugins
        # Do not silently choose a plugin. Wrong plugin = wrong DLC output.
        if fields["plugin"].get() not in plugins:
            fields["plugin"].set("")
        status_var.set(f"Found {len(plugins)} plugin(s); select the asset plugin")
        update_path_control_states()

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

    ttk.Button(
        profile_bar,
        text="Save",
        command=save_profile,
        cursor="hand2",
    ).grid(row=1, column=1, padx=(0, 4), sticky="ew")
    ttk.Button(
        profile_bar,
        text="Load",
        command=load_profile,
        cursor="hand2",
    ).grid(row=1, column=2, padx=4, sticky="ew")
    ttk.Button(
        profile_bar,
        text="Delete",
        command=delete_profile,
        cursor="hand2",
    ).grid(row=1, column=3, padx=4, sticky="ew")
    open_profiles_button = ttk.Button(
        profile_bar,
        text="Folder",
        command=lambda: os.startfile(PROFILES_DIR),
        cursor="hand2",
    )
    open_profiles_button.grid(row=1, column=4, padx=(4, 0), sticky="ew")

    for column in range(4):
        profile_bar.columnconfigure(column, weight=1)

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
            results.append(
                validation_result(
                    "error",
                    "Unreal Automation Tool path is missing",
                    "Select UE 5.6 RunUAT.bat.",
                )
            )
        else:
            ue_path = Path(ue_text).expanduser()

            if not ue_path.is_file():
                results.append(
                    validation_result(
                        "error",
                        "Unreal Automation Tool was not found",
                        str(ue_path),
                    )
                )
            elif ue_path.name.lower() != "runuat.bat":
                results.append(
                    validation_result(
                        "warning",
                        "Selected Unreal tool is not named RunUAT.bat",
                        str(ue_path),
                    )
                )
            else:
                unreal_version = detect_unreal_version(ue_path)

                if unreal_version:
                    level = "pass" if unreal_version.startswith("5.6") else "warning"

                    results.append(
                        validation_result(
                            level,
                            f"Unreal Engine {unreal_version} found",
                            str(ue_path),
                        )
                    )

                    if not unreal_version.startswith("5.6"):
                        results.append(
                            validation_result(
                                "warning",
                                "The Meccha Mod Kit expects Unreal Engine 5.6",
                                f"Selected installation appears to be Unreal Engine {unreal_version}.",
                            )
                        )
                else:
                    results.append(
                        validation_result(
                            "pass",
                            "Unreal Automation Tool found",
                            str(ue_path),
                        )
                    )

                    results.append(
                        validation_result(
                            "warning",
                            "Unreal version could not be identified from the path",
                            "Confirm that this RunUAT.bat belongs to Unreal Engine 5.6.",
                        )
                    )

        # ---------------------------------------------------------
        # Unreal project
        # ---------------------------------------------------------
        project = None

        if not project_text:
            results.append(
                validation_result(
                    "error",
                    "Meccha project path is missing",
                    "Select the Meccha .uproject file.",
                )
            )
        else:
            project = Path(project_text).expanduser()

            if not project.is_file():
                results.append(
                    validation_result(
                        "error",
                        "Meccha project was not found",
                        str(project),
                    )
                )
                project = None

            elif project.suffix.lower() != ".uproject":
                results.append(
                    validation_result(
                        "error",
                        "Selected project is not a .uproject file",
                        str(project),
                    )
                )
                project = None

            else:
                project_data, project_error = inspect_json_descriptor(project)

                if project_error:
                    results.append(
                        validation_result(
                            "error",
                            "The .uproject descriptor is invalid",
                            project_error,
                        )
                    )
                else:
                    results.append(
                        validation_result(
                            "pass",
                            "Meccha project found",
                            str(project),
                        )
                    )

                    engine_association = str(
                        project_data.get("EngineAssociation", "")
                    ).strip()

                    if engine_association:
                        results.append(
                            validation_result(
                                "pass",
                                f"Project EngineAssociation: {engine_association}",
                            )
                        )
                    else:
                        results.append(
                            validation_result(
                                "warning",
                                "The project has no EngineAssociation value",
                                "This may be intentional for a source-built Unreal project.",
                            )
                        )

        # ---------------------------------------------------------
        # Plugin
        # ---------------------------------------------------------
        plugin_root = None
        plugin_descriptor = None

        if not plugin_name:
            results.append(
                validation_result(
                    "error",
                    "Asset plugin is not selected",
                    "Select the plugin containing the map assets.",
                )
            )

        elif project is not None:
            plugin_root = project.parent / "Plugins" / plugin_name

            if not plugin_root.is_dir():
                results.append(
                    validation_result(
                        "error",
                        "Plugin folder was not found",
                        str(plugin_root),
                    )
                )
            else:
                descriptors = sorted(plugin_root.glob("*.uplugin"))

                if not descriptors:
                    results.append(
                        validation_result(
                            "error",
                            "Plugin descriptor was not found",
                            f"No .uplugin file exists in:\n{plugin_root}",
                        )
                    )

                elif len(descriptors) > 1:
                    results.append(
                        validation_result(
                            "warning",
                            "Multiple .uplugin descriptors were found",
                            "\n".join(str(path) for path in descriptors),
                        )
                    )
                    plugin_descriptor = descriptors[0]

                else:
                    plugin_descriptor = descriptors[0]

                if plugin_descriptor is not None:
                    plugin_data, plugin_error = inspect_json_descriptor(
                        plugin_descriptor
                    )

                    if plugin_error:
                        results.append(
                            validation_result(
                                "error",
                                "Plugin descriptor contains invalid JSON",
                                plugin_error,
                            )
                        )
                    else:
                        results.append(
                            validation_result(
                                "pass",
                                f"Plugin found: {plugin_name}",
                                str(plugin_root),
                            )
                        )

                        if plugin_descriptor.stem != plugin_name:
                            results.append(
                                validation_result(
                                    "warning",
                                    "Plugin folder and descriptor names differ",
                                    (
                                        f"Folder: {plugin_name}\n"
                                        f"Descriptor: {plugin_descriptor.name}"
                                    ),
                                )
                            )
                        else:
                            results.append(
                                validation_result(
                                    "pass",
                                    "Plugin folder and descriptor names match",
                                    plugin_descriptor.name,
                                )
                            )

                        can_contain_content = plugin_data.get(
                            "CanContainContent",
                            False,
                        )

                        if can_contain_content is True:
                            results.append(
                                validation_result(
                                    "pass",
                                    "Plugin allows content",
                                    "CanContainContent is enabled.",
                                )
                            )
                        else:
                            results.append(
                                validation_result(
                                    "error",
                                    "Plugin does not allow content",
                                    (
                                        "CanContainContent is false or missing in the "
                                        ".uplugin descriptor."
                                    ),
                                )
                            )

        # ---------------------------------------------------------
        # Runtime map
        # ---------------------------------------------------------
        map_format_valid = True

        if not map_path:
            results.append(
                validation_result(
                    "error",
                    "Runtime map path is missing",
                    "Example: /Game/Mods/UserMap01/MyMap",
                )
            )
            map_format_valid = False

        else:
            if not map_path.startswith("/"):
                results.append(
                    validation_result(
                        "error",
                        "Runtime map path must begin with '/'",
                        map_path,
                    )
                )
                map_format_valid = False

            if map_path.lower().endswith(".umap"):
                results.append(
                    validation_result(
                        "error",
                        "Remove the .umap extension from the runtime map path",
                        map_path,
                    )
                )
                map_format_valid = False

            map_leaf = map_path.rstrip("/").rsplit("/", 1)[-1]

            if "." in map_leaf:
                results.append(
                    validation_result(
                        "error",
                        "Use a package path rather than Object.Object syntax",
                        map_path,
                    )
                )
                map_format_valid = False

            if map_format_valid:
                if map_path.startswith("/Game/Mods/UserMap01/"):
                    results.append(
                        validation_result(
                            "pass",
                            "Runtime map path uses Meccha's expected folder",
                            map_path,
                        )
                    )
                else:
                    results.append(
                        validation_result(
                            "warning",
                            "Runtime map path uses an unusual folder",
                            (
                                f"{map_path}\n\n"
                                "Known working Meccha location:\n"
                                "/Game/Mods/UserMap01/MapName"
                            ),
                        )
                    )

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

                        results.append(
                            validation_result(
                                "pass",
                                "Matching .umap file found",
                                details,
                            )
                        )
                    else:
                        results.append(
                            validation_result(
                                "warning",
                                "No matching .umap filename was found",
                                (
                                    "The build may still work if Meccha remaps or copies "
                                    "the map to its runtime path.\n\n"
                                    f"Searched for: {map_leaf}.umap"
                                ),
                            )
                        )

        # ---------------------------------------------------------
        # Release
        # ---------------------------------------------------------
        if not release:
            results.append(
                validation_result(
                    "error",
                    "Release version is missing",
                )
            )
        elif not re.fullmatch(r"\d+(?:\.\d+)*", release):
            results.append(
                validation_result(
                    "warning",
                    "Release version uses an unusual format",
                    release,
                )
            )
        else:
            results.append(
                validation_result(
                    "pass",
                    f"Release version is valid: {release}",
                )
            )

        # ---------------------------------------------------------
        # Workshop directory
        # ---------------------------------------------------------
        if not workshop_text:
            results.append(
                validation_result(
                    "error",
                    "Workshop folder is missing",
                    "Select the staging folder for the Workshop payload.",
                )
            )
        else:
            workshop = Path(workshop_text).expanduser()

            if workshop.exists():
                if not workshop.is_dir():
                    results.append(
                        validation_result(
                            "error",
                            "Workshop path is not a directory",
                            str(workshop),
                        )
                    )
                elif not os.access(workshop, os.W_OK):
                    results.append(
                        validation_result(
                            "error",
                            "Workshop folder is not writable",
                            str(workshop),
                        )
                    )
                else:
                    results.append(
                        validation_result(
                            "pass",
                            "Workshop folder is writable",
                            str(workshop),
                        )
                    )
            else:
                existing_parent = workshop.parent

                while (
                    not existing_parent.exists()
                    and existing_parent != existing_parent.parent
                ):
                    existing_parent = existing_parent.parent

                if existing_parent.is_dir() and os.access(existing_parent, os.W_OK):
                    results.append(
                        validation_result(
                            "warning",
                            "Workshop folder does not exist yet",
                            (
                                f"{workshop}\n\n"
                                "The folder will be created when the build starts."
                            ),
                        )
                    )
                else:
                    results.append(
                        validation_result(
                            "error",
                            "Workshop folder cannot be created",
                            (
                                f"Target: {workshop}\n"
                                f"Nearest existing parent: {existing_parent}"
                            ),
                        )
                    )

        # ---------------------------------------------------------
        # Preview image
        # ---------------------------------------------------------
        if not preview_text:
            results.append(
                validation_result(
                    "error",
                    "Workshop preview image is missing",
                )
            )
        else:
            preview = Path(preview_text).expanduser()

            if not preview.is_file():
                results.append(
                    validation_result(
                        "error",
                        "Workshop preview image was not found",
                        str(preview),
                    )
                )
            elif preview.suffix.lower() not in {
                ".png",
                ".jpg",
                ".jpeg",
                ".webp",
            }:
                results.append(
                    validation_result(
                        "warning",
                        "Preview image uses an unusual format",
                        (
                            f"{preview.suffix or 'No extension'}\n"
                            "PNG, JPG, JPEG, or WEBP is recommended."
                        ),
                    )
                )
            else:
                try:
                    size_bytes = preview.stat().st_size

                    if size_bytes <= 0:
                        results.append(
                            validation_result(
                                "error",
                                "Preview image is empty",
                                str(preview),
                            )
                        )
                    else:
                        results.append(
                            validation_result(
                                "pass",
                                "Workshop preview image found",
                                (f"{preview}\n" f"Size: {size_bytes:,} bytes"),
                            )
                        )
                except OSError as exc:
                    results.append(
                        validation_result(
                            "error",
                            "Preview image could not be inspected",
                            str(exc),
                        )
                    )

        # ---------------------------------------------------------
        # Steam Workshop identifiers
        # ---------------------------------------------------------
        if not appid:
            results.append(
                validation_result(
                    "error",
                    "Steam App ID is missing",
                )
            )
        elif not appid.isdigit():
            results.append(
                validation_result(
                    "error",
                    "Steam App ID must be numeric",
                    appid,
                )
            )
        elif appid != MECCHA_APP_ID:
            results.append(
                validation_result(
                    "warning",
                    "Steam App ID differs from Meccha Chameleon",
                    (f"Selected: {appid}\n" f"Expected: {MECCHA_APP_ID}"),
                )
            )
        else:
            results.append(
                validation_result(
                    "pass",
                    f"Meccha Steam App ID confirmed: {appid}",
                )
            )

        if not publishedfileid:
            results.append(
                validation_result(
                    "error",
                    "Published File ID is missing",
                )
            )
        elif not publishedfileid.isdigit():
            results.append(
                validation_result(
                    "error",
                    "Published File ID must be numeric",
                    publishedfileid,
                )
            )
        elif publishedfileid == "0":
            results.append(
                validation_result(
                    "warning",
                    "Published File ID is 0",
                    "SteamCMD will create a new Workshop item.",
                )
            )
        else:
            results.append(
                validation_result(
                    "pass",
                    "Existing Workshop item will be updated",
                    f"Published File ID: {publishedfileid}",
                )
            )

        # ---------------------------------------------------------
        # Build options
        # ---------------------------------------------------------
        if (
            not flags["copy_only"].get()
            and not flags["build_full"].get()
            and not flags["build_mod"].get()
        ):
            results.append(
                validation_result(
                    "error",
                    "No build operation is selected",
                    (
                        "Enable Build Full Game, Build My Mod / DLC, "
                        "or choose Copy only."
                    ),
                )
            )
        elif flags["copy_only"].get():
            results.append(
                validation_result(
                    "warning",
                    "Copy-only mode is enabled",
                    "No Unreal build commands will run.",
                )
            )
        else:
            if flags["build_full"].get():
                results.append(
                    validation_result(
                        "pass",
                        "Full-game build is enabled",
                    )
                )
            else:
                results.append(
                    validation_result(
                        "warning",
                        "Full-game build will be skipped",
                    )
                )

            if flags["build_mod"].get():
                results.append(
                    validation_result(
                        "pass",
                        "My Mod / DLC build is enabled",
                    )
                )
            else:
                results.append(
                    validation_result(
                        "warning",
                        "My Mod / DLC build will be skipped",
                    )
                )

        # ---------------------------------------------------------
        # SteamCMD upload
        # ---------------------------------------------------------
        if flags["upload"].get():
            steamcmd_text = fields["steamcmd"].get().strip()

            if not steamcmd_text:
                results.append(
                    validation_result(
                        "error",
                        "SteamCMD is required because upload is enabled",
                    )
                )
            else:
                steamcmd = Path(steamcmd_text).expanduser()

                if not steamcmd.is_file():
                    results.append(
                        validation_result(
                            "error",
                            "SteamCMD was not found",
                            str(steamcmd),
                        )
                    )
                elif steamcmd.name.lower() != "steamcmd.exe":
                    results.append(
                        validation_result(
                            "warning",
                            "Selected upload executable is not named steamcmd.exe",
                            str(steamcmd),
                        )
                    )
                else:
                    results.append(
                        validation_result(
                            "pass",
                            "SteamCMD found",
                            str(steamcmd),
                        )
                    )

            if fields["steam_login"].get().strip():
                results.append(
                    validation_result(
                        "warning",
                        "Steam login arguments are populated",
                        (
                            "Credentials may be visible in process arguments and logs.\n"
                            "Using an existing SteamCMD login is recommended."
                        ),
                    )
                )
            else:
                results.append(
                    validation_result(
                        "pass",
                        "No Steam credentials are stored in the build command",
                    )
                )
        else:
            results.append(
                validation_result(
                    "pass",
                    "Automatic SteamCMD upload is disabled",
                    "The Workshop payload will be prepared locally.",
                )
            )
        # ---------------------------------------------------------
        # Running Unreal Editor
        # ---------------------------------------------------------
        running_unreal_processes = find_running_unreal_processes()

        if running_unreal_processes:
            results.append(
                validation_result(
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
                )
            )
        else:
            results.append(
                validation_result(
                    "pass",
                    "Unreal Editor is not running",
                )
            )

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
                    (f"• {path.name} — {describe_file_age(path)}\n" f"  {path}")
                    for path in shown_files
                ]

                if len(recovery_files) > len(shown_files):
                    recovery_details.append(
                        f"...and {len(recovery_files) - len(shown_files)} more"
                    )

                results.append(
                    validation_result(
                        "warning",
                        "Potential Unreal recovery or autosave files were found",
                        (
                            "This does not necessarily mean assets are currently "
                            "unsaved. Save all work in Unreal before building.\n\n"
                            + "\n".join(recovery_details)
                        ),
                    )
                )
            else:
                results.append(
                    validation_result(
                        "pass",
                        "No Unreal autosave or recovery files were found",
                        (
                            "No recovery files were found in the project's standard "
                            "Saved\\Autosaves or Saved\\Backup folders."
                        ),
                    )
                )

        # ---------------------------------------------------------
        # Historical build-time estimate
        # ---------------------------------------------------------
        estimate_configuration = {
            "flags": {key: bool(variable.get()) for key, variable in flags.items()},
        }

        estimate = get_build_time_estimate(estimate_configuration)

        if estimate["available"]:
            results.append(
                validation_result(
                    "pass",
                    "Historical build-time estimate is available",
                    (
                        f"Mode: {estimate['mode_label']}\n"
                        f"Estimated total: "
                        f"{format_duration(estimate['estimated_seconds'])}\n"
                        f"Based on {estimate['sample_count']} successful "
                        "comparable build(s)."
                    ),
                )
            )
        else:
            results.append(
                validation_result(
                    "warning",
                    "Build-time estimate is still learning",
                    (
                        f"Mode: {estimate['mode_label']}\n"
                        f"Successful comparable builds: "
                        f"{estimate['sample_count']}\n\n"
                        "At least two successful builds in this mode are needed "
                        "before an estimate is shown."
                    ),
                )
            )

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

        apply_window_icon(report_window, remember_key="validation_report")

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
            readiness_text = "Build blocked — resolve all errors before continuing."
        elif counts["warning"]:
            readiness_text = "Ready with warnings — review them before continuing."
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

        cmd.extend(
            [
                "--ue",
                fields["ue"].get().strip(),
                "--project",
                fields["project"].get().strip(),
                "--plugin",
                fields["plugin"].get().strip(),
                "--map",
                fields["map"].get().strip(),
                "--release",
                fields["release"].get().strip(),
                "--workshop",
                fields["workshop"].get().strip(),
                "--preview",
                fields["preview"].get().strip(),
                "--appid",
                fields["appid"].get().strip(),
                "--publishedfileid",
                fields["publishedfileid"].get().strip(),
                "--visibility",
                fields["visibility"].get().strip(),
                "--title",
                fields["title"].get(),
                "--description",
                fields["description"].get(),
                "--changenote",
                fields["changenote"].get(),
            ]
        )

        if not flags["build_full"].get():
            cmd.append("--skip-full-game")

        if not flags["build_mod"].get():
            cmd.append("--skip-mod")

        if flags["copy_only"].get():
            cmd.append("--copy-only")

        if flags["clean_workshop"].get():
            cmd.append("--clean-workshop")

        if flags["upload"].get():
            cmd.extend(
                [
                    "--upload",
                    "--steamcmd",
                    fields["steamcmd"].get().strip(),
                ]
            )

            if fields["steam_login"].get().strip():
                cmd.extend(
                    [
                        "--steam-login",
                        fields["steam_login"].get().strip(),
                    ]
                )

        return cmd

    def reader_thread(process):
        try:
            for line in iter(process.stdout.readline, ""):
                messages.put(("log", line))
            messages.put(("done", process.wait()))
        except Exception as exc:
            messages.put(("error", str(exc)))

    def recover_created_workshop_item_id() -> str:
        """
        Recover a new Published File ID after a successful SteamCMD upload.

        SteamCMD may replace publishedfileid "0" inside my_item.vdf with the
        newly created item ID.
        """
        configuration = build_state.get("configuration")

        if not isinstance(configuration, dict):
            return ""

        build_flags = configuration.get("flags", {})

        if not isinstance(build_flags, dict) or not build_flags.get("upload"):
            return ""

        original_id = str(configuration.get("publishedfileid", "")).strip()

        if original_id not in {"", "0"}:
            return ""

        workshop_text = str(configuration.get("workshop", "")).strip()

        if not workshop_text:
            return ""

        vdf_path = Path(workshop_text).expanduser() / "my_item.vdf"
        recovered_id = read_published_file_id_from_vdf(vdf_path)

        if not recovered_id:
            return ""

        updated_configuration = dict(configuration)
        updated_configuration["publishedfileid"] = recovered_id

        update_build_history_record(
            str(build_state.get("id", "")),
            {
                "configuration": updated_configuration,
                "recovered_publishedfileid": recovered_id,
            },
        )

        should_save = messagebox.askyesno(
            "Workshop item created",
            (
                "SteamCMD created a new Workshop item.\n\n"
                f"Published File ID: {recovered_id}\n\n"
                "Save this ID to the current Workshop settings?"
            ),
        )

        if should_save:
            fields["publishedfileid"].set(recovered_id)
            update_workshop_summary()
            save_settings()
            status_var.set(f"Saved new Workshop item ID {recovered_id}")

        return recovered_id

    def start_build():
        results = collect_preflight_results()

        if not show_preflight_report(results):
            status_var.set("Build cancelled during validation")
            return

        save_settings()

        configure_build_pipeline()
        set_pipeline_stage("validate", "complete")

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
            finish_pipeline_with_state("failed")

            finish_build_record(
                status="launch_error",
                exit_code=None,
                error=error_text,
            )

            timing_var.set("Elapsed: 0s    Result: Launch error")
            reset_active_build_state()

            messagebox.showerror(
                "Failed to start",
                error_text,
            )
            return

        process_holder["process"] = process
        estimate_seconds = build_state.get("estimated_seconds")
        estimate_samples = build_state.get("estimate_sample_count", 0)

        if estimate_seconds:
            timing_var.set(
                "Elapsed: 0s    "
                f"Estimated total: {format_duration(estimate_seconds)}    "
                f"Based on: {estimate_samples} successful build(s)"
            )
        else:
            timing_var.set("Elapsed: 0s    " "Estimate: learning from build history")

        build_button.configure(state="disabled")
        validate_button.configure(state="disabled")
        cancel_button.configure(state="normal")
        set_busy_indicator(True)

        if "build_full" in pipeline_state["enabled"]:
            activate_pipeline_stage("build_full")
        elif "build_mod" in pipeline_state["enabled"]:
            activate_pipeline_stage("build_mod")
        else:
            activate_pipeline_stage("copy_files")

        status_var.set("Building…")
        update_build_timing_display()

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

            log("\n=== CANCELLATION REQUESTED ===\n" f"{current_local_timestamp()}\n\n")

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
                    marker_match = re.fullmatch(
                        r"=== PIPELINE:([A-Z_]+) ===\s*",
                        str(value),
                    )

                    if marker_match:
                        marker_to_stage = {
                            "BUILD_FULL": "build_full",
                            "BUILD_MOD": "build_mod",
                            "COPY_FILES": "copy_files",
                            "UPLOAD": "upload",
                        }
                        stage_key = marker_to_stage.get(marker_match.group(1))

                        if stage_key:
                            activate_pipeline_stage(stage_key)
                    else:
                        log(value)

                elif kind == "done":
                    set_busy_indicator(False)
                    build_button.configure(state="normal")
                    validate_button.configure(state="normal")
                    cancel_button.configure(state="disabled")
                    process_holder["process"] = None

                    # Calculate this once before entering any result branch.
                    final_duration = calculate_duration_seconds(
                        build_state.get("started_at")
                    )

                    was_cancelled = bool(build_state.get("cancel_requested"))

                    log_path = build_state.get("log_path")

                    if was_cancelled:
                        finish_pipeline_with_state("cancelled")
                        finish_build_record(
                            status="cancelled",
                            exit_code=value,
                        )

                        status_var.set("Build cancelled")

                        show_finished_timing(
                            "Cancelled",
                            final_duration,
                        )

                        messagebox.showwarning(
                            "Meccha Builder",
                            "The build was cancelled.\n\n" f"Log saved to:\n{log_path}",
                        )

                    elif value == 0:
                        finish_pipeline_successfully()
                        finish_build_record(
                            status="success",
                            exit_code=value,
                        )

                        recovered_workshop_id = recover_created_workshop_item_id()
                        rebuild_build_statistics()

                        status_var.set("Build completed successfully")

                        show_finished_timing(
                            "Success",
                            final_duration,
                        )

                        workshop_result = (
                            f"\nNew Workshop ID: {recovered_workshop_id}\n"
                            if recovered_workshop_id
                            else ""
                        )

                        messagebox.showinfo(
                            "Meccha Builder",
                            "Build completed successfully.\n\n"
                            f"Duration: {format_duration(final_duration)}\n"
                            f"{workshop_result}"
                            f"Log saved to:\n{log_path}",
                        )

                    else:
                        finish_pipeline_with_state("failed")
                        finish_build_record(
                            status="failed",
                            exit_code=value,
                            error=f"Process exited with code {value}",
                        )

                        status_var.set(f"Build failed with exit code {value}")

                        show_finished_timing(
                            "Failed",
                            final_duration,
                        )

                        messagebox.showerror(
                            "Meccha Builder",
                            f"Build failed with exit code {value}.\n"
                            "Review the log.\n\n"
                            f"Duration: {format_duration(final_duration)}\n"
                            f"Log saved to:\n{log_path}",
                        )

                    reset_active_build_state()

                elif kind == "error":
                    set_busy_indicator(False)
                    build_button.configure(state="normal")
                    validate_button.configure(state="normal")
                    cancel_button.configure(state="disabled")
                    process_holder["process"] = None

                    final_duration = calculate_duration_seconds(
                        build_state.get("started_at")
                    )

                    error_text = str(value)
                    log_path = build_state.get("log_path")
                    finish_pipeline_with_state("failed")

                    finish_build_record(
                        status="failed",
                        exit_code=None,
                        error=error_text,
                    )

                    status_var.set("Build failed")

                    show_finished_timing(
                        "Failed",
                        final_duration,
                    )

                    messagebox.showerror(
                        "Meccha Builder",
                        f"{error_text}\n\n"
                        f"Duration: {format_duration(final_duration)}\n"
                        f"Log saved to:\n{log_path}",
                    )

                    reset_active_build_state()

        except queue.Empty:
            pass
        root.after(100, poll_queue)

    def create_cursor_from_png(
        png_path: Path,
        cursor_path: Path,
        hotspot_x: int = 0,
        hotspot_y: int = 0,
    ) -> Path | None:
        """
        Wrap a PNG inside a Windows CUR container using only Python's standard
        library. Modern Windows accepts PNG-compressed cursor images.
        """
        if os.name != "nt" or not png_path.is_file():
            return None

        try:
            png_data = png_path.read_bytes()

            if not png_data.startswith(b"\x89PNG\r\n\x1a\n"):
                raise ValueError("Cursor source is not a valid PNG.")

            if len(png_data) < 24:
                raise ValueError("Cursor PNG is incomplete.")

            width = int.from_bytes(png_data[16:20], "big")
            height = int.from_bytes(png_data[20:24], "big")

            if not (1 <= width <= 256 and 1 <= height <= 256):
                raise ValueError(
                    "Cursor PNG dimensions must be between 1 and 256 pixels."
                )

            hotspot_x = max(0, min(int(hotspot_x), width - 1))
            hotspot_y = max(0, min(int(hotspot_y), height - 1))

            width_byte = 0 if width == 256 else width
            height_byte = 0 if height == 256 else height

            header = (
                (0).to_bytes(2, "little")
                + (2).to_bytes(2, "little")
                + (1).to_bytes(2, "little")
            )
            entry = (
                bytes((width_byte, height_byte, 0, 0))
                + hotspot_x.to_bytes(2, "little")
                + hotspot_y.to_bytes(2, "little")
                + len(png_data).to_bytes(4, "little")
                + (22).to_bytes(4, "little")
            )

            cursor_path.parent.mkdir(parents=True, exist_ok=True)
            cursor_path.write_bytes(header + entry + png_data)
            return cursor_path
        except (OSError, ValueError) as exc:
            print(f"Could not create custom cursor: {exc}")
            return None

    custom_cursor_path = None

    if CURSOR_FILE_PATH.is_file():
        custom_cursor_path = CURSOR_FILE_PATH
    elif CURSOR_SOURCE_PATH.is_file():
        custom_cursor_path = create_cursor_from_png(
            CURSOR_SOURCE_PATH,
            GENERATED_CURSOR_PATH,
            hotspot_x=0,
            hotspot_y=0,
        )

    custom_cursor_name = (
        f"@{custom_cursor_path.resolve()}"
        if custom_cursor_path is not None and custom_cursor_path.is_file()
        else None
    )

    if custom_cursor_name:
        try:
            root.configure(cursor=custom_cursor_name)
        except tk.TclError as exc:
            #print(f"Could not apply root custom cursor: {exc}")
            custom_cursor_name = None

    if CURSOR_SOURCE_PATH.is_file() and custom_cursor_name is None:
        print(
            "The Meccha cursor could not be enabled. Falling back to hand2."
        )

    def apply_interactive_cursors(widget) -> None:
        """
        Apply the Meccha cursor to clickable widgets.

        Text-editing and resize behavior retain their native cursors. When the
        packaged cursor.cur is absent or unsupported, hand2 is used safely.
        """
        try:
            widget_class = widget.winfo_class()

            if widget_class in {
                "TButton",
                "TCheckbutton",
                "TRadiobutton",
                "TCombobox",
            }:
                cursor_name = custom_cursor_name or "hand2"

                try:
                    widget.configure(cursor=cursor_name)
                except tk.TclError:
                    widget.configure(cursor="hand2")

            elif widget_class in {"TEntry", "Text"}:
                widget.configure(cursor="xterm")
        except (tk.TclError, TypeError):
            pass

        for child in widget.winfo_children():
            apply_interactive_cursors(child)

    def invoke_button_if_enabled(button) -> None:
        """Invoke a button only when it is currently enabled."""
        if str(button.cget("state")) != "disabled":
            button.invoke()

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

    def clear_build_output():
        """Clear the visible command output without affecting saved build logs."""
        output_box.configure(state="normal")
        output_box.delete("1.0", "end")
        output_box.configure(state="disabled")
        status_var.set("Build output cleared")

    def save_current_settings():
        """Persist the current application settings and show a status update."""
        save_settings()
        status_var.set("Current settings saved")

    def save_and_exit():
        """Save settings before closing the application."""
        save_settings()
        close_application()

    def copy_debug_information():
        """Copy a compact, credential-safe diagnostics summary to the clipboard."""
        debug_text = (
            f"{APP_NAME}\n"
            f"Version: {APP_VERSION}\n"
            f"Python: {platform.python_version()}\n"
            f"Platform: {platform.platform()}\n"
            f"Executable: {sys.executable}\n"
            f"Frozen build: {bool(getattr(sys, 'frozen', False))}\n"
            f"User data: {USER_DATA_DIR}\n"
            f"Project: {fields['project'].get().strip()}\n"
            f"Plugin: {fields['plugin'].get().strip()}\n"
            f"Workshop: {fields['workshop'].get().strip()}\n"
        )

        root.clipboard_clear()
        root.clipboard_append(debug_text)
        root.update_idletasks()
        status_var.set("Debug information copied to clipboard")

    def export_diagnostics():
        """Export sanitized settings, history, statistics, and recent logs."""
        destination = filedialog.asksaveasfilename(
            parent=root,
            title="Export diagnostics",
            defaultextension=".zip",
            initialfile=f"meccha_mod_builder_diagnostics_{datetime.now():%Y%m%d_%H%M%S}.zip",
            filetypes=[("ZIP archive", "*.zip"), ("All files", "*.*")],
        )

        if not destination:
            return

        sanitized_settings = profile_payload()
        sanitized_settings.get("fields", {}).pop("steam_login", None)

        system_info = (
            f"Application: {APP_NAME}\n"
            f"Version: {APP_VERSION}\n"
            f"Generated: {current_local_timestamp()}\n"
            f"Python: {platform.python_version()}\n"
            f"Platform: {platform.platform()}\n"
            f"Executable: {sys.executable}\n"
            f"Frozen build: {bool(getattr(sys, 'frozen', False))}\n"
            f"User data directory: {USER_DATA_DIR}\n"
        )

        try:
            with zipfile.ZipFile(
                destination,
                "w",
                compression=zipfile.ZIP_DEFLATED,
            ) as archive:
                archive.writestr("system_info.txt", system_info)
                archive.writestr(
                    "settings_sanitized.json",
                    json.dumps(sanitized_settings, indent=2, ensure_ascii=False),
                )
                archive.writestr(
                    "build_history.json",
                    json.dumps(load_build_history(), indent=2, ensure_ascii=False),
                )
                archive.writestr(
                    "build_statistics.json",
                    json.dumps(load_build_statistics(), indent=2, ensure_ascii=False),
                )

                if UPDATE_SETTINGS_FILE.is_file():
                    archive.write(UPDATE_SETTINGS_FILE, "update_settings.json")

                recent_logs = sorted(
                    BUILD_LOGS_DIR.glob("*.log"),
                    key=lambda path: path.stat().st_mtime,
                    reverse=True,
                )[:10]

                for log_path in recent_logs:
                    archive.write(log_path, f"logs/{log_path.name}")

            status_var.set("Diagnostics exported")
            messagebox.showinfo(
                "Export diagnostics",
                f"Diagnostics were exported successfully:\n\n{destination}",
                parent=root,
            )
        except Exception as exc:
            messagebox.showerror(
                "Export diagnostics",
                f"Could not export diagnostics:\n\n{exc}",
                parent=root,
            )

    def show_shortcuts():
        messagebox.showinfo(
            "Keyboard Shortcuts",
            "Ctrl+B — Build Mod\n"
            "Ctrl+Shift+V — Validate\n"
            "Ctrl+W — Workshop Manager\n"
            "Ctrl+H — Build History\n"
            "Ctrl+L — Focus Build Output\n"
            "F1 — About\n"
            "Escape — Close supported dialogs",
            parent=root,
        )

    def show_troubleshooting():
        messagebox.showinfo(
            "Troubleshooting",
            "1. Run Validate before building.\n"
            "2. Confirm Unreal Editor is closed.\n"
            "3. Review Build History and the saved log.\n"
            "4. Export Diagnostics when reporting an issue.\n"
            "5. Verify the selected plugin and runtime map path.",
            parent=root,
        )

    def show_release_notes():
        messagebox.showinfo(
            "Release Notes",
            f"{APP_NAME} {APP_VERSION}\n\n"
            "Recent improvements:\n"
            "• Workshop VDF preview and item ID recovery\n"
            "• Scrollable Workshop settings\n"
            "• Profiles moved into the header\n"
            "• Organized build output\n"
            "• Application menu bar and improved icon handling",
            parent=root,
        )

    def check_for_updates():
        messagebox.showinfo(
            "Check for Updates",
            "The update-check interface is ready, but a GitHub repository URL "
            "must be configured before online version checks can be enabled.",
            parent=root,
        )

    def open_github_repository():
        """Open the configured GitHub repository or explain what is missing."""
        if not GITHUB_REPOSITORY_URL:
            messagebox.showinfo(
                "GitHub Repository",
                "No GitHub repository URL has been configured yet.",
                parent=root,
            )
            return

        webbrowser.open(GITHUB_REPOSITORY_URL)

    def show_about():
        about = tk.Toplevel(root)
        about.title(f"About {APP_NAME}")
        about.geometry("540x430")
        about.minsize(500, 390)
        about.transient(root)
        about.grab_set()
        apply_window_icon(about, remember_key="about")

        container = ttk.Frame(about, padding=18)
        container.pack(fill="both", expand=True)

        heading = ttk.Frame(container)
        heading.pack(fill="x")

        if HEADER_LOGO_PATH.is_file():
            try:
                if pillow_available:
                    image = Image.open(HEADER_LOGO_PATH).convert("RGBA")
                    image.thumbnail((64, 64), Image.Resampling.LANCZOS)
                    about_photo = ImageTk.PhotoImage(image)
                else:
                    about_photo = tk.PhotoImage(
                        file=str(HEADER_LOGO_PATH.resolve())
                    )

                about._logo_reference = about_photo
                ttk.Label(
                    heading,
                    image=about_photo,
                ).pack(side="left", padx=(0, 14))
            except Exception as exc:
                print(f"Could not load About logo: {exc}")

        heading_text = ttk.Frame(heading)
        heading_text.pack(side="left", fill="x", expand=True)

        ttk.Label(
            heading_text,
            text="Universal Meccha Mod Builder",
            font=("Segoe UI", 16, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            heading_text,
            text=f"Version {APP_VERSION}",
        ).pack(anchor="w", pady=(2, 0))
        ttk.Label(
            heading_text,
            text="Created by Limbs",
            font=("Segoe UI", 9, "italic"),
        ).pack(anchor="w", pady=(2, 0))

        ttk.Separator(container).pack(fill="x", pady=14)

        details = ttk.Frame(container)
        details.pack(fill="both", expand=True)
        details.columnconfigure(1, weight=1)

        ttk.Label(details, text="Application").grid(
            row=0, column=0, sticky="nw", padx=(0, 14), pady=4
        )
        ttk.Label(
            details,
            text="Build, package, validate, and publish custom Meccha Chameleon maps.",
            wraplength=350,
            justify="left",
        ).grid(row=0, column=1, sticky="nw", pady=4)

        ttk.Label(details, text="Author").grid(
            row=1, column=0, sticky="nw", padx=(0, 14), pady=4
        )
        ttk.Label(details, text="Limbs").grid(
            row=1, column=1, sticky="nw", pady=4
        )

        ttk.Label(details, text="License").grid(
            row=2, column=0, sticky="nw", padx=(0, 14), pady=4
        )
        ttk.Label(
            details,
            text=LICENSE_NAME,
            wraplength=350,
            justify="left",
        ).grid(row=2, column=1, sticky="nw", pady=4)

        ttk.Label(details, text="GitHub").grid(
            row=3, column=0, sticky="nw", padx=(0, 14), pady=4
        )
        github_text = GITHUB_REPOSITORY_URL or "Repository URL not configured"
        github_label = ttk.Label(
            details,
            text=github_text,
            cursor="hand2" if GITHUB_REPOSITORY_URL else "",
            wraplength=350,
            justify="left",
        )
        github_label.grid(row=3, column=1, sticky="nw", pady=4)

        if GITHUB_REPOSITORY_URL:
            github_label.bind(
                "<Button-1>",
                lambda _event: open_github_repository(),
            )

        ttk.Label(details, text="Disclaimer").grid(
            row=4, column=0, sticky="nw", padx=(0, 14), pady=4
        )
        ttk.Label(
            details,
            text=MECCHA_DISCLAIMER,
            wraplength=350,
            justify="left",
        ).grid(row=4, column=1, sticky="nw", pady=4)

        button_row = ttk.Frame(container)
        button_row.pack(fill="x", pady=(14, 0))

        github_button = ttk.Button(
            button_row,
            text="Open GitHub",
            command=open_github_repository,
            state="normal" if GITHUB_REPOSITORY_URL else "disabled",
            cursor="hand2",
        )
        github_button.pack(side="left")

        ttk.Button(
            button_row,
            text="Open AppData",
            command=lambda: open_path_in_windows(USER_DATA_DIR),
            cursor="hand2",
        ).pack(side="left", padx=(8, 0))

        ttk.Button(
            button_row,
            text="Copy System Info",
            command=copy_debug_information,
            cursor="hand2",
        ).pack(side="left", padx=(8, 0))

        ttk.Button(
            button_row,
            text="Close",
            command=about.destroy,
            cursor="hand2",
        ).pack(side="right")

        about.bind("<Escape>", lambda _event: about.destroy())
        apply_interactive_cursors(about)

    def set_theme_from_menu(theme_name: str):
        fields["theme"].set(theme_name)
        apply_theme()
        save_settings()

    def reset_window_size():
        root.geometry("1060x760")
        status_var.set("Window size reset")

    def focus_build_output():
        output_box.focus_set()
        output_box.see("end")

    def show_build_history():
        history_window = tk.Toplevel(root)
        history_window.title("Build History")
        history_window.geometry("1050x560")
        history_window.minsize(820, 420)
        history_window.transient(root)

        apply_window_icon(history_window, remember_key="build_history")

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
                        format_duration(record.get("duration_seconds")),
                        exit_code_display,
                    ),
                )

                record_lookup[build_id] = record

            history_count_var.set(f"{len(record_lookup)} build(s)")

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

            estimate = record.get("estimate", {})

            if not isinstance(estimate, dict):
                estimate = {}

            if not isinstance(configuration, dict):
                configuration = {}

            details = (
                f"Build ID: {record.get('id', '')}\n"
                f"Status: {record.get('status', '')}\n"
                f"Started: {record.get('started_at', '')}\n"
                f"Finished: {record.get('finished_at') or '—'}\n"
                f"Duration: "
                f"{format_duration(record.get('duration_seconds'))}\n"
                f"Build mode: "
                f"{estimate.get('mode_label') or describe_build_mode(classify_build_mode(configuration))}\n"
                f"Original estimate: "
                f"{format_duration(estimate.get('estimated_seconds'))}\n"
                f"Estimate samples: "
                f"{estimate.get('sample_count', 0)}\n"
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

        history_window.bind(
            "<Escape>",
            lambda _event: history_window.destroy(),
        )
        apply_interactive_cursors(history_window)
        refresh_history_table()

    def open_workshop():
        path = fields["workshop"].get().strip()
        if path and Path(path).exists():
            os.startfile(path)
        else:
            messagebox.showwarning(
                "Workshop folder", "Workshop folder does not exist yet."
            )

    validate_button = ttk.Button(
        buttons,
        text="Validate",
        command=validate_only,
        cursor="hand2",
    )
    validate_button.pack(side="left", padx=(0, 8))
    build_button = ttk.Button(
        buttons,
        text="Build Mod",
        command=start_build,
        style="Primary.TButton",
        cursor="hand2",
    )
    build_button.pack(side="left")
    cancel_button = ttk.Button(
        buttons,
        text="Cancel",
        command=cancel_build,
        state="disabled",
        style="Danger.TButton",
        cursor="hand2",
    )
    cancel_button.pack(side="left", padx=8)
    ttk.Button(
        buttons,
        text="Open Workshop Folder",
        command=open_workshop,
        cursor="hand2",
    ).pack(side="left")
    ttk.Button(
        buttons,
        text="Build History",
        command=show_build_history,
        cursor="hand2",
    ).pack(side="left", padx=(8, 0))
    ttk.Button(
        buttons,
        text="Refresh Plugins",
        command=refresh_plugins,
        cursor="hand2",
    ).pack(side="left", padx=8)

    # ------------------------------------------------------------------
    # Application menu bar
    # ------------------------------------------------------------------
    menu_bar = tk.Menu(root)

    file_menu = tk.Menu(menu_bar, tearoff=False)
    file_menu.add_command(
        label="Save Current Settings",
        accelerator="Ctrl+S",
        command=save_current_settings,
    )
    file_menu.add_command(
        label="Save Current Profile…",
        command=save_profile,
    )
    file_menu.add_separator()
    file_menu.add_command(
        label="Export Diagnostics…",
        command=export_diagnostics,
    )
    file_menu.add_command(
        label="Open AppData Folder",
        command=lambda: open_path_in_windows(USER_DATA_DIR),
    )
    file_menu.add_command(
        label="Open Build Logs Folder",
        command=lambda: open_path_in_windows(BUILD_LOGS_DIR),
    )
    file_menu.add_separator()
    file_menu.add_command(
        label="Save and Exit",
        command=save_and_exit,
    )
    file_menu.add_command(
        label="Exit",
        command=close_application,
    )
    menu_bar.add_cascade(label="File", menu=file_menu)

    view_menu = tk.Menu(menu_bar, tearoff=False)

    appearance_menu = tk.Menu(view_menu, tearoff=False)
    theme_menu_var = tk.StringVar(value=fields["theme"].get())
    appearance_menu.add_radiobutton(
        label="Dark Mode",
        value="dark",
        variable=theme_menu_var,
        command=lambda: set_theme_from_menu("dark"),
    )
    appearance_menu.add_radiobutton(
        label="Light Mode",
        value="light",
        variable=theme_menu_var,
        command=lambda: set_theme_from_menu("light"),
    )
    view_menu.add_cascade(
        label="Appearance",
        menu=appearance_menu,
    )
    view_menu.add_separator()
    view_menu.add_command(
        label="Focus Build Output",
        accelerator="Ctrl+L",
        command=focus_build_output,
    )
    view_menu.add_command(
        label="Clear Build Output",
        command=clear_build_output,
    )
    view_menu.add_command(
        label="Reset Window Size",
        command=reset_window_size,
    )
    menu_bar.add_cascade(label="View", menu=view_menu)

    tools_menu = tk.Menu(menu_bar, tearoff=False)
    tools_menu.add_command(
        label="Validate Configuration",
        accelerator="Ctrl+Shift+V",
        command=validate_only,
    )
    tools_menu.add_command(
        label="Workshop Manager",
        accelerator="Ctrl+W",
        command=open_workshop_manager,
    )
    tools_menu.add_command(
        label="Build History",
        accelerator="Ctrl+H",
        command=show_build_history,
    )
    tools_menu.add_separator()
    tools_menu.add_command(
        label="Open Workshop Folder",
        command=open_workshop,
    )
    tools_menu.add_command(
        label="Open Profiles Folder",
        command=lambda: open_path_in_windows(PROFILES_DIR),
    )
    tools_menu.add_command(
        label="Refresh Plugins",
        command=refresh_plugins,
    )
    tools_menu.add_separator()

    utility_scripts_menu = tk.Menu(tools_menu, tearoff=False)
    utility_scripts_menu.add_command(
        label="Utility scripts will appear here",
        state="disabled",
    )
    tools_menu.add_cascade(
        label="Utility Scripts",
        menu=utility_scripts_menu,
    )
    menu_bar.add_cascade(label="Tools", menu=tools_menu)

    help_menu = tk.Menu(menu_bar, tearoff=False)
    help_menu.add_command(
        label="Keyboard Shortcuts",
        command=show_shortcuts,
    )
    help_menu.add_command(
        label="Troubleshooting",
        command=show_troubleshooting,
    )
    help_menu.add_command(
        label="Copy Debug Information",
        command=copy_debug_information,
    )
    help_menu.add_command(
        label="Export Diagnostics…",
        command=export_diagnostics,
    )
    help_menu.add_separator()
    help_menu.add_command(
        label="Check for Updates",
        command=check_for_updates,
    )
    help_menu.add_command(
        label="Release Notes",
        command=show_release_notes,
    )
    help_menu.add_separator()
    help_menu.add_command(
        label=f"About {APP_NAME}",
        accelerator="F1",
        command=show_about,
    )
    menu_bar.add_cascade(label="Help", menu=help_menu)

    root.configure(menu=menu_bar)

    # ------------------------------------------------------------------
    # Persistent application footer
    # ------------------------------------------------------------------
    footer_left = ttk.Frame(footer_host)
    footer_left.pack(side="left", fill="x", expand=True)

    ttk.Label(
        footer_left,
        text=f"Meccha Mod Builder v{APP_VERSION}",
    ).pack(side="left")

    ttk.Label(
        footer_left,
        text="Created by Limbs",
        font=("Segoe UI", 9, "italic"),
    ).pack(side="left", padx=(12, 0))

    # Keep this reference somewhere persistent, such as near your other UI images.
    github_source = Image.open(GIT_LOGO_PATH).convert("RGBA")
    github_source.thumbnail((18, 18), Image.Resampling.LANCZOS)

    github_footer_image = ImageTk.PhotoImage(github_source)

    footer_right = ttk.Frame(footer_host)
    footer_right.pack(side="right")

    # Exact GitHub icon sizing
    github_source = Image.open(GIT_LOGO_PATH).convert("RGBA")
    github_source.thumbnail((25, 25), Image.Resampling.LANCZOS)
    github_footer_image = ImageTk.PhotoImage(github_source)

    github_footer_label = ttk.Label(
        footer_right,
        image=github_footer_image,
        cursor="hand2",
    )

    github_footer_label.pack(side="left", padx=(0, 10))

    if GITHUB_REPOSITORY_URL:
        github_footer_label.bind(
            "<Button-1>",
            lambda event: open_github_repository(),
        )

    ToolTip(
        github_footer_label,
        (
            "Open the GitHub repository."
            if GITHUB_REPOSITORY_URL
            else "GitHub repository link is unavailable."
        ),
    )


    def handle_build_shortcut(_event=None):
        invoke_button_if_enabled(build_button)
        return "break"

    def handle_validate_shortcut(_event=None):
        invoke_button_if_enabled(validate_button)
        return "break"

    def handle_workshop_shortcut(_event=None):
        open_workshop_manager()
        return "break"

    def handle_history_shortcut(_event=None):
        show_build_history()
        return "break"

    root.bind("<Control-b>", handle_build_shortcut)
    root.bind("<Control-B>", handle_build_shortcut)
    root.bind("<Control-Shift-v>", handle_validate_shortcut)
    root.bind("<Control-Shift-V>", handle_validate_shortcut)
    root.bind("<Control-w>", handle_workshop_shortcut)
    root.bind("<Control-W>", handle_workshop_shortcut)
    root.bind("<Control-h>", handle_history_shortcut)
    root.bind("<Control-H>", handle_history_shortcut)
    root.bind("<Control-s>", lambda _event: (save_current_settings(), "break")[1])
    root.bind("<Control-S>", lambda _event: (save_current_settings(), "break")[1])
    root.bind("<Control-l>", lambda _event: (focus_build_output(), "break")[1])
    root.bind("<Control-L>", lambda _event: (focus_build_output(), "break")[1])
    root.bind("<F1>", lambda _event: (show_about(), "break")[1])

    ToolTip(build_button, "Start the build (Ctrl+B).")
    ToolTip(validate_button, "Run preflight validation (Ctrl+Shift+V).")
    ToolTip(cancel_button, "Stop the active build.")

    apply_interactive_cursors(root)

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