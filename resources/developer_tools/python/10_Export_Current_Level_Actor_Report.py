import csv
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog

import unreal


def choose_output_path(default_name):
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    path = filedialog.asksaveasfilename(
        title="Export Current Level Actor Report",
        defaultextension=".csv",
        initialfile=default_name,
        filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        parent=root,
    )
    root.destroy()
    return path


def actor_asset_path(actor):
    if isinstance(actor, unreal.StaticMeshActor):
        component = actor.static_mesh_component
        if component and component.static_mesh:
            return component.static_mesh.get_path_name()

    try:
        actor_class = actor.get_class()
        return actor_class.get_path_name() if actor_class else ""
    except Exception:
        return ""


def export_report():
    actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    actors = list(actor_subsystem.get_all_level_actors())
    level_name = level_subsystem.get_current_level_name()

    default_name = (
        f"{level_name}_ActorReport_{datetime.now():%Y%m%d_%H%M%S}.csv"
    )
    output_text = choose_output_path(default_name)
    if not output_text:
        unreal.log_warning("Actor report export was cancelled.")
        return

    output_path = Path(output_text)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            [
                "Label",
                "Class",
                "Folder",
                "AssetOrClassPath",
                "LocationX",
                "LocationY",
                "LocationZ",
                "Pitch",
                "Yaw",
                "Roll",
                "ScaleX",
                "ScaleY",
                "ScaleZ",
                "CollisionEnabled",
            ]
        )

        for actor in sorted(actors, key=lambda item: item.get_actor_label().lower()):
            location = actor.get_actor_location()
            rotation = actor.get_actor_rotation()
            scale = actor.get_actor_scale3d()

            try:
                collision = actor.get_actor_enable_collision()
            except Exception:
                collision = ""

            writer.writerow(
                [
                    actor.get_actor_label(),
                    actor.get_class().get_name(),
                    str(actor.get_folder_path()),
                    actor_asset_path(actor),
                    location.x,
                    location.y,
                    location.z,
                    rotation.pitch,
                    rotation.yaw,
                    rotation.roll,
                    scale.x,
                    scale.y,
                    scale.z,
                    collision,
                ]
            )

    unreal.EditorDialog.show_message(
        "Actor Report Exported",
        f"Exported {len(actors)} actors to:\n{output_path}",
        unreal.AppMsgType.OK,
    )


try:
    export_report()
except Exception as error:
    unreal.log_error(f"[Actor Report Export] {error}")
