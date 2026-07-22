import re
import tkinter as tk
from tkinter import colorchooser, messagebox, ttk
import unreal

PRESETS = {
    "Standard Surface": dict(blend="opaque", shade="default", two=False, color=(0.5,0.5,0.5,1), rough=0.55, metal=0.0, spec=0.5, emissive=0.0, opacity=1.0),
    "Painted Prop": dict(blend="opaque", shade="default", two=False, color=(0.18,0.28,0.55,1), rough=0.42, metal=0.0, spec=0.45, emissive=0.0, opacity=1.0),
    "Metallic": dict(blend="opaque", shade="default", two=False, color=(0.35,0.37,0.4,1), rough=0.22, metal=1.0, spec=0.5, emissive=0.0, opacity=1.0),
    "Emissive": dict(blend="opaque", shade="default", two=False, color=(0.0,0.65,1.0,1), rough=0.3, metal=0.0, spec=0.5, emissive=8.0, opacity=1.0),
    "Glass": dict(blend="translucent", shade="default", two=True, color=(0.2,0.65,0.8,1), rough=0.08, metal=0.0, spec=0.6, emissive=0.0, opacity=0.18, refraction=1.02),
    "Unlit Artwork": dict(blend="opaque", shade="unlit", two=False, color=(1,1,1,1), rough=1.0, metal=0.0, spec=0.0, emissive=1.0, opacity=1.0),
    "Foliage": dict(blend="masked", shade="foliage", two=True, color=(0.18,0.48,0.12,1), rough=0.72, metal=0.0, spec=0.35, emissive=0.0, opacity=1.0),
    "Decal": dict(blend="translucent", shade="default", two=False, color=(1,1,1,1), rough=0.6, metal=0.0, spec=0.4, emissive=0.0, opacity=0.85, decal=True),
}


def enum_pick(enum_type, *names):
    for name in names:
        if hasattr(enum_type, name):
            return getattr(enum_type, name)
    raise RuntimeError(f"Missing enum value: {names}")


def clean_name(value):
    value = re.sub(r"[^A-Za-z0-9_]", "_", value.strip())
    value = re.sub(r"_+", "_", value).strip("_")
    if not value:
        raise RuntimeError("Asset name cannot be empty.")
    return f"Material_{value}" if value[0].isdigit() else value


def content_path(value):
    value = value.strip().replace("\\", "/").rstrip("/")
    if not value.startswith("/"):
        value = "/" + value
    if value.count("/") < 2:
        raise RuntimeError("Use a content path like /Game/Materials or /MyMapUGC/Materials.")
    return value


def hex_color(value):
    value = value.strip().lstrip("#")
    if not re.fullmatch(r"[0-9A-Fa-f]{6}", value):
        raise RuntimeError("Color must be a six-digit hex value.")
    return unreal.LinearColor(int(value[:2],16)/255, int(value[2:4],16)/255, int(value[4:],16)/255, 1)


def to_hex(color):
    return "#{:02X}{:02X}{:02X}".format(*(int(max(0,min(1,v))*255) for v in color[:3]))


def expression(material, cls, x, y):
    return unreal.MaterialEditingLibrary.create_material_expression(material, cls, x, y)


def scalar(material, name, default, x, y):
    node = expression(material, unreal.MaterialExpressionScalarParameter, x, y)
    node.set_editor_property("parameter_name", unreal.Name(name))
    node.set_editor_property("default_value", float(default))
    return node


def vector(material, name, default, x, y):
    node = expression(material, unreal.MaterialExpressionVectorParameter, x, y)
    node.set_editor_property("parameter_name", unreal.Name(name))
    node.set_editor_property("default_value", unreal.LinearColor(*default))
    return node


def texture(material, name, x, y):
    node = expression(material, unreal.MaterialExpressionTextureSampleParameter2D, x, y)
    node.set_editor_property("parameter_name", unreal.Name(name))
    return node


def connect_property(node, material, *names):
    for name in names:
        try:
            prop = getattr(unreal.MaterialProperty, name)
            if unreal.MaterialEditingLibrary.connect_material_property(node, "", prop) is not False:
                return
        except Exception:
            pass
    unreal.log_warning(f"Could not connect material property {names}")


def configure_material(material, preset):
    blend = {"opaque":("OPAQUE","BLEND_OPAQUE"), "masked":("MASKED","BLEND_MASKED"), "translucent":("TRANSLUCENT","BLEND_TRANSLUCENT")}[preset["blend"]]
    material.set_editor_property("blend_mode", enum_pick(unreal.BlendMode, *blend))
    material.set_editor_property("two_sided", preset["two"])
    shade = {"default":("DEFAULT_LIT","MSM_DEFAULT_LIT"), "unlit":("UNLIT","MSM_UNLIT"), "foliage":("TWO_SIDED_FOLIAGE","MSM_TWO_SIDED_FOLIAGE")}[preset["shade"]]
    try:
        material.set_editor_property("shading_model", enum_pick(unreal.MaterialShadingModel, *shade))
    except Exception as error:
        unreal.log_warning(f"Shading model not set automatically: {error}")
    if preset.get("decal"):
        try:
            material.set_editor_property("material_domain", enum_pick(unreal.MaterialDomain, "DEFERRED_DECAL", "MD_DEFERRED_DECAL"))
        except Exception as error:
            unreal.log_warning(f"Decal domain not set automatically: {error}")


def build_graph(material, preset):
    configure_material(material, preset)
    base = vector(material, "BaseColor", preset["color"], -700, -300)
    texture(material, "BaseTexture", -700, -100)
    rough = scalar(material, "Roughness", preset["rough"], -450, 100)
    metal = scalar(material, "Metallic", preset["metal"], -450, 200)
    spec = scalar(material, "Specular", preset["spec"], -450, 300)
    ecolor = vector(material, "EmissiveColor", preset["color"], -700, 450)
    estrength = scalar(material, "EmissiveStrength", preset["emissive"], -700, 550)
    multiply = expression(material, unreal.MaterialExpressionMultiply, -350, 500)
    unreal.MaterialEditingLibrary.connect_material_expressions(ecolor, "", multiply, "A")
    unreal.MaterialEditingLibrary.connect_material_expressions(estrength, "", multiply, "B")
    connect_property(base, material, "MP_BASE_COLOR", "BASE_COLOR")
    connect_property(rough, material, "MP_ROUGHNESS", "ROUGHNESS")
    connect_property(metal, material, "MP_METALLIC", "METALLIC")
    connect_property(spec, material, "MP_SPECULAR", "SPECULAR")
    connect_property(multiply, material, "MP_EMISSIVE_COLOR", "EMISSIVE_COLOR")
    if preset["blend"] in ("translucent", "masked"):
        opacity = scalar(material, "Opacity", preset["opacity"], -400, 680)
        connect_property(opacity, material, *("MP_OPACITY_MASK","OPACITY_MASK") if preset["blend"] == "masked" else ("MP_OPACITY","OPACITY"))
    if "refraction" in preset:
        refract = scalar(material, "Refraction", preset["refraction"], -400, 780)
        connect_property(refract, material, "MP_REFRACTION", "REFRACTION")
    unreal.MaterialEditingLibrary.layout_material_expressions(material)
    unreal.MaterialEditingLibrary.recompile_material(material)
    unreal.EditorAssetLibrary.save_loaded_asset(material)


def make_asset(name, folder, cls, factory):
    path = f"{folder}/{name}"
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        raise RuntimeError(f"Asset already exists:\n{path}")
    asset = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, folder, cls, factory)
    if not asset:
        raise RuntimeError(f"Failed to create asset:\n{path}")
    return asset


def create_instance(parent, name, folder, values):
    instance = make_asset(name, folder, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    lib = unreal.MaterialEditingLibrary
    lib.set_material_instance_parent(instance, parent)
    lib.set_material_instance_vector_parameter_value(instance, unreal.Name("BaseColor"), values["color"])
    for parameter, key in (("Roughness","rough"),("Metallic","metal"),("Specular","spec"),("EmissiveStrength","emissive"),("Opacity","opacity"),("Refraction","refraction")):
        if key in values:
            lib.set_material_instance_scalar_parameter_value(instance, unreal.Name(parameter), float(values[key]))
    lib.update_material_instance(instance)
    unreal.EditorAssetLibrary.save_loaded_asset(instance)
    return instance


class Dialog:
    def __init__(self):
        self.root = tk.Tk(); self.root.title("Meccha Material Factory"); self.root.attributes("-topmost", True); self.root.resizable(False, False)
        self.result = None
        self.preset = tk.StringVar(value="Standard Surface"); self.name = tk.StringVar(value="MySurface"); self.folder = tk.StringVar(value="/MyMapUGC/Materials")
        self.color = tk.StringVar(); self.rough = tk.StringVar(); self.metal = tk.StringVar(); self.spec = tk.StringVar(); self.emissive = tk.StringVar(); self.opacity = tk.StringVar(); self.instance = tk.BooleanVar(value=True)
        frame = ttk.Frame(self.root, padding=16); frame.pack(); frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text="Create a parameterized master material and instance.", font=("Segoe UI",11,"bold")).grid(row=0,column=0,columnspan=3,sticky="w",pady=(0,12))
        self.row(frame,1,"Preset",ttk.Combobox(frame,textvariable=self.preset,values=list(PRESETS),state="readonly",width=30))
        self.row(frame,2,"Asset base name",ttk.Entry(frame,textvariable=self.name,width=33))
        self.row(frame,3,"Destination",ttk.Entry(frame,textvariable=self.folder,width=33))
        self.row(frame,4,"Base color",ttk.Entry(frame,textvariable=self.color,width=24)); ttk.Button(frame,text="Choose…",command=self.choose).grid(row=4,column=2,padx=(8,0))
        for row,label,var in ((5,"Roughness",self.rough),(6,"Metallic",self.metal),(7,"Specular",self.spec),(8,"Emissive strength",self.emissive),(9,"Opacity",self.opacity)):
            self.row(frame,row,label,ttk.Entry(frame,textvariable=var,width=33))
        ttk.Checkbutton(frame,text="Create Material Instance",variable=self.instance).grid(row=10,column=1,sticky="w",pady=(8,0))
        buttons=ttk.Frame(frame); buttons.grid(row=11,column=0,columnspan=3,sticky="e",pady=(14,0)); ttk.Button(buttons,text="Cancel",command=self.root.destroy).pack(side="left",padx=(0,8)); ttk.Button(buttons,text="Create",command=self.submit).pack(side="left")
        self.preset.trace_add("write",lambda *_:self.apply()); self.apply(); self.root.bind("<Escape>",lambda _:self.root.destroy()); self.root.bind("<Return>",lambda _:self.submit())
    def row(self,frame,row,label,widget):
        ttk.Label(frame,text=label+":").grid(row=row,column=0,sticky="w",padx=(0,10),pady=4); widget.grid(row=row,column=1,sticky="ew",pady=4)
    def apply(self):
        p=PRESETS[self.preset.get()]; self.color.set(to_hex(p["color"])); self.rough.set(str(p["rough"])); self.metal.set(str(p["metal"])); self.spec.set(str(p["spec"])); self.emissive.set(str(p["emissive"])); self.opacity.set(str(p["opacity"]))
    def choose(self):
        selected=colorchooser.askcolor(color=self.color.get(),parent=self.root)[1]
        if selected:self.color.set(selected)
    def submit(self):
        try:
            p=dict(PRESETS[self.preset.get()]); c=hex_color(self.color.get()); p.update(color=(c.r,c.g,c.b,c.a),rough=float(self.rough.get()),metal=float(self.metal.get()),spec=float(self.spec.get()),emissive=float(self.emissive.get()),opacity=float(self.opacity.get()))
            for key in ("rough","metal","spec","opacity"):
                if not 0<=p[key]<=1: raise RuntimeError(f"{key} must be between 0 and 1.")
            self.result=dict(name=clean_name(self.name.get()),folder=content_path(self.folder.get()),preset=p,instance=self.instance.get(),values=dict(color=c,rough=p["rough"],metal=p["metal"],spec=p["spec"],emissive=p["emissive"],opacity=p["opacity"],refraction=p.get("refraction",1.0)))
            self.root.destroy()
        except Exception as error: messagebox.showerror("Invalid Settings",str(error),parent=self.root)
    def show(self): self.root.mainloop(); return self.result


def main():
    settings=Dialog().show()
    if not settings:return
    folder=settings["folder"]; instances=f"{folder}/Instances"; unreal.EditorAssetLibrary.make_directory(folder); unreal.EditorAssetLibrary.make_directory(instances)
    material=make_asset(f"M_{settings['name']}_Master",folder,unreal.Material,unreal.MaterialFactoryNew()); build_graph(material,settings["preset"])
    created=[material.get_path_name()]
    if settings["instance"]: created.append(create_instance(material,f"MI_{settings['name']}",instances,settings["values"]).get_path_name())
    unreal.EditorDialog.show_message("Meccha Material Factory Complete","Created:\n"+"\n".join(created),unreal.AppMsgType.OK)


try:
    main()
except Exception as error:
    unreal.log_error(f"[Meccha Material Factory] {error}")
    unreal.EditorDialog.show_message("Material Factory Failed",str(error),unreal.AppMsgType.OK)
