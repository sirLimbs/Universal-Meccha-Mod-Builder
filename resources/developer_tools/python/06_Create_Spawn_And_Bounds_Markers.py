import unreal


SPAWN_LOCATION = unreal.Vector(0.0, 0.0, 100.0)
ARENA_WIDTH = 5000.0
ARENA_LENGTH = 5000.0
FLOOR_Z = 0.0
MARKER_HEIGHT = 300.0
FOLDER = "MecchaReferences"
TAG = "MecchaReferenceMarkerGenerated"
CREATE_CORNER_MARKERS = True
CREATE_CENTER_MARKER = True


def has_tag(actor):
    try:
        return any(str(tag) == TAG for tag in actor.get_editor_property("tags"))
    except Exception:
        return False


def configure(actor, label):
    actor.set_actor_label(label)
    actor.set_folder_path(unreal.Name(FOLDER))
    actor.set_editor_property("tags", [unreal.Name(TAG)])


def create_markers():
    subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    old = [actor for actor in subsystem.get_all_level_actors() if has_tag(actor)]
    for actor in old:
        subsystem.destroy_actor(actor)

    created = []
    spawn = subsystem.spawn_actor_from_class(
        unreal.TargetPoint,
        SPAWN_LOCATION,
        unreal.Rotator(),
        False,
    )
    if spawn:
        configure(spawn, "REFERENCE_GameSpawn_0_0_100")
        created.append(spawn)

    locations = []
    if CREATE_CENTER_MARKER:
        locations.append(("Center", unreal.Vector(0.0, 0.0, FLOOR_Z + MARKER_HEIGHT)))

    if CREATE_CORNER_MARKERS:
        half_x = ARENA_WIDTH / 2.0
        half_y = ARENA_LENGTH / 2.0
        locations.extend(
            [
                ("NorthEast", unreal.Vector(half_x, half_y, FLOOR_Z + MARKER_HEIGHT)),
                ("NorthWest", unreal.Vector(-half_x, half_y, FLOOR_Z + MARKER_HEIGHT)),
                ("SouthEast", unreal.Vector(half_x, -half_y, FLOOR_Z + MARKER_HEIGHT)),
                ("SouthWest", unreal.Vector(-half_x, -half_y, FLOOR_Z + MARKER_HEIGHT)),
            ]
        )

    for name, location in locations:
        marker = subsystem.spawn_actor_from_class(
            unreal.TargetPoint,
            location,
            unreal.Rotator(),
            False,
        )
        if marker:
            configure(marker, f"REFERENCE_Bounds_{name}")
            created.append(marker)

    subsystem.set_selected_level_actors(created)
    unreal.EditorDialog.show_message(
        "Reference Markers Created",
        f"Created {len(created)} non-colliding TargetPoint references.",
        unreal.AppMsgType.OK,
    )


try:
    create_markers()
except Exception as error:
    unreal.log_error(f"[Spawn and Bounds Markers] {error}")
