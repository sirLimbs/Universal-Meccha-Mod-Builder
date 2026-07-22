import unreal


# Replace selected actors with instances of this Blueprint or actor asset.
REPLACEMENT_ASSET_PATH = "/MyMapUGC/Blueprints/Props/BP_Replacement.BP_Replacement"
PRESERVE_LABELS = True
PRESERVE_FOLDERS = True
DESTROY_ORIGINALS = False


def load_replacement_class():
    asset = unreal.EditorAssetLibrary.load_asset(REPLACEMENT_ASSET_PATH)
    if not asset:
        raise RuntimeError(f"Could not load replacement asset:\n{REPLACEMENT_ASSET_PATH}")

    generated_class = getattr(asset, "generated_class", None)
    if generated_class:
        return generated_class()

    if isinstance(asset, unreal.Blueprint):
        return asset.generated_class()

    raise RuntimeError("Replacement asset is not a spawnable Blueprint.")


def replace_selected():
    subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    selected = list(subsystem.get_selected_level_actors())
    if not selected:
        raise RuntimeError("Select one or more actors first.")

    replacement_class = load_replacement_class()
    replacements = []

    for original in selected:
        replacement = subsystem.spawn_actor_from_class(
            replacement_class,
            original.get_actor_location(),
            original.get_actor_rotation(),
            False,
        )
        if not replacement:
            raise RuntimeError(f"Failed to replace {original.get_actor_label()}")

        replacement.set_actor_scale3d(original.get_actor_scale3d())

        if PRESERVE_LABELS:
            replacement.set_actor_label(original.get_actor_label())
        if PRESERVE_FOLDERS:
            replacement.set_folder_path(original.get_folder_path())

        replacements.append(replacement)

    if DESTROY_ORIGINALS:
        for original in selected:
            subsystem.destroy_actor(original)

    subsystem.set_selected_level_actors(replacements)
    unreal.EditorDialog.show_message(
        "Actor Replacement Complete",
        f"Created {len(replacements)} replacement actors.\n\n"
        f"Originals destroyed: {DESTROY_ORIGINALS}",
        unreal.AppMsgType.OK,
    )


try:
    replace_selected()
except Exception as error:
    unreal.log_error(f"[Replace Selected Actors] {error}")
