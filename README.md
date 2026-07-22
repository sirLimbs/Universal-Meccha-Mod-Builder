<p align="center"># Universal Meccha Mod Builder
</a>
</p>

A Windows desktop application and command-line utility for building, validating, packaging, staging, and optionally uploading custom **Meccha Chameleon** maps created with the Unreal Engine mod kit.

<p align="center">
    <img src="https://i.imgur.com/sTAxRmW.png" alt="Meccha Mod Builder preview" width="900">
  </a>
</p>
## More Screenshots <details open> <summary><strong>1. Builder Toolbar & Build History</strong></summary> <br> <p align="center"> <a href="https://imgur.com/gallery/meccha-mod-builder-image-showcase-PfPgiIX"> <img src="https://i.imgur.com/tyvPAhS.png" width="750" alt="Meccha Mod Builder toolbar and build history" /> </a> </p> </details> <details> <summary><strong>2. Validation Reports</strong></summary> <br> <p align="center"> <a href="https://imgur.com/gallery/meccha-mod-builder-image-showcase-PfPgiIX"> <img src="https://i.imgur.com/oQYTF7e.png" width="750" alt="Viewable and exportable validation report" /> </a> </p> </details> <details> <summary><strong>3. Developer Resources</strong></summary> <br> <p align="center"> <a href="https://imgur.com/gallery/meccha-mod-builder-image-showcase-PfPgiIX"> <img src="https://i.imgur.com/KzLarR4.png" width="750" alt="Developer resources and Unreal Engine 5.6 Python scripts" /> </a> </p> </details> <details> <summary><strong>4. Visual Workshop Settings</strong></summary> <br> <p align="center"> <a href="https://imgur.com/gallery/meccha-mod-builder-image-showcase-PfPgiIX"> <img src="https://i.imgur.com/qnpmYG3.png" width="750" alt="Visual workshop settings panel" /> </a> </p> </details> <details> <summary><strong>5. Live Update Checker</strong></summary> <br> <p align="center"> <a href="https://imgur.com/gallery/meccha-mod-builder-image-showcase-PfPgiIX"> <img src="https://i.imgur.com/0VjGLB5.png" width="750" alt="Live update checker" /> </a> </p> </details>

> **Disclaimer:** Universal Meccha Mod Builder is an independent community tool. It is not affiliated with or endorsed by the developers or publishers of Meccha Chameleon.

## Version

Current release: **v1.2.1**

## What the application does

Meccha Mod Builder automates the most repetitive parts of the Unreal Engine mod-build workflow:

1. Validates the selected Unreal installation, project, plugin, runtime map path, Workshop folder, and preview image.
2. Runs Unreal Automation Tool through `RunUAT.bat`.
3. Optionally creates the required full-game release build.
4. Builds the selected plugin as DLC.
5. Locates the generated `.pak`, `.ucas`, `.utoc`, and `AssetRegistry.bin` files.
6. Copies the payload into a clean Steam Workshop staging folder.
7. Generates `my_item.vdf`.
8. Optionally uploads the Workshop item through SteamCMD.
9. Records build history, timing information, logs, and completion details.

## v1.2.1 features

- Streamlined Workshop Manager workflow
- Removed the duplicate Workshop-folder field from the main window
- Automatic Published File ID detection from `my_item.vdf`
- Steam Workshop header branding and improved tooltips
- Workshop-aware profile and validation behavior
- Simplified post-build summary
- Copyable SteamCMD workshop command
- New Developer Resources browser
- Fourteen included Unreal Engine 5.6 map-development scripts
- Blueprint data exporter
- Meccha Material Factory with configurable presets

## v1.2 features

- Windows Tkinter desktop interface
- Full command-line interface
- Dark and light themes
- Icon-based utility controls with descriptive tooltips
- Saveable build profiles
- Persistent application settings
- Recent-project tracking
- Plugin discovery from the selected Unreal project
- Preflight validation with pass, warning, and error results
- Detection of running Unreal Editor processes
- Detection of recent Unreal autosave and backup files
- Runtime map-path validation for Meccha conventions
- Full-game release builds
- Plugin/DLC builds
- Copy-only staging mode
- Expected payload detection with fallback scanning
- Fresh-build timestamp checks that reduce stale-file uploads
- Optional Workshop-folder cleanup
- Automatic Workshop VDF generation
- New Workshop item creation and existing-item updates
- Public, friends-only, and private Workshop visibility
- Workshop readiness checks
- Workshop preview-image metadata and thumbnail display
- SteamCMD upload support
- Live, timestamped, color-coded subprocess output
- Build-pipeline stage tracking
- Build cancellation
- Build history and stored log files
- Build-time estimates based on successful previous builds
- Post-build summary with direct log and Workshop actions
- Diagnostics export
- Manual and automatic GitHub release checks
- Configurable update-check intervals
- Ability to skip a specific application release

## Requirements

### Packaged application

- Windows 10 or Windows 11
- Unreal Engine 5.6 and the Meccha Chameleon mod kit
- A valid Meccha `.uproject`
- A plugin containing the map assets and a matching `.uplugin`
- A Workshop preview image
- SteamCMD only when automatic Workshop upload is used

Python is **not required** when using the packaged executable.

### Running from source

- Python 3.10 or newer
- Pillow is optional but recommended for high-quality image scaling

Install the development dependencies:

```powershell
py -m pip install Pillow
```

Install the release-build dependencies:

```powershell
py -m pip install pyinstaller Pillow
```

## Repository structure

```text
Universal-Meccha-Mod-Builder/
├── build_meccha_mod.py
├── README.md
├── LICENSE
├── MecchaModBuilder.spec
├── build_release.ps1
├── version_info.txt
└── resources/
    ├── icon/
    │   ├── buttons/
    │   │   ├── check.png
    │   │   ├── copy.png
    │   │   ├── delete.png
    │   │   ├── details.png
    │   │   ├── exit.png
    │   │   ├── folder.png
    │   │   ├── glass.png
    │   │   ├── history.png
    │   │   ├── info.png
    │   │   ├── link.png
    │   │   ├── load.png
    │   │   ├── refresh.png
    │   │   ├── save.png
    │   │   └── steamwm.png
    │   ├── github_icon.png
    │   ├── header_icon.png
    │   ├── icon.ico
    │   └── icon_source.png
    ├── cursor/
    │   ├── cursor.cur
    │   └── cursor.png
    └── spinner/
        └── spinner.svg
```

## Application data

User-generated files are not stored inside the installation folder.

On Windows, the application uses:

```text
%APPDATA%\Meccha Mod Builder\
```

The directory can contain:

```text
Meccha Mod Builder/
├── build_meccha_mod_gui_settings_v3.json
├── build_profiles/
├── build_history/
│   ├── history.json
│   └── logs/
├── cache/
│   ├── recent_projects.json
│   ├── build_statistics.json
│   └── update_settings.json
└── previews/
```

This keeps packaged application files separate from personal settings, logs, profiles, and cached data.

## Running the application

### Packaged executable

Open:

```text
Meccha Mod Builder.exe
```

### From source

```powershell
py build_meccha_mod.py
```

With no command-line arguments, the GUI launches automatically.

## First-time setup

### UE RunUAT.bat

Select Unreal Automation Tool. A typical path is:

```text
C:\Program Files\Epic Games\UE_5.6\Engine\Build\BatchFiles\RunUAT.bat
```

### Meccha `.uproject`

Select the mod kit's `.uproject` file.

The application scans the project's `Plugins` directory for `.uplugin` descriptors and populates the plugin selector.

### Asset plugin

Choose the exact plugin containing the map's imported assets.

The selected plugin controls:

- Unreal's `-dlcName` argument
- expected staged payload locations
- expected generated payload names

### Runtime map path

Enter an Unreal package path, not a Windows path.

Do not include `.umap` or object syntax.

Known Meccha runtime convention:

```text
/Game/Mods/UserMap01/MyMap
```

### Workshop folder

Choose a staging folder where the application can assemble:

```text
<PluginName><ProjectName>-Windows.pak
<PluginName><ProjectName>-Windows.ucas
<PluginName><ProjectName>-Windows.utoc
AssetRegistry.bin
preview.png
my_item.vdf
```

## Build modes

### Build Full Game

Creates the Unreal release version used as the base for the DLC build.

### Build My Mod / DLC

Cooks and stages the selected plugin and runtime map as DLC.

### Copy only

Skips Unreal build commands and stages already-existing payload files.

Copy-only mode cannot guarantee that those files came from the latest Unreal build.

### Clean Workshop first

Removes older payload and VDF files while preserving the selected preview image.

### Upload with SteamCMD

Uploads the prepared Workshop item after staging.

## Preflight validation

Select **Validate** before building to inspect the current configuration.

Validation can check:

- `RunUAT.bat`
- Unreal version detection
- `.uproject` descriptor
- plugin directory and `.uplugin`
- runtime map path
- likely `.umap` candidates
- Workshop folder
- preview image
- SteamCMD
- published Workshop ID
- running Unreal Editor processes
- recent autosave and backup files

Errors block the build. Warnings can be reviewed and approved.

## Workshop Manager

The Workshop Manager centralizes:

- Create or Update mode
- Published File ID
- Workshop title
- Description
- Change note
- Visibility
- Preview image
- SteamCMD path
- Automatic upload preference
- Readiness checks
- VDF preview
- Workshop page and folder actions

### Published File ID

- `0`: create a new Workshop item
- Existing non-zero numeric ID: update that Workshop item

### Visibility

- `0`: Public
- `1`: Friends-only
- `2`: Private

## Steam Workshop upload

When automatic upload is disabled, the application still prepares the Workshop folder and prints the SteamCMD command:

```text
workshop_build_item "C:\Path\To\Workshop\my_item.vdf"
```

For automatic upload, select `steamcmd.exe` and enable the upload option.

> **Security warning:** Do not commit Steam usernames, passwords, authentication tokens, generated settings, or private profile JSON files. Steam login arguments passed on the command line may be visible to local process-inspection tools.

## Build history and logs

Each build can create:

- a build-history record
- a timestamped log file
- status and duration information
- the selected build mode
- the configuration snapshot used for the build
- an error summary when the build fails

The Build History window can refresh records, show details, open a selected log, and open the log directory.

## Update checks

The application can query the repository's latest published GitHub release.

Update preferences support:

- automatic checks on startup
- configurable check intervals
- manual checks
- skipping notification for one specific version

No GitHub token is required for normal occasional checks.

## Command-line usage

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

## Building the packaged executable

The release build uses PyInstaller in **one-folder mode**.

The complete `resources` directory is packaged with the executable. User-generated settings, profiles, logs, and caches are not included.

From PowerShell in the repository root:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\build_release.ps1
```

The script:

1. verifies required files
2. installs or verifies PyInstaller
3. removes old build output
4. runs `MecchaModBuilder.spec`
5. copies `README.md` and `LICENSE`
6. creates a versioned ZIP
7. generates a SHA-256 checksum

Expected output:

```text
release/
├── Meccha-Mod-Builder-v1.2.0/
│   ├── Meccha Mod Builder.exe
│   ├── resources/
│   ├── README.md
│   └── LICENSE
├── Meccha-Mod-Builder-v1.2.0.zip
└── Meccha-Mod-Builder-v1.2.0.zip.sha256
```

## Release testing

Before publishing, test the packaged executable from outside the source repository.

Recommended checks:

- first launch with no existing AppData
- all icons and tooltips
- dark and light themes
- profile save, load, and delete
- Browse and Open Folder controls
- plugin refresh
- validation report
- successful build
- intentional failed build
- cancellation
- Copy-only mode
- Workshop Manager
- VDF preview
- SteamCMD upload
- Build History
- post-build summary
- diagnostics export
- manual update check
- update-preference persistence

Temporarily rename the source repository's `resources` folder after packaging. If the packaged application still displays every asset, the bundle is self-contained.

## Safety and limitations

- Designed primarily for Windows.
- The Meccha Steam App ID is hardcoded.
- Selecting the wrong plugin can build or stage the wrong assets.
- Copy-only mode accepts existing payload files.
- Steam login arguments may be visible to local process-inspection tools.
- Cancelling the application process may not terminate every Unreal child process; verify the Windows process list when necessary.
- The first public executable may trigger Windows SmartScreen because it is not code-signed.

## Contributing

Contributions are welcome.

By submitting a contribution, you agree that it may be distributed under the same GPL-3.0-only license as the project.

Useful contribution areas include:

- validation improvements
- additional Unreal output detection
- UI accessibility
- packaging and installer support
- documentation
- testing across different Unreal and SteamCMD configurations

Please avoid committing:

- Steam credentials
- generated settings
- private profiles
- personal file paths
- Workshop payload files
- Unreal cooked or staged output
- build logs

## License

Universal Meccha Mod Builder is licensed under the **GNU General Public License v3.0 only**.

See [`LICENSE`](LICENSE) for the complete license text.
