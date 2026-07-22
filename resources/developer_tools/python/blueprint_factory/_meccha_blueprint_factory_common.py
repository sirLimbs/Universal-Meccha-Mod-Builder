import re
import tkinter as tk
from tkinter import messagebox, ttk

import unreal

FACTORY_HELPER_REVISION = "1.0.3"


COMPONENT_CLASSES = {
    "BoxComponent": unreal.BoxComponent,
    "ArrowComponent": unreal.ArrowComponent,
    "BillboardComponent": unreal.BillboardComponent,
    "StaticMeshComponent": unreal.StaticMeshComponent,
}


def normalize_content_path(value):
    value = str(value).strip().replace("\\", "/").rstrip("/")
    if not value.startswith("/"):
        value = "/" + value
    if not (value.startswith("/Game") or value.count("/") >= 2):
        raise RuntimeError(
            "Use an Unreal content path such as /Game/Blueprints or "
            "/MyMapUGC/Blueprints/Core."
        )
    return value


def sanitize_name(value, default_name):
    value = re.sub(r"[^A-Za-z0-9_]", "_", str(value).strip())
    value = re.sub(r"_+", "_", value).strip("_")
    if not value:
        value = default_name
    if value[0].isdigit():
        value = "BP_" + value
    return value


def basic_type(name):
    aliases = {"float": "real", "boolean": "bool", "integer": "int"}
    return unreal.BlueprintEditorLibrary.get_basic_type_by_name(
        unreal.Name(aliases.get(name.lower(), name.lower()))
    )


def variable_pin_type(type_name):
    type_name = type_name.lower()

    if type_name in {"bool", "boolean", "float", "real", "int", "integer", "name", "string", "text"}:
        return basic_type(type_name)
    if type_name == "actor":
        return unreal.BlueprintEditorLibrary.get_object_reference_type(unreal.Actor)
    if type_name == "static_mesh_actor":
        return unreal.BlueprintEditorLibrary.get_object_reference_type(unreal.StaticMeshActor)
    if type_name == "material_interface":
        return unreal.BlueprintEditorLibrary.get_object_reference_type(unreal.MaterialInterface)
    if type_name == "sound_base":
        return unreal.BlueprintEditorLibrary.get_object_reference_type(unreal.SoundBase)
    if type_name == "vector":
        return unreal.BlueprintEditorLibrary.get_struct_type(unreal.Vector.static_struct())
    if type_name == "rotator":
        return unreal.BlueprintEditorLibrary.get_struct_type(unreal.Rotator.static_struct())
    if type_name == "transform":
        return unreal.BlueprintEditorLibrary.get_struct_type(unreal.Transform.static_struct())

    raise RuntimeError(f"Unsupported variable type: {type_name}")


def create_blueprint(template, asset_path):
    if unreal.EditorAssetLibrary.does_asset_exist(asset_path):
        raise RuntimeError(f"Asset already exists:\n{asset_path}")

    if template.get("interface"):
        # UE 5.6 exposes a dedicated BlueprintInterfaceFactory. BlueprintFactory
        # itself does not expose a blueprint_type editor property in this build.
        factory = unreal.BlueprintInterfaceFactory()
        destination, asset_name = asset_path.rsplit("/", 1)
        blueprint = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
            asset_name,
            destination,
            unreal.Blueprint,
            factory,
        )
    else:
        blueprint = unreal.BlueprintEditorLibrary.create_blueprint_asset_with_parent(
            asset_path,
            unreal.Actor,
        )

    if not blueprint:
        raise RuntimeError(f"Could not create Blueprint:\n{asset_path}")

    return blueprint


def add_component(blueprint, component_info):
    subsystem = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    handles = subsystem.k2_gather_subobject_data_for_blueprint(blueprint)
    if not handles:
        raise RuntimeError("Could not gather Blueprint subobject data.")

    component_class = COMPONENT_CLASSES[component_info["class"]]
    params = unreal.AddNewSubobjectParams(
        parent_handle=handles[0],
        new_class=component_class,
        blueprint_context=blueprint,
        conform_transform_to_parent=True,
    )
    handle, fail_reason = subsystem.add_new_subobject(params)

    if not handle:
        raise RuntimeError(str(fail_reason))

    try:
        subsystem.rename_subobject(handle, unreal.Text(component_info["name"]))
    except Exception:
        try:
            subsystem.rename_subobject_member_variable(
                blueprint,
                handle,
                unreal.Name(component_info["name"]),
            )
        except Exception:
            pass


def add_variable(blueprint, variable_info):
    pin_type = variable_pin_type(variable_info["type"])
    if variable_info.get("array"):
        pin_type = unreal.BlueprintEditorLibrary.get_array_type(pin_type)

    success = unreal.BlueprintEditorLibrary.add_member_variable(
        blueprint,
        unreal.Name(variable_info["name"]),
        pin_type,
    )
    if not success:
        raise RuntimeError("add_member_variable returned False")

    if variable_info.get("editable", True):
        unreal.BlueprintEditorLibrary.set_blueprint_variable_instance_editable(
            blueprint,
            unreal.Name(variable_info["name"]),
            True,
        )


class BlueprintDialog:
    def __init__(self, template):
        self.template = template
        self.result = None

        self.root = tk.Tk()
        self.root.title(f"Meccha Blueprint Factory — {template['title']}")
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)

        self.name_var = tk.StringVar(value=template["default_name"])
        self.destination_var = tk.StringVar(value=template["default_destination"])

        frame = ttk.Frame(self.root, padding=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text=template["title"], font=("Segoe UI", 12, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w"
        )
        ttk.Label(frame, text=template["summary"], wraplength=500, justify="left").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(5, 14)
        )
        ttk.Label(frame, text="Asset name:").grid(row=2, column=0, sticky="w", padx=(0, 10), pady=5)
        ttk.Entry(frame, textvariable=self.name_var, width=45).grid(row=2, column=1, sticky="ew", pady=5)
        ttk.Label(frame, text="Destination:").grid(row=3, column=0, sticky="w", padx=(0, 10), pady=5)
        ttk.Entry(frame, textvariable=self.destination_var, width=45).grid(row=3, column=1, sticky="ew", pady=5)
        ttk.Label(
            frame,
            text=(
                "The generator creates the asset shell, components, variables, "
                "and function placeholders. A completion popup lists the remaining graph work."
            ),
            wraplength=500,
            justify="left",
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(12, 12))

        buttons = ttk.Frame(frame)
        buttons.grid(row=5, column=0, columnspan=2, sticky="e")
        ttk.Button(buttons, text="Cancel", command=self.cancel).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="Create Blueprint", command=self.submit).pack(side="left")

        self.root.bind("<Escape>", lambda _event: self.cancel())
        self.root.bind("<Return>", lambda _event: self.submit())
        self.root.protocol("WM_DELETE_WINDOW", self.cancel)

    def submit(self):
        try:
            self.result = {
                "name": sanitize_name(self.name_var.get(), self.template["default_name"]),
                "destination": normalize_content_path(self.destination_var.get()),
            }
            self.root.destroy()
        except Exception as error:
            messagebox.showerror("Invalid Settings", str(error), parent=self.root)

    def cancel(self):
        self.result = None
        self.root.destroy()

    def show(self):
        self.root.mainloop()
        return self.result


def run_template(template):
    try:
        settings = BlueprintDialog(template).show()
        if not settings:
            unreal.log_warning(f"Blueprint creation cancelled. Helper {FACTORY_HELPER_REVISION}")
            return

        asset_path = f"{settings['destination']}/{settings['name']}"
        blueprint = create_blueprint(template, asset_path)
        warnings = []

        for component in template.get("components", []):
            try:
                add_component(blueprint, component)
            except Exception as error:
                warnings.append(f"Component {component['name']}: {error}")

        for variable in template.get("variables", []):
            try:
                add_variable(blueprint, variable)
            except Exception as error:
                warnings.append(f"Variable {variable['name']}: {error}")

        for function_name in template.get("functions", []):
            try:
                unreal.BlueprintEditorLibrary.add_function_graph(blueprint, function_name)
            except Exception as error:
                warnings.append(f"Function {function_name}: {error}")

        try:
            unreal.BlueprintEditorLibrary.compile_blueprint(blueprint)
        except Exception as error:
            warnings.append(f"Compile: {error}")

        unreal.EditorAssetLibrary.save_loaded_asset(blueprint)

        try:
            unreal.get_editor_subsystem(
                unreal.AssetEditorSubsystem
            ).open_editor_for_assets([blueprint])
        except Exception:
            pass

        steps = "\n".join(
            f"{index}. {step}"
            for index, step in enumerate(template["finish_steps"], start=1)
        )
        warning_text = ""
        if warnings:
            warning_text = "\n\nReview these generator warnings:\n- " + "\n- ".join(warnings)

        unreal.EditorDialog.show_message(
            f"{template['title']} Created",
            (
                f"Factory helper: {FACTORY_HELPER_REVISION}\n"
                f"Created:\n{blueprint.get_path_name()}\n\n"
                f"Finish these steps:\n{steps}"
                f"{warning_text}\n\n"
                "Compile, save, and test in a temporary level."
            ),
            unreal.AppMsgType.OK,
        )

    except Exception as error:
        unreal.log_error(
            f"[Meccha Blueprint Factory {FACTORY_HELPER_REVISION}] {error}"
        )
        unreal.EditorDialog.show_message(
            "Blueprint Factory Failed",
            str(error),
            unreal.AppMsgType.OK,
        )
