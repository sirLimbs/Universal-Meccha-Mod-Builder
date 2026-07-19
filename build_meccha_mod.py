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

MECCHA_APP_ID = "4704690" #DO NOT CHANGE

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
GUI_SETTINGS_VERSION = 3

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
    root.title("Universal Meccha Mod Builder")

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

    # New v2 settings file intentionally avoids loading old saved plugin selections.
    try:
        if SETTINGS_FILE.exists():
            saved = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            for key, value in saved.get("fields", {}).items():
                if key in fields:
                    fields[key].set(value)
            for key, value in saved.get("flags", {}).items():
                if key in flags:
                    flags[key].set(bool(value))
    except Exception:
        pass

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
    process_holder = {"process": None}

    def log(text):
        output_box.configure(state="normal")
        output_box.insert("end", text)
        output_box.see("end")
        output_box.configure(state="disabled")

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
        path.write_text(json.dumps(profile_payload(), indent=2), encoding="utf-8")
        refresh_profiles()
        profile_var.set(safe)
        status_var.set(f"Saved profile: {safe}")

    def load_profile():
        name = profile_var.get().strip()
        if not name:
            messagebox.showwarning("Profiles", "Select a profile first.")
            return
        path = PROFILES_DIR / f"{name}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
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
        SETTINGS_FILE.write_text(
            json.dumps(profile_payload(), indent=2),
            encoding="utf-8",
        )

    def validate_gui():
        for label, key in [
            ("UE RunUAT.bat", "ue"),
            ("Meccha .uproject", "project"),
            ("Asset plugin", "plugin"),
            ("Runtime map path", "map"),
            ("Workshop folder", "workshop"),
            ("Preview image", "preview"),
        ]:
            if not fields[key].get().strip():
                raise ValueError(f"{label} is required.")

        project = Path(fields["project"].get().strip())
        plugin = fields["plugin"].get().strip()

        if not project.exists():
            raise FileNotFoundError(f"Project does not exist:\n{project}")

        validate_plugin(project.parent, plugin)
        validate_map_path(fields["map"].get().strip(), plugin)

        if plugin not in plugin_combo["values"]:
            raise ValueError(
                f"Selected plugin '{plugin}' was not found under:\n"
                f"{project.parent / 'Plugins'}"
            )

        if flags["upload"].get() and not fields["steamcmd"].get().strip():
            raise ValueError("SteamCMD path is required when Upload is enabled.")

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
        try:
            validate_gui()
        except Exception as exc:
            messagebox.showerror("Cannot start build", str(exc))
            return

        summary = (
            "Confirm the build target:\n\n"
            f"Plugin / DLC:  {fields['plugin'].get()}\n"
            f"Runtime map:   {fields['map'].get()}\n"
            f"Workshop:      {fields['workshop'].get()}\n"
            f"Published ID:  {fields['publishedfileid'].get()}\n\n"
            "The selected plugin controls which assets are cooked and which "
            "plugin-named .pak/.ucas/.utoc files are produced."
        )
        if not messagebox.askyesno("Confirm build target", summary):
            return

        save_settings()

        output_box.configure(state="normal")
        output_box.delete("1.0", "end")
        output_box.configure(state="disabled")

        cmd = build_command()
        log("=== GUI COMMAND ===\n" + subprocess.list2cmdline(cmd) + "\n\n")

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
            messagebox.showerror("Failed to start", str(exc))
            return

        process_holder["process"] = process
        build_button.configure(state="disabled")
        cancel_button.configure(state="normal")
        progress.start(10)
        status_var.set("Building…")
        threading.Thread(target=reader_thread, args=(process,), daemon=True).start()

    def cancel_build():
        process = process_holder["process"]
        if process and process.poll() is None:
            process.terminate()
            status_var.set("Stopping…")

    def poll_queue():
        try:
            while True:
                kind, value = messages.get_nowait()
                if kind == "log":
                    log(value)
                elif kind == "done":
                    progress.stop()
                    build_button.configure(state="normal")
                    cancel_button.configure(state="disabled")
                    process_holder["process"] = None
                    if value == 0:
                        status_var.set("Build completed successfully")
                        messagebox.showinfo("Meccha builder", "Build completed successfully.")
                    else:
                        status_var.set(f"Build failed with exit code {value}")
                        messagebox.showerror(
                            "Meccha builder",
                            f"Build failed with exit code {value}.\nReview the log.",
                        )
                elif kind == "error":
                    progress.stop()
                    build_button.configure(state="normal")
                    cancel_button.configure(state="disabled")
                    process_holder["process"] = None
                    status_var.set("Build failed")
                    messagebox.showerror("Meccha builder", value)
        except queue.Empty:
            pass
        root.after(100, poll_queue)


    def open_workshop():
        path = fields["workshop"].get().strip()
        if path and Path(path).exists():
            os.startfile(path)
        else:
            messagebox.showwarning("Workshop folder", "Workshop folder does not exist yet.")

    build_button = ttk.Button(buttons, text="Build Mod", command=start_build)
    build_button.pack(side="left")
    cancel_button = ttk.Button(buttons, text="Cancel", command=cancel_build, state="disabled")
    cancel_button.pack(side="left", padx=8)
    ttk.Button(buttons, text="Open Workshop Folder", command=open_workshop).pack(side="left")
    ttk.Button(buttons, text="Refresh Plugins", command=refresh_plugins).pack(side="left", padx=8)
    ttk.Button(buttons, text="Exit", command=root.destroy).pack(side="right")

    project_entry.bind("<FocusOut>", lambda _event: refresh_plugins(), add="+")
    refresh_profiles()
    refresh_plugins()
    apply_theme()
    apply_hardcoded_branding()
    update_steamcmd_visibility()
    poll_queue()
    root.mainloop()


if __name__ == "__main__":
    if len(sys.argv) == 1:
        launch_gui()
    else:
        main_cli()