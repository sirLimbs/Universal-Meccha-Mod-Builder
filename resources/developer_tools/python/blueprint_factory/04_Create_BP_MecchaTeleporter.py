from pathlib import Path
import sys

# Unreal's "Execute Python Script" does not always add the selected script's
# folder to sys.path. Add it explicitly so the shared factory helper can load.
SCRIPT_DIR = str(Path(__file__).resolve().parent)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import importlib
import _meccha_blueprint_factory_common as meccha_blueprint_factory_common

# Unreal keeps imported Python modules cached for the editor session.
# Reload the helper so replacing the pack takes effect without restarting UE.
importlib.invalidate_caches()
meccha_blueprint_factory_common = importlib.reload(
    meccha_blueprint_factory_common
)
run_template = meccha_blueprint_factory_common.run_template

TEMPLATE = {'title': 'BP Meccha Teleporter', 'default_name': 'BP_MecchaTeleporter', 'default_destination': '/MyMapUGC/Blueprints/Movement/Teleporters', 'summary': 'Teleport trigger shell with destination actor, delay, cooldown, and portal visuals.', 'components': [{'name': 'TriggerVolume', 'class': 'BoxComponent'}, {'name': 'PortalMesh', 'class': 'StaticMeshComponent'}, {'name': 'DestinationPreview', 'class': 'ArrowComponent'}], 'variables': [{'name': 'DestinationActor', 'type': 'actor'}, {'name': 'DestinationTransform', 'type': 'transform'}, {'name': 'UseDestinationActor', 'type': 'bool'}, {'name': 'PreserveVelocity', 'type': 'bool'}, {'name': 'RotateToDestination', 'type': 'bool'}, {'name': 'ExitOffset', 'type': 'vector'}, {'name': 'TeleportDelay', 'type': 'float'}, {'name': 'Cooldown', 'type': 'float'}, {'name': 'PlayerOnly', 'type': 'bool'}, {'name': 'Enabled', 'type': 'bool'}, {'name': 'ActorToTeleport', 'type': 'actor', 'editable': False}, {'name': 'CoolingDown', 'type': 'bool', 'editable': False}], 'functions': ['PerformTeleport', 'ResetCooldown', 'CanTeleport'], 'finish_steps': ['Set TriggerVolume to overlap the Meccha player.', 'On overlap, validate PlayerOnly, Enabled, and cooldown.', 'Use DestinationActor transform when valid; otherwise use DestinationTransform.', 'Call Teleport or SetActorLocationAndRotation, then apply cooldown.']}

run_template(TEMPLATE)
