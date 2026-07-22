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

TEMPLATE = {'title': 'BP Jump Pad', 'default_name': 'BP_JumpPad', 'default_destination': '/MyMapUGC/Blueprints/Movement/Launchers', 'summary': 'Launch pad shell with arrow- or target-based velocity.', 'components': [{'name': 'PadMesh', 'class': 'StaticMeshComponent'}, {'name': 'LaunchVolume', 'class': 'BoxComponent'}, {'name': 'LaunchDirection', 'class': 'ArrowComponent'}], 'variables': [{'name': 'LaunchStrength', 'type': 'float'}, {'name': 'LaunchDirectionVector', 'type': 'vector'}, {'name': 'UseArrowDirection', 'type': 'bool'}, {'name': 'TargetActor', 'type': 'actor'}, {'name': 'UseTargetActor', 'type': 'bool'}, {'name': 'PreserveHorizontalVelocity', 'type': 'bool'}, {'name': 'PreserveVerticalVelocity', 'type': 'bool'}, {'name': 'Cooldown', 'type': 'float'}, {'name': 'CoolingDown', 'type': 'bool', 'editable': False}], 'functions': ['LaunchActor', 'CalculateLaunchVelocity', 'ResetCooldown'], 'finish_steps': ['Set LaunchVolume to overlap the Meccha player.', 'Use TargetActor trajectory logic or LaunchDirection forward vector.', "Call LaunchCharacter or Meccha's supported movement method.", 'Apply cooldown and optional effects.']}

run_template(TEMPLATE)
