"""Apply the static R1 layout to a new derived Blender scene."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import json
import math
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.task08_data import load_json

from stage_09A_R1_exploded_rework.scripts.build_explosion_groups import (
    EXPECTED_PART_IDS,
    IMPORTANT_PART_IDS,
    validate_explosion_layout,
)

try:  # Blender is available only when this module is executed by Blender.
    import bpy  # type: ignore
except ImportError:  # pragma: no cover
    bpy = None  # type: ignore


OUTPUT_BLEND = "stage_09A_R1_exploded_rework/scene/exploded_layout_v2.blend"
R1_ROOT_COLLECTION = "PRESENTATION_R1"
GROUP_COLLECTIONS = (
    "MAIN_STACK",
    "SENSOR_BRANCH",
    "PCB_BRANCH",
    "BATTERY_BRANCH",
    "TOP_INTERFACE_BRANCH",
    "LEVELING_BRANCH",
)
HIDDEN_COLLECTION = "SOURCE_HIDDEN_R1"


def validate_r1_scene_facts(
    facts: Sequence[Mapping[str, Any]],
    *,
    vertices: int,
    polygons: int,
    require_visibility_policy: bool = True,
) -> dict[str, Any]:
    """Validate source PART coverage, frozen totals, visibility, and staticness."""
    if not isinstance(facts, Sequence) or isinstance(facts, (str, bytes)):
        raise ValueError("R1 scene facts must be a sequence")
    source = [fact for fact in facts if fact.get("source") == "original_stl" and fact.get("type") == "MESH"]
    if len(source) != len(EXPECTED_PART_IDS):
        raise ValueError("R1 source PART count changed")
    ids = [fact.get("part_id") for fact in source]
    if any(not isinstance(part_id, str) for part_id in ids):
        raise ValueError("R1 source PART IDs must be strings")
    if len(set(ids)) != len(ids) or set(ids) != set(EXPECTED_PART_IDS):
        raise ValueError("R1 source PART coverage is not PART_001..PART_082")
    if int(vertices) != 221902 or int(polygons) != 444296:
        raise ValueError("R1 frozen geometry totals changed")
    animated = [str(fact["part_id"]) for fact in source if fact.get("animation_data") is not None]
    if animated:
        raise ValueError(f"R1 source PARTs contain animation data: {animated}")
    visible = sorted(
        (str(fact["part_id"]) for fact in source if not bool(fact.get("hidden", False))),
        key=_part_number,
    )
    if require_visibility_policy and visible != list(IMPORTANT_PART_IDS):
        raise ValueError(
            "R1 visible source PART policy is invalid: "
            f"expected {list(IMPORTANT_PART_IDS)}, got {visible}"
        )
    return {
        "source_part_count": len(source),
        "vertices": int(vertices),
        "polygons": int(polygons),
        "visible_part_count": len(visible),
        "hidden_part_count": len(source) - len(visible),
        "animation_data_count": 0,
    }


def build_r1_scene(project_root: Path) -> dict[str, Any]:
    """Open Stage 02, materialize the R1 layout, and save a derived blend."""
    if bpy is None:
        raise RuntimeError("Blender bpy is required to build the R1 scene")
    root = Path(project_root).expanduser().resolve()
    layout = validate_explosion_layout(
        load_json(root / "stage_09A_R1_exploded_rework/config/explosion_layout_config.json")
    )
    bpy.ops.wm.open_mainfile(filepath=str(root / "output/stage02_semantic.blend"))
    source_objects = _source_objects()
    facts = [_object_facts(obj) for obj in source_objects.values()]
    scene_validation = validate_r1_scene_facts(
        facts,
        vertices=sum(len(obj.data.vertices) for obj in source_objects.values()),
        polygons=sum(len(obj.data.polygons) for obj in source_objects.values()),
        require_visibility_policy=False,
    )
    _remove_non_source_scene_objects(source_objects)
    collections = _create_collections()
    parts = layout["parts"]
    for part_id in EXPECTED_PART_IDS:
        obj = source_objects[part_id]
        record = parts[part_id]
        _unlink_from_all_collections(obj)
        if record["presentation_visibility"] == "VISIBLE":
            obj.location = record["presentation_location"]
            obj.rotation_euler = record["presentation_rotation"]
            obj.hide_viewport = False
            obj.hide_render = False
            obj.name = f"{part_id}__{record['semantic_name']}"
            target_collection = collections[record["group"]]
            target_collection.objects.link(obj)
            _apply_metadata(obj, record)
            _assign_neutral_material(obj, record["group"])
        else:
            obj.hide_viewport = True
            obj.hide_render = True
            collections[HIDDEN_COLLECTION].objects.link(obj)
            _apply_metadata(obj, record)

    post_facts = [_object_facts(obj) for obj in source_objects.values()]
    post_validation = validate_r1_scene_facts(
        post_facts,
        vertices=sum(len(obj.data.vertices) for obj in source_objects.values()),
        polygons=sum(len(obj.data.polygons) for obj in source_objects.values()),
        require_visibility_policy=True,
    )
    _set_scene_metadata()
    output_path = root / OUTPUT_BLEND
    output_path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output_path))
    return {
        "output": str(output_path),
        "scene_validation": post_validation,
        "input_scene_validation": scene_validation,
        "source_part_count": post_validation["source_part_count"],
        "visible_part_count": post_validation["visible_part_count"],
        "hidden_part_count": post_validation["hidden_part_count"],
        "animation_data_count": post_validation["animation_data_count"],
        "animation_created": False,
    }


def _source_objects() -> dict[str, Any]:
    objects: dict[str, Any] = {}
    for obj in bpy.data.objects:
        if obj.type != "MESH" or obj.get("source") != "original_stl":
            continue
        part_id = obj.get("part_id")
        if not isinstance(part_id, str) or part_id not in EXPECTED_PART_IDS or part_id in objects:
            raise ValueError(f"invalid or duplicate source PART object: {part_id!r}")
        objects[part_id] = obj
    if set(objects) != set(EXPECTED_PART_IDS):
        missing = sorted(set(EXPECTED_PART_IDS) - set(objects), key=_part_number)
        raise ValueError(f"missing source PART objects: {missing}")
    return objects


def _object_facts(obj: Any) -> dict[str, Any]:
    return {
        "part_id": obj.get("part_id"),
        "source": obj.get("source"),
        "type": obj.type,
        "hidden": bool(obj.hide_viewport or obj.hide_render),
        "animation_data": obj.animation_data,
    }


def _remove_non_source_scene_objects(source_objects: Mapping[str, Any]) -> None:
    source_set = set(source_objects.values())
    for obj in list(bpy.data.objects):
        if obj in source_set:
            continue
        if obj.type in {"CAMERA", "LIGHT"}:
            bpy.data.objects.remove(obj, do_unlink=True)


def _create_collections() -> dict[str, Any]:
    root = bpy.data.collections.get(R1_ROOT_COLLECTION)
    if root is None:
        root = bpy.data.collections.new(R1_ROOT_COLLECTION)
        bpy.context.scene.collection.children.link(root)
    collections = {R1_ROOT_COLLECTION: root}
    for name in GROUP_COLLECTIONS + (HIDDEN_COLLECTION, "EXPLOSION_GUIDES", "EXPLOSION_LABELS"):
        collection = bpy.data.collections.get(name)
        if collection is None:
            collection = bpy.data.collections.new(name)
        if collection.name not in {child.name for child in root.children}:
            root.children.link(collection)
        collections[name] = collection
    collections["EXPLOSION_GUIDES"].hide_viewport = True
    collections["EXPLOSION_LABELS"].hide_viewport = True
    return collections


def _unlink_from_all_collections(obj: Any) -> None:
    for collection in list(obj.users_collection):
        collection.objects.unlink(obj)


def _apply_metadata(obj: Any, record: Mapping[str, Any]) -> None:
    obj["part_id"] = record["part_id"]
    obj["source_component_index"] = int(record["source_component_index"])
    obj["source"] = "original_stl"
    obj["semantic_name"] = record["semantic_name"]
    obj["semantic_category"] = record["semantic_category"]
    obj["semantic_confidence"] = record["semantic_confidence"]
    obj["assembled_location"] = list(record["assembled_location"])
    obj["presentation_location"] = list(record["presentation_location"])
    obj["r1_group"] = record["group"] or "HIDDEN_SOURCE"
    obj["r1_visibility"] = record["presentation_visibility"]
    obj["r1_explosion_axis"] = record["explosion_axis"] or "NONE"
    obj["r1_explosion_distance"] = float(record["explosion_distance"])
    obj["r1_animation_created"] = False


def _assign_neutral_material(obj: Any, group_id: str) -> None:
    colors = {
        "MAIN_STACK": (0.58, 0.64, 0.70, 1.0),
        "SENSOR_BRANCH": (0.46, 0.54, 0.62, 1.0),
        "PCB_BRANCH": (0.52, 0.59, 0.66, 1.0),
        "BATTERY_BRANCH": (0.63, 0.67, 0.71, 1.0),
        "TOP_INTERFACE_BRANCH": (0.42, 0.49, 0.56, 1.0),
        "LEVELING_BRANCH": (0.38, 0.45, 0.52, 1.0),
    }
    material_name = f"R1_NEUTRAL_{group_id}"
    material = bpy.data.materials.get(material_name)
    if material is None:
        material = bpy.data.materials.new(material_name)
    material.diffuse_color = colors[group_id]
    if hasattr(material, "roughness"):
        material.roughness = 0.62
    obj.data.materials.clear()
    obj.data.materials.append(material)


def _set_scene_metadata() -> None:
    scene = bpy.context.scene
    scene["r1_layout_version"] = "r1"
    scene["r1_mode"] = "STATIC_HIERARCHICAL_PRESENTATION_R1"
    scene["r1_source_part_count"] = 82
    scene["r1_source_faces"] = 444296
    scene["r1_source_indexed_vertices"] = 221902
    scene["r1_animation_created"] = False


def _part_number(part_id: str) -> int:
    try:
        return int(str(part_id).split("_")[-1])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid PART ID: {part_id!r}") from exc


def _script_arguments() -> list[str]:
    arguments = list(sys.argv[1:])
    return arguments[arguments.index("--") + 1 :] if "--" in arguments else arguments


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args(argv if argv is not None else _script_arguments())
    print(json.dumps(build_r1_scene(args.project_root), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
