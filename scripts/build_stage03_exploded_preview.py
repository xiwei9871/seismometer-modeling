"""Build the no-keyframe Task 9A assembled/exploded Blender preview."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.task08_data import load_json
from scripts.task09_data import validate_task09_baseline

try:  # Blender is optional for the pure contract tests.
    import bpy  # type: ignore
except ImportError:  # pragma: no cover
    bpy = None  # type: ignore


VALID_STATES = ("assembled", "exploded")
SOURCE_PART_COUNT = 82
SOURCE_VERTICES = 221902
SOURCE_POLYGONS = 444296


def validate_stage03_source_scene(
    facts: Sequence[Mapping[str, Any]],
    *,
    vertices: int,
    polygons: int,
) -> dict[str, Any]:
    """Validate source-only facts without requiring Blender at import time."""
    source = [
        fact
        for fact in facts
        if fact.get("type") == "MESH" and fact.get("source") == "original_stl"
    ]
    if len(source) != SOURCE_PART_COUNT:
        raise ValueError(
            f"expected {SOURCE_PART_COUNT} source PART meshes, got {len(source)}"
        )
    expected = [f"PART_{index:03d}" for index in range(1, SOURCE_PART_COUNT + 1)]
    actual = sorted(str(fact.get("part_id")) for fact in source)
    if actual != expected:
        raise ValueError("source PART ID coverage is not PART_001..PART_082")
    if int(vertices) != SOURCE_VERTICES or int(polygons) != SOURCE_POLYGONS:
        raise ValueError(
            "frozen geometry totals changed: "
            f"vertices={vertices}, polygons={polygons}"
        )
    animated = sorted(
        str(fact.get("part_id"))
        for fact in source
        if fact.get("animation_data") is not None
    )
    if animated:
        raise ValueError(f"source PARTs contain animation data: {animated}")
    return {
        "source_part_count": len(source),
        "vertices": int(vertices),
        "polygons": int(polygons),
        "animated_objects": animated,
    }


def build_stage03_scene(project_root: Path, state: str = "exploded") -> dict[str, Any]:
    """Read Stage 02, apply a planned state, and save only the Stage 03 blend."""
    if state not in VALID_STATES:
        raise ValueError(f"state must be one of {VALID_STATES}, got {state!r}")
    if bpy is None:
        raise RuntimeError("Blender bpy is required to build stage03_exploded_preview.blend")

    root = Path(project_root).expanduser().resolve()
    baseline = validate_task09_baseline(root)
    stage02_path = root / "output/stage02_semantic.blend"
    output_path = root / "output/stage03_exploded_preview.blend"
    initial_payload = load_json(root / "data/assembly_initial.json")
    initial_objects = _require_objects(initial_payload)
    planned_state = load_json(root / "data/exploded_state.json")
    state_records = _require_state_records(planned_state)

    bpy.ops.wm.open_mainfile(filepath=str(stage02_path))
    source_objects = _source_objects()
    facts = [_object_facts(obj) for obj in source_objects.values()]
    before_validation = validate_stage03_source_scene(
        facts,
        vertices=sum(len(obj.data.vertices) for obj in source_objects.values()),
        polygons=sum(len(obj.data.polygons) for obj in source_objects.values()),
    )
    _validate_assembled_transforms(source_objects, initial_objects)

    for part_id in _expected_part_ids():
        obj = source_objects[part_id]
        initial = initial_objects[part_id]
        record = state_records[part_id]
        if state == "assembled":
            _set_vector(obj.location, initial["location"])
        else:
            _set_vector(obj.location, record["exploded_location"])
        _set_vector(obj.rotation_euler, initial["rotation_euler"])
        _set_vector(obj.scale, initial["scale"])
        obj["task09_state"] = state
        obj["task09_explode_vector"] = list(record["explode_vector"])
        obj["task09_explode_distance_mm"] = float(record["explode_distance_mm"])
        obj["task09_explode_order"] = int(record["explode_order"])
        obj["task09_motion_type"] = str(record["motion_type"])
        obj["task09_exploded_location"] = list(record["exploded_location"])
        obj["task09_source_geometry_unchanged"] = True

    output_path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output_path))
    reopened = _reopen_and_validate(output_path, state, state_records, initial_objects)
    return {
        "output": str(output_path),
        "state": state,
        "source_baseline": baseline,
        "before_validation": before_validation,
        "reopened": reopened,
        "animation_created": False,
        "source_geometry_modified": False,
    }


def _reopen_and_validate(
    path: Path,
    state: str,
    state_records: Mapping[str, Mapping[str, Any]],
    initial_objects: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    bpy.ops.wm.open_mainfile(filepath=str(path))
    objects = _source_objects()
    validation = validate_stage03_source_scene(
        [_object_facts(obj) for obj in objects.values()],
        vertices=sum(len(obj.data.vertices) for obj in objects.values()),
        polygons=sum(len(obj.data.polygons) for obj in objects.values()),
    )
    for part_id in _expected_part_ids():
        obj = objects[part_id]
        expected = (
            initial_objects[part_id]["location"]
            if state == "assembled"
            else state_records[part_id]["exploded_location"]
        )
        if not _close_vector(obj.location, expected):
            raise ValueError(f"{state} transform mismatch after reopening for {part_id}")
        if not _close_vector(obj.rotation_euler, initial_objects[part_id]["rotation_euler"]):
            raise ValueError(f"rotation transform mismatch after reopening for {part_id}")
        if not _close_vector(obj.scale, initial_objects[part_id]["scale"]):
            raise ValueError(f"scale transform mismatch after reopening for {part_id}")
        if obj.get("task09_state") != state:
            raise ValueError(f"missing Task 9A state metadata for {part_id}")
    return validation


def _source_objects() -> dict[str, Any]:
    objects: dict[str, Any] = {}
    for obj in bpy.data.objects:
        if obj.type != "MESH" or obj.get("source") != "original_stl":
            continue
        part_id = str(obj.get("part_id", ""))
        if part_id in objects:
            raise ValueError(f"duplicate source PART object: {part_id}")
        objects[part_id] = obj
    actual = sorted(objects, key=_part_number)
    if actual != _expected_part_ids():
        raise ValueError("Stage 02 source PART coverage is not PART_001..PART_082")
    return objects


def _object_facts(obj: Any) -> dict[str, Any]:
    return {
        "part_id": obj.get("part_id"),
        "source": obj.get("source"),
        "type": obj.type,
        "vertices": len(obj.data.vertices),
        "polygons": len(obj.data.polygons),
        "animation_data": obj.animation_data,
    }


def _require_objects(payload: Any) -> Mapping[str, Mapping[str, Any]]:
    if not isinstance(payload, Mapping) or not isinstance(payload.get("objects"), Mapping):
        raise ValueError("assembly_initial.json must contain an objects mapping")
    objects = payload["objects"]
    expected = set(_expected_part_ids())
    if set(objects) != expected:
        raise ValueError("assembly_initial.json does not cover PART_001..PART_082")
    return objects


def _require_state_records(payload: Any) -> Mapping[str, Mapping[str, Any]]:
    if not isinstance(payload, Mapping) or payload.get("state") != "EXPLODED":
        raise ValueError("exploded_state.json must have state EXPLODED")
    parts = payload.get("parts")
    if not isinstance(parts, Mapping) or set(parts) != set(_expected_part_ids()):
        raise ValueError("exploded_state.json does not cover PART_001..PART_082")
    records: dict[str, Mapping[str, Any]] = {}
    for part_id in _expected_part_ids():
        record = parts[part_id]
        if not isinstance(record, Mapping):
            raise ValueError(f"exploded_state record is not an object: {part_id}")
        if not isinstance(record.get("exploded_location"), Sequence):
            raise ValueError(f"exploded_state has no exploded_location: {part_id}")
        records[part_id] = record
    return records


def _validate_assembled_transforms(
    objects: Mapping[str, Any], initial: Mapping[str, Mapping[str, Any]]
) -> None:
    for part_id in _expected_part_ids():
        expected = initial[part_id]
        obj = objects[part_id]
        if not _close_vector(obj.location, expected["location"]):
            raise ValueError(f"Stage 02 transform differs from assembly_initial for {part_id}")
        if not _close_vector(obj.rotation_euler, expected["rotation_euler"]):
            raise ValueError(f"Stage 02 rotation differs from assembly_initial for {part_id}")
        if not _close_vector(obj.scale, expected["scale"]):
            raise ValueError(f"Stage 02 scale differs from assembly_initial for {part_id}")


def _set_vector(target: Any, values: Sequence[Any]) -> None:
    if len(values) != 3:
        raise ValueError("transform vector must contain three values")
    for index, value in enumerate(values):
        target[index] = float(value)


def _close_vector(actual: Sequence[Any], expected: Sequence[Any], tolerance: float = 1e-5) -> bool:
    if len(actual) != len(expected):
        return False
    return all(abs(float(left) - float(right)) <= tolerance for left, right in zip(actual, expected))


def _expected_part_ids() -> list[str]:
    return [f"PART_{index:03d}" for index in range(1, SOURCE_PART_COUNT + 1)]


def _part_number(part_id: str) -> int:
    try:
        return int(str(part_id).split("_")[-1])
    except ValueError:
        return 10**9


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--state", choices=VALID_STATES, default="exploded")
    args = parser.parse_args(argv)
    result = build_stage03_scene(args.project_root, args.state)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else None))
