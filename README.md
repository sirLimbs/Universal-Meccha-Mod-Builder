# Universal Meccha Mod Builder

A Windows GUI and command-line utility for building, packaging, staging, and optionally uploading custom **Meccha Chameleon** maps created with the Unreal Engine mod kit.

The tool automates Unreal Automation Tool (`RunUAT.bat`) full-game release builds and plugin-based DLC/mod builds, locates the generated IoStore payload, prepares a clean Steam Workshop staging directory, creates the Workshop VDF manifest, and can publish the item through SteamCMD.

## Features

- Tkinter desktop GUI and full command-line interface
- Unreal Engine `BuildCookRun` automation for Win64
- Optional full-game release build
- Plugin/DLC build based on a selected release version
- Plugin discovery from the selected Unreal project
- Runtime map-path validation for Meccha map conventions
- Expected payload detection with fallback scanning
- Fresh-build timestamp validation to prevent stale files from being uploaded
- Copies `.pak`, `.ucas`, `.utoc`, and `AssetRegistry.bin` into a Workshop folder
- Optional cleanup of old Workshop payload files
- Automatic `my_item.vdf` generation
- New Workshop item creation or existing item updates
- Public, friends-only, and private visibility settings
- Optional SteamCMD upload
- Saveable JSON build profiles
- Persistent GUI settings
- Dark and light themes
- Live subprocess output, progress indication, and build cancellation
- Optional PNG/ICO branding and PyInstaller-compatible resource lookup

## Requirements

- Windows 10 or Windows 11
- Python 3.10 or newer recommended
- Unreal Engine 5.6 / the Meccha Chameleon mod kit
- A valid Meccha `.uproject`
- A plugin containing the map's imported assets and a matching `.uplugin`
- A Workshop preview image (`.png`, `.jpg`, or `.jpeg`)
- SteamCMD only when using automatic Workshop upload
- Pillow is optional but recommended for higher-quality icon and logo scaling

Install the optional image dependency:

```powershell
py -m pip install Pillow
```

## Folder Structure

```text
Meccha Mod Builder/
├── build_meccha_mod.py
├── build_profiles/
└── icon/
    ├── icon.ico
    └── icon.png
```

The application creates `build_meccha_mod_gui_settings_v3.json` beside the script after GUI settings are saved.

## Running the GUI

Double-click `build_meccha_mod.py`, or run:

```powershell
py build_meccha_mod.py
```

With no command-line arguments, the GUI launches automatically.

## GUI Configuration

### UE RunUAT.bat

Select Unreal Automation Tool, commonly located at:

```text
C:\Program Files\Epic Games\UE_5.6\Engine\Build\BatchFiles\RunUAT.bat
```

### Meccha .uproject

Select the mod kit's `.uproject` file. The builder scans its `Plugins` directory and lists discovered `.uplugin` projects.

### Asset plugin

Choose the exact plugin that owns the map's imported assets. This selection controls Unreal's `-dlcName` argument and determines the expected names and locations of the generated payload files.

### Runtime map path

Enter an Unreal package path, not a Windows file path. Do not include `.umap` or object syntax.

Known Meccha runtime convention:

```text
/Game/Mods/UserMap01/MyMap
```

### Workshop folder

Choose a staging directory where the generated payload, preview image, and `my_item.vdf` will be assembled.

### Published ID

- `0`: create a new Workshop item
- Existing numeric Workshop ID: update that item

### Visibility

- `0`: Public
- `1`: Friends-only
- `2`: Private

## Build Modes

- **Build Full Game** — creates the Unreal release version used as the DLC base.
- **Build My Mod / DLC** — cooks and stages the selected plugin and map as DLC.
- **Copy only** — skips Unreal build commands and stages already-existing payload files.
- **Clean Workshop first** — removes old `.pak`, `.ucas`, `.utoc`, `.bin`, and `.vdf` files while preserving the selected preview image.
- **Upload with SteamCMD** — uploads the generated Workshop item after staging.

## Generated Payload

The builder expects the plugin build to produce:

```text
<PluginName><ProjectName>-Windows.pak
<PluginName><ProjectName>-Windows.ucas
<PluginName><ProjectName>-Windows.utoc
AssetRegistry.bin
```

It first checks Unreal's expected staged and cooked directories. If files are not found there, it searches the plugin's `Saved` tree for matching recent output.

For normal builds, each payload file must have been modified after the current build began. This reduces the chance of accidentally packaging stale output from a previous build.

## Command-Line Usage

```powershell
py build_meccha_mod.py `
  --ue "C:\Program Files\Epic Games\UE_5.6\Engine\Build\BatchFiles\RunUAT.bat" `
  --project "Z:\Path\To\MecchaProject.uproject" `
  --plugin "MyMapUGC" `
  --map "/Game/Mods/UserMap01/MyMap" `
  --release "1.0" `
  --workshop "C:\Steam_Workshop\MyMapUGC" `
  --preview "C:\Steam_Workshop\MyMapUGC\preview.png" `
  --title "My Custom Map" `
  --description "A custom map for Meccha Chameleon." `
  --changenote "Initial release"
```

Useful flags:

```text
--gui
--skip-full-game
--skip-mod
--copy-only
--clean-workshop
--upload
--steamcmd <path>
--steam-login <arguments>
--publishedfileid <id>
--visibility 0|1|2
```

## Steam Workshop Upload

When upload is disabled, the builder prints the SteamCMD command needed for manual publishing:

```text
workshop_build_item "C:\Path\To\Workshop\my_item.vdf"
```

For automatic upload, provide `steamcmd.exe` and enable **Upload with SteamCMD**.

> **Security warning:** Do not commit Steam usernames, passwords, authentication tokens, generated GUI settings, or private profile JSON files. Prefer signing into SteamCMD interactively rather than saving credentials in the application.

## Build Profiles

Profiles store the current fields and build flags as JSON in `build_profiles/`. They are useful for switching between maps or Workshop items.

Because profiles can contain local paths and Steam login arguments, profile JSON files are ignored by the recommended `.gitignore`. Commit only sanitized example profiles when needed.

## Packaging as an Executable

The resource lookup supports PyInstaller's bundled `_MEIPASS` directory. A basic Windows build can be created with:

```powershell
py -m pip install pyinstaller Pillow
pyinstaller --noconsole --onefile `
  --icon "icon\icon.ico" `
  --add-data "icon;icon" `
  build_meccha_mod.py
```

Test the packaged executable before release, especially icon loading, profile creation, subprocess output, Unreal paths, and SteamCMD execution.

## Safety and Limitations

- Designed primarily for Windows.
- The Meccha Steam App ID is hardcoded and should not be changed unless the target application changes.
- Selecting the wrong plugin can cook or stage the wrong assets.
- `Copy only` accepts existing files and therefore cannot guarantee they came from the latest build.
- Steam login arguments are passed through the command line and may be visible to local process-inspection tools.
- The builder terminates its immediate Python child process when Cancel is selected; Unreal child processes may require separate verification.

## License

No license has been selected yet. Add a `LICENSE` file before inviting outside contributions or redistribution.
