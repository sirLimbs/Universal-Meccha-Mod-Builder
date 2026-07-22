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

TEMPLATE = {'title': 'BP Falling Floor', 'default_name': 'BP_FallingFloor', 'default_destination': '/MyMapUGC/Blueprints/Gameplay/Hazards', 'summary': 'Warning-and-drop floor panel with optional reset.', 'components': [{'name': 'FloorMesh', 'class': 'StaticMeshComponent'}, {'name': 'TriggerVolume', 'class': 'BoxComponent'}], 'variables': [{'name': 'WarningDelay', 'type': 'float'}, {'name': 'FallDistance', 'type': 'float'}, {'name': 'FallTime', 'type': 'float'}, {'name': 'ResetDelay', 'type': 'float'}, {'name': 'RespawnAfterFall', 'type': 'bool'}, {'name': 'DisableCollisionWhileDown', 'type': 'bool'}, {'name': 'Triggered', 'type': 'bool', 'editable': False}, {'name': 'StartLocation', 'type': 'vector', 'editable': False}], 'functions': ['TriggerFall', 'DropFloor', 'ResetFloor'], 'finish_steps': ['Set FloorMesh Mobility to Movable.', 'On overlap, wait WarningDelay and optionally flash or shake.', 'Use a Timeline to move down by FallDistance.', 'Disable collision and reset after ResetDelay if enabled.']}

run_template(TEMPLATE)
