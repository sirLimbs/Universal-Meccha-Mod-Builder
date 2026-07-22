import tkinter as tk
from tkinter import simpledialog

import unreal


DEFAULT_FOLDER = "Map/Props"
USE_CLASS_SUBFOLDERS = True


def request_folder():
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    value = simpledialog.askstring(
        "Organize Selected Actors",
        "Base World Outliner folder:",
        initialvalue=DEFAULT_FOLDER,
        parent=root,
    )
    root.destroy()
    return value.strip().strip("/") if value else ""


def organize_selected():
    actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    selected = actor_subsystem.get_selected_level_actors()
    if not selected:
        raise RuntimeError("Select one or more actors first.")

    base_folder = request_folder()
    if not base_folder:
        unreal.log_warning("Actor organization was cancelled.")
        return

    for actor in selected:
        folder = base_folder
        if USE_CLASS_SUBFOLDERS:
            class_name = actor.get_class().get_name()
            folder = f"{base_folder}/{class_name}"
        actor.set_folder_path(unreal.Name(folder))

    unreal.EditorDialog.show_message(
        "Actors Organized",
        f"Moved {len(selected)} selected actors under:\n{base_folder}",
        unreal.AppMsgType.OK,
    )


try:
    organize_selected()
except Exception as error:
    unreal.log_error(f"[Organize Selected Actors] {error}")
    unreal.EditorDialog.show_message(
        "Organization Failed",
        str(error),
        unreal.AppMsgType.OK,
    )
