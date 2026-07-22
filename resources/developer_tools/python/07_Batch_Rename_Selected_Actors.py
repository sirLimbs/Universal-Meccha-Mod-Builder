import tkinter as tk
from tkinter import simpledialog

import unreal


STARTING_NUMBER = 1
DIGITS = 3
SORT_BY_LOCATION = True


def ask_text(title, prompt, initial):
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    value = simpledialog.askstring(title, prompt, initialvalue=initial, parent=root)
    root.destroy()
    return value


def rename_selected():
    subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    actors = list(subsystem.get_selected_level_actors())
    if not actors:
        raise RuntimeError("Select one or more actors first.")

    prefix = ask_text(
        "Batch Rename Selected Actors",
        "Actor label prefix:",
        "SM_Prop",
    )
    if not prefix:
        unreal.log_warning("Batch rename was cancelled.")
        return

    if SORT_BY_LOCATION:
        actors.sort(
            key=lambda actor: (
                actor.get_actor_location().y,
                actor.get_actor_location().x,
                actor.get_actor_location().z,
            )
        )

    for number, actor in enumerate(actors, start=STARTING_NUMBER):
        actor.set_actor_label(f"{prefix}_{number:0{DIGITS}d}")

    unreal.EditorDialog.show_message(
        "Batch Rename Complete",
        f"Renamed {len(actors)} actors using prefix:\n{prefix}",
        unreal.AppMsgType.OK,
    )


try:
    rename_selected()
except Exception as error:
    unreal.log_error(f"[Batch Rename] {error}")
