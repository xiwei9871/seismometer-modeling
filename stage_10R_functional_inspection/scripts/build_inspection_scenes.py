"""Build the four subtitle-free Task 10-R inspection scenes in Blender."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.task08_data import load_json, write_json
from stage_10R_functional_inspection.scripts.build_inspection_plan import PLAN_OUTPUT, CAMERA_OUTPUT
from stage_10R_functional_inspection.scripts.inspection_data import (
    BASELINE,
    EXPECTED_PART_IDS,
    HIDDEN_PART_IDS,
    INSPECTION_STATE_IDS,
    SOURCE_SCENE,
    SOURCE_SCENE_SHA256,
    STORY_PART_IDS,
    build_module_groups,
)
from stage_10_product_story.scripts.build_story_scene import mesh_geometry_fingerprint

try:  # pragma: no cover - executed through Blender.
    import bpy  # type: ignore
    from mathutils import Vector  # type: ignore
except ImportError:  # pragma: no cover
    bpy = None  # type: ignore
    Vector = None  # type: ignore


SCENE_OUTPUTS = {
    "STATE_01_PRIMARY_ARCHITECTURE": "stage_10R_functional_inspection/scene/primary_architecture.blend",
    "STATE_02_SENSOR_INSPECTION": "stage_10R_functional_inspection/scene/sensor_inspection.blend",
    "STATE_03_PCB_INSPECTION": "stage_10R_functional_inspection/scene/pcb_inspection.blend",
    "STATE_04_POWER_INSPECTION": "stage_10R_functional_inspection/scene/power_inspection.blend",
}
SCENE_BUILD_OUTPUT = "stage_10R_functional_inspection/config/scene_build.json"

PART_ROLES = {
    "PART_001": "LOWER_HOUSING",
    "PART_002": "UPPER_HOUSING",
    "PART_003": "SENSOR",
    "PART_004": "UPPER_COVER",
    "PART_005": "HANDLE",
    "PART_006": "SUPPORT",
    "PART_007": "SUPPORT",
    "PART_008": "BATTERY",
    "PART_009": "BATTERY",
    "PART_010": "BATTERY",
    "PART_011": "BATTERY",
    "PART_012": "SENSOR",
    "PART_013": "SENSOR",
    "PART_014": "SENSOR",
    "PART_015": "BATTERY",
    "PART_016": "BATTERY",
    "PART_017": "COMMUNICATION",
    "PART_018": "COMMUNICATION",
    "PART_019": "PCB",
    "PART_020": "SUPPORT",
    "PART_021": "SUPPORT",
    "PART_022": "SUPPORT",
}
BASE_COLORS = {
    "LOWER_HOUSING": (0.95, 0.18, 0.02, 1.0),
    "UPPER_HOUSING": (0.025, 0.03, 0.035, 1.0),
    "UPPER_COVER": (0.035, 0.04, 0.045, 1.0),
    "HANDLE": (0.05, 0.055, 0.06, 1.0),
    "PCB": (0.02, 0.48, 0.12, 1.0),
    "SENSOR": (0.40, 0.47, 0.54, 1.0),
    "BATTERY": (0.12, 0.13, 0.15, 1.0),
    "SUPPORT": (0.48, 0.52, 0.56, 1.0),
    "COMMUNICATION": (0.16, 0.18, 0.21, 1.0),
}


def build_inspection_scenes(project_root: Path) -> dict[str, Any]:
    if bpy is None or Vector is None:
        raise RuntimeError("Blender bpy is required to build Task 10-R scenes")
    root = Path(project_root).expanduser().resolve()
    input_path = root / SOURCE_SCENE
    if hashlib.sha256(input_path.read_bytes()).hexdigest() != SOURCE_SCENE_SHA256:
        raise ValueError("Task 10-R source scene SHA256 changed")
    plan = load_json(root / PLAN_OUTPUT)
    cameras = load_json(root / CAMERA_OUTPUT)["cameras"]
    outputs: dict[str, Any] = {}
    for state_id in INSPECTION_STATE_IDS:
        output = root / SCENE_OUTPUTS[state_id]
        output.parent.mkdir(parents=True, exist_ok=True)
        outputs[state_id] = _build_one_scene(root, input_path, output, plan["states"][state_id], cameras)
    result = {
        "source_baseline": dict(BASELINE),
        "source_scene": SOURCE_SCENE,
        "source_scene_sha256": SOURCE_SCENE_SHA256,
        "scenes": outputs,
        "animation_data_policy": "NO_KEYFRAMES_OR_ANIMATION_DATA",
        "text_policy": "NO_TEXT_OR_ANNOTATIONS",
    }
    write_json(root / SCENE_BUILD_OUTPUT, result)
    return result


def _build_one_scene(root: Path, input_path: Path, output: Path, state: Mapping[str, Any], cameras: Mapping[str, Any]) -> dict[str, Any]:
    bpy.ops.wm.open_mainfile(filepath=str(input_path))
    objects = _source_objects()
    _validate_totals(objects)
    _remove_non_source_objects()
    collections = _create_collections(state["state_id"])
    module_members = build_module_groups()
    focused_ids = _focused_part_ids(state["state_id"])
    module_for_part = {part_id: module_id for module_id, module in module_members.items() for part_id in module["part_ids"]}
    part_records = state["parts"]
    for part_id in EXPECTED_PART_IDS:
        obj = objects[part_id]
        fingerprint = mesh_geometry_fingerprint(obj.data)
        obj.animation_data_clear()
        _unlink(obj)
        obj["task10r_state_id"] = state["state_id"]
        obj["task10r_source_geometry_fingerprint"] = fingerprint
        obj["task10r_animation_enabled"] = False
        obj["task10r_text_enabled"] = False
        if part_id in STORY_PART_IDS:
            obj.data = obj.data.copy()
            record = part_records[part_id]
            obj.location = record["location"]
            obj.rotation_euler = record["rotation_euler"]
            obj.scale = record["scale"]
            obj.hide_viewport = False
            obj.hide_render = False
            is_focus = part_id in focused_ids
            _assign_material(obj, part_id, state["state_id"], is_focus)
            obj["task10r_presentation_role"] = "FOCUS" if is_focus else "CONTEXT"
            collections["FOCUS" if is_focus else "CONTEXT"].objects.link(obj)
        else:
            obj.hide_viewport = True
            obj.hide_render = True
            obj["task10r_presentation_role"] = "SOURCE_HIDDEN"
            collections["SOURCE_HIDDEN"].objects.link(obj)

    _create_state_cameras(state, cameras, collections["CAMERAS"])
    _configure_scene(state)
    default_camera = _default_camera_name(state)
    bpy.context.scene.camera = bpy.data.objects[default_camera]
    bpy.context.scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=str(output))
    bpy.ops.wm.open_mainfile(filepath=str(output))
    reopened = _source_objects()
    _validate_totals(reopened)
    fingerprint_failures = [
        part_id for part_id, obj in reopened.items()
        if str(obj.get("task10r_source_geometry_fingerprint")) != mesh_geometry_fingerprint(obj.data)
    ]
    animation_count = sum(obj.animation_data is not None for obj in reopened.values())
    font_count = sum(obj.type == "FONT" for obj in bpy.data.objects)
    if fingerprint_failures or animation_count or font_count:
        raise ValueError(f"Task 10-R scene validation failed: fingerprints={fingerprint_failures}, animation={animation_count}, fonts={font_count}")
    return {
        "path": str(output),
        "state_id": state["state_id"],
        "source_part_count": len(reopened),
        "source_faces": sum(len(obj.data.polygons) for obj in reopened.values()),
        "source_indexed_vertices": sum(len(obj.data.vertices) for obj in reopened.values()),
        "animation_data_count": animation_count,
        "font_object_count": font_count,
        "fingerprint_failures": fingerprint_failures,
        "focus_part_ids": sorted(focused_ids, key=_part_number),
        "camera_names": sorted(obj.name for obj in bpy.data.objects if obj.type == "CAMERA" and obj.name.startswith("CAM_INSPECTION_")),
    }


def _focused_part_ids(state_id: str) -> set[str]:
    if state_id == "STATE_02_SENSOR_INSPECTION":
        return {"PART_003", "PART_012", "PART_013", "PART_014"}
    if state_id == "STATE_03_PCB_INSPECTION":
        return {"PART_006", "PART_007", "PART_019"}
    if state_id == "STATE_04_POWER_INSPECTION":
        return {"PART_008", "PART_009", "PART_010", "PART_011", "PART_015", "PART_016"}
    return set(STORY_PART_IDS)


def _assign_material(obj: Any, part_id: str, state_id: str, is_focus: bool) -> None:
    role = PART_ROLES[part_id]
    factor = 1.0 if is_focus else 0.30
    base = BASE_COLORS[role]
    color = tuple(min(1.0, max(0.0, channel * factor)) for channel in base[:3]) + (base[3],)
    name = f"T10R_{state_id}_{part_id}_{role}_{'FOCUS' if is_focus else 'CONTEXT'}"
    material = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    material.diffuse_color = color
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = 0.38 if role not in {"SENSOR", "SUPPORT"} else 0.28
        if "Metallic" in bsdf.inputs:
            bsdf.inputs["Metallic"].default_value = 0.65 if role in {"SENSOR", "SUPPORT"} else 0.0
    obj.data.materials.clear()
    obj.data.materials.append(material)
    obj["task10r_material_role"] = role
    obj["task10r_focus_weight"] = 1.0 if is_focus else 0.30


def _create_state_cameras(state: Mapping[str, Any], cameras: Mapping[str, Any], collection: Any) -> None:
    for name, record in cameras.items():
        if record["state_id"] != state["state_id"]:
            continue
        data = bpy.data.cameras.new(name)
        camera = bpy.data.objects.new(name, data)
        collection.objects.link(camera)
        camera.location = record["location"]
        camera.rotation_euler = (Vector(record["target"]) - camera.location).to_track_quat("-Z", "Y").to_euler()
        data.type = record["projection"]
        data.lens = float(record["lens_mm"])
        data.clip_start = float(record["clip_start_mm"])
        data.clip_end = float(record["clip_end_mm"])
        camera["task10r_camera_role"] = record["view_role"]
        camera["task10r_state_id"] = state["state_id"]


def _configure_scene(state: Mapping[str, Any]) -> None:
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = 1
    scene.render.fps = 30
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.render.resolution_percentage = 100
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.film_transparent = False
    scene.render.image_settings.color_mode = "RGBA"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.studio_light = "paint.sl"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_shadows = True
    scene.display.shading.show_cavity = True
    scene.display.shading.show_specular_highlight = True
    scene.display.shading.background_type = "WORLD"
    scene.world.color = (0.055, 0.065, 0.08)
    scene["task10r_state_id"] = state["state_id"]
    scene["task10r_source_scene"] = SOURCE_SCENE
    scene["task10r_source_scene_sha256"] = SOURCE_SCENE_SHA256
    scene["task10r_animation_data_count"] = 0
    scene["task10r_text_policy"] = "NO_TEXT_OR_ANNOTATIONS"


def _create_collections(state_id: str) -> dict[str, Any]:
    root_name = f"TASK10R_{state_id}"
    root = bpy.data.collections.get(root_name) or bpy.data.collections.new(root_name)
    if root.name not in {child.name for child in bpy.context.scene.collection.children}:
        bpy.context.scene.collection.children.link(root)
    result = {}
    for suffix in ("FOCUS", "CONTEXT", "SOURCE_HIDDEN", "CAMERAS"):
        name = f"{root_name}_{suffix}"
        collection = bpy.data.collections.get(name) or bpy.data.collections.new(name)
        if collection.name not in {child.name for child in root.children}:
            root.children.link(collection)
        result[suffix] = collection
    return result


def _source_objects() -> dict[str, Any]:
    objects = {
        str(obj.get("part_id")): obj
        for obj in bpy.data.objects
        if obj.type == "MESH" and obj.get("source") == "original_stl"
    }
    if set(objects) != set(EXPECTED_PART_IDS):
        raise ValueError("Task 10-R source scene does not contain all 82 source PARTs")
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
        raise ValueError(f"Task 10-R frozen geometry totals changed: {totals}")


def _remove_non_source_objects() -> None:
    for obj in list(bpy.data.objects):
        if not (obj.type == "MESH" and obj.get("source") == "original_stl"):
            bpy.data.objects.remove(obj, do_unlink=True)


def _unlink(obj: Any) -> None:
    for collection in list(obj.users_collection):
        collection.objects.unlink(obj)


def _default_camera_name(state: Mapping[str, Any]) -> str:
    return str(state["camera_id"])


def _part_number(part_id: str) -> int:
    return int(part_id.split("_")[-1])


def _script_arguments() -> list[str]:
    arguments = list(sys.argv[1:])
    return arguments[arguments.index("--") + 1 :] if "--" in arguments else arguments


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args(argv if argv is not None else _script_arguments())
    print(json.dumps(build_inspection_scenes(args.project_root), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
