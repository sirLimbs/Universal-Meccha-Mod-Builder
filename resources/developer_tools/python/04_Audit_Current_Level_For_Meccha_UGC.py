import unreal


# Checks common map-authoring issues without modifying the level.

REQUIRED_SPAWN_LOCATION = unreal.Vector(0.0, 0.0, 100.0)
SPAWN_TOLERANCE = 10.0
MAX_ACTOR_COUNT_WARNING = 2500
CHECK_DUPLICATE_LABELS = True
CHECK_ZERO_SCALE = True
CHECK_MISSING_STATIC_MESHES = True
CHECK_MOVABLE_STATIC_MESHES = True


def nearly_equal(a, b, tolerance):
    return abs(a - b) <= tolerance


def audit_level():
    actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if not actor_subsystem or not level_subsystem:
        raise RuntimeError("Required Unreal Editor subsystems are unavailable.")

    actors = actor_subsystem.get_all_level_actors()
    warnings = []
    errors = []
    label_counts = {}
    spawn_found = False

    if len(actors) > MAX_ACTOR_COUNT_WARNING:
        warnings.append(
            f"High actor count: {len(actors)} actors "
            f"(warning threshold: {MAX_ACTOR_COUNT_WARNING})."
        )

    for actor in actors:
        label = actor.get_actor_label()
        label_counts[label] = label_counts.get(label, 0) + 1

        location = actor.get_actor_location()
        if (
            nearly_equal(location.x, REQUIRED_SPAWN_LOCATION.x, SPAWN_TOLERANCE)
            and nearly_equal(location.y, REQUIRED_SPAWN_LOCATION.y, SPAWN_TOLERANCE)
            and nearly_equal(location.z, REQUIRED_SPAWN_LOCATION.z, SPAWN_TOLERANCE)
        ):
            if isinstance(actor, (unreal.TargetPoint, unreal.PlayerStart)):
                spawn_found = True

        if CHECK_ZERO_SCALE:
            scale = actor.get_actor_scale3d()
            if abs(scale.x) < 0.0001 or abs(scale.y) < 0.0001 or abs(scale.z) < 0.0001:
                errors.append(f"Zero scale component: {label}")

        if isinstance(actor, unreal.StaticMeshActor):
            component = actor.static_mesh_component
            if CHECK_MISSING_STATIC_MESHES and component and not component.static_mesh:
                errors.append(f"StaticMeshActor has no mesh: {label}")

            if (
                CHECK_MOVABLE_STATIC_MESHES
                and component
                and component.mobility == unreal.ComponentMobility.MOVABLE
            ):
                warnings.append(f"Movable StaticMeshActor: {label}")

    if not spawn_found:
        errors.append(
            "No TargetPoint or PlayerStart was found near "
            f"{REQUIRED_SPAWN_LOCATION}."
        )

    if CHECK_DUPLICATE_LABELS:
        for label, count in sorted(label_counts.items()):
            if count > 1:
                warnings.append(f"Duplicate actor label ({count}): {label}")

    level_name = level_subsystem.get_current_level_name()
    lines = [
        f"Level: {level_name}",
        f"Actors scanned: {len(actors)}",
        f"Errors: {len(errors)}",
        f"Warnings: {len(warnings)}",
        "",
        "ERRORS",
        "------",
        *(errors or ["None"]),
        "",
        "WARNINGS",
        "--------",
        *(warnings or ["None"]),
    ]
    report = "\n".join(lines)
    unreal.log(report)

    unreal.EditorDialog.show_message(
        "Meccha UGC Level Audit",
        report[:8000],
        unreal.AppMsgType.OK,
    )


try:
    audit_level()
except Exception as error:
    unreal.log_error(f"[Meccha UGC Audit] {error}")
