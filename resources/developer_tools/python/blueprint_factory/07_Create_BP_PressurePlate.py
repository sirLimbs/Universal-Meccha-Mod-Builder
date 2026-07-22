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

TEMPLATE = {'title': 'BP Pressure Plate', 'default_name': 'BP_PressurePlate', 'default_destination': '/MyMapUGC/Blueprints/Gameplay/Triggers', 'summary': 'Floor switch that activates interface-compatible target actors.', 'components': [{'name': 'PlateMesh', 'class': 'StaticMeshComponent'}, {'name': 'PressureVolume', 'class': 'BoxComponent'}], 'variables': [{'name': 'Targets', 'type': 'actor', 'array': True}, {'name': 'ToggleMode', 'type': 'bool'}, {'name': 'OneShot', 'type': 'bool'}, {'name': 'RequiredActorCount', 'type': 'int'}, {'name': 'DepressDistance', 'type': 'float'}, {'name': 'ResetDelay', 'type': 'float'}, {'name': 'IsPressed', 'type': 'bool', 'editable': False}, {'name': 'ActorsOnPlate', 'type': 'actor', 'array': True, 'editable': False}], 'functions': ['PressPlate', 'ReleasePlate', 'NotifyTargets', 'ResetPlate'], 'finish_steps': ['Track overlapping actors in ActorsOnPlate.', 'Press when the required count is reached.', 'Animate PlateMesh down and call the activation interface on Targets.', 'Release or reset according to ToggleMode and OneShot.']}

run_template(TEMPLATE)
