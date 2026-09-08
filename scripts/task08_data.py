"""Shared immutable-baseline and strict data helpers for Task 8."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any


BASELINE: dict[str, Any] = {
    "source_sha256": "fd2a7b78540245fd098724206d5ddf169fd2f44c07638e9a6459cd92fea717d1",
    "source_parts": 82,
    "faces": 444296,
    "indexed_vertices": 221902,
    "components": 82,
}

CONFIDENCES = frozenset({"HIGH", "MEDIUM", "LOW", "UNKNOWN"})
PART_ID_PATTERN = re.compile(r"^PART_(\d{3})$")

STAGE01_INPUTS = (
    "data/stage01_run_result.json",
    "data/source_model_report.json",
    "data/parts_manifest.json",
    "data/parts_manifest.csv",
    "data/duplicate_groups.json",
    "data/suspicious_fragments.json",
    "data/mesh_quality_report.json",
    "data/assembly_initial.json",
    "output/stage01_split.blend",
)


def load_json(path: Path) -> Any:
    """Read JSON while rejecting NaN and Infinity constants."""
    source = Path(path)

    def reject_constant(value: str) -> None:
        raise ValueError(f"invalid JSON constant {value!r} in {source}")

    return json.loads(
        source.read_text(encoding="utf-8"),
        parse_constant=reject_constant,
    )


def write_json(path: Path, payload: Any) -> None:
    """Write deterministic UTF-8 JSON and reject non-standard float values."""
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def stable_part_ids(records: Iterable[Mapping[str, Any]]) -> list[str]:
    """Return numeric PART IDs in stable order, rejecting malformed IDs."""
    part_ids: list[str] = []
    for record in records:
        value = record.get("part_id")
        if not isinstance(value, str) or PART_ID_PATTERN.fullmatch(value) is None:
            raise ValueError(f"invalid part_id: {value!r}")
        part_ids.append(value)
    if len(part_ids) != len(set(part_ids)):
        raise ValueError("duplicate part_id values in manifest")
    return sorted(part_ids, key=lambda value: int(value[5:]))


def load_manifest(project_root: Path) -> list[dict[str, Any]]:
    """Load and validate the complete frozen Stage 01 PART manifest."""
    path = Path(project_root) / "data/parts_manifest.json"
    payload = load_json(path)
    if not isinstance(payload, list) or not all(
        isinstance(item, Mapping) for item in payload
    ):
        raise ValueError("parts_manifest.json must contain a list of objects")
    records = [dict(item) for item in payload]
    actual = stable_part_ids(records)
    expected = [f"PART_{index:03d}" for index in range(1, BASELINE["source_parts"] + 1)]
    if actual != expected:
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        raise ValueError(f"manifest PART coverage mismatch; missing={missing}, extra={extra}")
    return sorted(records, key=lambda record: int(record["part_id"][5:]))


def sorted_bbox(record: Mapping[str, Any]) -> list[float]:
    """Return finite bbox dimensions in rotation-invariant sorted order."""
    dimensions = record.get("bbox_dimensions")
    if dimensions is None:
        bbox = record.get("bbox")
        if not isinstance(bbox, Mapping):
            raise ValueError("record has no bbox dimensions")
        dimensions = [bbox.get(axis) for axis in ("x", "y", "z")]
    if not isinstance(dimensions, (list, tuple)) or len(dimensions) != 3:
        raise ValueError("bbox dimensions must contain exactly three values")
    values: list[float] = []
    for value in dimensions:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("bbox dimensions must be numeric")
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("bbox dimensions must be finite")
        values.append(number)
    return sorted(values)


def strict_confidence(value: str) -> str:
    """Validate one of the four allowed semantic confidence levels."""
    if value not in CONFIDENCES:
        raise ValueError(f"invalid confidence: {value!r}")
    return value


def validate_stage01_baseline(project_root: Path) -> dict[str, Any]:
    """Fail closed unless the project still matches the frozen Stage 01 run."""
    root = Path(project_root).expanduser().resolve()
    for relative in STAGE01_INPUTS:
        path = root / relative
        if not path.is_file():
            raise ValueError(f"immutable baseline input is missing: {relative}")

    run_result = load_json(root / "data/stage01_run_result.json")
    if not isinstance(run_result, Mapping):
        raise ValueError("stage01_run_result.json must contain an object")

    checks = {
        "status": "PASS",
        "source_sha256_before": BASELINE["source_sha256"],
        "source_sha256_after": BASELINE["source_sha256"],
        "component_count": BASELINE["components"],
        "manifest_count": BASELINE["source_parts"],
        "face_count": BASELINE["faces"],
        "indexed_vertex_count": BASELINE["indexed_vertices"],
    }
    for key, expected in checks.items():
        if run_result.get(key) != expected:
            raise ValueError(
                f"immutable baseline mismatch for {key}: "
                f"expected {expected!r}, got {run_result.get(key)!r}"
            )

    manifest = load_manifest(root)
    if len(manifest) != BASELINE["source_parts"]:
        raise ValueError("immutable baseline manifest count mismatch")
    return dict(BASELINE)
