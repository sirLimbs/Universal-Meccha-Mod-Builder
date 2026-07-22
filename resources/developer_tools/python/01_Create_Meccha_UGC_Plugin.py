import json
import re
from pathlib import Path
import tkinter as tk
from tkinter import messagebox

import unreal


CONTENT_FOLDERS = [
    "Maps",
    "Blueprints",
    "Blueprints/Generators",
    "Blueprints/Gameplay",
    "Blueprints/Props",
    "Meshes",
    "Meshes/Architecture",
    "Meshes/Clutter",
    "Materials",
    "Materials/Master",
    "Materials/Instances",
    "Textures",
    "Textures/Masks",
    "Props",
    "Data",
    "Audio",
]


def request_plugin_details():
    """Ask for the content-only plugin name and creator in one dialog."""
    root = tk.Tk()
    root.withdraw()

    dialog = tk.Toplevel(root)
    dialog.title("Meccha UGC Plugin Creator")
    dialog.resizable(False, False)
    dialog.attributes("-topmost", True)
    dialog.grab_set()

    result = {"value": None}
    plugin_name_var = tk.StringVar()
    created_by_var = tk.StringVar()

    container = tk.Frame(dialog, padx=18, pady=16)
    container.pack(fill="both", expand=True)
    container.columnconfigure(1, weight=1)

    tk.Label(
        container,
        text="Create a content-only Meccha Chameleon UGC plugin.",
        font=("Segoe UI", 11, "bold"),
    ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 14))

    tk.Label(container, text="Plugin Name:").grid(
        row=1, column=0, sticky="w", padx=(0, 10), pady=4
    )
    plugin_entry = tk.Entry(container, textvariable=plugin_name_var, width=34)
    plugin_entry.grid(row=1, column=1, sticky="ew", pady=4)

    tk.Label(
        container,
        text="Example: MyMapUGC",
        font=("Segoe UI", 8, "italic"),
        fg="#666666",
    ).grid(row=2, column=1, sticky="w", pady=(0, 8))

    tk.Label(container, text="Created By:").grid(
        row=3, column=0, sticky="w", padx=(0, 10), pady=4
    )
    creator_entry = tk.Entry(container, textvariable=created_by_var, width=34)
    creator_entry.grid(row=3, column=1, sticky="ew", pady=4)

    def submit():
        plugin_name = plugin_name_var.get().strip()
        created_by = created_by_var.get().strip()

        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", plugin_name):
            messagebox.showerror(
                "Invalid Plugin Name",
                "Use letters, numbers, and underscores only. "
                "The name cannot begin with a number.",
                parent=dialog,
            )
            plugin_entry.focus_set()
            return

        if not created_by:
            messagebox.showerror(
                "Invalid Creator Name",
                "Created By cannot be empty.",
                parent=dialog,
            )
            creator_entry.focus_set()
            return

        result["value"] = (plugin_name, created_by)
        dialog.destroy()

    def cancel():
        dialog.destroy()

    buttons = tk.Frame(container)
    buttons.grid(row=4, column=0, columnspan=2, sticky="e", pady=(14, 0))
    tk.Button(buttons, text="Cancel", width=10, command=cancel).pack(
        side="left", padx=(0, 8)
    )
    tk.Button(buttons, text="Create", width=10, command=submit).pack(side="left")

    dialog.bind("<Return>", lambda _event: submit())
    dialog.bind("<Escape>", lambda _event: cancel())
    dialog.protocol("WM_DELETE_WINDOW", cancel)
    dialog.update_idletasks()

    x = (dialog.winfo_screenwidth() - dialog.winfo_reqwidth()) // 2
    y = (dialog.winfo_screenheight() - dialog.winfo_reqheight()) // 2
    dialog.geometry(f"+{x}+{y}")
    plugin_entry.focus_set()

    root.wait_window(dialog)
    root.destroy()
    return result["value"]


def confirm_existing_plugin(plugin_name, plugin_directory):
    """Confirm that missing folders may be added to an existing plugin."""
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    try:
        return messagebox.askyesno(
            "Plugin Already Exists",
            (
                f'The plugin "{plugin_name}" already exists at:\n'
                f"{plugin_directory}\n\n"
                "Any missing standard folders will be added. Existing files and "
                "folders will not be overwritten.\n\n"
                "Are you sure you want to continue?"
            ),
            parent=root,
        )
    finally:
        root.destroy()


def create_plugin(plugin_name, created_by):
    project_directory = Path(
        unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
    ).resolve()

    plugin_directory = project_directory / "Plugins" / plugin_name
    content_directory = plugin_directory / "Content"
    descriptor_path = plugin_directory / f"{plugin_name}.uplugin"

    plugin_already_exists = plugin_directory.exists()

    if plugin_already_exists and not confirm_existing_plugin(
        plugin_name, plugin_directory
    ):
        unreal.log_warning(
            f'Cancelled adding folders to existing plugin: {plugin_directory}'
        )
        return

    plugin_directory.mkdir(parents=True, exist_ok=True)
    content_directory.mkdir(parents=True, exist_ok=True)

    descriptor = {
        "FileVersion": 3,
        "Version": 1,
        "VersionName": "1.0",
        "FriendlyName": plugin_name,
        "Description": "Content-only Meccha Chameleon custom map plugin.",
        "Category": "Meccha Chameleon UGC",
        "CreatedBy": created_by,
        "CanContainContent": True,
        "IsBetaVersion": False,
        "Installed": False,
        "EnabledByDefault": True,
    }

    if not descriptor_path.exists():
        descriptor_path.write_text(
            json.dumps(descriptor, indent=4) + "\n",
            encoding="utf-8",
        )

    created_folders = []
    for relative_folder in CONTENT_FOLDERS:
        folder_path = content_directory / relative_folder
        if not folder_path.exists():
            folder_path.mkdir(parents=True, exist_ok=True)
            created_folders.append(relative_folder)

    readme_path = plugin_directory / "README.txt"
    if not readme_path.exists():
        readme_path.write_text(
            f"""{plugin_name}

Meccha Chameleon content-only UGC plugin.

Primary map location:
Plugins/{plugin_name}/Content/Maps

Important:
- Keep the playable map inside the Maps folder.
- Do not package the base game's character Blueprint.
- Use "{plugin_name}" as the DLC name when packaging My Mod.
- Restart Unreal Editor after creating this plugin.
""",
            encoding="utf-8",
        )

    if plugin_already_exists:
        folder_summary = (
            "No folders were missing."
            if not created_folders
            else "Added folders:\n- " + "\n- ".join(created_folders)
        )
        unreal.log(
            f"Updated existing Meccha UGC plugin: {plugin_directory}; "
            f"added {len(created_folders)} folder(s)."
        )
        unreal.EditorDialog.show_message(
            f"{plugin_name} Updated",
            f"The existing plugin was updated at:\n{plugin_directory}\n\n"
            f"{folder_summary}\n\n"
            "Existing files and folders were preserved.",
            unreal.AppMsgType.OK,
        )
    else:
        unreal.log(f"Created Meccha UGC plugin: {plugin_directory}")
        unreal.EditorDialog.show_message(
            f"{plugin_name} Created",
            f"The plugin was created successfully at:\n{plugin_directory}\n\n"
            "Restart Unreal Editor, then enable it from Edit → Plugins.",
            unreal.AppMsgType.OK,
        )


def main():
    details = request_plugin_details()
    if details is None:
        unreal.log_warning("Plugin creation was cancelled.")
        return
    create_plugin(*details)


try:
    main()
except Exception as error:
    unreal.log_error(f"[Meccha UGC Plugin Creator] {error}")
    unreal.EditorDialog.show_message(
        "Plugin Creation Failed",
        str(error),
        unreal.AppMsgType.OK,
    )
