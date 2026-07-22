import os
import re
import tkinter as tk
from tkinter import filedialog

import unreal


# ============================================================
# BATCH IMPORT IMAGES AND ASSIGN THEM TO NUMBERED ACTORS
# ============================================================
# Generic replacement for the original RugWorld-specific script.
#
# Expected source names:
#   Image01.png, Image02.jpg, ... Image12.png
#
# Expected actor labels by default:
#   Panel_01_R1_C1, Panel_02_R1_C2, ...
#
# Change the configuration below to match your project.
# ============================================================

SOURCE_FOLDER = ""  # Leave empty to choose a folder when the script starts.
CONTENT_ROOT = "/MyMapUGC"
TEXTURE_DESTINATION = f"{CONTENT_ROOT}/Textures/Imported"
MATERIAL_INSTANCE_DESTINATION = f"{CONTENT_ROOT}/Materials/Instances"
MASTER_MATERIAL_PATH = (
    f"{CONTENT_ROOT}/Materials/Master/"
    "M_NumberedPanel_Master.M_NumberedPanel_Master"
)

TEXTURE_PARAMETER_NAME = "PanelImage"
EXPECTED_IMAGE_COUNT = 12
ACTOR_LABEL_PATTERN = r"^Panel_(\d+)(?:_R\d+_C\d+)?$"
TEXTURE_NAME_FORMAT = "T_Panel_{number:02d}"
MATERIAL_INSTANCE_NAME_FORMAT = "MI_Panel_{number:02d}"

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tga", ".bmp"}
REPLACE_EXISTING_TEXTURES = True


def log(message):
    unreal.log(f"[Batch Image Assignment] {message}")


def choose_source_folder():
    if SOURCE_FOLDER:
        return SOURCE_FOLDER

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    selected = filedialog.askdirectory(
        title="Select the folder containing numbered images",
        parent=root,
    )
    root.destroy()
    return selected


def extract_numeric_order(path):
    name = os.path.splitext(os.path.basename(path))[0]
    matches = re.findall(r"\d+", name)
    return int(matches[-1]) if matches else None


def find_images(source_folder):
    if not os.path.isdir(source_folder):
        raise RuntimeError(f"Source folder does not exist:\n{source_folder}")

    images = []
    for filename in os.listdir(source_folder):
        full_path = os.path.join(source_folder, filename)
        if not os.path.isfile(full_path):
            continue
        if os.path.splitext(filename)[1].lower() not in SUPPORTED_EXTENSIONS:
            continue
        number = extract_numeric_order(full_path)
        if number is not None:
            images.append((number, full_path))

    images.sort(key=lambda item: (item[0], os.path.basename(item[1]).lower()))

    expected = list(range(1, EXPECTED_IMAGE_COUNT + 1))
    detected = [number for number, _path in images]
    if detected != expected:
        raise RuntimeError(
            f"Expected numbered images 1 through {EXPECTED_IMAGE_COUNT}.\n\n"
            f"Detected numbers: {detected}"
        )

    return images


def load_asset_checked(asset_path):
    asset = unreal.EditorAssetLibrary.load_asset(asset_path)
    if not asset:
        raise RuntimeError(f"Could not load asset:\n{asset_path}")
    return asset


def import_texture(source_file, asset_name):
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", source_file)
    task.set_editor_property("destination_path", TEXTURE_DESTINATION)
    task.set_editor_property("destination_name", asset_name)
    task.set_editor_property("replace_existing", REPLACE_EXISTING_TEXTURES)
    task.set_editor_property("automated", True)
    task.set_editor_property("save", True)

    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])

    imported_paths = task.get_editor_property("imported_object_paths")
    if imported_paths:
        texture = unreal.EditorAssetLibrary.load_asset(imported_paths[0])
    else:
        texture = unreal.EditorAssetLibrary.load_asset(
            f"{TEXTURE_DESTINATION}/{asset_name}"
        )

    if not texture:
        raise RuntimeError(f"Failed to import:\n{source_file}")

    try:
        texture.set_editor_property("srgb", True)
        texture.set_editor_property(
            "compression_settings",
            unreal.TextureCompressionSettings.TC_DEFAULT,
        )
    except Exception as error:
        unreal.log_warning(f"Texture settings were not fully applied: {error}")

    unreal.EditorAssetLibrary.save_loaded_asset(texture)
    return texture


def create_or_update_material_instance(master_material, number):
    name = MATERIAL_INSTANCE_NAME_FORMAT.format(number=number)
    path = f"{MATERIAL_INSTANCE_DESTINATION}/{name}"
    instance = unreal.EditorAssetLibrary.load_asset(path)

    if not instance:
        factory = unreal.MaterialInstanceConstantFactoryNew()
        instance = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
            name,
            MATERIAL_INSTANCE_DESTINATION,
            unreal.MaterialInstanceConstant,
            factory,
        )

    if not instance:
        raise RuntimeError(f"Could not create material instance: {name}")

    unreal.MaterialEditingLibrary.set_material_instance_parent(
        instance,
        master_material,
    )
    unreal.MaterialEditingLibrary.update_material_instance(instance)
    unreal.EditorAssetLibrary.save_loaded_asset(instance)
    return instance


def assign_texture(instance, texture):
    parameter = unreal.Name(TEXTURE_PARAMETER_NAME)
    unreal.MaterialEditingLibrary.set_material_instance_texture_parameter_value(
        instance,
        parameter,
        texture,
        unreal.MaterialParameterAssociation.GLOBAL_PARAMETER,
    )
    unreal.MaterialEditingLibrary.update_material_instance(instance)
    unreal.EditorAssetLibrary.save_loaded_asset(instance)


def find_numbered_actors(actor_subsystem):
    pattern = re.compile(ACTOR_LABEL_PATTERN, re.IGNORECASE)
    actors = {}

    for actor in actor_subsystem.get_all_level_actors():
        match = pattern.match(actor.get_actor_label())
        if match:
            number = int(match.group(1))
            if number in actors:
                raise RuntimeError(
                    f"Duplicate actor number {number}: "
                    f"{actors[number].get_actor_label()} and {actor.get_actor_label()}"
                )
            actors[number] = actor

    missing = [
        number
        for number in range(1, EXPECTED_IMAGE_COUNT + 1)
        if number not in actors
    ]
    if missing:
        raise RuntimeError(f"Missing numbered actors: {missing}")

    return actors


def assign_material(actor, material):
    if not isinstance(actor, unreal.StaticMeshActor):
        raise RuntimeError(f"{actor.get_actor_label()} is not a StaticMeshActor.")
    component = actor.static_mesh_component
    if not component:
        raise RuntimeError(f"{actor.get_actor_label()} has no StaticMeshComponent.")
    component.set_material(0, material)


def run():
    source_folder = choose_source_folder()
    if not source_folder:
        unreal.log_warning("Image import was cancelled.")
        return

    actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if not actor_subsystem or not level_subsystem:
        raise RuntimeError("Required Unreal Editor subsystems are unavailable.")
    if level_subsystem.is_in_play_in_editor():
        raise RuntimeError("Stop Play In Editor before running this script.")

    images = find_images(source_folder)
    actors = find_numbered_actors(actor_subsystem)
    master = load_asset_checked(MASTER_MATERIAL_PATH)

    for number, source_file in images:
        texture = import_texture(
            source_file,
            TEXTURE_NAME_FORMAT.format(number=number),
        )
        instance = create_or_update_material_instance(master, number)
        assign_texture(instance, texture)
        assign_material(actors[number], instance)
        log(f"{os.path.basename(source_file)} → {actors[number].get_actor_label()}")

    if not level_subsystem.save_current_level():
        unreal.log_warning("Assignments completed, but level save was not confirmed.")

    unreal.EditorDialog.show_message(
        "Batch Image Assignment Complete",
        f"Imported and assigned {len(images)} images.",
        unreal.AppMsgType.OK,
    )


try:
    run()
except Exception as error:
    unreal.log_error(f"[Batch Image Assignment] {error}")
    unreal.EditorDialog.show_message(
        "Batch Image Assignment Failed",
        str(error),
        unreal.AppMsgType.OK,
    )
