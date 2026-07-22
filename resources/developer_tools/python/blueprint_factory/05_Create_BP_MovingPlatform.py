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

TEMPLATE = {'title': 'BP Moving Platform', 'default_name': 'BP_MovingPlatform', 'default_destination': '/MyMapUGC/Blueprints/Movement/Platforms', 'summary': 'Moving floor shell with offset, timing, loop, ping-pong, and activation settings.', 'components': [{'name': 'PlatformMesh', 'class': 'StaticMeshComponent'}, {'name': 'EndPointPreview', 'class': 'ArrowComponent'}, {'name': 'ActivationVolume', 'class': 'BoxComponent'}], 'variables': [{'name': 'EndOffset', 'type': 'vector'}, {'name': 'TravelTime', 'type': 'float'}, {'name': 'StartDelay', 'type': 'float'}, {'name': 'Loop', 'type': 'bool'}, {'name': 'PingPong', 'type': 'bool'}, {'name': 'StartActive', 'type': 'bool'}, {'name': 'PauseAtEnds', 'type': 'float'}, {'name': 'StartLocation', 'type': 'vector', 'editable': False}, {'name': 'EndLocation', 'type': 'vector', 'editable': False}], 'functions': ['StartMoving', 'StopMoving', 'ReverseMoving', 'ResetPlatform'], 'finish_steps': ['Set PlatformMesh Mobility to Movable.', 'Cache StartLocation and calculate EndLocation from EndOffset.', 'Create a Timeline from 0 to 1 and Lerp the actor location.', 'Use the Finished output for ping-pong, looping, or pauses.']}

run_template(TEMPLATE)
