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

TEMPLATE = {'title': 'BP Meccha Trigger Base', 'default_name': 'BP_MecchaTriggerBase', 'default_destination': '/MyMapUGC/Blueprints/Core/Triggers', 'summary': 'Reusable overlap-trigger parent with one-shot, cooldown, filtering, and activation placeholders.', 'components': [{'name': 'TriggerVolume', 'class': 'BoxComponent'}, {'name': 'DebugArrow', 'class': 'ArrowComponent'}], 'variables': [{'name': 'Enabled', 'type': 'bool'}, {'name': 'OneShot', 'type': 'bool'}, {'name': 'Cooldown', 'type': 'float'}, {'name': 'RequiredActorTag', 'type': 'name'}, {'name': 'DebugEnabled', 'type': 'bool'}, {'name': 'HasTriggered', 'type': 'bool', 'editable': False}, {'name': 'CoolingDown', 'type': 'bool', 'editable': False}, {'name': 'LastOverlappingActor', 'type': 'actor', 'editable': False}], 'functions': ['ActivateTrigger', 'CanActivate', 'ResetTrigger'], 'finish_steps': ['Set TriggerVolume collision to overlap the Meccha player/pawn.', 'Add OnComponentBeginOverlap and validate Enabled, cooldown, one-shot, and actor tag.', 'Store Other Actor, call ActivateTrigger, then start the cooldown timer.']}

run_template(TEMPLATE)
