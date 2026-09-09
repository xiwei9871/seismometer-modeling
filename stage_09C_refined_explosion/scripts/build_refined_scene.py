"""Build the Task 9C refined static scene from the frozen R1 blend."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.task08_data import load_json
from stage_09A_R1_exploded_rework.scripts.apply_explosion_layout import validate_r1_scene_facts
from stage_09C_refined_explosion.scripts.build_refined_layout import (
    EXPECTED_PART_IDS,
    VISIBLE_PART_IDS,
    validate_refined_layout,
)

try:  # pragma: no cover - executed by Blender.
    import bpy  # type: ignore
except ImportError:  # pragma: no cover
    bpy = None  # type: ignore


R1_BLEND_PATH = "stage_09A_R1_exploded_rework/scene/exploded_layout_v2.blend"
OUTPUT_BLEND_PATH = "stage_09C_refined_explosion/scene/exploded_animation_preview.blend"
REFINED_ROOT_COLLECTION = "PRESENTATION_REFINED_9C"
GROUP_COLLECTIONS = (
    "MAIN_STACK",
    "SENSOR_BRANCH",
    "PCB_BRANCH",
    "BATTERY_BRANCH",
    "TOP_INTERFACE_BRANCH",
    "LEVELING_BRANCH",
)
HIDDEN_COLLECTION = "SOURCE_HIDDEN_9C"


def build_refined_scene(project_root: Path) -> dict[str, Any]:
    if bpy is None:
        raise RuntimeError("Blender bpy is required to build Task 9C scene")
    root = Path(project_root).expanduser().resolve()
    layout = validate_refined_layout(
        load_json(root / "stage_09C_refined_explosion/config/refined_layout.json")
    )
    bpy.ops.wm.open_mainfile(filepath=str(root / R1_BLEND_PATH))
    source_objects = _source_objects()
    before = _validate_scene(source_objects, require_visible=True)
    _remove_existing_cameras_and_lights()
    collections = _create_collections()
    for part_id in EXPECTED_PART_IDS:
        obj = source_objects[part_id]
        record = layout["parts"][part_id]
        _unlink(obj)
        obj.animation_data_clear()
        if record["presentation_visibility"] == "VISIBLE":
            obj.location = record["refined_presentation_location"]
            obj.rotation_euler = record["assembled_rotation"]
            obj.scale = record["assembled_scale"]
            obj.hide_viewport = False
            obj.hide_render = False
            obj.name = f"{part_id}__{record['semantic_name']}"
            collections[record["presentation_group"]].objects.link(obj)
        else:
            obj.location = record["assembled_location"]
            obj.rotation_euler = record["assembled_rotation"]
            obj.scale = record["assembled_scale"]
            obj.hide_viewport = True
            obj.hide_render = True
            collections[HIDDEN_COLLECTION].objects.link(obj)
        _apply_metadata(obj, record)
    _set_scene_metadata()
    output = root / OUTPUT_BLEND_PATH
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output))
    reopened = _reopen_and_validate(output)
    return {
        "output": str(output),
        "source_part_count": reopened["source_part_count"],
        "visible_part_count": reopened["visible_part_count"],
        "hidden_part_count": reopened["hidden_part_count"],
        "vertices": reopened["vertices"],
        "polygons": reopened["polygons"],
        "animation_data_count": reopened["animation_data_count"],
        "animation_created": False,
        "input_r1_validation": before,
        "reopened_validation": reopened,
    }


def _source_objects() -> dict[str, Any]:
    objects: dict[str, Any] = {}
    for obj in bpy.data.objects:
        if obj.type != "MESH" or obj.get("source") != "original_stl":
            continue
        part_id = obj.get("part_id")
        if not isinstance(part_id, str) or part_id in objects:
            raise ValueError(f"invalid or duplicate Task 9C source PART: {part_id!r}")
        objects[part_id] = obj
    if set(objects) != set(EXPECTED_PART_IDS):
        raise ValueError("Task 9C source PART coverage is not PART_001..PART_082")
    return objects


def _validate_scene(objects: dict[str, Any], *, require_visible: bool) -> dict[str, Any]:
    facts = [
        {
            "part_id": obj.get("part_id"),
            "source": obj.get("source"),
            "type": obj.type,
            "hidden": bool(obj.hide_viewport or obj.hide_render),
            "animation_data": obj.animation_data,
        }
        for obj in objects.values()
    ]
    return validate_r1_scene_facts(
        facts,
        vertices=sum(len(obj.data.vertices) for obj in objects.values()),
        polygons=sum(len(obj.data.polygons) for obj in objects.values()),
        require_visibility_policy=require_visible,
    )


def _reopen_and_validate(path: Path) -> dict[str, Any]:
    bpy.ops.wm.open_mainfile(filepath=str(path))
    objects = _source_objects()
    return _validate_scene(objects, require_visible=True)


def _remove_existing_cameras_and_lights() -> None:
    for obj in list(bpy.data.objects):
        if obj.type in {"CAMERA", "LIGHT"}:
            bpy.data.objects.remove(obj, do_unlink=True)


def _create_collections() -> dict[str, Any]:
    root = bpy.data.collections.get(REFINED_ROOT_COLLECTION)
    if root is None:
        root = bpy.data.collections.new(REFINED_ROOT_COLLECTION)
        bpy.context.scene.collection.children.link(root)
    collections = {REFINED_ROOT_COLLECTION: root}
    for name in GROUP_COLLECTIONS + (HIDDEN_COLLECTION,):
        collection = bpy.data.collections.get(f"9C_{name}")
        if collection is None:
            collection = bpy.data.collections.new(f"9C_{name}")
        if collection.name not in {child.name for child in root.children}:
            root.children.link(collection)
        collections[name] = collection
    return collections


def _unlink(obj: Any) -> None:
    for collection in list(obj.users_collection):
        collection.objects.unlink(obj)


def _apply_metadata(obj: Any, record: dict[str, Any]) -> None:
    obj["part_id"] = record["part_id"]
    obj["source"] = "original_stl"
    obj["source_component_index"] = int(record["source_component_index"])
    obj["semantic_name"] = record["semantic_name"]
    obj["semantic_category"] = record["semantic_category"]
    obj["task09c_presentation_group"] = record["presentation_group"] or "HIDDEN_SOURCE"
    obj["task09c_presentation_visibility"] = record["presentation_visibility"]
    obj["task09c_assembled_location"] = list(record["assembled_location"])
    obj["task09c_refined_location"] = list(record["refined_presentation_location"])
    obj["task09c_animation_enabled"] = bool(record["animation_enabled"])
    obj["task09c_source_geometry_unchanged"] = True


def _set_scene_metadata() -> None:
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = 540
    scene.render.fps = 30
    scene["task09c_layout_version"] = "9c_refined_v1"
    scene["task09c_animation_created"] = False
    scene["task09c_source_part_count"] = 82
    scene["task09c_source_faces"] = 444296
    scene["task09c_source_indexed_vertices"] = 221902


def _script_arguments() -> list[str]:
    arguments = list(sys.argv[1:])
    return arguments[arguments.index("--") + 1 :] if "--" in arguments else arguments


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args(argv if argv is not None else _script_arguments())
    print(json.dumps(build_refined_scene(args.project_root), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
