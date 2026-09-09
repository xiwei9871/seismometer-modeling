"""Build the derived static hierarchical presentation scene for v3."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.presentation_explosion_v3 import EXPECTED_PART_IDS
from scripts.task08_data import load_json
from scripts.task09_data import TASK09_BASELINE, validate_task09_baseline

try:  # Blender is optional for pure contract tests.
    import bpy  # type: ignore
except ImportError:  # pragma: no cover
    bpy = None  # type: ignore


SOURCE_COLLECTION = "PRESENTATION_V3"
OUTPUT_BLEND = "output/stage03_presentation_exploded_v3.blend"


def validate_presentation_scene_facts(
    facts: Sequence[Mapping[str, Any]],
    *,
    vertices: int,
    polygons: int,
) -> dict[str, Any]:
    """Require the immutable source geometry and zero animation data."""
    source = [
        fact
        for fact in facts
        if fact.get("type", "MESH") == "MESH"
        and fact.get("source") == "original_stl"
    ]
    if len(source) != TASK09_BASELINE["source_parts"]:
        raise ValueError(
            "source PART count changed: "
            f"expected {TASK09_BASELINE['source_parts']}, got {len(source)}"
        )
    actual_ids = sorted(str(fact.get("part_id")) for fact in source)
    if actual_ids != list(EXPECTED_PART_IDS):
        raise ValueError("source PART coverage is not PART_001..PART_082")
    if int(vertices) != TASK09_BASELINE["indexed_vertices"] or int(polygons) != TASK09_BASELINE["faces"]:
        raise ValueError(
            "frozen geometry totals changed: "
            f"expected {TASK09_BASELINE['indexed_vertices']}/{TASK09_BASELINE['faces']}, "
            f"got {vertices}/{polygons}"
        )
    animated = [
        str(fact.get("part_id"))
        for fact in source
        if fact.get("animation_data") is not None
    ]
    if animated:
        raise ValueError(f"animation data exists on source PARTs: {animated}")
    return {
        "source_part_count": len(source),
        "vertices": int(vertices),
        "polygons": int(polygons),
        "animation_data_count": 0,
    }


def build_presentation_scene(project_root: Path) -> dict[str, Any]:
    """Apply the v3 static layout to a derived copy of Stage 02."""
    if bpy is None:
        raise RuntimeError("Blender bpy is required to build the v3 presentation scene")
    root = Path(project_root).expanduser().resolve()
    baseline = validate_task09_baseline(root)
    layout = load_json(root / "data/presentation_explosion_v3.json")
    if not isinstance(layout, Mapping) or layout.get("layout_version") != "v3":
        raise ValueError("presentation_explosion_v3.json must contain layout_version v3")
    parts = layout.get("parts")
    if not isinstance(parts, Mapping) or set(parts) != set(EXPECTED_PART_IDS):
        raise ValueError("v3 layout must contain exactly PART_001..PART_082")

    bpy.ops.wm.open_mainfile(filepath=str(root / "output/stage02_semantic.blend"))
    objects = _source_objects()
    facts = [_object_facts(obj) for obj in objects.values()]
    validation = validate_presentation_scene_facts(
        facts,
        vertices=sum(len(obj.data.vertices) for obj in objects.values()),
        polygons=sum(len(obj.data.polygons) for obj in objects.values()),
    )

    root_collection = _collection(SOURCE_COLLECTION, bpy.context.scene.collection)
    assembly_collections: dict[str, Any] = {}
    assemblies = layout.get("assemblies")
    if not isinstance(assemblies, Mapping):
        raise ValueError("v3 layout must contain assemblies")
    for assembly_id in sorted(assemblies):
        assembly_collections[assembly_id] = _collection(
            str(assembly_id), root_collection
        )
    hidden_count = 0
    visible_count = 0
    for part_id in EXPECTED_PART_IDS:
        obj = objects[part_id]
        record = parts[part_id]
        if not isinstance(record, Mapping):
            raise ValueError(f"v3 part record is malformed: {part_id}")
        visibility = str(record.get("presentation_visibility"))
        presentation_location = _vector(record.get("presentation_location"), part_id)
        if visibility == "VISIBLE":
            obj.location = presentation_location
            obj.hide_viewport = False
            obj.hide_render = False
            visible_count += 1
        elif visibility == "HIDDEN":
            # Keep the source transform intact for hidden no-parent parts.
            obj.hide_viewport = True
            obj.hide_render = True
            hidden_count += 1
        else:
            raise ValueError(f"invalid v3 visibility for {part_id}: {visibility!r}")

        obj["v3_layout_version"] = "v3"
        obj["v3_presentation_visibility"] = visibility
        obj["v3_presentation_mode"] = str(record.get("presentation_mode"))
        obj["v3_presentation_zone"] = str(record.get("presentation_zone") or "")
        obj["v3_presentation_assembly"] = str(
            record.get("presentation_assembly") or ""
        )
        obj["v3_presentation_parent"] = str(
            record.get("presentation_parent") or ""
        )
        obj["v3_assembly_zone_offset_mm"] = _vector(
            record.get("assembly_zone_offset_mm"), part_id
        )
        obj["v3_local_offset_mm"] = _vector(record.get("local_offset_mm"), part_id)
        target_id = record.get("presentation_assembly")
        if target_id is not None:
            target = assembly_collections.get(str(target_id))
            if target is None:
                raise ValueError(f"unknown v3 assembly for {part_id}: {target_id!r}")
            if target.objects.get(obj.name) is None:
                target.objects.link(obj)

    if visible_count != 44 or hidden_count != 38:
        raise ValueError(
            f"unexpected v3 visibility counts: visible={visible_count}, hidden={hidden_count}"
        )
    output = root / OUTPUT_BLEND
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output))
    reopened = _reopen_and_validate(output)
    return {
        "output": str(output),
        "source_baseline": baseline,
        "validation": validation,
        "reopened": reopened,
        "visible_part_count": visible_count,
        "hidden_part_count": hidden_count,
        "animation_created": False,
        "source_geometry_modified": False,
    }


def _source_objects() -> dict[str, Any]:
    objects: dict[str, Any] = {}
    for obj in bpy.data.objects:
        if obj.type != "MESH" or obj.get("source") != "original_stl":
            continue
        part_id = str(obj.get("part_id") or "")
        if part_id in objects:
            raise ValueError(f"duplicate source object PART ID: {part_id}")
        objects[part_id] = obj
    if set(objects) != set(EXPECTED_PART_IDS):
        raise ValueError("Stage 02 source objects do not cover PART_001..PART_082")
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


def _reopen_and_validate(path: Path) -> dict[str, Any]:
    bpy.ops.wm.open_mainfile(filepath=str(path))
    objects = _source_objects()
    validation = validate_presentation_scene_facts(
        [_object_facts(obj) for obj in objects.values()],
        vertices=sum(len(obj.data.vertices) for obj in objects.values()),
        polygons=sum(len(obj.data.polygons) for obj in objects.values()),
    )
    if any(obj.animation_data is not None for obj in objects.values()):
        raise ValueError("animation data exists after reopening v3 scene")
    if any(obj.animation_data is not None for obj in bpy.data.objects):
        raise ValueError("animation data exists on a v3 scene object")
    return validation


def _collection(name: str, parent: Any) -> Any:
    collection = bpy.data.collections.get(name)
    if collection is None:
        collection = bpy.data.collections.new(name)
    if collection.name not in {child.name for child in parent.children}:
        parent.children.link(collection)
    return collection


def _vector(value: Any, part_id: str) -> list[float]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 3:
        raise ValueError(f"invalid v3 vector for {part_id}")
    result = [float(item) for item in value]
    if not all(value == value and abs(value) != float("inf") for value in result):
        raise ValueError(f"invalid finite v3 vector for {part_id}")
    return result


def _script_arguments() -> list[str]:
    arguments = list(sys.argv[1:])
    return arguments[arguments.index("--") + 1 :] if "--" in arguments else arguments


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args(argv if argv is not None else _script_arguments())
    result = build_presentation_scene(args.project_root)
    print(result)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

