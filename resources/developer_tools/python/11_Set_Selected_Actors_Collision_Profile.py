import tkinter as tk
from tkinter import simpledialog

import unreal


DEFAULT_COLLISION_PROFILE = "BlockAll"
ENABLE_COLLISION = True


def request_profile():
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    profile = simpledialog.askstring(
        "Set Collision Profile",
        "Collision profile name:",
        initialvalue=DEFAULT_COLLISION_PROFILE,
        parent=root,
    )
    root.destroy()
    return profile.strip() if profile else ""


def set_collision_profile():
    subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    selected = list(subsystem.get_selected_level_actors())
    if not selected:
        raise RuntimeError("Select one or more actors first.")

    profile = request_profile()
    if not profile:
        unreal.log_warning("Collision profile change was cancelled.")
        return

    updated = 0
    skipped = []

    for actor in selected:
        components = actor.get_components_by_class(unreal.PrimitiveComponent)
        if not components:
            skipped.append(actor.get_actor_label())
            continue

        for component in components:
            component.set_collision_profile_name(unreal.Name(profile))
            component.set_collision_enabled(
                unreal.CollisionEnabled.QUERY_AND_PHYSICS
                if ENABLE_COLLISION
                else unreal.CollisionEnabled.NO_COLLISION
            )

        actor.set_actor_enable_collision(ENABLE_COLLISION)
        updated += 1

    message = f"Updated {updated} actors with collision profile:\n{profile}"
    if skipped:
        message += f"\n\nSkipped actors with no primitive components: {len(skipped)}"

    unreal.EditorDialog.show_message(
        "Collision Profiles Updated",
        message,
        unreal.AppMsgType.OK,
    )


try:
    set_collision_profile()
except Exception as error:
    unreal.log_error(f"[Set Collision Profile] {error}")
