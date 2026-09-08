"""Create the geometry-only Stage 01 Blender scene from an original STL.

The module deliberately keeps its manifest, matching, naming, colour, and
assembly-payload helpers independent of Blender.  Blender is imported only at
runtime so the contract tests can run on machines without bpy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import struct
import sys
from collections.abc import Mapping, Sequence
from numbers import Real
from pathlib import Path
from typing import Any

try:  # Blender is optional for the pure helper/test surface.
    import bpy  # type: ignore
except ImportError:  # pragma: no cover - exercised only outside Blender
    bpy = None  # type: ignore


COLLECTION_NAMES = (
    "MAJOR",
    "MEDIUM",
    "SMALL",
    "TINY",
    "SUSPECTED_FRAGMENT",
)
REQUIRED_PROPERTIES = (
    "part_id",
    "source_component_index",
    "bbox_x",
    "bbox_y",
    "bbox_z",
    "face_count",
    "vertex_count",
    "duplicate_group",
    "duplicate_confidence",
    "suspected_fragment",
    "source",
)
DIMENSION_ABSOLUTE_TOLERANCE = 0.1
DIMENSION_RELATIVE_TOLERANCE = 0.005
AREA_RELATIVE_TOLERANCE = 0.01
VOLUME_RELATIVE_TOLERANCE = 0.01
CENTROID_ABSOLUTE_TOLERANCE = 0.1
CENTROID_RELATIVE_TOLERANCE = 0.005


def part_object_name(part_id: Any) -> str:
    """Validate and return the stable Blender object name for a PART."""
    value = str(part_id or "")
    if not value.startswith("PART_") or not value[5:].isdigit():
        raise ValueError(f"invalid PART ID: {part_id!r}")
    return value


def stable_part_color(part_id: Any) -> tuple[float, float, float, float]:
    """Return a deterministic viewport-only RGBA colour derived from PART ID."""
    digest = hashlib.sha256(part_object_name(part_id).encode("utf-8")).digest()
    return (
        digest[0] / 255.0,
        digest[1] / 255.0,
        digest[2] / 255.0,
        1.0,
    )


def manifest_custom_properties(record: Mapping[str, Any]) -> dict[str, Any]:
    """Return the non-semantic custom properties required on each object."""
    return {
        "part_id": part_object_name(record.get("part_id")),
        "source_component_index": _json_scalar(record.get("source_component_index")),
        "bbox_x": _first(record, "bbox_x_mm", "bbox_x"),
        "bbox_y": _first(record, "bbox_y_mm", "bbox_y"),
        "bbox_z": _first(record, "bbox_z_mm", "bbox_z"),
        "face_count": _json_scalar(record.get("face_count")),
        "vertex_count": _json_scalar(record.get("vertex_count")),
        "duplicate_group": record.get("duplicate_group") or "",
        "duplicate_confidence": record.get("duplicate_confidence") or "",
        "suspected_fragment": bool(record.get("suspected_fragment") is True),
        "source": "original_stl",
    }


def build_assembly_initial_payload(
    records: Sequence[Mapping[str, Any]],
    *,
    source_file: str,
    source_sha256: str,
) -> dict[str, Any]:
    """Build an explicit identity-inference assembly payload from the manifest."""
    objects: dict[str, dict[str, Any]] = {}
    for record in sorted(records, key=lambda item: str(item.get("part_id", ""))):
        part_id = part_object_name(record.get("part_id"))
        location = _vector(record.get("centroid"), record, "centroid")
        objects[part_id] = {
            "location": location,
            "rotation_euler": [0.0, 0.0, 0.0],
            "scale": [1.0, 1.0, 1.0],
            "world_matrix": _identity_world_matrix(location),
            "bbox": {
                "x": _first(record, "bbox_x_mm", "bbox_x"),
                "y": _first(record, "bbox_y_mm", "bbox_y"),
                "z": _first(record, "bbox_z_mm", "bbox_z"),
            },
            "source_component_index": record.get("source_component_index"),
            "transform_source": "stl_identity_inference",
        }
    return {
        "source_file": str(source_file),
        "source_sha256": str(source_sha256),
        "part_count": len(objects),
        "objects": objects,
    }


def match_object_facts(
    object_facts: Sequence[Mapping[str, Any]],
    records: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Map imported objects to PART records using deterministic geometry facts.

    Face count, bbox dimensions, area, and centroid are hard compatibility
    facts.  Vertex count is intentionally a soft score because an STL importer
    may retain one vertex per facet corner.  Candidate ties are rejected,
    rather than resolved by importer iteration order.
    """
    prepared_records = []
    for record in records:
        part_id = part_object_name(record.get("part_id"))
        prepared_records.append((part_id, record))
    prepared_records.sort(key=lambda item: item[0])

    prepared_objects = []
    for index, facts in enumerate(object_facts):
        object_id = str(facts.get("object_id") or f"OBJECT_{index:06d}")
        prepared_objects.append((object_id, facts))
    prepared_objects.sort(key=lambda item: item[0])

    if len(prepared_objects) != len(prepared_records):
        raise ValueError(
            "component mapping count mismatch: "
            f"{len(prepared_objects)} imported objects vs {len(prepared_records)} manifest records"
        )

    candidates: dict[str, list[tuple[float, str, Mapping[str, Any]]]] = {}
    for object_id, facts in prepared_objects:
        ranked: list[tuple[float, str, Mapping[str, Any]]] = []
        for part_id, record in prepared_records:
            score = _match_score(facts, record)
            if score is not None:
                ranked.append((score, part_id, record))
        if not ranked:
            raise ValueError(f"no manifest match for imported object {object_id}")
        ranked.sort(key=lambda item: (item[0], item[1]))
        candidates[object_id] = ranked

    record_ids = [part_id for part_id, _record in prepared_records]
    object_ids = [object_id for object_id, _facts in prepared_objects]
    if len(set(record_ids)) != len(record_ids):
        raise ValueError("manifest contains duplicate PART IDs")
    if len(set(object_ids)) != len(object_ids):
        raise ValueError("imported objects contain duplicate object IDs")

    assignment, total_score = _minimum_cost_assignment(
        object_ids,
        record_ids,
        candidates,
    )
    if assignment is None:
        raise ValueError("no perfect manifest assignment exists for imported objects")

    if _assignment_has_equal_optimum(
        object_ids,
        record_ids,
        candidates,
        assignment,
        total_score,
    ):
        raise ValueError(
            "ambiguous manifest match: more than one equal-cost global assignment"
        )

    records_by_id = {part_id: record for part_id, record in prepared_records}
    return {
        object_id: dict(records_by_id[part_id])
        for object_id, part_id in assignment.items()
    }


def validate_write_paths(
    source: Path,
    manifest: Path,
    write_paths: Mapping[str, Path | None],
) -> None:
    """Reject every output that aliases an input or another output.

    The check covers paths that do not exist yet through canonical path
    equality, and existing paths through ``samefile`` so hard links and
    symlinked aliases cannot bypass source protection.  It performs no writes.
    """
    source_path = Path(source).expanduser().resolve()
    manifest_path = Path(manifest).expanduser().resolve()
    normalized = {
        str(label): Path(path).expanduser().resolve()
        for label, path in write_paths.items()
        if path is not None
    }
    for label, path in normalized.items():
        if _same_path_or_file(path, source_path):
            raise ValueError(f"{label} output aliases the source STL")
        if _same_path_or_file(path, manifest_path):
            raise ValueError(f"{label} output aliases the manifest")

    items = sorted(normalized.items(), key=lambda item: item[0])
    for index, (left_label, left_path) in enumerate(items):
        for right_label, right_path in items[index + 1 :]:
            if _same_path_or_file(left_path, right_path):
                raise ValueError(
                    "outputs alias each other: "
                    f"{left_label} and {right_label}"
                )


def _same_path_or_file(left: Path, right: Path) -> bool:
    """Compare canonical paths and existing filesystem identities safely."""
    left_path = Path(left).expanduser().resolve()
    right_path = Path(right).expanduser().resolve()
    if left_path == right_path:
        return True
    if not left_path.exists() or not right_path.exists():
        return False
    try:
        return os.path.samefile(left_path, right_path)
    except OSError:
        return False


def format_geometry_facts(facts: Mapping[str, Any]) -> str:
    """Format a compact, JSON-safe geometry fact line for logs/inspection."""
    fields = (
        "face_count",
        "vertex_count",
        "bbox_dimensions",
        "centroid",
        "surface_area",
        "volume",
        "volume_valid",
        "watertight",
    )
    return json.dumps(
        {field: _json_ready(facts.get(field)) for field in fields},
        ensure_ascii=False,
        sort_keys=True,
    )


def read_binary_stl_indexed(
    path: Path,
) -> tuple[list[tuple[float, float, float]], list[tuple[int, int, int]]]:
    """Read every binary STL facet and index only exactly equal coordinates.

    Duplicate triangles are intentionally retained.  This avoids Blender's
    built-in STL importer validation, which can remove source facets.
    """
    path = Path(path)
    file_size = path.stat().st_size
    with path.open("rb") as handle:
        header = handle.read(80)
        count_bytes = handle.read(4)
        if len(header) != 80 or len(count_bytes) != 4:
            raise ValueError("binary STL header is incomplete")
        triangle_count = struct.unpack("<I", count_bytes)[0]
        expected_size = 84 + triangle_count * 50
        if file_size != expected_size:
            raise ValueError("file size does not match binary STL facet count")

        vertices: list[tuple[float, float, float]] = []
        faces: list[tuple[int, int, int]] = []
        vertex_indices: dict[tuple[float, float, float], int] = {}
        for triangle_index in range(triangle_count):
            facet = handle.read(50)
            if len(facet) != 50:
                raise ValueError(
                    f"binary STL facet {triangle_index} is incomplete"
                )
            values = struct.unpack("<12fH", facet)
            face: list[int] = []
            for start in (3, 6, 9):
                coordinate = (
                    float(values[start]),
                    float(values[start + 1]),
                    float(values[start + 2]),
                )
                index = vertex_indices.get(coordinate)
                if index is None:
                    index = len(vertices)
                    vertex_indices[coordinate] = index
                    vertices.append(coordinate)
                face.append(index)
            faces.append((face[0], face[1], face[2]))
        if handle.read(1):
            raise ValueError("binary STL has unexpected trailing bytes")
    return vertices, faces


def main(argv: Sequence[str] | None = None) -> int:
    """Run the Blender import/split operation and save a verified scene."""
    parser = _build_parser()
    args = parser.parse_args(_script_arguments(argv))
    if bpy is None:
        print("Error: Blender bpy is required for scene generation.", file=sys.stderr)
        return 2

    try:
        source = args.source.expanduser().resolve()
        manifest_path = args.manifest.expanduser().resolve()
        output = args.output.expanduser().resolve()
        assembly_output = args.assembly_output.expanduser().resolve()
        report = args.report.expanduser().resolve() if args.report else None
        inspection = args.inspection.expanduser().resolve() if args.inspection else None
        log = args.log.expanduser().resolve() if args.log else None
        validate_write_paths(
            source,
            manifest_path,
            {
                "output": output,
                "assembly-output": assembly_output,
                "report": report,
                "inspection": inspection,
                "log": log,
            },
        )
    except Exception as exc:
        print(f"Error validating Blender output paths: {exc}", file=sys.stderr)
        return 1

    try:
        records = _load_manifest(manifest_path)
        source_sha256 = _sha256_file(source)
        _clear_scene()
        imported = _import_stl(source)
        split_objects = _separate_loose_parts(imported)
        facts = [_object_geometry_facts(obj) for obj in split_objects]
        mapping = match_object_facts(facts, records)
        _configure_scene(split_objects, mapping)
        payload = build_assembly_initial_payload(
            records,
            source_file=str(source),
            source_sha256=source_sha256,
        )
        _update_assembly_with_blender_objects(payload, split_objects, mapping)
        _write_json(assembly_output, payload)
        if report:
            _write_json(
                report,
                {
                    "source_file": str(source),
                    "source_sha256": source_sha256,
                    "part_count": len(split_objects),
                    "parts": sorted(mapping),
                    "geometry_facts": [format_geometry_facts(item) for item in facts],
                },
            )
        if inspection:
            _write_text(inspection, _inspection_summary(split_objects, mapping))
        if log:
            _append_log(log, f"BLENDER_STAGE_OK parts={len(split_objects)}")
        output.parent.mkdir(parents=True, exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=str(output))
    except Exception as exc:
        if log:
            _append_log(log, f"BLENDER_STAGE_ERROR {type(exc).__name__}: {exc}")
        print(f"Error creating Stage 01 Blender scene: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote Blender Stage 01 scene to {args.output}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--assembly-output", type=Path, required=True)
    parser.add_argument("--log", type=Path)
    parser.add_argument("--inspection", type=Path)
    parser.add_argument("--report", type=Path)
    return parser


def _script_arguments(argv: Sequence[str] | None) -> list[str]:
    if argv is not None:
        return list(argv)
    arguments = list(sys.argv[1:])
    if "--" in arguments:
        arguments = arguments[arguments.index("--") + 1 :]
    return arguments


def _load_manifest(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("manifest JSON must contain a list")
    records = [dict(item) for item in payload if isinstance(item, Mapping)]
    if len(records) != len(payload):
        raise ValueError("manifest JSON contains a non-object record")
    return records


def _clear_scene() -> None:
    _require_bpy()
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


def _import_stl(source: Path) -> list[Any]:
    _require_bpy()
    if _is_binary_stl(source):
        vertices, faces = read_binary_stl_indexed(source)
        mesh = bpy.data.meshes.new(source.stem)
        mesh.from_pydata(vertices, [], faces)
        mesh.update(calc_edges=True)
        obj = bpy.data.objects.new(source.stem, mesh)
        bpy.context.scene.collection.objects.link(obj)
        return [obj]

    before = {obj.as_pointer() for obj in bpy.data.objects}
    if hasattr(bpy.ops.wm, "stl_import"):
        try:
            result = bpy.ops.wm.stl_import(
                filepath=str(source),
                use_mesh_validate=False,
            )
        except TypeError:
            # Older Blender builds may not expose the validation option.
            result = bpy.ops.wm.stl_import(filepath=str(source))
    elif hasattr(bpy.ops, "import_mesh") and hasattr(bpy.ops.import_mesh, "stl"):
        result = bpy.ops.import_mesh.stl(filepath=str(source))
    else:
        raise RuntimeError("this Blender build has no STL import operator")
    if "FINISHED" not in result:
        raise RuntimeError(f"STL import did not finish: {result}")
    imported = [
        obj
        for obj in bpy.data.objects
        if obj.as_pointer() not in before and obj.type == "MESH"
    ]
    if not imported:
        raise RuntimeError("STL import created no mesh object")
    return sorted(imported, key=lambda obj: obj.name)


def _is_binary_stl(path: Path) -> bool:
    try:
        size = Path(path).stat().st_size
        with Path(path).open("rb") as handle:
            header = handle.read(84)
        if len(header) != 84:
            return False
        triangle_count = struct.unpack("<I", header[80:84])[0]
        return size == 84 + triangle_count * 50
    except OSError:
        return False


def _separate_loose_parts(objects: Sequence[Any]) -> list[Any]:
    _require_bpy()
    _ensure_object_mode()
    for obj in bpy.context.view_layer.objects:
        obj.select_set(False)
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.separate(type='LOOSE')
    bpy.ops.object.mode_set(mode="OBJECT")
    result = [obj for obj in bpy.context.selected_objects if obj.type == "MESH"]
    if not result:
        raise RuntimeError("Loose Parts separation created no mesh objects")
    return sorted(result, key=lambda obj: obj.name)


def _object_geometry_facts(obj: Any) -> dict[str, Any]:
    """Compute world-space facts without changing the Blender mesh."""
    _require_bpy()
    vertices = [obj.matrix_world @ vertex.co for vertex in obj.data.vertices]
    if not vertices or not obj.data.polygons:
        raise ValueError(f"object {obj.name} has no mesh geometry")
    minimum = [min(vertex[index] for vertex in vertices) for index in range(3)]
    maximum = [max(vertex[index] for vertex in vertices) for index in range(3)]
    dimensions = [maximum[index] - minimum[index] for index in range(3)]
    triangles = []
    for polygon in obj.data.polygons:
        indices = list(polygon.vertices)
        if len(indices) < 3:
            continue
        first = vertices[indices[0]]
        for index in range(1, len(indices) - 1):
            triangles.append((first, vertices[indices[index]], vertices[indices[index + 1]]))
    area_total = 0.0
    centroid_total = [0.0, 0.0, 0.0]
    signed_volume = 0.0
    for first, second, third in triangles:
        cross = (second - first).cross(third - first)
        area = 0.5 * cross.length
        area_total += area
        center = (first + second + third) / 3.0
        for axis in range(3):
            centroid_total[axis] += float(center[axis]) * area
        signed_volume += float(first.dot(second.cross(third))) / 6.0
    if area_total > 0.0:
        centroid = [value / area_total for value in centroid_total]
    else:
        centroid = [sum(float(vertex[axis]) for vertex in vertices) / len(vertices) for axis in range(3)]
    edge_counts: dict[tuple[int, int], int] = {}
    for polygon in obj.data.polygons:
        indices = list(polygon.vertices)
        for index, first in enumerate(indices):
            second = indices[(index + 1) % len(indices)]
            edge = tuple(sorted((int(first), int(second))))
            edge_counts[edge] = edge_counts.get(edge, 0) + 1
    watertight = bool(edge_counts) and all(count == 2 for count in edge_counts.values())
    volume = abs(signed_volume) if watertight else None
    return {
        "object_id": obj.name,
        "centroid": centroid,
        "bbox_dimensions": dimensions,
        "face_count": int(len(obj.data.polygons)),
        "vertex_count": int(len(obj.data.vertices)),
        "surface_area": area_total,
        "volume": volume,
        "volume_valid": bool(volume is not None and math.isfinite(volume) and volume > 0.0),
        "watertight": watertight,
    }


def _configure_scene(objects: Sequence[Any], mapping: Mapping[str, Mapping[str, Any]]) -> None:
    _require_bpy()
    device = bpy.data.collections.get("DEVICE") or bpy.data.collections.new("DEVICE")
    if device.name not in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.link(device)
    collections = {name: _get_child_collection(device, name) for name in COLLECTION_NAMES}
    for obj in objects:
        record = mapping.get(obj.name)
        if record is None:
            raise ValueError(f"missing PART mapping for object {obj.name}")
        part_id = part_object_name(record.get("part_id"))
        obj.name = part_id
        for collection in list(obj.users_collection):
            collection.objects.unlink(obj)
        target_name = "SUSPECTED_FRAGMENT" if record.get("suspected_fragment") is True else str(record.get("size_class") or "TINY").upper()
        target = collections.get(target_name)
        if target is None:
            raise ValueError(f"unsupported size class for {part_id}: {target_name}")
        target.objects.link(obj)
        for key, value in manifest_custom_properties(record).items():
            obj[key] = value
        obj.color = stable_part_color(part_id)
        obj.show_transparent = False
        _set_origin_to_geometry_centroid_preserving_world(obj)


def _get_child_collection(parent: Any, name: str) -> Any:
    child = parent.children.get(name)
    if child is None:
        child = bpy.data.collections.new(name)
        parent.children.link(child)
    return child


def _set_origin_to_geometry_centroid_preserving_world(obj: Any) -> None:
    """Move local mesh coordinates and compensate matrix_world exactly."""
    _require_bpy()
    from mathutils import Matrix, Vector  # type: ignore

    old_world = obj.matrix_world.copy()
    local_vertices = [vertex.co.copy() for vertex in obj.data.vertices]
    if not local_vertices:
        return
    centroid = sum(local_vertices, Vector((0.0, 0.0, 0.0))) / len(local_vertices)
    obj.data.transform(Matrix.Translation(-centroid))
    obj.matrix_world = old_world @ Matrix.Translation(centroid)


def _update_assembly_with_blender_objects(
    payload: dict[str, Any],
    objects: Sequence[Any],
    mapping: Mapping[str, Mapping[str, Any]],
) -> None:
    for obj in objects:
        record = mapping[obj.name] if obj.name in mapping else None
        if record is None:
            # _configure_scene changed names; locate by stored PART property.
            part_id = str(obj.get("part_id", ""))
        else:
            part_id = str(record.get("part_id"))
        if part_id not in payload["objects"]:
            raise ValueError(f"assembly payload has no {part_id}")
        matrix = obj.matrix_world
        item = payload["objects"][part_id]
        item.update(
            {
                "location": [float(value) for value in obj.location],
                "rotation_euler": [float(value) for value in obj.rotation_euler],
                "scale": [float(value) for value in obj.scale],
                "world_matrix": [
                    [float(matrix[row][column]) for column in range(4)]
                    for row in range(4)
                ],
                "transform_source": "blender_scene",
            }
        )


def _inspection_summary(objects: Sequence[Any], mapping: Mapping[str, Mapping[str, Any]]) -> str:
    lines = []
    for obj in sorted(objects, key=lambda item: str(item.get("part_id", item.name))):
        lines.append(format_geometry_facts(_object_geometry_facts(obj)))
    return "\n".join(lines) + ("\n" if lines else "")


def _match_score(facts: Mapping[str, Any], record: Mapping[str, Any]) -> float | None:
    object_faces = _finite_number(facts.get("face_count"))
    record_faces = _finite_number(record.get("face_count"))
    if object_faces is None or record_faces is None or int(object_faces) != int(record_faces):
        return None
    object_dims = _dimensions(facts.get("bbox_dimensions"))
    record_dims = _dimensions(record.get("bbox_dimensions"))
    if record_dims is None:
        record_dims = _dimensions([_first(record, "bbox_x_mm", "bbox_x"), _first(record, "bbox_y_mm", "bbox_y"), _first(record, "bbox_z_mm", "bbox_z")])
    if object_dims is None or record_dims is None or not _dimensions_match(object_dims, record_dims):
        return None
    object_area = _nonnegative(facts.get("surface_area"))
    record_area = _nonnegative(_first(record, "surface_area", "surface_area_mm2"))
    if object_area is None or record_area is None or not _relative_match(object_area, record_area, AREA_RELATIVE_TOLERANCE):
        return None
    object_centroid = _dimensions(facts.get("centroid"))
    record_centroid = _dimensions(record.get("centroid"))
    if object_centroid is None or record_centroid is None:
        return None
    if not all(_scalar_match(left, right, CENTROID_ABSOLUTE_TOLERANCE, CENTROID_RELATIVE_TOLERANCE) for left, right in zip(object_centroid, record_centroid)):
        return None

    score = sum(abs(left - right) for left, right in zip(object_dims, record_dims))
    score += abs(object_area - record_area) / max(abs(object_area), abs(record_area), 1.0)
    score += sum(abs(left - right) for left, right in zip(object_centroid, record_centroid))
    object_vertex_count = _finite_number(facts.get("vertex_count"))
    record_vertex_count = _finite_number(record.get("vertex_count"))
    if object_vertex_count is not None and record_vertex_count is not None:
        score += 1e-6 * abs(object_vertex_count - record_vertex_count)
    object_volume = _nonnegative(facts.get("volume"))
    record_volume = _nonnegative(record.get("volume"))
    if object_volume is not None and record_volume is not None:
        score += 0.1 * abs(object_volume - record_volume) / max(object_volume, record_volume, 1.0)
    return score if math.isfinite(score) else None


def _minimum_cost_assignment(
    object_ids: Sequence[str],
    record_ids: Sequence[str],
    candidates: Mapping[str, Sequence[tuple[float, str, Mapping[str, Any]]]],
    *,
    forbidden_edge: tuple[str, str] | None = None,
) -> tuple[dict[str, str] | None, float]:
    """Solve the finite candidate graph with a deterministic Hungarian pass."""
    if len(object_ids) != len(record_ids):
        return None, math.inf
    if not object_ids:
        return {}, 0.0

    score_by_edge: dict[tuple[str, str], float] = {}
    finite_scores = []
    for object_id in object_ids:
        for score, part_id, _record in candidates.get(object_id, ()):
            if not math.isfinite(score):
                continue
            score_by_edge[(object_id, part_id)] = score
            finite_scores.append(score)
    forbidden_cost = max(1.0, max(finite_scores, default=0.0))
    forbidden_cost *= (len(object_ids) + 1) * 1_000_000.0
    if not math.isfinite(forbidden_cost):
        forbidden_cost = 1.0e300
    matrix = []
    for object_id in object_ids:
        row = []
        for part_id in record_ids:
            if forbidden_edge == (object_id, part_id):
                row.append(forbidden_cost)
            else:
                row.append(score_by_edge.get((object_id, part_id), forbidden_cost))
        matrix.append(row)

    columns = _hungarian_columns(matrix, forbidden_cost)
    if columns is None:
        return None, math.inf
    assignment: dict[str, str] = {}
    total = 0.0
    for row_index, column_index in enumerate(columns):
        if column_index is None or matrix[row_index][column_index] >= forbidden_cost:
            return None, math.inf
        assignment[object_ids[row_index]] = record_ids[column_index]
        total += matrix[row_index][column_index]
    return assignment, total


def _hungarian_columns(
    costs: Sequence[Sequence[float]], forbidden_cost: float
) -> list[int | None] | None:
    """Return a minimum-cost one-to-one column assignment for a square matrix."""
    size = len(costs)
    if size == 0:
        return []
    if any(len(row) != size for row in costs):
        raise ValueError("assignment cost matrix must be square")

    # This is the classic O(n^3) primal-dual Hungarian algorithm.  Missing
    # candidate edges use a large sentinel and are rejected after the solve.
    u = [0.0] * (size + 1)
    v = [0.0] * (size + 1)
    matching = [0] * (size + 1)
    way = [0] * (size + 1)
    for row_number in range(1, size + 1):
        matching[0] = row_number
        minimum = [math.inf] * (size + 1)
        used = [False] * (size + 1)
        column_zero = 0
        while True:
            used[column_zero] = True
            row_zero = matching[column_zero]
            delta = math.inf
            column_one = 0
            for column in range(1, size + 1):
                if used[column]:
                    continue
                current = costs[row_zero - 1][column - 1] - u[row_zero] - v[column]
                if current < minimum[column]:
                    minimum[column] = current
                    way[column] = column_zero
                if minimum[column] < delta:
                    delta = minimum[column]
                    column_one = column
            if column_one == 0 or delta >= forbidden_cost:
                return None
            for column in range(size + 1):
                if used[column]:
                    u[matching[column]] += delta
                    v[column] -= delta
                else:
                    minimum[column] -= delta
            column_zero = column_one
            if matching[column_zero] == 0:
                break
        while True:
            previous = way[column_zero]
            matching[column_zero] = matching[previous]
            column_zero = previous
            if column_zero == 0:
                break

    columns: list[int | None] = [None] * size
    for column in range(1, size + 1):
        if matching[column] != 0:
            columns[matching[column] - 1] = column - 1
    return columns


def _assignment_has_equal_optimum(
    object_ids: Sequence[str],
    record_ids: Sequence[str],
    candidates: Mapping[str, Sequence[tuple[float, str, Mapping[str, Any]]]],
    assignment: Mapping[str, str],
    total_score: float,
) -> bool:
    """Detect another perfect assignment with the same minimum score."""
    for object_id in object_ids:
        selected_part = assignment[object_id]
        alternative, alternative_score = _minimum_cost_assignment(
            object_ids,
            record_ids,
            candidates,
            forbidden_edge=(object_id, selected_part),
        )
        if alternative is None:
            continue
        if math.isclose(
            alternative_score,
            total_score,
            rel_tol=1e-9,
            abs_tol=1e-9,
        ):
            return True
    return False


def _dimensions(value: Any) -> list[float] | None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 3:
        return None
    values = [_nonnegative(item) for item in value]
    return values if all(item is not None for item in values) else None  # type: ignore[return-value]


def _dimensions_match(left: Sequence[float], right: Sequence[float]) -> bool:
    return all(
        _scalar_match(a, b, DIMENSION_ABSOLUTE_TOLERANCE, DIMENSION_RELATIVE_TOLERANCE)
        for a, b in zip(sorted(left), sorted(right))
    )


def _scalar_match(left: float, right: float, absolute: float, relative: float) -> bool:
    return abs(left - right) <= max(absolute, relative * max(abs(left), abs(right), 1.0))


def _relative_match(left: float, right: float, ratio: float) -> bool:
    return abs(left - right) <= ratio * max(abs(left), abs(right), 1.0)


def _vector(value: Any, record: Mapping[str, Any], name: str) -> list[float]:
    vector = value
    if not isinstance(vector, Sequence) or isinstance(vector, (str, bytes)):
        vector = [_first(record, f"{name}_x_mm", f"{name}_x"), _first(record, f"{name}_y_mm", f"{name}_y"), _first(record, f"{name}_z_mm", f"{name}_z")]
    values = [_finite_number(item) for item in list(vector)[:3]]
    values.extend([None] * (3 - len(values)))
    return [float(item) if item is not None else 0.0 for item in values[:3]]


def _identity_world_matrix(location: Sequence[float]) -> list[list[float]]:
    return [
        [1.0, 0.0, 0.0, float(location[0])],
        [0.0, 1.0, 0.0, float(location[1])],
        [0.0, 0.0, 1.0, float(location[2])],
        [0.0, 0.0, 0.0, 1.0],
    ]


def _first(record: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in record:
            return _json_scalar(record[key])
    return None


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _nonnegative(value: Any) -> float | None:
    number = _finite_number(value)
    return number if number is not None and number >= 0.0 else None


def _json_scalar(value: Any) -> Any:
    if isinstance(value, bool) or isinstance(value, (str, int)) or value is None:
        return value
    number = _finite_number(value)
    return number


def _json_ready(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [_json_ready(item) for item in value]
    if isinstance(value, Real) and not isinstance(value, bool):
        return _json_scalar(value)
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _reject_source_output_alias(source: Path, output: Path) -> None:
    if source == output:
        raise ValueError("output path is the source STL")
    if output.exists() and os.path.samefile(source, output):
        raise ValueError("output path aliases the source STL")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_json_ready(payload), ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _append_log(path: Path, message: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(message + "\n")


def _require_bpy() -> None:
    if bpy is None:
        raise RuntimeError("Blender bpy is required")


def _ensure_object_mode() -> None:
    if bpy.context.object is not None and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")


if __name__ == "__main__":
    raise SystemExit(main())
