"""Build the Task 10-V2 story scene: v1 layout plus the populated board."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.task08_data import write_json
from stage_10_product_story.scripts.build_story_scene import (
    EXPECTED_PART_IDS,
    HIDDEN_PART_IDS,
    INPUT_BLEND,
    INPUT_BLEND_SHA256,
    VISIBLE_PART_IDS,
    mesh_geometry_fingerprint,
)
from stage_10_product_story.scripts.story_data import FUNCTIONAL_MODULES
from stage_10V2_product_story.scripts.story_v2_data import (
    SCENE_OUTPUT,
    STATE_OUTPUT,
    build_story_v2_state_transforms,
)

try:  # pragma: no cover - executed through Blender.
    import bpy  # type: ignore
except ImportError:  # pragma: no cover
    bpy = None  # type: ignore


PRESENTATION_COLLECTION = "STORY_PCB_PRESENTATION"


def write_state_transforms(project_root: Path, payload: Mapping[str, Any]) -> Path:
    root = Path(project_root).expanduser().resolve()
    output = root / STATE_OUTPUT
    write_json(output, payload)
    return output


def build_story_scene_v2(project_root: Path) -> dict[str, Any]:
    if bpy is None:
        raise RuntimeError("Blender bpy is required to build the Task 10-V2 scene")
    root = Path(project_root).expanduser().resolve()
    input_path = root / INPUT_BLEND
    digest = hashlib.sha256(input_path.read_bytes()).hexdigest()
    if digest != INPUT_BLEND_SHA256:
        raise ValueError("Task 9C scene SHA256 changed after approval")
    state_data = build_story_v2_state_transforms(root)
    write_state_transforms(root, state_data)

    bpy.ops.wm.open_mainfile(filepath=str(input_path))
    objects = _source_objects()
    _validate_geometry(objects)
    _remove_non_source_objects()
    collections = _create_story_collections()
    module_for_part = {
        part_id: module_id
        for module_id, part_ids in FUNCTIONAL_MODULES.items()
        for part_id in part_ids
    }
    assembled = state_data["states"]["ASSEMBLED"]["parts"]
    for part_id in EXPECTED_PART_IDS:
        obj = objects[part_id]
        source_fingerprint = mesh_geometry_fingerprint(obj.data)
        obj.animation_data_clear()
        _unlink(obj)
        if part_id in VISIBLE_PART_IDS:
            obj.data = obj.data.copy()
            record = assembled[part_id]
            obj.location = record["location"]
            obj.rotation_euler = record["rotation_euler"]
            obj.scale = record["scale"]
            obj.hide_viewport = False
            obj.hide_render = False
            collections[module_for_part[part_id]].objects.link(obj)
            obj["task10v2_functional_module"] = module_for_part[part_id]
            obj["task10v2_animation_enabled"] = True
            obj["task10v2_story_animation_enabled"] = True
        else:
            obj.hide_viewport = True
            obj.hide_render = True
            collections["SOURCE_HIDDEN"].objects.link(obj)
            obj["task10v2_functional_module"] = "SOURCE_HIDDEN"
            obj["task10v2_animation_enabled"] = False
            obj["task10v2_story_animation_enabled"] = False
        obj["task10v2_story_state_source"] = STATE_OUTPUT
        obj["task10v2_source_geometry_fingerprint"] = source_fingerprint
        obj["task10v2_geometry_data_role"] = "presentation_copy" if part_id in VISIBLE_PART_IDS else "source"
        obj["task10v2_source_geometry_unchanged"] = True

    reclass = state_data["presentation"]["part_reclassification"]
    for part_id, record in reclass.items():
        obj = objects[part_id]
        obj["presentation_priority"] = record["presentation_priority"]
        obj["independent_focus"] = bool(record["independent_focus"])
        obj["presentation_weight"] = float(record["presentation_weight"])

    presentation_collection = collections["PRESENTATION"]
    for component in state_data["presentation"]["components"]:
        _build_component(
            component,
            state_data["states"]["ASSEMBLED"]["components"][component["component_id"]],
            presentation_collection,
        )

    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = 900
    scene.render.fps = 30
    scene["task10v2_story_version"] = "task10V2_story_v1"
    scene["task10v2_source_part_count"] = 82
    scene["task10v2_source_faces"] = 444296
    scene["task10v2_source_indexed_vertices"] = 221902
    scene["task10v2_communication_protocol_text"] = "PENDING_PRODUCT_CONFIRMATION"
    scene["task10v2_animation_created"] = False
    scene["task10v2_story_state_source"] = STATE_OUTPUT
    scene["task10v2_presentation_component_count"] = len(state_data["presentation"]["components"])
    output = root / SCENE_OUTPUT
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output))
    bpy.ops.wm.open_mainfile(filepath=str(output))
    reopened = _source_objects()
    _validate_geometry(reopened)
    return {
        "output": str(output),
        "source_part_count": len(reopened),
        "source_faces": sum(len(obj.data.polygons) for obj in reopened.values()),
        "source_indexed_vertices": sum(len(obj.data.vertices) for obj in reopened.values()),
        "visible_part_count": sum(not obj.hide_render for obj in reopened.values()),
        "hidden_part_count": sum(obj.hide_render for obj in reopened.values()),
        "presentation_component_count": sum(
            obj.get("task10v2_presentation_component") is True
            for obj in bpy.data.objects
            if obj.type == "MESH"
        ),
    }


def _build_component(component: Mapping[str, Any], transform: Mapping[str, Any], collection: Any) -> Any:
    cid = component["component_id"]
    location = [float(v) for v in transform["location"]]
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
    obj["source"] = "photographic_presentation_reconstruction"
    obj["mounted_on"] = "PART_019"
    obj["reference_source"] = component["reference_source"]
    obj["task10v2_presentation_component"] = True
    obj["task10v2_board_local_location"] = [float(v) for v in component["board_local_location"]]
    obj["task10v2_material_role"] = component["material_role"]
    obj["task10v2_functional_module"] = "HIGH_PRECISION_ACQUISITION_CORE"
    obj["task10v2_animation_enabled"] = True
    obj["task10v2_story_animation_enabled"] = True
    obj["task10v2_story_state_source"] = STATE_OUTPUT
    return obj


def _source_objects() -> dict[str, Any]:
    objects: dict[str, Any] = {}
    for obj in bpy.data.objects:
        if obj.type != "MESH" or obj.get("source") != "original_stl":
            continue
        part_id = str(obj.get("part_id"))
        if part_id in objects:
            raise ValueError(f"duplicate source PART: {part_id}")
        objects[part_id] = obj
    if set(objects) != set(EXPECTED_PART_IDS):
        raise ValueError("Task 10-V2 source scene does not contain PART_001..PART_082")
    return objects


def _validate_geometry(objects: Mapping[str, Any]) -> None:
    if len(objects) != 82:
        raise ValueError("Task 10-V2 source PART count changed")
    faces = sum(len(obj.data.polygons) for obj in objects.values())
    vertices = sum(len(obj.data.vertices) for obj in objects.values())
    if faces != 444296 or vertices != 221902:
        raise ValueError(f"Task 10-V2 frozen geometry totals changed: {faces}/{vertices}")


def _remove_non_source_objects() -> None:
    for obj in list(bpy.data.objects):
        if not (obj.type == "MESH" and obj.get("source") == "original_stl"):
            bpy.data.objects.remove(obj, do_unlink=True)


def _create_story_collections() -> dict[str, Any]:
    root_collection = bpy.data.collections.get("STORY_10V2")
    if root_collection is None:
        root_collection = bpy.data.collections.new("STORY_10V2")
        bpy.context.scene.collection.children.link(root_collection)
    modules_collection = bpy.data.collections.get("STORY_MODULES")
    if modules_collection is None:
        modules_collection = bpy.data.collections.new("STORY_MODULES")
    if modules_collection.name not in {child.name for child in root_collection.children}:
        root_collection.children.link(modules_collection)
    hidden_collection = bpy.data.collections.get("STORY_SOURCE_HIDDEN")
    if hidden_collection is None:
        hidden_collection = bpy.data.collections.new("STORY_SOURCE_HIDDEN")
    if hidden_collection.name not in {child.name for child in root_collection.children}:
        root_collection.children.link(hidden_collection)
    presentation_collection = bpy.data.collections.get(PRESENTATION_COLLECTION)
    if presentation_collection is None:
        presentation_collection = bpy.data.collections.new(PRESENTATION_COLLECTION)
    if presentation_collection.name not in {child.name for child in root_collection.children}:
        root_collection.children.link(presentation_collection)
    result: dict[str, Any] = {}
    for name in FUNCTIONAL_MODULES:
        collection_name = f"STORY_{name}"
        collection = bpy.data.collections.get(collection_name)
        if collection is None:
            collection = bpy.data.collections.new(collection_name)
        if collection.name not in {child.name for child in modules_collection.children}:
            modules_collection.children.link(collection)
        result[name] = collection
    result["SOURCE_HIDDEN"] = hidden_collection
    result["PRESENTATION"] = presentation_collection
    return result


def _unlink(obj: Any) -> None:
    for collection in list(obj.users_collection):
        collection.objects.unlink(obj)


def _vector(value: Any, label: str = "vector") -> list[float]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 3:
        raise ValueError(f"{label} must contain three values")
    result = [float(item) for item in value]
    if not all(math.isfinite(item) for item in result):
        raise ValueError(f"{label} must be finite")
    return result


def _script_arguments() -> list[str]:
    arguments = list(sys.argv[1:])
    return arguments[arguments.index("--") + 1 :] if "--" in arguments else arguments


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--data-only", action="store_true")
    args = parser.parse_args(argv if argv is not None else _script_arguments())
    if args.data_only:
        output = write_state_transforms(args.project_root, build_story_v2_state_transforms(args.project_root))
        result = {"state_transforms": str(output)}
    else:
        result = build_story_scene_v2(args.project_root)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
