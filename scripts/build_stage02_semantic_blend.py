"""Build a derived semantic Blender scene from the frozen Stage 01 blend."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.task08_data import load_json, load_manifest, strict_confidence

try:  # Blender is optional for the pure contract tests.
    import bpy  # type: ignore
except ImportError:  # pragma: no cover
    bpy = None  # type: ignore


SOURCE_PART_COUNT = 82
SOURCE_VERTICES = 221902
SOURCE_POLYGONS = 444296
SEMANTIC_ROOT = "SEMANTIC"


def semantic_object_name(part_id: str, semantic_name: str) -> str:
    """Return a stable readable name without discarding the permanent PART ID."""
    if not part_id.startswith("PART_"):
        raise ValueError(f"invalid PART ID: {part_id!r}")
    if not semantic_name or any(character.isspace() for character in semantic_name):
        raise ValueError(f"invalid semantic name: {semantic_name!r}")
    return f"{part_id}__{semantic_name}"


def validate_source_scene_facts(
    facts: Sequence[Mapping[str, Any]],
    *,
    vertices: int,
    polygons: int,
) -> dict[str, Any]:
    """Fail closed if the derived scene input no longer matches Stage 01."""
    source = [
        fact
        for fact in facts
        if fact.get("type") == "MESH" and fact.get("source") == "original_stl"
    ]
    if len(source) != SOURCE_PART_COUNT:
        raise ValueError(f"expected {SOURCE_PART_COUNT} source PART meshes, got {len(source)}")
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
    transforms_changed = sorted(
        str(fact.get("part_id"))
        for fact in source
        if fact.get("transforms_changed") is True
    )
    if animated:
        raise ValueError(f"source PARTs already contain animation data: {animated}")
    if transforms_changed:
        raise ValueError(f"source PART transforms differ from Stage 01: {transforms_changed}")
    return {
        "source_part_count": len(source),
        "vertices": int(vertices),
        "polygons": int(polygons),
        "animated_objects": animated,
        "transforms_changed": transforms_changed,
    }


def build_semantic_scene(project_root: Path) -> dict[str, Any]:
    """Read Stage 01 and save a separate semantic scene."""
    if bpy is None:
        raise RuntimeError("Blender bpy is required to build stage02_semantic.blend")
    root = Path(project_root).expanduser().resolve()
    blend = root / "output/stage01_split.blend"
    output = root / "output/stage02_semantic.blend"
    semantic_records = load_json(root / "data/semantic_parts.json")
    if not isinstance(semantic_records, list) or len(semantic_records) != SOURCE_PART_COUNT:
        raise ValueError("semantic_parts.json must contain exactly 82 records")
    by_part = {str(record["part_id"]): record for record in semantic_records}
    expected = [f"PART_{index:03d}" for index in range(1, SOURCE_PART_COUNT + 1)]
    if sorted(by_part) != expected:
        raise ValueError("semantic_parts.json does not cover PART_001..PART_082")

    bpy.ops.wm.open_mainfile(filepath=str(blend))
    initial = load_json(root / "data/assembly_initial.json")["objects"]
    objects = {
        str(obj.get("part_id")): obj
        for obj in bpy.data.objects
        if obj.type == "MESH" and obj.get("source") == "original_stl"
    }
    facts = [_object_facts(obj, initial) for obj in objects.values()]
    validation = validate_source_scene_facts(
        facts,
        vertices=sum(len(obj.data.vertices) for obj in objects.values()),
        polygons=sum(len(obj.data.polygons) for obj in objects.values()),
    )

    semantic_root = _collection(SEMANTIC_ROOT, bpy.context.scene.collection)
    category_collections: dict[str, Any] = {}
    for record in semantic_records:
        category = str(record.get("semantic_category") or "UNKNOWN")
        category_collections.setdefault(
            category,
            _collection(category, semantic_root),
        )

    for part_id in expected:
        obj = objects[part_id]
        record = by_part[part_id]
        semantic_name = str(record.get("semantic_name") or "UNKNOWN")
        confidence = strict_confidence(str(record.get("confidence", "UNKNOWN")))
        original_transform = _transform_tuple(obj)
        obj["semantic_name"] = semantic_name
        obj["semantic_category"] = str(record.get("semantic_category") or "UNKNOWN")
        obj["semantic_confidence"] = confidence
        obj["semantic_evidence"] = ", ".join(record.get("evidence", []))
        obj["semantic_reason"] = str(record.get("reason", ""))
        obj["assembly_group"] = _assembly_group(record)
        obj.name = semantic_object_name(part_id, semantic_name)
        if _transform_tuple(obj) != original_transform:
            raise ValueError(f"semantic metadata changed transform for {part_id}")
        target = category_collections[str(record.get("semantic_category") or "UNKNOWN")]
        if target.objects.get(obj.name) is None:
            target.objects.link(obj)

    for obj in bpy.data.objects:
        if obj.type == "MESH" and obj.get("source") == "original_stl":
            obj["stage02_source_geometry_unchanged"] = True
            obj["animation_data_present"] = obj.animation_data is not None

    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output))
    reopened = _reopen_and_validate(output)
    return {
        "output": str(output),
        "validation": validation,
        "reopened": reopened,
        "animation_created": False,
        "source_geometry_modified": False,
    }


def _reopen_and_validate(path: Path) -> dict[str, Any]:
    bpy.ops.wm.open_mainfile(filepath=str(path))
    objects = [
        obj
        for obj in bpy.data.objects
        if obj.type == "MESH" and obj.get("source") == "original_stl"
    ]
    facts = [
        {
            "part_id": obj.get("part_id"),
            "source": obj.get("source"),
            "type": obj.type,
            "vertices": len(obj.data.vertices),
            "polygons": len(obj.data.polygons),
            "animation_data": obj.animation_data,
            "transforms_changed": False,
        }
        for obj in objects
    ]
    return validate_source_scene_facts(
        facts,
        vertices=sum(fact["vertices"] for fact in facts),
        polygons=sum(fact["polygons"] for fact in facts),
    )


def _object_facts(obj: Any, initial: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    part_id = str(obj.get("part_id"))
    expected = initial.get(part_id, {})
    transforms_changed = not (
        _close_vector(obj.location, expected.get("location", []))
        and _close_vector(obj.rotation_euler, expected.get("rotation_euler", []))
        and _close_vector(obj.scale, expected.get("scale", []))
    )
    return {
        "part_id": part_id,
        "source": obj.get("source"),
        "type": obj.type,
        "vertices": len(obj.data.vertices),
        "polygons": len(obj.data.polygons),
        "animation_data": obj.animation_data,
        "transforms_changed": transforms_changed,
    }


def _close_vector(actual: Sequence[Any], expected: Sequence[Any], tolerance: float = 1e-6) -> bool:
    if len(actual) != len(expected):
        return False
    return all(abs(float(left) - float(right)) <= tolerance for left, right in zip(actual, expected))


def _transform_tuple(obj: Any) -> tuple[tuple[float, ...], tuple[float, ...], tuple[float, ...]]:
    return (
        tuple(float(value) for value in obj.location),
        tuple(float(value) for value in obj.rotation_euler),
        tuple(float(value) for value in obj.scale),
    )


def _collection(name: str, parent: Any) -> Any:
    collection = bpy.data.collections.get(name)
    if collection is None:
        collection = bpy.data.collections.new(name)
    if collection.name not in {child.name for child in parent.children}:
        parent.children.link(collection)
    return collection


def _assembly_group(record: Mapping[str, Any]) -> str:
    category = str(record.get("semantic_category") or "UNKNOWN")
    return {
        "ENCLOSURE": "ENCLOSURE",
        "HANDLE": "HANDLE_ASSEMBLY",
        "PCB_ASSEMBLY": "PCB_ASSEMBLY",
        "SENSOR_ASSEMBLY": "SENSOR_ASSEMBLY",
        "BATTERY_ASSEMBLY": "BATTERY_ASSEMBLY",
        "CONNECTOR": "TOP_INTERFACE",
        "LEVELING_ASSEMBLY": "LEVELING_ASSEMBLY",
        "SMALL_ACCESSORY": "FASTENERS_AND_SMALL_ACCESSORIES",
    }.get(category, "UNKNOWN")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv if argv is not None else _script_arguments())
    result = build_semantic_scene(args.project_root)
    print(f"Built {result['output']}")
    print(result["reopened"])
    return 0


def _script_arguments() -> list[str]:
    arguments = list(sys.argv[1:])
    return arguments[arguments.index("--") + 1:] if "--" in arguments else arguments


if __name__ == "__main__":
    raise SystemExit(main())
