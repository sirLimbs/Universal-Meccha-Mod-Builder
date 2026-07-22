import json
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog

import unreal

MAX_ITEMS = 250
MAX_TEXT = 2000


def text(value):
    try:
        result = str(value)
    except Exception:
        result = repr(value)
    return result if len(result) <= MAX_TEXT else result[:MAX_TEXT] + "..."


def path_name(obj):
    if obj is None:
        return None
    try:
        return obj.get_path_name()
    except Exception:
        return text(obj)


def class_name(obj):
    try:
        return obj.get_class().get_name()
    except Exception:
        return type(obj).__name__


def reflected_properties(obj):
    output = {}
    if obj is None:
        return output
    for name in dir(obj):
        if name.startswith("_"):
            continue
        try:
            value = obj.get_editor_property(name)
        except Exception:
            continue
        if isinstance(value, (bool, int, float, str)) or value is None:
            output[name] = value
        elif isinstance(value, (list, tuple, unreal.Array)):
            output[name] = [text(item) for item in list(value)[:MAX_ITEMS]]
        else:
            output[name] = {"class": class_name(value), "path": path_name(value), "text": text(value)}
    return output


def export_pin(pin):
    data = {
        "name": text(getattr(pin, "pin_name", "")),
        "direction": text(getattr(pin, "direction", "")),
        "default_value": text(getattr(pin, "default_value", "")),
        "links": [],
    }
    try:
        pin_type = pin.pin_type
        data["type"] = {
            "category": text(pin_type.pin_category),
            "subcategory": text(pin_type.pin_sub_category),
            "subcategory_object": path_name(pin_type.pin_sub_category_object),
            "container": text(pin_type.container_type),
        }
    except Exception:
        pass
    try:
        data["links"] = [
            {"node": linked.get_outer().get_name(), "pin": text(linked.pin_name)}
            for linked in list(pin.linked_to)
        ]
    except Exception:
        pass
    return data


def export_graph(graph):
    try:
        nodes = list(graph.get_editor_property("nodes"))
    except Exception:
        nodes = []
    exported = []
    for node in nodes[:MAX_ITEMS]:
        item = {"name": node.get_name(), "class": class_name(node), "pins": []}
        for prop in ("node_pos_x", "node_pos_y", "node_comment", "enabled_state"):
            try:
                item[prop] = text(node.get_editor_property(prop))
            except Exception:
                pass
        try:
            item["title"] = text(node.get_node_title(unreal.NodeTitleType.FULL_TITLE))
        except Exception:
            item["title"] = node.get_name()
        try:
            item["pins"] = [export_pin(pin) for pin in list(node.pins)]
        except Exception:
            pass
        exported.append(item)
    return {"name": graph.get_name(), "class": class_name(graph), "nodes": exported, "node_count": len(nodes)}


def graphs_for(blueprint):
    output, seen = [], set()
    for prop in ("ubergraph_pages", "function_graphs", "macro_graphs", "delegate_signature_graphs"):
        try:
            graphs = list(blueprint.get_editor_property(prop))
        except Exception:
            continue
        for graph in graphs:
            key = path_name(graph)
            if graph and key not in seen:
                seen.add(key)
                output.append(export_graph(graph))
    return output


def variables_for(blueprint):
    try:
        variables = list(blueprint.get_editor_property("new_variables"))
    except Exception:
        variables = []
    return [reflected_properties(variable) for variable in variables]


def components_for(default_object):
    if default_object is None:
        return []
    try:
        components = default_object.get_components_by_class(unreal.ActorComponent)
    except Exception:
        components = []
    return [
        {"name": component.get_name(), "class": class_name(component), "properties": reflected_properties(component)}
        for component in components
    ]


def export_blueprint(asset):
    blueprint = unreal.BlueprintEditorLibrary.get_blueprint_asset(asset)
    if not blueprint:
        raise RuntimeError(f"Not a readable Blueprint: {path_name(asset)}")
    try:
        generated_class = blueprint.generated_class()
    except Exception:
        generated_class = blueprint.get_editor_property("generated_class")
    default_object = unreal.get_default_object(generated_class) if generated_class else None
    try:
        parent_class = blueprint.get_editor_property("parent_class")
    except Exception:
        parent_class = None
    return {
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "engine_version": text(unreal.SystemLibrary.get_engine_version()),
        "asset": {"name": asset.get_name(), "path": path_name(asset), "class": class_name(asset)},
        "blueprint": {
            "parent_class": path_name(parent_class),
            "generated_class": path_name(generated_class),
            "variables": variables_for(blueprint),
            "graphs": graphs_for(blueprint),
            "properties": reflected_properties(blueprint),
        },
        "default_object": {
            "path": path_name(default_object),
            "properties": reflected_properties(default_object),
            "components": components_for(default_object),
        },
    }


def choose_folder():
    root = tk.Tk(); root.withdraw(); root.attributes("-topmost", True)
    selected = filedialog.askdirectory(title="Choose Blueprint export folder", parent=root)
    root.destroy()
    return Path(selected) if selected else None


def main():
    assets = list(unreal.EditorUtilityLibrary.get_selected_assets())
    if not assets:
        raise RuntimeError("Select one or more Blueprint assets in the Content Browser first.")
    folder = choose_folder()
    if folder is None:
        return
    folder.mkdir(parents=True, exist_ok=True)
    done, failed = [], []
    for asset in assets:
        try:
            destination = folder / f"{asset.get_name()}_BlueprintData.json"
            destination.write_text(json.dumps(export_blueprint(asset), indent=2), encoding="utf-8")
            done.append(str(destination))
        except Exception as error:
            failed.append(f"{asset.get_name()}: {error}")
    message = f"Exported: {len(done)}\nFailed: {len(failed)}"
    if done:
        message += "\n\n" + "\n".join(done[:10])
    if failed:
        message += "\n\nFailures:\n" + "\n".join(failed[:10])
    unreal.EditorDialog.show_message("Blueprint Data Export", message, unreal.AppMsgType.OK)


try:
    main()
except Exception as error:
    unreal.log_error(f"[Blueprint Data Exporter] {error}")
    unreal.EditorDialog.show_message("Blueprint Export Failed", str(error), unreal.AppMsgType.OK)
