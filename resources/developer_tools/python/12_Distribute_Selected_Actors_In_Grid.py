import math

import unreal


COLUMNS = 4
SPACING_X = 300.0
SPACING_Y = 300.0
KEEP_ORIGINAL_Z = True
CENTER_GRID_ON_SELECTION = True
SORT_BY_LABEL = True


def distribute_selected():
    subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    actors = list(subsystem.get_selected_level_actors())
    if not actors:
        raise RuntimeError("Select one or more actors first.")
    if COLUMNS < 1:
        raise RuntimeError("COLUMNS must be at least 1.")

    if SORT_BY_LABEL:
        actors.sort(key=lambda actor: actor.get_actor_label().lower())

    rows = math.ceil(len(actors) / COLUMNS)
    average_x = sum(actor.get_actor_location().x for actor in actors) / len(actors)
    average_y = sum(actor.get_actor_location().y for actor in actors) / len(actors)
    average_z = sum(actor.get_actor_location().z for actor in actors) / len(actors)

    start_x = average_x
    start_y = average_y

    if CENTER_GRID_ON_SELECTION:
        used_columns = min(COLUMNS, len(actors))
        start_x -= (used_columns - 1) * SPACING_X / 2.0
        start_y -= (rows - 1) * SPACING_Y / 2.0

    for index, actor in enumerate(actors):
        row = index // COLUMNS
        column = index % COLUMNS
        old_location = actor.get_actor_location()
        actor.set_actor_location(
            unreal.Vector(
                start_x + column * SPACING_X,
                start_y + row * SPACING_Y,
                old_location.z if KEEP_ORIGINAL_Z else average_z,
            ),
            False,
            False,
        )

    unreal.EditorDialog.show_message(
        "Grid Distribution Complete",
        f"Distributed {len(actors)} actors across {rows} row(s).",
        unreal.AppMsgType.OK,
    )


try:
    distribute_selected()
except Exception as error:
    unreal.log_error(f"[Distribute Selected Actors] {error}")
