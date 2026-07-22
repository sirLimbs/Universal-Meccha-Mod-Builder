# Meccha Blueprint and Material Starter Guide

## Enable the required UE5.6 plugins

1. Open **Edit → Plugins**.
2. Enable **Python Editor Script Plugin**.
3. Enable **Editor Scripting Utilities**.
4. Enable **Editor Utility Widgets** if shown separately.
5. Restart Unreal Editor.

Python is editor-only. Use it to inspect and generate assets. Gameplay logic must live in Blueprint or C++.

---

## Export Blueprint data for analysis

Use `python/01_Export_Selected_Blueprint_Data.py`.

1. Select one or more Blueprint assets in the Content Browser.
2. Choose **Tools → Execute Python Script**.
3. Run the exporter.
4. Choose an output folder.
5. Send the generated `*_BlueprintData.json` files.

Use it on teleporters, moving floors, ladders, escalators, doors, triggers, barriers, and working gameplay examples. It exports parent class, variables, graph names, graph nodes and pins when exposed, default-object properties, and components.

---

## Run Meccha Material Factory

Use `python/02_Meccha_Material_Factory.py`.

1. Choose **Tools → Execute Python Script**.
2. Select a preset.
3. Enter an asset base name.
4. Enter your real plugin content path, such as `/RugWorldUGC/Materials`.
5. Adjust the color and numeric values.
6. Leave **Create Material Instance** checked.
7. Press **Create**.
8. Open the generated Material and verify its graph once before broad use.

It creates:

- `M_<Name>_Master`
- `Instances/MI_<Name>`

Presets: Standard Surface, Painted Prop, Metallic, Emissive, Glass, Unlit Artwork, Foliage, and Decal.

The master includes editable BaseColor, BaseTexture, Roughness, Metallic, Specular, EmissiveColor, EmissiveStrength, Opacity, and Refraction parameters where relevant. BaseColor is connected by default; BaseTexture is provided as a ready node so the material still compiles without requiring a texture.

---

# Recommended Blueprint folder

```text
Blueprints/
    Core/
    Movement/
    Triggers/
    Interaction/
    Visual/
    Audio/
    EditorUtilities/
```

Recommended starting assets:

```text
Core/BP_MecchaTriggerBase
Triggers/BP_Teleporter
Movement/BP_MovingPlatform
Movement/BP_Elevator
Movement/BP_Escalator
Movement/BP_LadderVolume
Interaction/BP_SimpleDoor
Core/BP_TimedBarrier
Visual/BP_DynamicMaterialProp
Audio/BP_AmbientAudioZone
```

---

# 1. BP_MecchaTriggerBase

Create an **Actor Blueprint**.

## Components

- Scene root
- Box Collision named `Trigger`

Set Trigger to overlap the player/pawn and ignore unrelated objects.

## Variables

- `Enabled` — Boolean, true, Instance Editable
- `OneShot` — Boolean, false, Instance Editable
- `Cooldown` — Float, 0, Instance Editable
- `RequiredActorTag` — Name, None, Instance Editable
- `HasTriggered` — Boolean, false
- `CoolingDown` — Boolean, false

## Event graph

On `Trigger → OnComponentBeginOverlap`:

1. Branch on `Enabled`.
2. Branch on `NOT CoolingDown`.
3. If `OneShot`, require `NOT HasTriggered`.
4. If `RequiredActorTag` is not None, call `Actor Has Tag` on Other Actor.
5. Call custom event `ActivateTrigger`.
6. Set `HasTriggered` true.
7. If Cooldown is greater than zero, set `CoolingDown` true and use `Set Timer by Event` to reset it.

Use this as the parent of doors, teleporters, and trigger-driven objects.

---

# 2. BP_Teleporter

Create a child Blueprint of `BP_MecchaTriggerBase`.

## Components

- Inherited Trigger
- Arrow named `DestinationPreview`
- Optional portal mesh or Niagara effect

## Variables

- `DestinationActor` — Actor reference, Instance Editable
- `DestinationTransform` — Transform, Instance Editable
- `UseDestinationActor` — Boolean, true
- `PreserveVelocity` — Boolean, false
- `ExitOffset` — Vector, default 0,0,100
- `TeleportDelay` — Float, 0
- `RotateToDestination` — Boolean, true

## Activation logic

1. Store Other Actor from overlap.
2. Use DestinationActor transform when assigned; otherwise use DestinationTransform.
3. Add ExitOffset to destination location.
4. Call `Teleport` or `SetActorLocationAndRotation`.
5. If PreserveVelocity is false, clear velocity through the character movement component when available.
6. Use the inherited cooldown to prevent an immediate teleport loop.

Place a TargetPoint at each exit and assign it to DestinationActor.

---

# 3. BP_MovingPlatform

Create an Actor Blueprint.

## Components

- Scene root
- Static Mesh named `Platform`, Mobility = Movable
- Optional Box Collision activation trigger

## Variables

- `EndOffset` — Vector, default 0,0,500
- `TravelTime` — Float, 3
- `StartDelay` — Float, 0
- `Loop` — Boolean, true
- `PingPong` — Boolean, true
- `StartActive` — Boolean, true

## Graph

1. Begin Play: cache `StartLocation`.
2. Set `EndLocation = StartLocation + EndOffset`.
3. Add Timeline `MovementTimeline` with a float track 0→1 over TravelTime.
4. Timeline Update: Lerp Vector from StartLocation to EndLocation.
5. Call SetActorLocation with Sweep enabled.
6. Timeline Finished: Reverse for ping-pong or restart for looping.

Test whether Meccha's character correctly inherits platform motion.

---

# 4. BP_Elevator

Create as a child of `BP_MovingPlatform`.

- Use a vertical EndOffset.
- Add lower and upper trigger boxes.
- Add state enum: Bottom, MovingUp, Top, MovingDown.
- Ignore calls while moving.
- Add optional pause timers at each floor.

---

# 5. BP_Escalator

The stable approach is a static stair mesh plus an invisible movement volume.

## Components

- Escalator/stair Static Mesh
- Box Collision named `MovementVolume`
- Arrow named `TravelDirection`

## Variables

- `PushSpeed` — Float, 150
- `Enabled` — Boolean, true
- `ActorsInside` — Actor array

## Graph

1. Begin overlap: add Other Actor uniquely to ActorsInside.
2. End overlap: remove Other Actor.
3. Tick: for each valid actor, multiply Arrow forward vector by `PushSpeed × DeltaSeconds`.
4. Use AddActorWorldOffset with Sweep enabled.
5. Remove invalid entries.

A character-movement-based version may be better after inspecting Meccha's player Blueprint.

---

# 6. BP_LadderVolume

## Components

- Box Collision `LadderVolume`
- Arrow showing upward direction
- Optional ladder mesh

## Variables

- `ClimbSpeed` — Float, 250
- `AutoClimb` — Boolean, true
- `ClimbingActor` — Actor reference
- `OriginalGravityScale` — Float

## Generic graph

1. Begin overlap: verify supported character and store it.
2. Store its current gravity scale.
3. Set gravity scale to zero or change movement mode appropriately.
4. While overlapping, move upward by `ClimbSpeed × DeltaSeconds` or use player input.
5. End overlap: restore gravity and movement mode.
6. Add top/bottom exit triggers for safe placement.

Export a working Meccha movement Blueprint before finalizing this; character movement details are game-specific.

---

# 7. BP_SimpleDoor

## Components

- Doorframe mesh
- Movable Door mesh
- Trigger box

## Variables

- `OpenAngle` — Float, 90
- `OpenTime` — Float, 1
- `AutoClose` — Boolean, true
- `AutoCloseDelay` — Float, 2
- `Locked` — Boolean, false

Cache the closed rotation. Use a Timeline 0→1 and Lerp Rotator to the open rotation. Begin overlap plays forward; end overlap or a timer reverses.

---

# 8. BP_TimedBarrier

## Components

- Barrier mesh
- Separate blocking collision component

## Variables

- `DisableAfterSeconds` — Float, 25
- `ReEnableAfterSeconds` — Float, 30
- `StartEnabled` — Boolean, true
- `HideWhenDisabled` — Boolean, false

On Begin Play, start a timer. Disable collision and optionally hide the barrier. Start a second timer to restore both.

---

# 9. BP_DynamicMaterialProp

## Components

- Static Mesh

## Variables

- `SourceMaterial` — Material Interface
- `ColorParameter` — Name, BaseColor
- `EmissiveParameter` — Name, EmissiveStrength
- `InitialColor` — Linear Color
- `InitialEmissive` — Float
- `DynamicMaterial` — Material Instance Dynamic reference

On Begin Play, call Create Dynamic Material Instance on mesh slot 0. Store it. Add functions `SetColor`, `SetGlow`, and `Pulse` using Set Vector/Scalar Parameter Value.

---

# 10. BP_AmbientAudioZone

## Components

- Box Collision
- Audio Component

## Variables

- `LoopingSound`
- `FadeInSeconds`
- `FadeOutSeconds`
- `Volume`

Begin overlap assigns/plays and fades in. End overlap fades out. Guard against duplicate component overlaps.

---

# Optional Editor Utility Widget launcher

1. Create Editor Utility Widget `EUW_MecchaTools`.
2. Add two buttons: Export Blueprint Data and Material Factory.
3. On Click, use `Execute Python Command`.
4. During testing, point to the absolute script path.
5. Later place scripts in your project's or enabled plugin's `Content/Python` folder and execute them by filename.

Regular Actor Blueprints cannot run editor-only Python in packaged gameplay.
