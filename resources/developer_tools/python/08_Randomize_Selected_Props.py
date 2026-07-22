import random

import unreal


SEED = 12345
YAW_RANGE = (-180.0, 180.0)
PITCH_RANGE = (0.0, 0.0)
ROLL_RANGE = (0.0, 0.0)
UNIFORM_SCALE_RANGE = (0.9, 1.1)
LOCATION_JITTER_XY = 25.0
LOCATION_JITTER_Z = 0.0


def randomize_selected():
    subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    actors = list(subsystem.get_selected_level_actors())
    if not actors:
        raise RuntimeError("Select one or more actors first.")

    random.seed(SEED)

    for actor in actors:
        location = actor.get_actor_location()
        actor.set_actor_location(
            unreal.Vector(
                location.x + random.uniform(-LOCATION_JITTER_XY, LOCATION_JITTER_XY),
                location.y + random.uniform(-LOCATION_JITTER_XY, LOCATION_JITTER_XY),
                location.z + random.uniform(-LOCATION_JITTER_Z, LOCATION_JITTER_Z),
            ),
            False,
            False,
        )

        rotation = actor.get_actor_rotation()
        actor.set_actor_rotation(
            unreal.Rotator(
                rotation.pitch + random.uniform(*PITCH_RANGE),
                rotation.yaw + random.uniform(*YAW_RANGE),
                rotation.roll + random.uniform(*ROLL_RANGE),
            ),
            False,
        )

        scale = random.uniform(*UNIFORM_SCALE_RANGE)
        actor.set_actor_scale3d(unreal.Vector(scale, scale, scale))

    unreal.EditorDialog.show_message(
        "Prop Randomization Complete",
        f"Randomized {len(actors)} selected actors using seed {SEED}.",
        unreal.AppMsgType.OK,
    )


try:
    randomize_selected()
except Exception as error:
    unreal.log_error(f"[Randomize Selected Props] {error}")
