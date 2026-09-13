"""Build the Task 10-R-PCB-V1 presentation PCB scene in Blender."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.task08_data import load_json, write_json
from stage_10R_pcb_presentation.scripts.pcb_presentation_data import (
    ASSET_TEXTURE,
    BASELINE,
    BOARD_THICKNESS_MM,
    CAMERAS_PATH,
    EXPECTED_PART_IDS,
    HIDDEN_PART_IDS,
    MANIFEST_PATH,
    MATERIALS_PATH,
    SCENE_OUTPUT,
    SOURCE_SCENE,
    SOURCE_SCENE_SHA256,
    STORY_PART_IDS,
    build_material_contract,
)
from stage_10_product_story.scripts.build_story_scene import mesh_geometry_fingerprint

try:  # pragma: no cover - executed through Blender.
    import bpy  # type: ignore
    from mathutils import Vector  # type: ignore
except ImportError:  # pragma: no cover
    bpy = None  # type: ignore
    Vector = None  # type: ignore


SCENE_BUILD_OUTPUT = "stage_10R_pcb_presentation/config/scene_build.json"
COLLECTION_ROOT = "TASK10R_PCB"
COLLECTIONS = ("HERO", "SECONDARY", "SUPPORT", "CONTEXT", "SOURCE_HIDDEN", "CAMERAS", "LIGHTS")

CONTEXT_COLORS = {
    "PART_001": (0.95, 0.18, 0.02, 1.0),
    "PART_002": (0.025, 0.03, 0.035, 1.0),
    "PART_003": (0.40, 0.47, 0.54, 1.0),
    "PART_004": (0.035, 0.04, 0.045, 1.0),
    "PART_005": (0.05, 0.055, 0.06, 1.0),
    "PART_017": (0.16, 0.18, 0.21, 1.0),
    "PART_018": (0.16, 0.18, 0.21, 1.0),
    "PART_020": (0.48, 0.52, 0.56, 1.0),
    "PART_021": (0.48, 0.52, 0.56, 1.0),
    "PART_022": (0.48, 0.52, 0.56, 1.0),
    "BATTERY": (0.12, 0.13, 0.15, 1.0),
}
BATTERY_IDS = {"PART_008", "PART_009", "PART_010", "PART_011", "PART_015", "PART_016"}


def build_presentation_scene(project_root: Path) -> dict[str, Any]:
    if bpy is None or Vector is None:
        raise RuntimeError("Blender bpy is required to build the PCB presentation scene")
    root = Path(project_root).expanduser().resolve()
    input_path = root / SOURCE_SCENE
    if hashlib.sha256(input_path.read_bytes()).hexdigest() != SOURCE_SCENE_SHA256:
        raise ValueError("Task 10-R-PCB-V1 source scene SHA256 changed")
    manifest = load_json(root / MANIFEST_PATH)
    cameras = load_json(root / CAMERAS_PATH)["cameras"]
    materials = load_json(root / MATERIALS_PATH)["materials"]
    texture_path = root / ASSET_TEXTURE
    if not texture_path.is_file():
        raise ValueError("surface texture missing; run generate_surface_texture.py first")

    output = root / SCENE_OUTPUT
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(input_path))
    objects = _source_objects()
    _validate_totals(objects)
    _remove_non_source_objects()
    collections = _create_collections()
    _place_source_parts(objects, manifest, materials, collections, texture_path)
    component_report = _create_components(manifest, materials, collections["HERO"], objects["PART_019"])
    _create_cameras(cameras, collections["CAMERAS"])
    _create_light_rig(manifest, collections["LIGHTS"])
    _configure_scene(manifest)

    bpy.ops.wm.save_as_mainfile(filepath=str(output))
    bpy.ops.wm.open_mainfile(filepath=str(output))
    reopened = _source_objects()
    _validate_totals(reopened)
    fingerprint_failures = [
        part_id
        for part_id, obj in reopened.items()
        if str(obj.get("task10r_pcb_source_geometry_fingerprint")) != mesh_geometry_fingerprint(obj.data)
    ]
    animation_count = sum(obj.animation_data is not None for obj in bpy.data.objects)
    font_count = sum(obj.type == "FONT" for obj in bpy.data.objects)
    comp_count = sum(
        obj.get("source") == "photographic_presentation_reconstruction"
        for obj in bpy.data.objects
        if obj.type == "MESH"
    )
    if fingerprint_failures or animation_count or font_count or comp_count != manifest["component_count"]:
        raise ValueError(
            "PCB presentation scene validation failed: "
            f"fingerprints={fingerprint_failures}, animation={animation_count}, "
            f"fonts={font_count}, components={comp_count}"
        )
    return {
        "path": str(output),
        "source_part_count": len(reopened),
        "source_faces": sum(len(obj.data.polygons) for obj in reopened.values()),
        "source_indexed_vertices": sum(len(obj.data.vertices) for obj in reopened.values()),
        "animation_data_count": animation_count,
        "font_object_count": font_count,
        "component_count": comp_count,
        "component_mount_check": component_report,
        "fingerprint_failures": fingerprint_failures,
        "camera_names": sorted(
            obj.name for obj in bpy.data.objects if obj.type == "CAMERA" and obj.name.startswith("CAM_PCB_")
        ),
    }


def _place_source_parts(
    objects: Mapping[str, Any],
    manifest: Mapping[str, Any],
    materials: Mapping[str, Any],
    collections: Mapping[str, Any],
    texture_path: Path,
) -> None:
    transforms = manifest["part_transforms"]
    for part_id in EXPECTED_PART_IDS:
        obj = objects[part_id]
        obj.animation_data_clear()
        _unlink(obj)
        obj["task10r_pcb_source_geometry_fingerprint"] = mesh_geometry_fingerprint(obj.data)
        obj["task10r_pcb_animation_enabled"] = False
        if part_id not in STORY_PART_IDS:
            obj.hide_viewport = True
            obj.hide_render = True
            obj["task10r_pcb_tier"] = "SOURCE_HIDDEN"
            collections["SOURCE_HIDDEN"].objects.link(obj)
            continue
        record = transforms[part_id]
        obj.data = obj.data.copy()
        obj.location = record["location"]
        obj.rotation_euler = record["rotation_euler"]
        obj.scale = record["scale"]
        obj.hide_viewport = False
        obj.hide_render = False
        tier = record["presentation_tier"]
        obj["task10r_pcb_tier"] = tier
        reclass = manifest["part_reclassification"].get(part_id)
        if reclass:
            obj["presentation_priority"] = reclass["presentation_priority"]
            obj["independent_focus"] = bool(reclass["independent_focus"])
            obj["follow_parent"] = str(reclass["follow_parent"])
            obj["presentation_weight"] = float(reclass["presentation_weight"])
        if part_id == "PART_019":
            _assign_soldermask(obj, materials["pcb_soldermask"], texture_path)
            collections["HERO"].objects.link(obj)
        elif tier == "SECONDARY":
            _assign_flat_material(obj, materials["secondary_plate"], name=f"T10RPCB_{part_id}_SECONDARY")
            collections["SECONDARY"].objects.link(obj)
        elif tier == "SUPPORT":
            _assign_flat_material(obj, materials["support_frame"], name=f"T10RPCB_{part_id}_SUPPORT")
            collections["SUPPORT"].objects.link(obj)
        else:
            base = CONTEXT_COLORS.get(part_id) or CONTEXT_COLORS["BATTERY"]
            if part_id not in CONTEXT_COLORS and part_id not in BATTERY_IDS:
                base = (0.3, 0.33, 0.36, 1.0)
            factor = float(materials["context"]["weight"])
            color = tuple(c * factor for c in base[:3]) + (base[3],)
            _assign_flat_material(
                obj,
                {"base_color": color, "roughness": 0.45, "metallic": 0.15},
                name=f"T10RPCB_{part_id}_CONTEXT",
            )
            collections["CONTEXT"].objects.link(obj)


def _create_components(
    manifest: Mapping[str, Any],
    materials: Mapping[str, Any],
    collection: Any,
    board_obj: Any,
) -> dict[str, Any]:
    report: dict[str, Any] = {}
    board_top_z = float(manifest["board_top_z_mm"])
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for component in manifest["components"]:
        hits = _verify_component_mount(component, board_obj, board_top_z, depsgraph)
        if not all(hits.values()):
            raise ValueError(
                f"component footprint misses PART_019: {component['component_id']} -> {hits}"
            )
        report[component["component_id"]] = hits
    for component in manifest["components"]:
        _build_component(component, materials[component["material_role"]], collection)
    return report


def _build_component(component: Mapping[str, Any], material: Mapping[str, Any], collection: Any) -> Any:
    cid = component["component_id"]
    location = [float(v) for v in component["world_location"]]
    if component["shape"] == "cylinder":
        bpy.ops.mesh.primitive_cylinder_add(
            vertices=28,
            radius=float(component["radius_mm"]),
            depth=float(component["height_mm"]),
            location=location,
        )
    else:
        w, d = (float(v) for v in component["size_xy_mm"])
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=location)
        bpy.context.object.scale = (w, d, float(component["height_mm"]))
        bpy.ops.object.transform_apply(scale=True)
    obj = bpy.context.object
    obj.name = cid
    bevel = obj.modifiers.new("presentation_edge_bevel", "BEVEL")
    bevel.width = float(component.get("bevel_mm", 0.5))
    bevel.segments = 2
    bpy.ops.object.modifier_apply(modifier=bevel.name)
    _unlink(obj)
    collection.objects.link(obj)
    _assign_flat_material(obj, material, name=f"T10RPCB_{cid}")
    obj["source"] = "photographic_presentation_reconstruction"
    obj["mounted_on"] = component["mounted_on"]
    obj["reference_source"] = component["reference_source"]
    obj["task10r_pcb_tier"] = "HERO"
    obj["task10r_pcb_animation_enabled"] = False
    return obj


def _verify_component_mount(
    component: Mapping[str, Any],
    board_obj: Any,
    board_top_z: float,
    depsgraph: Any,
) -> dict[str, bool]:
    cx, cy = (float(v) for v in component["center_xy_mm"])
    rect = component["footprint_board_local"]
    local_points = [
        (cx, cy),
        (rect["x_min"], rect["y_min"]),
        (rect["x_max"], rect["y_min"]),
        (rect["x_max"], rect["y_max"]),
        (rect["x_min"], rect["y_max"]),
    ]
    board_origin = board_obj.location
    hits: dict[str, bool] = {}
    for index, (lx, ly) in enumerate(local_points):
        origin = Vector((board_origin.x + lx, board_origin.y + ly, board_top_z + 4.0))
        result, _loc, _n, _i, hit_obj, _m = bpy.context.scene.ray_cast(
            depsgraph, origin, Vector((0.0, 0.0, -1.0))
        )
        hits[f"point_{index}"] = bool(result) and hit_obj == board_obj
    return hits


def _assign_soldermask(obj: Any, spec: Mapping[str, Any], texture_path: Path) -> None:
    material = bpy.data.materials.get("T10RPCB_SOLDERMASK") or bpy.data.materials.new("T10RPCB_SOLDERMASK")
    material.use_nodes = True
    material.diffuse_color = tuple(spec["base_color"])
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    texcoord = nodes.new("ShaderNodeTexCoord")
    image_node = nodes.new("ShaderNodeTexImage")
    image = bpy.data.images.load(str(texture_path))
    image_node.image = image
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.22
    bump.inputs["Distance"].default_value = 0.15
    links.new(texcoord.outputs["Generated"], image_node.inputs["Vector"])
    links.new(image_node.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(image_node.outputs["Color"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    bsdf.inputs["Roughness"].default_value = float(spec["roughness"])
    bsdf.inputs["Metallic"].default_value = float(spec["metallic"])
    obj.data.materials.clear()
    obj.data.materials.append(material)
    obj["task10r_pcb_material_role"] = "pcb_soldermask"


def _assign_flat_material(obj: Any, spec: Mapping[str, Any], name: str) -> None:
    material = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    color = tuple(float(c) for c in spec["base_color"])
    material.diffuse_color = color
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = float(spec.get("roughness", 0.45))
        if "Metallic" in bsdf.inputs:
            bsdf.inputs["Metallic"].default_value = float(spec.get("metallic", 0.0))
    obj.data.materials.clear()
    obj.data.materials.append(material)


def _create_cameras(cameras: Mapping[str, Any], collection: Any) -> None:
    for name, record in cameras.items():
        data = bpy.data.cameras.new(name)
        camera = bpy.data.objects.new(name, data)
        collection.objects.link(camera)
        camera.location = record["location"]
        camera.rotation_euler = (Vector(record["target"]) - camera.location).to_track_quat("-Z", "Y").to_euler()
        data.type = record["projection"]
        data.lens = float(record["lens_mm"])
        data.clip_start = float(record["clip_start_mm"])
        data.clip_end = float(record["clip_end_mm"])
        camera["task10r_pcb_camera_role"] = record["view_role"]


def _create_light_rig(manifest: Mapping[str, Any], collection: Any) -> None:
    zone = manifest["board_zone_center_mm"]
    anchor = [zone[0] - 175.0, zone[1], zone[2]]
    mid = [(zone[0] + anchor[0]) / 2.0, (zone[1] + anchor[1]) / 2.0, zone[2]]
    rig = [
        ("LIGHT_KEY", (mid[0] + 40.0, mid[1] - 160.0, mid[2] + 430.0), 65000.0, 380.0),
        ("LIGHT_FILL", (mid[0] - 60.0, mid[1] + 200.0, mid[2] + 300.0), 28000.0, 320.0),
        ("LIGHT_RIM", (mid[0] + 60.0, mid[1] + 40.0, mid[2] + 520.0), 36000.0, 260.0),
    ]
    for name, location, energy, size in rig:
        data = bpy.data.lights.new(name, type="AREA")
        data.energy = energy
        data.shape = "DISK"
        data.size = size
        obj = bpy.data.objects.new(name, data)
        collection.objects.link(obj)
        obj.location = location
        target = Vector((mid[0], mid[1], mid[2] - 20.0))
        obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()
        obj["task10r_pcb_role"] = "presentation_light"


def _configure_scene(manifest: Mapping[str, Any]) -> None:
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = 1
    scene.render.fps = 30
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.render.resolution_percentage = 100
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    world = scene.world or bpy.data.worlds.new("TASK10R_PCB_WORLD")
    scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    if background is not None:
        background.inputs["Color"].default_value = (0.11, 0.125, 0.16, 1.0)
        background.inputs["Strength"].default_value = 0.85
    scene.view_settings.exposure = 1.7
    scene["task10r_pcb_source_scene"] = SOURCE_SCENE
    scene["task10r_pcb_source_scene_sha256"] = SOURCE_SCENE_SHA256
    scene["task10r_pcb_animation_data_count"] = 0
    scene["task10r_pcb_text_policy"] = "NO_TEXT_OR_ANNOTATIONS"
    scene.camera = bpy.data.objects["CAM_PCB_CLEAN"]
    scene.frame_set(1)


def _source_objects() -> dict[str, Any]:
    objects = {
        str(obj.get("part_id")): obj
        for obj in bpy.data.objects
        if obj.type == "MESH" and obj.get("source") == "original_stl"
    }
    if set(objects) != set(EXPECTED_PART_IDS):
        raise ValueError("Task 10-R-PCB-V1 source scene does not contain all 82 source PARTs")
    return objects


def _validate_totals(objects: Mapping[str, Any]) -> None:
    totals = {
        "source_part_count": len(objects),
        "source_faces": sum(len(obj.data.polygons) for obj in objects.values()),
        "source_indexed_vertices": sum(len(obj.data.vertices) for obj in objects.values()),
    }
    if totals != {
        "source_part_count": BASELINE["source_part_count"],
        "source_faces": BASELINE["faces"],
        "source_indexed_vertices": BASELINE["indexed_vertices"],
    }:
        raise ValueError(f"Task 10-R-PCB-V1 frozen geometry totals changed: {totals}")


def _remove_non_source_objects() -> None:
    for obj in list(bpy.data.objects):
        if not (obj.type == "MESH" and obj.get("source") == "original_stl"):
            bpy.data.objects.remove(obj, do_unlink=True)


def _unlink(obj: Any) -> None:
    for collection in list(obj.users_collection):
        collection.objects.unlink(obj)


def _create_collections() -> dict[str, Any]:
    root = bpy.data.collections.get(COLLECTION_ROOT) or bpy.data.collections.new(COLLECTION_ROOT)
    if root.name not in {child.name for child in bpy.context.scene.collection.children}:
        bpy.context.scene.collection.children.link(root)
    result = {}
    for suffix in COLLECTIONS:
        name = f"{COLLECTION_ROOT}_{suffix}"
        collection = bpy.data.collections.get(name) or bpy.data.collections.new(name)
        if collection.name not in {child.name for child in root.children}:
            root.children.link(collection)
        result[suffix] = collection
    return result


def _script_arguments() -> list[str]:
    arguments = list(sys.argv[1:])
    return arguments[arguments.index("--") + 1 :] if "--" in arguments else arguments


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args(argv if argv is not None else _script_arguments())
    print(json.dumps(build_presentation_scene(args.project_root), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
