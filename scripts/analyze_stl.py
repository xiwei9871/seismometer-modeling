"""Read-only overall and connected-component analysis for an STL source."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections.abc import Mapping, Sequence
from numbers import Real
from pathlib import Path
from typing import Any

import numpy as np
import trimesh

if __package__:
    from .stage01_core import (
        assign_part_ids,
        build_exact_indexed_mesh,
        component_metrics,
    )
else:
    from stage01_core import (
        assign_part_ids,
        build_exact_indexed_mesh,
        component_metrics,
    )


ANALYSIS_TOPOLOGY_NOTE = (
    "STL loading may expose facet-expanded (unindexed) vertices; exact-coordinate "
    "indexing collapses equal coordinates only for in-memory analysis topology and "
    "does not modify the source file."
)


def analyze_source_file(source_file: Path) -> dict:
    """Load and analyze an STL without modifying the source file."""
    source_file = Path(source_file)
    file_size_bytes = source_file.stat().st_size
    file_sha256 = _sha256_file(source_file)
    loaded = trimesh.load_mesh(source_file, file_type="stl", process=False)
    raw_mesh = _loaded_to_mesh(loaded)

    report = analyze_source_mesh(
        raw_mesh,
        source_file=str(source_file),
        file_size_bytes=file_size_bytes,
    )
    report["file_sha256"] = file_sha256
    return report


def analyze_source_mesh(
    mesh: trimesh.Trimesh,
    source_file: str,
    file_size_bytes: int,
) -> dict:
    """Analyze a mesh using a separate exact-coordinate indexed copy."""
    try:
        raw_vertex_count = int(len(mesh.vertices))
        raw_face_count = int(len(mesh.faces))
    except Exception as exc:
        raise ValueError(f"source mesh topology is unavailable: {exc}") from exc
    if raw_face_count == 0:
        raise ValueError("source mesh contains no faces")

    indexed_mesh = build_exact_indexed_mesh(mesh)
    global_metric_errors: dict[str, str] = {}

    vertices = _capture_metric(
        "vertices", lambda: int(len(indexed_mesh.vertices)), global_metric_errors
    )
    faces = _capture_metric(
        "faces", lambda: int(len(indexed_mesh.faces)), global_metric_errors
    )
    bounds_min = _capture_metric(
        "bounds_min", lambda: indexed_mesh.bounds[0], global_metric_errors
    )
    bounds_max = _capture_metric(
        "bounds_max", lambda: indexed_mesh.bounds[1], global_metric_errors
    )
    bbox_dimensions = _capture_metric(
        "bbox_dimensions",
        lambda: indexed_mesh.bounds[1] - indexed_mesh.bounds[0],
        global_metric_errors,
    )
    centroid = _capture_metric(
        "centroid", lambda: indexed_mesh.centroid, global_metric_errors
    )
    surface_area = _capture_metric(
        "surface_area", lambda: float(indexed_mesh.area), global_metric_errors
    )
    is_watertight = _capture_metric(
        "is_watertight",
        lambda: bool(indexed_mesh.is_watertight),
        global_metric_errors,
    )
    winding_consistent = _capture_metric(
        "winding_consistent",
        lambda: bool(indexed_mesh.is_winding_consistent),
        global_metric_errors,
    )
    euler_number = _capture_metric(
        "euler_number", lambda: int(indexed_mesh.euler_number), global_metric_errors
    )

    volume = None
    volume_valid = False
    if is_watertight is True and winding_consistent is True:
        candidate_volume = _capture_metric(
            "volume", lambda: float(indexed_mesh.volume), global_metric_errors
        )
        if _finite_number(candidate_volume) is not None and candidate_volume > 0.0:
            volume = candidate_volume
            volume_valid = True

    split_error: str | None = None
    try:
        split_meshes = list(indexed_mesh.split(only_watertight=False))
    except Exception as exc:
        try:
            split_meshes = _fallback_split(indexed_mesh)
        except Exception as fallback_exc:
            split_error = (
                f"{type(exc).__name__}: {exc}; fallback "
                f"{type(fallback_exc).__name__}: {fallback_exc}"
            )
            split_meshes = []

    component_records: list[dict] = []
    for source_component_index, component in enumerate(split_meshes):
        try:
            component_records.append(
                component_metrics(component, source_component_index)
            )
        except Exception as exc:
            component_records.append(
                {
                    "source_component_index": source_component_index,
                    "metric_errors": {
                        "component_metrics": f"{type(exc).__name__}: {exc}"
                    },
                }
            )
    components = assign_part_ids(component_records)
    if split_error is None:
        connected_component_count = _capture_metric(
            "connected_component_count",
            lambda: len(split_meshes),
            global_metric_errors,
        )
    else:
        global_metric_errors["connected_component_count"] = split_error
        connected_component_count = None

    bounding_box = _dimension_mapping(bbox_dimensions)
    return {
        "source_file": str(source_file),
        "file_size_bytes": _json_safe(file_size_bytes),
        "file_sha256": None,
        "raw_vertex_count": _json_safe(raw_vertex_count),
        "vertices": vertices,
        "faces": faces,
        "bounding_box": bounding_box,
        "bbox_dimensions": bbox_dimensions,
        "bounds_min": bounds_min,
        "bounds_max": bounds_max,
        "centroid": centroid,
        "surface_area": surface_area,
        "volume": volume,
        "volume_valid": volume_valid,
        "is_watertight": is_watertight,
        "winding_consistent": winding_consistent,
        "euler_number": euler_number,
        "connected_component_count": connected_component_count,
        "unit_assumption": "mm",
        "unit_confidence": "assumed",
        "analysis_topology_note": ANALYSIS_TOPOLOGY_NOTE,
        "global_metric_errors": global_metric_errors,
        "components": components,
    }


def write_json(path: Path, payload: dict) -> None:
    """Write a UTF-8, indented, strict-JSON report with a final newline."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)
    path.write_text(serialized + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    """Run source analysis from ``--source`` to ``--output``."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        report = analyze_source_file(args.source)
        write_json(args.output, report)
    except Exception as exc:
        print(f"Error analyzing STL source: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote STL analysis report to {args.output}")
    return 0


def _loaded_to_mesh(loaded: Any) -> trimesh.Trimesh:
    if isinstance(loaded, trimesh.Scene):
        geometries = list(loaded.geometry.values())
        if not geometries:
            raise ValueError("loaded STL scene contains no geometry")
        if not all(isinstance(geometry, trimesh.Trimesh) for geometry in geometries):
            raise ValueError("loaded STL scene contains non-mesh geometry")
        try:
            return trimesh.util.concatenate(geometries)
        except Exception as exc:
            raise ValueError(f"could not concatenate STL scene geometry: {exc}") from exc
    if isinstance(loaded, trimesh.Trimesh):
        return loaded
    raise ValueError(f"loaded STL object is not a mesh or scene: {type(loaded).__name__}")


def _sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fallback_split(mesh: trimesh.Trimesh) -> list[trimesh.Trimesh]:
    """Split by shared edges when trimesh's optional graph engine is unavailable."""
    faces = np.asarray(mesh.faces, dtype=np.int64)
    edge_to_faces: dict[tuple[int, int], list[int]] = {}
    for face_index, face in enumerate(faces):
        face_edges = (
            (int(face[0]), int(face[1])),
            (int(face[1]), int(face[2])),
            (int(face[2]), int(face[0])),
        )
        for first, second in face_edges:
            edge = (first, second) if first <= second else (second, first)
            edge_to_faces.setdefault(edge, []).append(face_index)

    adjacent: list[set[int]] = [set() for _ in range(len(faces))]
    for edge_faces in edge_to_faces.values():
        for face_index in edge_faces:
            adjacent[face_index].update(edge_faces)

    components: list[trimesh.Trimesh] = []
    visited: set[int] = set()
    for first_face in range(len(faces)):
        if first_face in visited:
            continue
        pending = [first_face]
        visited.add(first_face)
        component_faces: list[int] = []
        while pending:
            face_index = pending.pop()
            component_faces.append(face_index)
            for neighbor in sorted(adjacent[face_index]):
                if neighbor not in visited:
                    visited.add(neighbor)
                    pending.append(neighbor)
        component_faces.sort()
        split_result = mesh.submesh(
            [np.asarray(component_faces, dtype=np.int64)],
            only_watertight=False,
            repair=False,
        )
        if not isinstance(split_result, list) or len(split_result) != 1:
            raise ValueError("trimesh fallback split returned an unexpected result")
        components.append(split_result[0])
    return components


def _capture_metric(name: str, getter: Any, errors: dict[str, str]) -> Any:
    try:
        non_finite_values: list[str] = []
        value = _json_safe(getter(), non_finite_values)
        if non_finite_values:
            errors[name] = "non-finite value converted to None"
        return value
    except Exception as exc:
        errors[name] = f"{type(exc).__name__}: {exc}"
        return None


def _dimension_mapping(dimensions: Any) -> dict[str, Any]:
    if isinstance(dimensions, list) and len(dimensions) == 3:
        return {axis: dimensions[index] for index, axis in enumerate(("x", "y", "z"))}
    return {"x": None, "y": None, "z": None}


def _json_safe(value: Any, non_finite_values: list[str] | None = None) -> Any:
    if isinstance(value, np.ndarray):
        return [_json_safe(item, non_finite_values) for item in value.tolist()]
    if isinstance(value, np.generic):
        return _json_safe(value.item(), non_finite_values)
    if isinstance(value, Mapping):
        return {
            key: _json_safe(item, non_finite_values)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_json_safe(item, non_finite_values) for item in value]
    if isinstance(value, Real) and not isinstance(value, bool):
        numeric = float(value)
        if not math.isfinite(numeric):
            if non_finite_values is not None:
                non_finite_values.append("non-finite numeric value")
            return None
    return value


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    numeric = float(value)
    return numeric if math.isfinite(numeric) else None


if __name__ == "__main__":
    raise SystemExit(main())
