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

TEMPLATE = {'title': 'BPI Meccha Activatable', 'default_name': 'BPI_MecchaActivatable', 'default_destination': '/MyMapUGC/Blueprints/Core/Interfaces', 'summary': 'Shared activation interface for doors, platforms, barriers, lights, and triggers.', 'interface': True, 'components': [], 'variables': [], 'functions': ['Activate', 'Deactivate', 'Toggle', 'Reset'], 'finish_steps': ['Confirm the created asset is a Blueprint Interface.', 'Add an optional Instigator Actor input to the interface functions.', 'Implement the interface through Class Settings on reusable gameplay Blueprints.']}

run_template(TEMPLATE)
