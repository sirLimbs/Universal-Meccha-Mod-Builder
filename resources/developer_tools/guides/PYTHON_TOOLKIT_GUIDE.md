# Meccha Chameleon UE 5.6 Python Toolkit

These scripts are intended to be run from Unreal Editor 5.6 through:

`Tools → Execute Python Script`

They are editor utilities. Back up your project or commit your work before running
scripts that create, delete, move, rename, or replace actors.

## Included scripts

1. `01_Create_Meccha_UGC_Plugin.py`
   Creates a content-only UGC plugin and a recommended folder structure.

2. `02_Generate_Configurable_Arena_Blockout.py`
   Creates a configurable floor, sealed perimeter walls, optional panel grid,
   spawn reference, and basic lighting.

3. `03_Batch_Import_Images_To_Numbered_Actors.py`
   Imports numbered images, creates material instances, and assigns them to
   numbered StaticMeshActors.

4. `04_Audit_Current_Level_For_Meccha_UGC.py`
   Reports common issues such as missing spawn references, duplicate labels,
   zero scales, missing meshes, and movable static meshes.

5. `05_Organize_Selected_Actors_Into_Folders.py`
   Moves selected actors into clean World Outliner folders.

6. `06_Create_Spawn_And_Bounds_Markers.py`
   Creates non-colliding TargetPoint references for the Meccha spawn and arena bounds.

7. `07_Batch_Rename_Selected_Actors.py`
   Renames selected actors sequentially with a chosen prefix.

8. `08_Randomize_Selected_Props.py`
   Adds deterministic location, rotation, and scale variation to selected props.

9. `09_Replace_Selected_Actors_With_Asset.py`
   Replaces selected actors with a configured Blueprint while preserving transforms.

10. `10_Export_Current_Level_Actor_Report.py`
    Exports actor labels, classes, folders, assets, transforms, and collision state to CSV.

11. `11_Set_Selected_Actors_Collision_Profile.py`
    Applies a named collision profile to primitive components on selected actors.

12. `12_Distribute_Selected_Actors_In_Grid.py`
    Arranges selected actors into a configurable grid.

13. `13_Export_Selected_Blueprint_Data.py`
    Exports selected Blueprint assets to a readable JSON format for inspection and
    documentation. The exporter attempts to capture:

    - Blueprint parent class and generated class
    - Class hierarchy
    - Blueprint variables
    - Construction, Event, Function and Macro graphs (when exposed)
    - Graph nodes, pins and connections
    - Component hierarchy
    - Class Default Object (CDO) properties
    - Editable component properties
    - Engine version and asset metadata

    This script is intended for reverse engineering existing Meccha gameplay
    Blueprints (teleporters, moving platforms, doors, ladders, escalators,
    triggers, etc.) so they can be recreated, improved or documented.

14. `14_Meccha_Material_Factory.py`
    Creates fully parameterized Unreal Materials and optional Material Instances
    through a simple popup window.

    Features include:

    - Material name and destination selection
    - Built-in material presets
    - Color picker
    - Roughness
    - Metallic
    - Specular
    - Emissive Strength
    - Opacity
    - Automatic Material Instance creation
    - Automatic parameter generation
    - Automatic graph layout and recompilation

    Included presets:

    - Standard Surface
    - Painted Prop
    - Metallic
    - Emissive
    - Glass
    - Unlit Artwork
    - Foliage
    - Decal

    Generated assets:

        M_<Name>_Master
        MI_<Name>

    The generated master material contains reusable parameter nodes for:

    - BaseColor
    - BaseTexture
    - Roughness
    - Metallic
    - Specular
    - EmissiveColor
    - EmissiveStrength
    - Opacity
    - Refraction (where applicable)

## Additional Documentation

Detailed setup guides for the Blueprint exporter, Material Factory, reusable
Blueprint templates, and Editor Utility Widgets can be found in:

guides/
└── BLUEPRINT_AND_MATERIAL_GUIDE.md

## Before running 

Open each script and review the configuration values near the top before
executing it.

Many scripts contain placeholder Unreal content paths such as:

/MyMapUGC/

Replace these with the appropriate content path for your project or plugin.

Some scripts create or modify assets, actors, materials, or folders inside the
current project. It is recommended to:

- Commit your project to source control first.
- Back up important maps.
- Test new scripts in a temporary project before using them in production.

The scripts have been syntax-checked with standard Python but should still be
tested inside your specific Unreal Engine 5.6 Meccha Chameleon project because
available assets, collision profiles, Blueprint classes, material settings and
plugin APIs may differ between projects.

For advanced Blueprint generation, Material Factory usage, and reusable gameplay
Blueprint setup, see:

guides/BLUEPRINT_AND_MATERIAL_GUIDE.md
