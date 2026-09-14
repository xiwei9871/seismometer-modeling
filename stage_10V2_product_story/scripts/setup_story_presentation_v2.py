"""Add Task 10-V2 Eevee materials, lighting, cameras, and annotations."""

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
from stage_10_product_story.scripts.build_story_scene import EXPECTED_PART_IDS, VISIBLE_PART_IDS
from stage_10_product_story.scripts.story_data import (
    FUNCTIONAL_MODULES,
    build_annotation_config,
    build_camera_sequence,
    build_material_roles,
    build_story_config,
)
from stage_10_product_story.scripts.setup_story_presentation import annotation_screen_layout
from stage_10V2_product_story.scripts.camera_plan import (
    build_camera_records,
    drifted_pose,
)
from stage_10V2_product_story.scripts.motion_timing import (
    MOTION_TIMING,
    hide_schedule,
)
from stage_10V2_product_story.scripts.story_v2_data import (
    ANNOTATION_SCALE,
    ASSET_TEXTURE,
    EXPOSURE,
    LIGHTING_OUTPUT,
    PART_EMPHASIS_CAP,
    RENDER_ENGINE,
    SCENE_OUTPUT,
    STATE_OUTPUT,
    WORLD_COLOR,
    WORLD_GRADIENT_BOTTOM,
    WORLD_GRADIENT_TOP,
    WORLD_STRENGTH,
    build_component_material_roles,
    build_lighting_config,
    build_story_v2_state_transforms,
)

try:  # pragma: no cover - Blender-only implementation.
    import bpy  # type: ignore
    from mathutils import Vector  # type: ignore
except ImportError:  # pragma: no cover
    bpy = None  # type: ignore
    Vector = None  # type: ignore


CAMERA_CONFIG_OUTPUT = "stage_10V2_product_story/config/camera_sequence.json"
ANNOTATION_CONFIG_OUTPUT = "stage_10V2_product_story/config/annotation_config.json"
ANNOTATION_COLLECTION = "STORY_ANNOTATIONS"
CAMERA_COLLECTION = "STORY_CAMERAS"
LIGHT_COLLECTION = "STORY_LIGHTS"
COLLECTION_ROOT = "STORY_10V2"
WHITE = (0.93, 0.96, 1.0, 1.0)


def apply_story_presentation_v2(project_root: Path) -> dict[str, Any]:
    if bpy is None or Vector is None:
        raise RuntimeError("Blender bpy is required for Task 10-V2 presentation setup")
    root = Path(project_root).expanduser().resolve()
    scene_path = root / SCENE_OUTPUT
    bpy.ops.wm.open_mainfile(filepath=str(scene_path))
    objects = _source_objects()
    _validate_geometry(objects)
    components = _component_objects()
    _remove_presentation_objects()

    state_data = load_json(root / STATE_OUTPUT)
    _apply_materials(objects)
    _apply_presentation_materials(objects, components, state_data, root)

    _key_context_visibility(objects, components)

    camera_config = _build_camera_config(root, state_data)
    write_json(root / CAMERA_CONFIG_OUTPUT, camera_config)
    _create_cameras(camera_config)

    annotation_config = build_annotation_config()
    write_json(root / ANNOTATION_CONFIG_OUTPUT, annotation_config)
    _create_annotations(annotation_config, camera_config)

    lighting = build_lighting_config(root, state_data=state_data)
    write_json(root / LIGHTING_OUTPUT, lighting)
    _create_light_rig(lighting)
    _configure_scene(lighting)

    bpy.context.scene.camera = bpy.data.objects["CAM_STORY_HERO"]
    bpy.context.scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=str(scene_path))
    return {
        "output": str(scene_path),
        "source_part_count": len(objects),
        "source_faces": sum(len(obj.data.polygons) for obj in objects.values()),
        "source_indexed_vertices": sum(len(obj.data.vertices) for obj in objects.values()),
        "presentation_component_count": len(components),
        "camera_names": list(camera_config["camera_names"]),
        "annotation_count": len(annotation_config["items"]),
        "light_count": len(lighting["lights"]),
        "engine": RENDER_ENGINE,
        "exposure": EXPOSURE,
    }


def _source_objects() -> dict[str, Any]:
    objects = {
        str(obj.get("part_id")): obj
        for obj in bpy.data.objects
        if obj.type == "MESH" and obj.get("source") == "original_stl"
    }
    if set(objects) != set(EXPECTED_PART_IDS):
        raise ValueError("Task 10-V2 source coverage changed during presentation setup")
    return objects


def _component_objects() -> dict[str, Any]:
    objects = {
        obj.name: obj
        for obj in bpy.data.objects
        if obj.type == "MESH" and obj.get("task10v2_presentation_component") is True
    }
    if len(objects) != 15:
        raise ValueError("Task 10-V2 presentation components are missing")
    return objects


def _apply_materials(objects: Mapping[str, Any]) -> None:
    roles = build_material_roles()
    # The v1 near-black sensor material reads as a dark blob under Eevee;
    # V2 lifts it so the focus subject stays legible against the internals.
    roles["SENSOR"] = {
        **roles["SENSOR"],
        "base_color": (0.20, 0.235, 0.27, 1.0),
        "metallic": 0.6,
        "roughness": 0.3,
    }
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
        if part_id == "PART_019":
            continue  # textured soldermask material handled separately
        obj = objects[part_id]
        role = part_role[part_id]
        descriptor = roles[role]
        material = bpy.data.materials.get(f"T10V2_{part_id}_{role}")
        if material is None:
            material = bpy.data.materials.new(f"T10V2_{part_id}_{role}")
        material.use_nodes = True
        material.diffuse_color = tuple(descriptor["base_color"])
        bsdf = material.node_tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            bsdf.inputs["Base Color"].default_value = tuple(descriptor["base_color"])
            bsdf.inputs["Roughness"].default_value = float(descriptor.get("roughness", 0.4))
            if "Metallic" in bsdf.inputs:
                bsdf.inputs["Metallic"].default_value = float(descriptor.get("metallic", 0.0))
        obj.data.materials.clear()
        obj.data.materials.append(material)
        cap = PART_EMPHASIS_CAP.get(part_id)
        _key_focus_colors(material, descriptor, module_for_part[part_id], story, cap=cap)
        obj["task10v2_material_role"] = role
        obj["task10v2_focus_material_keyed"] = True


def _apply_presentation_materials(
    objects: Mapping[str, Any],
    components: Mapping[str, Any],
    state_data: Mapping[str, Any],
    root: Path,
) -> None:
    story = build_story_config()
    _assign_soldermask(objects["PART_019"], story, root / ASSET_TEXTURE)
    component_roles = build_component_material_roles()
    for component_id, obj in components.items():
        role = str(obj.get("task10v2_material_role"))
        descriptor = component_roles[role]
        material = bpy.data.materials.get(f"T10V2_{component_id}_{role}")
        if material is None:
            material = bpy.data.materials.new(f"T10V2_{component_id}_{role}")
        material.use_nodes = True
        material.diffuse_color = tuple(descriptor["base_color"])
        bsdf = material.node_tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            bsdf.inputs["Base Color"].default_value = tuple(descriptor["base_color"])
            bsdf.inputs["Roughness"].default_value = float(descriptor.get("roughness", 0.45))
            if "Metallic" in bsdf.inputs:
                bsdf.inputs["Metallic"].default_value = float(descriptor.get("metallic", 0.0))
        obj.data.materials.clear()
        obj.data.materials.append(material)
        _key_focus_colors(
            material, descriptor, "HIGH_PRECISION_ACQUISITION_CORE", story, cap=None
        )
        obj["task10v2_focus_material_keyed"] = True


def _focus_factors(module_id: str, story: Mapping[str, Any], cap: float | None) -> list[tuple[int, float]]:
    factors: list[tuple[int, float]] = []
    for shot in story["shots"]:
        focus = shot.get("focus_module")
        if focus is None or focus == module_id:
            factor = 1.0
        elif module_id in FUNCTIONAL_MODULES and focus in FUNCTIONAL_MODULES:
            factor = 0.40
        else:
            factor = 0.28
        if cap is not None:
            factor = min(factor, cap)
        factors.extend(
            (frame, factor)
            for frame in (int(shot["frame_start"]), int(shot["frame_end"]))
        )
    return factors


def _key_focus_colors(
    material: Any,
    descriptor: Mapping[str, Any],
    module_id: str,
    story: Mapping[str, Any],
    cap: float | None,
) -> None:
    """Keyframe both the Workbench diffuse color and the Eevee BSDF color."""
    base = tuple(float(value) for value in descriptor["base_color"])
    bsdf = material.node_tree.nodes.get("Principled BSDF") if material.use_nodes else None
    for frame, factor in _focus_factors(module_id, story, cap):
        color = tuple(min(1.0, max(0.0, channel * factor)) for channel in base[:3]) + (base[3],)
        material.diffuse_color = color
        material.keyframe_insert(data_path="diffuse_color", frame=frame)
        if bsdf is not None:
            socket = bsdf.inputs["Base Color"]
            socket.default_value = color
            socket.keyframe_insert(data_path="default_value", frame=frame)
    material.diffuse_color = base
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = base


def _assign_soldermask(obj: Any, story: Mapping[str, Any], texture_path: Path) -> None:
    """Textured soldermask whose brightness follows the same focus policy."""
    if not texture_path.is_file():
        raise ValueError("Task 10-V2 surface texture is missing; copy the 10R asset first")
    material = bpy.data.materials.get("T10V2_SOLDERMASK") or bpy.data.materials.new("T10V2_SOLDERMASK")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    for node in list(nodes):
        nodes.remove(node)
    output = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    texcoord = nodes.new("ShaderNodeTexCoord")
    image_node = nodes.new("ShaderNodeTexImage")
    image_node.image = bpy.data.images.load(str(texture_path))
    brightness = nodes.new("ShaderNodeHueSaturation")
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.22
    bump.inputs["Distance"].default_value = 0.15
    links.new(texcoord.outputs["Generated"], image_node.inputs["Vector"])
    links.new(image_node.outputs["Color"], brightness.inputs["Color"])
    links.new(brightness.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(image_node.outputs["Color"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
    bsdf.inputs["Roughness"].default_value = 0.42
    bsdf.inputs["Metallic"].default_value = 0.05
    base = (0.075, 0.42, 0.09, 1.0)
    value_socket = brightness.inputs["Value"]
    for frame, factor in _focus_factors("HIGH_PRECISION_ACQUISITION_CORE", story, cap=None):
        color = tuple(channel * factor for channel in base[:3]) + (base[3],)
        material.diffuse_color = color
        material.keyframe_insert(data_path="diffuse_color", frame=frame)
        value_socket.default_value = factor
        value_socket.keyframe_insert(data_path="default_value", frame=frame)
    material.diffuse_color = base
    value_socket.default_value = 1.0
    obj.data.materials.clear()
    obj.data.materials.append(material)
    obj["task10v2_material_role"] = "PCB_SOLDERMASK_TEXTURED"
    obj["task10v2_focus_material_keyed"] = True


def _key_context_visibility(
    objects: Mapping[str, Any], components: Mapping[str, Any]
) -> None:
    """Isolate focus shots hide every non-subject part/component outright.

    Minimalist presentation: the subject floats alone on the backdrop
    instead of competing with dimmed context geometry.
    """
    story = build_story_config()
    all_ids = list(objects) + list(components)
    schedule = hide_schedule(story["shots"], all_ids)
    for pid in all_ids:
        obj = objects.get(pid) or components.get(pid)
        if obj is None:
            continue
        for frame, hidden in schedule.get(pid, []):
            obj.hide_render = hidden
            obj.hide_viewport = hidden
            obj.keyframe_insert(data_path="hide_render", frame=frame)
            obj.keyframe_insert(data_path="hide_viewport", frame=frame)
        obj["task10v2_isolate_visibility_keyed"] = True


def _build_camera_config(root: Path, state_data: Mapping[str, Any]) -> dict[str, Any]:
    layout = load_json(root / "stage_09C_refined_explosion/config/refined_layout.json")
    # Cameras are frozen on the deterministic builder output — the same
    # baseline the layout solver evaluates against. Basing cameras on solved
    # positions would let later solves retroactively invalidate earlier ones
    # (the hero camera depends on bounds over all states).
    baseline = build_story_v2_state_transforms(root)
    records = build_camera_records(baseline, layout)
    config = build_camera_sequence()
    return {**config, **records}


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
        camera["task10v2_camera_role"] = name.removeprefix("CAM_STORY_").lower()
    scene = bpy.context.scene
    for marker in list(scene.timeline_markers):
        if marker.name.startswith("T10_CAMERA_"):
            scene.timeline_markers.remove(marker)
    for index, segment in enumerate(config["camera_segments"]):
        marker = scene.timeline_markers.new(
            f"T10_CAMERA_{index:02d}_{segment['camera_id']}",
            frame=int(segment["frame_start"]),
        )
        marker.camera = bpy.data.objects[segment["camera_id"]]
    _key_camera_drift(config)


def _key_camera_drift(config: Mapping[str, Any]) -> None:
    """Every segment slowly pushes in and orbits — motion never stops."""
    push = float(MOTION_TIMING["camera_push_fraction"])
    orbit = float(MOTION_TIMING["camera_orbit_deg"])
    for index, segment in enumerate(config["camera_segments"]):
        camera = bpy.data.objects[segment["camera_id"]]
        record = config["cameras"][segment["camera_id"]]
        target = Vector(record["target"])
        sign = 1.0 if index % 2 == 0 else -1.0
        end_location = drifted_pose(record, push, orbit * sign)
        for frame, location in (
            (int(segment["frame_start"]), record["location"]),
            (int(segment["frame_end"]), end_location),
        ):
            camera.location = location
            camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
            camera.keyframe_insert(data_path="location", frame=frame)
            camera.keyframe_insert(data_path="rotation_euler", frame=frame)
        camera["task10v2_camera_drift"] = True
        _auto_bezier(camera)


def _auto_bezier(obj: Any) -> None:
    action = obj.animation_data.action if obj.animation_data else None
    if action is None:
        return
    curves = getattr(action, "fcurves", None)
    if curves is None:
        curves = [
            fc
            for layer in action.layers
            for strip in layer.strips
            for bag in strip.channelbags
            for fc in bag.fcurves
        ]
    for curve in curves:
        for key in curve.keyframe_points:
            key.interpolation = "BEZIER"
            key.handle_left_type = "AUTO_CLAMPED"
            key.handle_right_type = "AUTO_CLAMPED"


def _create_annotations(config: Mapping[str, Any], camera_config: Mapping[str, Any]) -> None:
    collection = _ensure_collection(ANNOTATION_COLLECTION)
    camera_for_shot = {record["shot_id"]: record["camera_id"] for record in build_story_config()["shots"]}
    metric_counts: dict[str, int] = {}
    for index, item in enumerate(config["items"]):
        text_data = bpy.data.curves.new(f"T10V2_TEXT_{item['id']}", type="FONT")
        text_data.body = str(item["text"])
        text_data.align_x = "LEFT"
        is_metric = "metric" in item["id"]
        metric_index = metric_counts.get(item["shot_id"], 0) if is_metric else 0
        if is_metric:
            metric_counts[item["shot_id"]] = metric_index + 1
        layout = annotation_screen_layout(is_metric=is_metric, metric_index=metric_index)
        text_data.size = layout["font_size_mm"] * ANNOTATION_SCALE
        text_data.extrude = 0.08
        text_data.bevel_depth = 0.02
        text_data.materials.append(_text_material())
        text = bpy.data.objects.new(f"T10V2_ANNOTATION_{index:02d}_{item['id']}", text_data)
        collection.objects.link(text)
        camera_name = camera_for_shot[item["shot_id"]]
        cam = bpy.data.objects[camera_name]
        depth = layout["depth_mm"]
        horizontal_half = depth * float(cam.data.sensor_width) / (2.0 * float(cam.data.lens))
        vertical_half = horizontal_half / (1920.0 / 1080.0)
        text.parent = cam
        text.location = (
            layout["x_normalized"] * horizontal_half,
            layout["y_normalized"] * vertical_half,
            -depth,
        )
        text.rotation_euler = (0.0, 0.0, 0.0)
        text["task10v2_annotation_shot"] = item["shot_id"]
        text["task10v2_render_text"] = item["text"]
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
    material = bpy.data.materials.get("T10V2_ANNOTATION_WHITE")
    if material is None:
        material = bpy.data.materials.new("T10V2_ANNOTATION_WHITE")
    material.diffuse_color = WHITE
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = WHITE
        bsdf.inputs["Emission Color"].default_value = WHITE
        bsdf.inputs["Emission Strength"].default_value = 0.8
    return material


def _create_light_rig(lighting: Mapping[str, Any]) -> None:
    collection = _ensure_collection(LIGHT_COLLECTION)
    target = Vector(lighting["target"])
    for record in lighting["lights"]:
        old = bpy.data.objects.get(record["name"])
        if old is not None:
            bpy.data.objects.remove(old, do_unlink=True)
        data = bpy.data.lights.new(record["name"], type="AREA")
        data.energy = float(record["energy"])
        data.shape = "DISK"
        data.size = float(record["size"])
        obj = bpy.data.objects.new(record["name"], data)
        collection.objects.link(obj)
        obj.location = record["location"]
        obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()
        obj["task10v2_role"] = "presentation_light"


def _configure_scene(lighting: Mapping[str, Any]) -> None:
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = 900
    scene.render.fps = 30
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.render.resolution_percentage = 100
    scene.render.engine = RENDER_ENGINE
    scene.render.film_transparent = False
    scene.render.image_settings.color_mode = "RGBA"
    _configure_gradient_world(lighting)
    if hasattr(scene.render, "use_motion_blur"):
        scene.render.use_motion_blur = True
    scene.view_settings.exposure = float(lighting["exposure"])
    scene["task10v2_render_engine"] = RENDER_ENGINE


def _configure_gradient_world(lighting: Mapping[str, Any]) -> None:
    """Vertical studio gradient backdrop (top lighter, floor darker)."""
    scene = bpy.context.scene
    world = scene.world or bpy.data.worlds.new("TASK10V2_WORLD")
    scene.world = world
    world.use_nodes = True
    nodes = world.node_tree.nodes
    links = world.node_tree.links
    for node in list(nodes):
        nodes.remove(node)
    output = nodes.new("ShaderNodeOutputWorld")
    background = nodes.new("ShaderNodeBackground")
    texcoord = nodes.new("ShaderNodeTexCoord")
    separate = nodes.new("ShaderNodeSeparateXYZ")
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = tuple(WORLD_GRADIENT_BOTTOM)
    ramp.color_ramp.elements[1].color = tuple(WORLD_GRADIENT_TOP)
    links.new(texcoord.outputs["Normal"], separate.inputs["Vector"])
    links.new(separate.outputs["Z"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], background.inputs["Color"])
    links.new(background.outputs["Background"], output.inputs["Surface"])
    background.inputs["Strength"].default_value = float(lighting["world"]["strength"])


def _ensure_collection(name: str) -> Any:
    collection = bpy.data.collections.get(name)
    if collection is None:
        collection = bpy.data.collections.new(name)
    parent = bpy.data.collections.get(COLLECTION_ROOT) or bpy.context.scene.collection
    if collection.name not in {child.name for child in parent.children}:
        parent.children.link(collection)
    return collection


def _remove_presentation_objects() -> None:
    for obj in list(bpy.data.objects):
        if obj.type in {"CAMERA", "LIGHT"} or obj.name.startswith("T10V2_ANNOTATION_"):
            bpy.data.objects.remove(obj, do_unlink=True)


def _validate_geometry(objects: Mapping[str, Any]) -> None:
    if len(objects) != 82:
        raise ValueError("Task 10-V2 source PART count changed")
    faces = sum(len(obj.data.polygons) for obj in objects.values())
    vertices = sum(len(obj.data.vertices) for obj in objects.values())
    if faces != 444296 or vertices != 221902:
        raise ValueError(f"Task 10-V2 frozen geometry totals changed: {faces}/{vertices}")


def _script_arguments() -> list[str]:
    arguments = list(sys.argv[1:])
    return arguments[arguments.index("--") + 1 :] if "--" in arguments else arguments


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args(argv if argv is not None else _script_arguments())
    print(json.dumps(apply_story_presentation_v2(args.project_root), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
