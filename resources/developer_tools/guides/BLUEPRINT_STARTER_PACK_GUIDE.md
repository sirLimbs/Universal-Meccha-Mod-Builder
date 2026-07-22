# Meccha UE5.6 Blueprint Starter Pack

## Included generators

1. BPI_MecchaActivatable
2. BP_MecchaTriggerBase
3. BP_TeleporterTarget
4. BP_MecchaTeleporter
5. BP_MovingPlatform
6. BP_DelayedCollisionBarrier
7. BP_PressurePlate
8. BP_SimpleDoor
9. BP_FallingFloor
10. BP_JumpPad

## Install

Keep `_meccha_blueprint_factory_common.py` beside the ten numbered scripts.

Recommended Unreal location:

```text
<Project>/Content/Python/MecchaBlueprintFactory/
```

Or include the whole folder under:

```text
resources/developer_tools/python/blueprint_factory/
```

Enable **Python Editor Script Plugin** and **Editor Scripting Utilities**, then restart UE.

## Run

1. Tools → Execute Python Script
2. Choose a numbered script.
3. Fill in the asset name and Unreal destination.
4. Press Create Blueprint.
5. Follow the completion popup.
6. Compile, save, and test in a temporary level.

## Organization

```text
<MyMapUGC>/
└── Blueprints/
    ├── Core/
    │   ├── Interfaces/
    │   └── Triggers/
    ├── Movement/
    │   ├── Teleporters/
    │   ├── Platforms/
    │   └── Launchers/
    ├── Gameplay/
    │   ├── Barriers/
    │   ├── Triggers/
    │   └── Hazards/
    ├── Interaction/
    │   └── Doors/
    └── Templates/
```

## Parent and child strategy

Use parent Blueprints for reusable logic and child Blueprints for map-specific art and values.

```text
BP_MecchaTeleporter
├── BP_CastleTeleporter
├── BP_WinterTeleporter
└── BP_GalaxyTeleporter

BP_MovingPlatform
├── BP_ElevatorPlatform
├── BP_FloatingRockPlatform
└── BP_ConveyorPlatform
```

Children should mainly override meshes, materials, sounds, timing, travel distance, and destination references.

## Limitation

The generators create Blueprint assets, components, member variables, function graph placeholders,
compile, save, and open the asset. Complete Event Graph node placement, Timeline creation, latent
nodes, game-specific casts, and pin wiring still need a manual pass or a verified template Blueprint.
