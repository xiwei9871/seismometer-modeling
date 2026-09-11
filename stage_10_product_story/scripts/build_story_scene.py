"""Build Task 10 state transforms and a geometry-preserving Blender scene."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import struct
from typing import Any, Mapping, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.task08_data import load_json, write_json
from stage_10_product_story.scripts.story_data import (
    FUNCTIONAL_MODULES,
    build_story_config,
)

try:  # pragma: no cover - executed through Blender.
    import bpy  # type: ignore
except ImportError:  # pragma: no cover
    bpy = None  # type: ignore


INPUT_BLEND = "stage_09C_refined_explosion/scene/exploded_animation_preview.blend"
INPUT_BLEND_SHA256 = "a3b5359861877e247ad1b035b00cace3e29eea2789ac227e6eeddfaaba1a7766"
LAYOUT_PATH = "stage_09C_refined_explosion/config/refined_layout.json"
STATE_OUTPUT = "stage_10_product_story/config/state_transforms.json"
SCENE_OUTPUT = "stage_10_product_story/scene/product_story_preview.blend"
EXPECTED_PART_IDS = tuple(f"PART_{index:03d}" for index in range(1, 83))
VISIBLE_PART_IDS = tuple(f"PART_{index:03d}" for index in range(1, 23))
HIDDEN_PART_IDS = tuple(f"PART_{index:03d}" for index in range(23, 83))
STATE_IDS = tuple(shot_id for shot_id, _, _ in (
    ("ASSEMBLED", 1, 75),
    ("PRIMARY_ARCHITECTURE", 75, 165),
    ("SENSOR_FOCUS", 165, 300),
    ("PCB_FOCUS", 300, 420),
    ("COMMUNICATION_FOCUS", 420, 510),
    ("POWER_FOCUS", 510, 615),
    ("RUGGED_FOCUS", 615, 705),
    ("REASSEMBLED", 705, 810),
    ("FINAL_HERO", 810, 900),
))


def build_story_visibility_policy() -> dict[str, Any]:
    return {
        "visible_part_ids": list(VISIBLE_PART_IDS),
        "hidden_part_ids": list(HIDDEN_PART_IDS),
        "hidden_policy": "PRESENTATION_HIDDEN_NO_ANIMATION",
        "source_parts_preserved": True,
    }


def build_state_transforms(project_root: Path) -> dict[str, Any]:
    """Create absolute transforms for nine functional-story states."""
    root = Path(project_root).expanduser().resolve()
    layout = load_json(root / LAYOUT_PATH)
    source_parts = layout.get("parts")
    if not isinstance(source_parts, Mapping) or set(source_parts) != set(EXPECTED_PART_IDS):
        raise ValueError("Task 10 requires the complete Task 9C PART layout")

    assembled: dict[str, dict[str, list[float]]] = {}
    for part_id in VISIBLE_PART_IDS:
        record = source_parts[part_id]
        assembled[part_id] = {
            "location": _vector(record["assembled_location"]),
            "rotation_euler": _vector(record["assembled_rotation"]),
            "scale": _vector(record["assembled_scale"]),
        }

    offsets = _state_offsets(assembled)
    focus_by_state = {
        "ASSEMBLED": None,
        "PRIMARY_ARCHITECTURE": None,
        "SENSOR_FOCUS": "SMART_3_AXIS_SENSING_SYSTEM",
        "PCB_FOCUS": "HIGH_PRECISION_ACQUISITION_CORE",
        "COMMUNICATION_FOCUS": "REAL_TIME_COMMUNICATION_SYSTEM",
        "POWER_FOCUS": "LONG_ENDURANCE_POWER_SYSTEM",
        "RUGGED_FOCUS": "RUGGED_FIELD_PLATFORM",
        "REASSEMBLED": None,
        "FINAL_HERO": None,
    }
    states: dict[str, Any] = {}
    for state_id in STATE_IDS:
        parts: dict[str, Any] = {}
        for part_id in VISIBLE_PART_IDS:
            base = assembled[part_id]
            delta = offsets[state_id].get(part_id, [0.0, 0.0, 0.0])
            parts[part_id] = {
                "location": [base["location"][axis] + delta[axis] for axis in range(3)],
                "rotation_euler": list(base["rotation_euler"]),
                "scale": list(base["scale"]),
                "offset_from_assembled_mm": list(delta),
            }
        states[state_id] = {
            "state_id": state_id,
            "focus_module": focus_by_state[state_id],
            "parts": parts,
        }
    payload = {
        "version": "task10_story_states_v1",
        "unit_assumption": "mm",
        "source_baseline": {
            "source_part_count": 82,
            "faces": 444296,
            "indexed_vertices": 221902,
        },
        "source_scene": INPUT_BLEND,
        "source_scene_sha256": INPUT_BLEND_SHA256,
        "visibility_policy": build_story_visibility_policy(),
        "states": states,
    }
    return validate_state_transforms(payload)


def _state_offsets(assembled: Mapping[str, Mapping[str, Sequence[float]]]) -> dict[str, dict[str, list[float]]]:
    zero = {part_id: [0.0, 0.0, 0.0] for part_id in VISIBLE_PART_IDS}

    architecture = {part_id: [0.0, 0.0, 0.0] for part_id in VISIBLE_PART_IDS}
    for part_id in ("PART_002", "PART_004", "PART_005", "PART_017", "PART_018"):
        architecture[part_id] = [0.0, 0.0, 92.0]
    for part_id in ("PART_006", "PART_007", "PART_019"):
        architecture[part_id] = [0.0, 0.0, 40.0]
    for part_id in ("PART_008", "PART_009", "PART_010", "PART_011", "PART_015", "PART_016"):
        architecture[part_id] = [0.0, 0.0, 24.0]
    for part_id in ("PART_003", "PART_012", "PART_013", "PART_014"):
        architecture[part_id] = [0.0, 0.0, -14.0]
    for part_id in ("PART_020", "PART_021", "PART_022"):
        architecture[part_id] = [0.0, 0.0, -46.0]

    sensor = _copy_offsets(architecture)
    sensor_base = [-96.0, 0.0, 18.0]
    sensor["PART_003"] = list(sensor_base)
    sensor["PART_012"] = [sensor_base[0] - 28.0, sensor_base[1], sensor_base[2] + 12.0]
    sensor["PART_013"] = [sensor_base[0], sensor_base[1] - 28.0, sensor_base[2] + 12.0]
    sensor["PART_014"] = [sensor_base[0], sensor_base[1], sensor_base[2] + 40.0]

    pcb = _copy_offsets(architecture)
    pcb["PART_006"] = [70.0, -8.0, 76.0]
    pcb["PART_019"] = [62.0, 0.0, 46.0]
    pcb["PART_007"] = [54.0, 8.0, 16.0]

    communication = _copy_offsets(architecture)
    communication["PART_005"] = [34.0, 0.0, 122.0]
    communication["PART_017"] = [45.0, -12.0, 94.0]
    communication["PART_018"] = [45.0, 12.0, 94.0]
    communication["PART_019"] = [0.0, 0.0, 26.0]
    communication["PART_006"] = [0.0, 0.0, 36.0]
    communication["PART_007"] = [0.0, 0.0, 16.0]

    power = _copy_offsets(architecture)
    # Preserve each cell's mounting correspondence while opening the radial pattern.
    center_x = sum(float(assembled[p]["location"][0]) for p in FUNCTIONAL_MODULES["LONG_ENDURANCE_POWER_SYSTEM"]) / 6.0
    center_y = sum(float(assembled[p]["location"][1]) for p in FUNCTIONAL_MODULES["LONG_ENDURANCE_POWER_SYSTEM"]) / 6.0
    for part_id in FUNCTIONAL_MODULES["LONG_ENDURANCE_POWER_SYSTEM"]:
        x, y, _ = assembled[part_id]["location"]
        dx, dy = float(x) - center_x, float(y) - center_y
        length = math.hypot(dx, dy) or 1.0
        power[part_id] = [34.0 * dx / length, 34.0 * dy / length, 38.0]

    rugged = {part_id: [0.0, 0.0, 0.0] for part_id in VISIBLE_PART_IDS}
    rugged["PART_002"] = [0.0, 0.0, 32.0]
    rugged["PART_004"] = [0.0, 0.0, 48.0]
    for part_id in ("PART_020", "PART_021", "PART_022"):
        rugged[part_id] = [0.0, 0.0, -62.0]

    return {
        "ASSEMBLED": _copy_offsets(zero),
        "PRIMARY_ARCHITECTURE": architecture,
        "SENSOR_FOCUS": sensor,
        "PCB_FOCUS": pcb,
        "COMMUNICATION_FOCUS": communication,
        "POWER_FOCUS": power,
        "RUGGED_FOCUS": rugged,
        "REASSEMBLED": _copy_offsets(zero),
        "FINAL_HERO": _copy_offsets(zero),
    }


def _copy_offsets(source: Mapping[str, Sequence[float]]) -> dict[str, list[float]]:
    return {part_id: [float(value) for value in offset] for part_id, offset in source.items()}


def validate_state_transforms(payload: Mapping[str, Any]) -> dict[str, Any]:
    expected_baseline = {"source_part_count": 82, "faces": 444296, "indexed_vertices": 221902}
    if payload.get("source_baseline") != expected_baseline:
        raise ValueError("Task 10 state baseline is invalid")
    states = payload.get("states")
    if not isinstance(states, Mapping) or list(states) != list(STATE_IDS):
        raise ValueError("Task 10 state set is incomplete or unordered")
    for state_id, state in states.items():
        parts = state.get("parts")
        if not isinstance(parts, Mapping) or list(parts) != list(VISIBLE_PART_IDS):
            raise ValueError(f"Task 10 state PART coverage is invalid: {state_id}")
        for part_id, record in parts.items():
            for key in ("location", "rotation_euler", "scale", "offset_from_assembled_mm"):
                _vector(record.get(key), f"{state_id}/{part_id}/{key}")
    for part_id in VISIBLE_PART_IDS:
        assembled = states["ASSEMBLED"]["parts"][part_id]
        for state_id in ("REASSEMBLED", "FINAL_HERO"):
            if states[state_id]["parts"][part_id]["location"] != assembled["location"]:
                raise ValueError(f"{state_id} does not restore {part_id}")
    return dict(payload)


def write_state_transforms(project_root: Path, payload: Mapping[str, Any]) -> Path:
    root = Path(project_root).expanduser().resolve()
    output = root / STATE_OUTPUT
    write_json(output, validate_state_transforms(payload))
    return output


def build_story_scene(project_root: Path) -> dict[str, Any]:
    if bpy is None:
        raise RuntimeError("Blender bpy is required to build the Task 10 scene")
    root = Path(project_root).expanduser().resolve()
    input_path = root / INPUT_BLEND
    digest = hashlib.sha256(input_path.read_bytes()).hexdigest()
    if digest != INPUT_BLEND_SHA256:
        raise ValueError("Task 9C scene SHA256 changed after approval")
    state_data = build_state_transforms(root)
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
            # Presentation materials live on a copied mesh datablock.  The
            # original Stage 9C mesh datablock is therefore never mutated.
            obj.data = obj.data.copy()
            record = assembled[part_id]
            obj.location = record["location"]
            obj.rotation_euler = record["rotation_euler"]
            obj.scale = record["scale"]
            obj.hide_viewport = False
            obj.hide_render = False
            collections[module_for_part[part_id]].objects.link(obj)
            obj["task10_functional_module"] = module_for_part[part_id]
            obj["task10_animation_enabled"] = True
            obj["task10_story_animation_enabled"] = True
        else:
            obj.hide_viewport = True
            obj.hide_render = True
            collections["SOURCE_HIDDEN"].objects.link(obj)
            obj["task10_functional_module"] = "SOURCE_HIDDEN"
            obj["task10_animation_enabled"] = False
            obj["task10_story_animation_enabled"] = False
        obj["task10_story_state_source"] = "stage_10_product_story/config/state_transforms.json"
        obj["task10_source_geometry_fingerprint"] = source_fingerprint
        obj["task10_geometry_data_role"] = "presentation_copy" if part_id in VISIBLE_PART_IDS else "source"
        obj["task10_source_geometry_unchanged"] = True

    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = 900
    scene.render.fps = 30
    scene["task10_story_version"] = "task10_story_v1"
    scene["task10_source_part_count"] = 82
    scene["task10_source_faces"] = 444296
    scene["task10_source_indexed_vertices"] = 221902
    scene["task10_communication_protocol_text"] = "PENDING_PRODUCT_CONFIRMATION"
    scene["task10_animation_created"] = False
    scene["task10_story_state_source"] = "stage_10_product_story/config/state_transforms.json"
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
        "animation_data_count": sum(obj.animation_data is not None for obj in reopened.values()),
    }


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
        raise ValueError("Task 10 source scene does not contain PART_001..PART_082")
    return objects


def _validate_geometry(objects: Mapping[str, Any]) -> None:
    if len(objects) != 82:
        raise ValueError("Task 10 source PART count changed")
    faces = sum(len(obj.data.polygons) for obj in objects.values())
    vertices = sum(len(obj.data.vertices) for obj in objects.values())
    if faces != 444296 or vertices != 221902:
        raise ValueError(f"Task 10 frozen geometry totals changed: {faces}/{vertices}")


def mesh_geometry_fingerprint(mesh: Any) -> str:
    """Hash vertex coordinates and polygon index order without changing a mesh."""
    digest = hashlib.sha256()
    for vertex in mesh.vertices:
        for coordinate in vertex.co:
            digest.update(struct.pack("<d", float(coordinate)))
    for polygon in mesh.polygons:
        digest.update(struct.pack("<I", len(polygon.vertices)))
        for index in polygon.vertices:
            digest.update(struct.pack("<I", int(index)))
    return digest.hexdigest()


def _remove_non_source_objects() -> None:
    for obj in list(bpy.data.objects):
        if not (obj.type == "MESH" and obj.get("source") == "original_stl"):
            bpy.data.objects.remove(obj, do_unlink=True)


def _create_story_collections() -> dict[str, Any]:
    root_collection = bpy.data.collections.get("STORY_10")
    if root_collection is None:
        root_collection = bpy.data.collections.new("STORY_10")
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
        output = write_state_transforms(args.project_root, build_state_transforms(args.project_root))
        result = {"state_transforms": str(output)}
    else:
        result = build_story_scene(args.project_root)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
