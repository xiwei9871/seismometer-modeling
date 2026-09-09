"""Read-only assembled-state analysis for Task 9A-R1."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
from pathlib import Path
from typing import Any

from scripts.task08_data import load_json, load_manifest
from scripts.task09_data import validate_task09_baseline


EXPECTED_PART_IDS = tuple(f"PART_{index:03d}" for index in range(1, 83))


def analyze_assembled_state(project_root: Path) -> dict[str, Any]:
    """Return deterministic facts from the immutable assembled data files."""
    root = Path(project_root).expanduser().resolve()
    baseline = validate_task09_baseline(root)
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
        bbox = _bbox_dimensions(initial_record, manifest_record, part_id)
        parts[part_id] = {
            "part_id": part_id,
            "source_component_index": int(manifest_record["source_component_index"]),
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
            "face_count": int(manifest_record["face_count"]),
            "vertex_count": int(manifest_record["vertex_count"]),
            "semantic_name": str(semantic_record.get("semantic_name") or "UNKNOWN"),
            "semantic_category": str(
                semantic_record.get("semantic_category") or "UNKNOWN"
            ),
            "semantic_confidence": str(semantic_record.get("confidence") or "UNKNOWN"),
            "semantic_evidence": list(semantic_record.get("evidence") or []),
            "semantic_reason": str(semantic_record.get("reason") or ""),
            "size_class": str(manifest_record.get("size_class") or "UNKNOWN"),
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
        part_id = str(record.get("part_id") or "")
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
    if isinstance(bbox, Mapping):
        values = [bbox.get(axis) for axis in ("x", "y", "z")]
    else:
        values = manifest_record.get("bbox_dimensions")
    return _vector(values, f"{part_id} bbox_dimensions")


def _vector(value: Any, label: str) -> list[float]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 3:
        raise ValueError(f"{label} must be a 3-value vector")
    result = [float(item) for item in value]
    if not all(math.isfinite(item) for item in result):
        raise ValueError(f"{label} must contain finite values")
    return result
