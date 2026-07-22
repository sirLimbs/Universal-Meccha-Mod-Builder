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

TEMPLATE = {'title': 'BP Simple Door', 'default_name': 'BP_SimpleDoor', 'default_destination': '/MyMapUGC/Blueprints/Interaction/Doors', 'summary': 'Rotating or sliding door shell with lock and auto-close settings.', 'components': [{'name': 'DoorFrameMesh', 'class': 'StaticMeshComponent'}, {'name': 'DoorMesh', 'class': 'StaticMeshComponent'}, {'name': 'InteractionVolume', 'class': 'BoxComponent'}], 'variables': [{'name': 'UseSlidingDoor', 'type': 'bool'}, {'name': 'OpenAngle', 'type': 'float'}, {'name': 'OpenOffset', 'type': 'vector'}, {'name': 'OpenTime', 'type': 'float'}, {'name': 'AutoClose', 'type': 'bool'}, {'name': 'AutoCloseDelay', 'type': 'float'}, {'name': 'Locked', 'type': 'bool'}, {'name': 'StartsOpen', 'type': 'bool'}, {'name': 'IsOpen', 'type': 'bool', 'editable': False}], 'functions': ['OpenDoor', 'CloseDoor', 'ToggleDoor', 'SetLocked'], 'finish_steps': ['Verify DoorMesh pivot for rotating mode.', 'Cache closed transform and create a 0-to-1 Timeline.', 'Lerp rotation or location according to UseSlidingDoor.', 'Connect overlap or interface activation and auto-close timer.']}

run_template(TEMPLATE)
