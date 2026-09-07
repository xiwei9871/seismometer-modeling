"""Non-destructive geometry facts and deterministic part identifiers."""

from __future__ import annotations

import copy
import math
from collections import Counter
from collections.abc import Mapping, Sequence
from numbers import Real
from typing import Any

import numpy as np
import trimesh


def build_exact_indexed_mesh(raw_mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """Return a new mesh indexed by exact coordinate equality."""
    raw_vertices = np.asarray(raw_mesh.vertices)
    raw_faces = np.asarray(raw_mesh.faces)

    coordinate_indices: dict[tuple[Any, ...], int] = {}
    indexed_vertices: list[np.ndarray] = []
    old_to_new = np.empty(len(raw_vertices), dtype=np.int64)

    for old_index, vertex in enumerate(raw_vertices):
        coordinate = tuple(vertex.tolist())
        new_index = coordinate_indices.get(coordinate)
        if new_index is None:
            new_index = len(indexed_vertices)
            coordinate_indices[coordinate] = new_index
            indexed_vertices.append(np.array(vertex, copy=True))
        old_to_new[old_index] = new_index

    if indexed_vertices:
        vertices = np.asarray(indexed_vertices, dtype=raw_vertices.dtype)
    else:
        vertices = np.empty((0, 3), dtype=raw_vertices.dtype)

    faces = np.asarray(old_to_new[raw_faces], dtype=np.int64).copy()
    return trimesh.Trimesh(vertices=vertices, faces=faces, process=False)


def component_metrics(mesh: trimesh.Trimesh, source_component_index: int) -> dict:
    """Return JSON-safe geometry and topology facts without repairing ``mesh``."""
    metric_errors: dict[str, str] = {}

    def capture(name: str, getter: Any) -> Any:
        try:
            non_finite_values: list[str] = []
            value = _json_safe(getter(), non_finite_values)
            if non_finite_values:
                metric_errors[name] = "non-finite value converted to None"
            return value
        except Exception as exc:  # Trimesh properties can fail independently.
            metric_errors[name] = f"{type(exc).__name__}: {exc}"
            return None

    face_count = capture("face_count", lambda: len(mesh.faces))
    vertex_count = capture("vertex_count", lambda: len(mesh.vertices))
    min_bound = capture("min_bound", lambda: mesh.bounds[0])
    max_bound = capture("max_bound", lambda: mesh.bounds[1])
    bbox_dimensions = capture("bbox_dimensions", lambda: mesh.bounds[1] - mesh.bounds[0])
    bbox_volume = capture(
        "bbox_volume", lambda: float(np.prod(mesh.bounds[1] - mesh.bounds[0]))
    )
    bbox_diagonal = capture(
        "bbox_diagonal", lambda: float(np.linalg.norm(mesh.bounds[1] - mesh.bounds[0]))
    )
    centroid = capture("centroid", lambda: mesh.centroid)
    surface_area = capture("surface_area", lambda: float(mesh.area))
    watertight = capture("watertight", lambda: bool(mesh.is_watertight))
    winding_consistent = capture(
        "winding_consistent", lambda: bool(mesh.is_winding_consistent)
    )
    euler_number = capture("euler_number", lambda: int(mesh.euler_number))
    try:
        boundary_edge_count, non_manifold_edge_count = _edge_incidence_counts(mesh)
    except Exception as exc:
        edge_error = f"{type(exc).__name__}: {exc}"
        metric_errors["boundary_edge_count"] = edge_error
        metric_errors["non_manifold_edge_count"] = edge_error
        boundary_edge_count = None
        non_manifold_edge_count = None
    duplicate_face_count = capture(
        "duplicate_face_count", lambda: _count_duplicate_faces(mesh)
    )

    volume = None
    volume_valid = False
    if watertight is True and winding_consistent is True:
        candidate_volume = capture("volume", lambda: float(mesh.volume))
        if _finite_number(candidate_volume) is not None and candidate_volume > 0.0:
            volume = candidate_volume
            volume_valid = True

    return {
        "source_component_index": _json_safe(source_component_index),
        "face_count": face_count,
        "vertex_count": vertex_count,
        "bbox_dimensions": bbox_dimensions,
        "bbox_volume": bbox_volume,
        "bbox_diagonal": bbox_diagonal,
        "centroid": centroid,
        "min_bound": min_bound,
        "max_bound": max_bound,
        "surface_area": surface_area,
        "volume": volume,
        "volume_valid": volume_valid,
        "watertight": watertight,
        "euler_number": euler_number,
        "winding_consistent": winding_consistent,
        "boundary_edge_count": boundary_edge_count,
        "non_manifold_edge_count": non_manifold_edge_count,
        "duplicate_face_count": duplicate_face_count,
        "metric_errors": metric_errors,
    }


def assign_part_ids(records: list[dict]) -> list[dict]:
    """Return normalized record copies in deterministic PART ID order."""
    copied = [_normalize_empty_values(copy.deepcopy(record)) for record in records]

    def sort_key(record: dict) -> tuple[Any, ...]:
        centroid = record.get("centroid")
        valid_volume = (
            record.get("volume") if record.get("volume_valid") is True else None
        )
        return (
            _descending_number(record.get("bbox_volume")),
            _descending_number(valid_volume),
            _descending_number(record.get("face_count")),
            _ascending_number(_sequence_item(centroid, 0)),
            _ascending_number(_sequence_item(centroid, 1)),
            _ascending_number(_sequence_item(centroid, 2)),
            _ascending_number(record.get("vertex_count")),
            _ascending_number(record.get("source_component_index")),
        )

    assigned = sorted(copied, key=sort_key)
    for part_number, record in enumerate(assigned, start=1):
        record["part_id"] = f"PART_{part_number:03d}"
    return assigned


def sorted_bbox_dimensions(dimensions: Sequence[float]) -> list[float]:
    """Return dimensions in rotation-independent ascending order."""
    normalized = [_finite_number(value) for value in dimensions]
    return sorted(normalized, key=lambda value: (value is None, value or 0.0))


def bbox_dimensions_match(
    left: Sequence[float],
    right: Sequence[float],
    absolute_mm: float = 0.1,
    relative_ratio: float = 0.005,
) -> bool:
    """Compare rotation-independent dimensions with absolute/relative tolerance."""
    if len(left) != len(right):
        return False

    left_sorted = sorted_bbox_dimensions(left)
    right_sorted = sorted_bbox_dimensions(right)
    absolute = _finite_number(absolute_mm)
    relative = _finite_number(relative_ratio)
    if absolute is None or relative is None or absolute < 0.0 or relative < 0.0:
        return False

    for left_value, right_value in zip(left_sorted, right_sorted, strict=True):
        if left_value is None or right_value is None:
            return False
        tolerance = max(
            absolute,
            relative * max(abs(left_value), abs(right_value), 1.0),
        )
        if abs(left_value - right_value) > tolerance:
            return False
    return True


def relative_value_match(left: float, right: float, ratio: float = 0.01) -> bool:
    """Compare finite values using a symmetric relative tolerance."""
    left_value = _finite_number(left)
    right_value = _finite_number(right)
    relative = _finite_number(ratio)
    if (
        left_value is None
        or right_value is None
        or relative is None
        or relative < 0.0
    ):
        return False
    tolerance = relative * max(abs(left_value), abs(right_value))
    return abs(left_value - right_value) <= tolerance


def _edge_incidence_counts(mesh: trimesh.Trimesh) -> tuple[int, int]:
    faces = np.asarray(mesh.faces, dtype=np.int64)
    edges = np.concatenate(
        (faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]), axis=0
    )
    edges.sort(axis=1)
    _, counts = np.unique(edges, axis=0, return_counts=True)
    return int(np.count_nonzero(counts == 1)), int(np.count_nonzero(counts > 2))


def _count_duplicate_faces(mesh: trimesh.Trimesh) -> int:
    faces = Counter(
        tuple(sorted(int(vertex) for vertex in face))
        for face in np.asarray(mesh.faces, dtype=np.int64)
    )
    return sum(count - 1 for count in faces.values() if count > 1)


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


def _normalize_empty_values(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return [_normalize_empty_values(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return _normalize_empty_values(value.item())
    if isinstance(value, Mapping):
        return {key: _normalize_empty_values(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_empty_values(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_normalize_empty_values(item) for item in value)
    if isinstance(value, str) and value == "":
        return None
    if isinstance(value, Real) and not isinstance(value, bool):
        numeric = float(value)
        if not math.isfinite(numeric):
            return None
    return value


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    numeric = float(value)
    return numeric if math.isfinite(numeric) else None


def _descending_number(value: Any) -> tuple[int, float]:
    numeric = _finite_number(value)
    return (1, 0.0) if numeric is None else (0, -numeric)


def _ascending_number(value: Any) -> tuple[int, float]:
    numeric = _finite_number(value)
    return (1, 0.0) if numeric is None else (0, numeric)


def _sequence_item(value: Any, index: int) -> Any:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return value[index] if index < len(value) else None
    return None
