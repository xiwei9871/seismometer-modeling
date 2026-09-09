"""Read-only assembled-state analysis for Task 9A-R1."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
from pathlib import Path
from typing import Any

from scripts.task08_data import load_json, load_manifest, strict_confidence
from scripts.task09_data import validate_task09_baseline


EXPECTED_PART_IDS = tuple(f"PART_{index:03d}" for index in range(1, 83))
EXPECTED_SOURCE_BASELINE = {
    "source_sha256": "fd2a7b78540245fd098724206d5ddf169fd2f44c07638e9a6459cd92fea717d1",
    "source_parts": 82,
    "faces": 444296,
    "indexed_vertices": 221902,
}


def analyze_assembled_state(project_root: Path) -> dict[str, Any]:
    """Return deterministic facts from the immutable assembled data files."""
    root = Path(project_root).expanduser().resolve()
    baseline = validate_task09_baseline(root)
    if baseline != EXPECTED_SOURCE_BASELINE:
        raise ValueError("Task 9A baseline does not match the frozen R1 baseline")
    manifest = _index_records(load_manifest(root), "parts_manifest.json")
    semantic = _index_records(
        _load_records(root / "data/semantic_parts.json", "semantic_parts.json"),
        "semantic_parts.json",
    )
    initial_payload = load_json(root / "data/assembly_initial.json")
    if not isinstance(initial_payload, Mapping):
        raise ValueError("assembly_initial.json must contain an object")
    initial = initial_payload.get("objects")
    if not isinstance(initial, Mapping):
        raise ValueError("assembly_initial.json must contain an objects mapping")

    _validate_coverage(manifest, semantic, initial)
    parts: dict[str, dict[str, Any]] = {}
    for part_id in EXPECTED_PART_IDS:
        initial_record = initial[part_id]
        manifest_record = manifest[part_id]
        semantic_record = semantic[part_id]
        manifest_counts = _strict_source_counts(manifest_record, f"{part_id} manifest")
        semantic_counts = _strict_source_counts(semantic_record, f"{part_id} semantic")
        initial_component_index = _strict_int(
            initial_record.get("source_component_index"),
            f"{part_id} initial source_component_index",
        )
        if semantic_counts != manifest_counts:
            raise ValueError(f"{part_id} manifest and semantic source counts differ")
        if initial_component_index != manifest_counts["source_component_index"]:
            raise ValueError(f"{part_id} source_component_index values differ")
        bbox = _bbox_dimensions(initial_record, manifest_record, part_id)
        parts[part_id] = {
            "part_id": part_id,
            "source_component_index": manifest_counts["source_component_index"],
            "assembled_location": _vector(
                initial_record.get("location"), f"{part_id} location"
            ),
            "assembled_rotation": _vector(
                initial_record.get("rotation_euler", [0.0, 0.0, 0.0]),
                f"{part_id} rotation_euler",
            ),
            "assembled_scale": _vector(
                initial_record.get("scale", [1.0, 1.0, 1.0]),
                f"{part_id} scale",
            ),
            "bbox_dimensions_mm": bbox,
            "face_count": manifest_counts["face_count"],
            "vertex_count": manifest_counts["vertex_count"],
            "semantic_name": _strict_string(
                semantic_record.get("semantic_name"), f"{part_id} semantic_name"
            ),
            "semantic_category": _strict_string(
                semantic_record.get("semantic_category"),
                f"{part_id} semantic_category",
            ),
            "semantic_confidence": strict_confidence(
                _strict_string(semantic_record.get("confidence"), f"{part_id} confidence")
            ),
            "semantic_evidence": _strict_string_list(
                semantic_record.get("evidence"), f"{part_id} evidence"
            ),
            "semantic_reason": _strict_string(
                semantic_record.get("reason"), f"{part_id} reason"
            ),
            "size_class": _strict_string(
                manifest_record.get("size_class"), f"{part_id} size_class"
            ),
            "source": "original_stl",
        }

    return {
        "source_file": str(initial_payload.get("source_file") or ""),
        "source_sha256": baseline["source_sha256"],
        "source_baseline": {
            "source_parts": baseline["source_parts"],
            "faces": baseline["faces"],
            "indexed_vertices": baseline["indexed_vertices"],
        },
        "parts": parts,
    }


def _load_records(path: Path, label: str) -> list[dict[str, Any]]:
    payload = load_json(path)
    if not isinstance(payload, list) or not all(isinstance(item, Mapping) for item in payload):
        raise ValueError(f"{label} must contain a list of objects")
    return [dict(item) for item in payload]


def _index_records(records: Sequence[Mapping[str, Any]], label: str) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, Mapping):
            raise ValueError(f"{label} records must be objects")
        part_id = record.get("part_id")
        if part_id not in EXPECTED_PART_IDS or part_id in indexed:
            raise ValueError(f"invalid or duplicate PART in {label}: {part_id!r}")
        indexed[part_id] = dict(record)
    return indexed


def _validate_coverage(
    manifest: Mapping[str, Any],
    semantic: Mapping[str, Any],
    initial: Mapping[str, Any],
) -> None:
    for label, mapping in (("manifest", manifest), ("semantic", semantic), ("initial", initial)):
        if list(mapping) != list(EXPECTED_PART_IDS):
            raise ValueError(f"{label} PART coverage is not PART_001..PART_082")


def _bbox_dimensions(
    initial_record: Mapping[str, Any],
    manifest_record: Mapping[str, Any],
    part_id: str,
) -> list[float]:
    bbox = initial_record.get("bbox")
    if not isinstance(bbox, Mapping):
        raise ValueError(f"{part_id} assembly_initial bbox is missing")
    initial_values = _vector(
        [bbox.get(axis) for axis in ("x", "y", "z")],
        f"{part_id} assembly_initial bbox",
    )
    manifest_values = _vector(
        manifest_record.get("bbox_dimensions"),
        f"{part_id} manifest bbox_dimensions",
    )
    for axis, left, right in zip(("x", "y", "z"), initial_values, manifest_values):
        if abs(left - right) > 1e-4:
            raise ValueError(
                f"{part_id} bbox differs on {axis} between assembly_initial and manifest"
            )
    return initial_values


def _strict_source_counts(record: Mapping[str, Any], label: str) -> dict[str, int]:
    return {
        "face_count": _strict_int(record.get("face_count"), f"{label} face_count"),
        "vertex_count": _strict_int(record.get("vertex_count"), f"{label} vertex_count"),
        "source_component_index": _strict_int(
            record.get("source_component_index"),
            f"{label} source_component_index",
        ),
    }


def _vector(value: Any, label: str) -> list[float]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 3:
        raise ValueError(f"{label} must be a 3-value vector")
    if any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in value):
        raise ValueError(f"{label} must contain numeric values")
    result = [float(item) for item in value]
    if not all(math.isfinite(item) for item in result):
        raise ValueError(f"{label} must contain finite values")
    return result


def _strict_int(value: Any, label: str) -> int:
    if type(value) is not int:
        raise ValueError(f"{label} must be an integer")
    return value


def _strict_string(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    return value


def _strict_string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a list of strings")
    return list(value)
