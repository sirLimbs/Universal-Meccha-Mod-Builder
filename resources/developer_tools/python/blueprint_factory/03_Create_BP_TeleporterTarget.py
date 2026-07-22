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

TEMPLATE = {'title': 'BP Teleporter Target', 'default_name': 'BP_TeleporterTarget', 'default_destination': '/MyMapUGC/Blueprints/Movement/Teleporters', 'summary': 'Editor target marking teleporter exit position and facing direction.', 'components': [{'name': 'ExitArrow', 'class': 'ArrowComponent'}, {'name': 'ExitBillboard', 'class': 'BillboardComponent'}], 'variables': [{'name': 'TargetID', 'type': 'name'}, {'name': 'ExitOffset', 'type': 'vector'}], 'functions': [], 'finish_steps': ['Choose a Billboard sprite if desired.', 'Place the target at the exit and rotate ExitArrow toward the desired facing direction.']}

run_template(TEMPLATE)
