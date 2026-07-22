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

TEMPLATE = {'title': 'BP Delayed Collision Barrier', 'default_name': 'BP_DelayedCollisionBarrier', 'default_destination': '/MyMapUGC/Blueprints/Gameplay/Barriers', 'summary': 'General delayed collision controller compatible with multiple primitive components.', 'components': [{'name': 'ActivationVolume', 'class': 'BoxComponent'}, {'name': 'BarrierPreview', 'class': 'BillboardComponent'}], 'variables': [{'name': 'BarrierActors', 'type': 'actor', 'array': True}, {'name': 'DelaySeconds', 'type': 'float'}, {'name': 'EnableCollision', 'type': 'bool'}, {'name': 'CollisionProfileName', 'type': 'name'}, {'name': 'ChangeVisibility', 'type': 'bool'}, {'name': 'VisibleAfterActivation', 'type': 'bool'}, {'name': 'OneShot', 'type': 'bool'}, {'name': 'Activated', 'type': 'bool', 'editable': False}], 'functions': ['ActivateBarrier', 'ApplyBarrierState', 'ResetBarrier'], 'finish_steps': ['Choose BeginPlay, overlap, or interface activation.', 'After DelaySeconds, loop through BarrierActors.', 'Get PrimitiveComponents on each actor and set collision/profile.', 'Use an invisible material rather than Actor Hidden in Game for invisible walls.']}

run_template(TEMPLATE)
