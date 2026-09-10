"""Add Task 10 product materials, focus emphasis, cameras, and annotations."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.task08_data import load_json, write_json
from stage_10_product_story.scripts.build_story_scene import (
    EXPECTED_PART_IDS,
    SCENE_OUTPUT,
    VISIBLE_PART_IDS,
    _validate_geometry,
)
from stage_10_product_story.scripts.story_data import (
    FUNCTIONAL_MODULES,
    build_annotation_config,
    build_camera_sequence,
    build_material_roles,
    build_story_config,
)

try:  # pragma: no cover - Blender-only implementation.
    import bpy  # type: ignore
    from mathutils import Vector  # type: ignore
except ImportError:  # pragma: no cover
    bpy = None  # type: ignore
    Vector = None  # type: ignore


CAMERA_CONFIG_OUTPUT = "stage_10_product_story/config/camera_sequence.json"
ANNOTATION_CONFIG_OUTPUT = "stage_10_product_story/config/annotation_config.json"
ANNOTATION_COLLECTION = "T10_ANNOTATIONS"
CAMERA_COLLECTION = "T10_CAMERAS"
WHITE = (0.93, 0.96, 1.0, 1.0)


def apply_story_presentation(project_root: Path) -> dict[str, Any]:
    if bpy is None or Vector is None:
        raise RuntimeError("Blender bpy is required for Task 10 presentation setup")
    root = Path(project_root).expanduser().resolve()
    scene_path = root / SCENE_OUTPUT
    bpy.ops.wm.open_mainfile(filepath=str(scene_path))
    objects = _source_objects()
    _validate_geometry(objects)
    _remove_presentation_objects()
    _apply_materials(objects)

    camera_config = _build_camera_config(root)
    write_json(root / CAMERA_CONFIG_OUTPUT, camera_config)
    _create_cameras(camera_config)

    annotation_config = build_annotation_config()
    write_json(root / ANNOTATION_CONFIG_OUTPUT, annotation_config)
    _create_annotations(annotation_config, camera_config)
    _configure_scene()
    bpy.context.scene.camera = bpy.data.objects["CAM_STORY_HERO"]
    bpy.context.scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=str(scene_path))
    return {
        "output": str(scene_path),
        "source_part_count": len(objects),
        "source_faces": sum(len(obj.data.polygons) for obj in objects.values()),
        "source_indexed_vertices": sum(len(obj.data.vertices) for obj in objects.values()),
        "camera_names": list(camera_config["camera_names"]),
        "annotation_count": len(annotation_config["items"]),
    }


def _source_objects() -> dict[str, Any]:
    objects = {
        str(obj.get("part_id")): obj
        for obj in bpy.data.objects
        if obj.type == "MESH" and obj.get("source") == "original_stl"
    }
    if set(objects) != set(EXPECTED_PART_IDS):
        raise ValueError("Task 10 source coverage changed during presentation setup")
    return objects


def _apply_materials(objects: Mapping[str, Any]) -> None:
    roles = build_material_roles()
    part_role: dict[str, str] = {
        "PART_001": "LOWER_HOUSING",
        "PART_002": "UPPER_HOUSING",
        "PART_004": "UPPER_HOUSING_TOP_COVER",
        "PART_005": "COMMUNICATION",
        "PART_006": "SUPPORT",
        "PART_007": "SUPPORT",
        "PART_019": "MAIN_PCB",
        "PART_003": "SENSOR",
        "PART_012": "SENSOR",
        "PART_013": "SENSOR",
        "PART_014": "SENSOR",
        "PART_017": "COMMUNICATION",
        "PART_018": "COMMUNICATION",
        "PART_008": "BATTERY",
        "PART_009": "BATTERY",
        "PART_010": "BATTERY",
        "PART_011": "BATTERY",
        "PART_015": "BATTERY",
        "PART_016": "BATTERY",
        "PART_020": "SUPPORT",
        "PART_021": "SUPPORT",
        "PART_022": "SUPPORT",
    }
    module_for_part = {
        part_id: module_id
        for module_id, part_ids in FUNCTIONAL_MODULES.items()
        for part_id in part_ids
    }
    story = build_story_config()
    for part_id in VISIBLE_PART_IDS:
        obj = objects[part_id]
        role = part_role[part_id]
        descriptor = roles[role]
        material = bpy.data.materials.get(f"T10_{part_id}_{role}")
        if material is None:
            material = bpy.data.materials.new(f"T10_{part_id}_{role}")
        material.diffuse_color = tuple(descriptor["base_color"])
        material.use_nodes = True
        bsdf = material.node_tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            bsdf.inputs["Base Color"].default_value = tuple(descriptor["base_color"])
            bsdf.inputs["Roughness"].default_value = float(descriptor.get("roughness", 0.4))
            if "Metallic" in bsdf.inputs:
                bsdf.inputs["Metallic"].default_value = float(descriptor.get("metallic", 0.0))
        obj.data.materials.clear()
        obj.data.materials.append(material)
        _key_focus_colors(material, descriptor, module_for_part[part_id], story)
        obj["task10_material_role"] = role
        obj["task10_focus_material_keyed"] = True


def _key_focus_colors(material: Any, descriptor: Mapping[str, Any], module_id: str, story: Mapping[str, Any]) -> None:
    base = tuple(float(value) for value in descriptor["base_color"])
    for shot in story["shots"]:
        focus = shot.get("focus_module")
        if focus is None:
            factor = 1.0
        elif focus == module_id:
            factor = 1.0
        elif module_id in FUNCTIONAL_MODULES and focus in FUNCTIONAL_MODULES:
            factor = 0.48
        else:
            factor = 0.32
        color = tuple(min(1.0, max(0.0, channel * factor)) for channel in base[:3]) + (base[3],)
        for frame in (int(shot["frame_start"]), int(shot["frame_end"])):
            material.diffuse_color = color
            material.keyframe_insert(data_path="diffuse_color", frame=frame)
            if material.use_nodes:
                bsdf = material.node_tree.nodes.get("Principled BSDF")
                if bsdf is not None:
                    bsdf.inputs["Base Color"].default_value = color
    material.diffuse_color = base


def _build_camera_config(root: Path) -> dict[str, Any]:
    state_data = load_json(root / "stage_10_product_story/config/state_transforms.json")
    layout = load_json(root / "stage_09C_refined_explosion/config/refined_layout.json")
    bounds = _state_bounds(state_data, layout)
    low, high = bounds["min"], bounds["max"]
    target = [(low[index] + high[index]) / 2.0 for index in range(3)]
    dimensions = bounds["dimensions"]
    diagonal = math.sqrt(sum(value * value for value in dimensions))
    hero = _camera_record("CAM_STORY_HERO", target, (0.72, -1.0, 0.58), max(diagonal * 2.30, 1050.0), 68.0)
    sensor_target = _module_target(state_data, "SENSOR_FOCUS", ("PART_003", "PART_012", "PART_013", "PART_014"))
    pcb_target = _module_target(state_data, "PCB_FOCUS", ("PART_006", "PART_007", "PART_019"))
    sensor = _camera_record("CAM_STORY_SENSOR", sensor_target, (0.68, -1.0, 0.5), max(diagonal * 1.70, 700.0), 70.0)
    pcb = _camera_record("CAM_STORY_PCB", pcb_target, (0.72, -1.0, 0.48), max(diagonal * 1.70, 700.0), 70.0)
    config = build_camera_sequence()
    return {
        **config,
        "camera_names": ["CAM_STORY_HERO", "CAM_STORY_SENSOR", "CAM_STORY_PCB"],
        "bounds": bounds,
        "cameras": {record["name"]: record for record in (hero, sensor, pcb)},
    }


def _state_bounds(state_data: Mapping[str, Any], layout: Mapping[str, Any]) -> dict[str, Any]:
    low = [float("inf")] * 3
    high = [float("-inf")] * 3
    for state in state_data["states"].values():
        for part_id, record in state["parts"].items():
            dims = layout["parts"][part_id]["bbox_dimensions_mm"]
            for axis in range(3):
                half = float(dims[axis]) / 2.0
                low[axis] = min(low[axis], float(record["location"][axis]) - half)
                high[axis] = max(high[axis], float(record["location"][axis]) + half)
    return {"min": low, "max": high, "dimensions": [high[i] - low[i] for i in range(3)]}


def _module_target(state_data: Mapping[str, Any], state_id: str, part_ids: Sequence[str]) -> list[float]:
    records = state_data["states"][state_id]["parts"]
    return [sum(float(records[part_id]["location"][axis]) for part_id in part_ids) / len(part_ids) for axis in range(3)]


def _camera_record(name: str, target: Sequence[float], direction: Sequence[float], distance: float, lens: float) -> dict[str, Any]:
    unit = _normalise(direction)
    location = [float(target[index]) + unit[index] * distance for index in range(3)]
    return {
        "name": name,
        "type": "PERSP",
        "target": [float(value) for value in target],
        "location": location,
        "direction": unit,
        "lens_mm": float(lens),
        "clip_start_mm": 0.1,
        "clip_end_mm": max(distance * 4.0, 10000.0),
    }


def _normalise(value: Sequence[float]) -> list[float]:
    length = math.sqrt(sum(float(item) ** 2 for item in value))
    if length <= 0.0:
        raise ValueError("camera direction cannot be zero")
    return [float(item) / length for item in value]


def _create_cameras(config: Mapping[str, Any]) -> None:
    collection = _ensure_collection(CAMERA_COLLECTION)
    for name in config["camera_names"]:
        old = bpy.data.objects.get(name)
        if old is not None:
            bpy.data.objects.remove(old, do_unlink=True)
        record = config["cameras"][name]
        data = bpy.data.cameras.new(name)
        camera = bpy.data.objects.new(name, data)
        collection.objects.link(camera)
        camera.location = record["location"]
        camera.rotation_euler = (Vector(record["target"]) - camera.location).to_track_quat("-Z", "Y").to_euler()
        data.type = "PERSP"
        data.lens = float(record["lens_mm"])
        data.clip_start = float(record["clip_start_mm"])
        data.clip_end = float(record["clip_end_mm"])
        camera["task10_camera_role"] = name.removeprefix("CAM_STORY_").lower()
    # Blender 5.2 exposes Scene.camera as a non-animatable pointer.  Timeline
    # marker camera bindings are the native, saved mechanism for deterministic
    # camera cuts and survive reopening the .blend.
    scene = bpy.context.scene
    for marker in list(scene.timeline_markers):
        if marker.name.startswith("T10_CAMERA_"):
            scene.timeline_markers.remove(marker)
    camera_segments = config["camera_segments"]
    for index, segment in enumerate(camera_segments):
        marker = scene.timeline_markers.new(
            f"T10_CAMERA_{index:02d}_{segment['camera_id']}",
            frame=int(segment["frame_start"]),
        )
        marker.camera = bpy.data.objects[segment["camera_id"]]


def _create_annotations(config: Mapping[str, Any], camera_config: Mapping[str, Any]) -> None:
    collection = _ensure_collection(ANNOTATION_COLLECTION)
    camera_for_shot = {record["shot_id"]: record["camera_id"] for record in build_story_config()["shots"]}
    metric_counts: dict[str, int] = {}
    for index, item in enumerate(config["items"]):
        text_data = bpy.data.curves.new(f"T10_TEXT_{item['id']}", type="FONT")
        text_data.body = str(item["text"])
        text_data.align_x = "LEFT"
        is_metric = "metric" in item["id"]
        text_data.size = 8.0 if not is_metric else 5.5
        text_data.extrude = 0.08
        text_data.bevel_depth = 0.02
        text_data.materials.append(_text_material())
        text = bpy.data.objects.new(f"T10_ANNOTATION_{index:02d}_{item['id']}", text_data)
        collection.objects.link(text)
        camera_name = camera_for_shot[item["shot_id"]]
        cam = bpy.data.objects[camera_name]
        cam_record = camera_config["cameras"][camera_name]
        target = Vector(cam_record["target"])
        right = cam.matrix_world.to_quaternion() @ Vector((1.0, 0.0, 0.0))
        up = cam.matrix_world.to_quaternion() @ Vector((0.0, 1.0, 0.0))
        toward_camera = (Vector(cam.location) - target).normalized()
        metric_index = metric_counts.get(item["shot_id"], 0) if is_metric else 0
        if is_metric:
            metric_counts[item["shot_id"]] = metric_index + 1
        line = (56.0 + metric_index * 12.0) if is_metric else 0.0
        text.location = target + right * -112.0 + up * (68.0 - line) + toward_camera * 40.0
        text.rotation_euler = (Vector(cam.location) - text.location).to_track_quat("Z", "Y").to_euler()
        text["task10_annotation_shot"] = item["shot_id"]
        text["task10_render_text"] = item["text"]
        _key_annotation_visibility(text, item["shot_id"])


def _key_annotation_visibility(obj: Any, shot_id: str) -> None:
    shot = next(item for item in build_story_config()["shots"] if item["shot_id"] == shot_id)
    start, end = int(shot["frame_start"]), int(shot["frame_end"])
    for frame, hidden in ((1, True), (start - 1, True), (start, False), (end, False), (end + 1, True), (900, True)):
        obj.hide_render = hidden
        obj.hide_viewport = hidden
        obj.keyframe_insert(data_path="hide_render", frame=frame)
        obj.keyframe_insert(data_path="hide_viewport", frame=frame)


def _text_material() -> Any:
    material = bpy.data.materials.get("T10_ANNOTATION_WHITE")
    if material is None:
        material = bpy.data.materials.new("T10_ANNOTATION_WHITE")
    material.diffuse_color = WHITE
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = WHITE
        bsdf.inputs["Emission Color"].default_value = WHITE
        bsdf.inputs["Emission Strength"].default_value = 0.3
    return material


def _configure_scene() -> None:
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = 900
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
    scene.display.shading.cavity_type = "WORLD"
    scene.display.shading.show_specular_highlight = True
    scene.display.shading.background_type = "WORLD"
    scene.world.color = (0.055, 0.065, 0.08)


def _ensure_collection(name: str) -> Any:
    collection = bpy.data.collections.get(name)
    if collection is None:
        collection = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(collection)
    return collection


def _remove_presentation_objects() -> None:
    for obj in list(bpy.data.objects):
        if obj.type in {"CAMERA", "LIGHT"} or obj.name.startswith("T10_ANNOTATION_"):
            bpy.data.objects.remove(obj, do_unlink=True)


def _script_arguments() -> list[str]:
    arguments = list(sys.argv[1:])
    return arguments[arguments.index("--") + 1 :] if "--" in arguments else arguments


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args(argv if argv is not None else _script_arguments())
    print(json.dumps(apply_story_presentation(args.project_root), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
