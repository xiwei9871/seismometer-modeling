"""Detect tolerant duplicate geometry in a Stage 01 parts manifest.

This module compares only recorded geometry facts.  It never loads, repairs,
joins, or otherwise modifies mesh data, and every physical PART remains an
independent manifest record.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import os
import sys
from collections.abc import Mapping, Sequence
from numbers import Real
from pathlib import Path
from typing import Any

if __package__:
    from .stage01_core import bbox_dimensions_match, relative_value_match
else:  # pragma: no cover - supports running the file directly from scripts/
    from stage01_core import bbox_dimensions_match, relative_value_match


SIGNATURE_FIELDS = (
    "bbox_dimensions",
    "face_count",
    "vertex_count",
    "surface_area",
    "volume",
    "volume_valid",
    "watertight",
)


def geometry_signature(record: Mapping[str, Any]) -> dict[str, Any]:
    """Return a JSON-safe geometry signature for a manifest record.

    Dimensions are sorted so that a component's axis-aligned bbox has the same
    signature after a rotation.  Missing, non-finite, malformed, and negative
    measurements are represented by ``None`` instead of raising or comparing
    as if they were valid measurements.
    """
    if not isinstance(record, Mapping):
        record = {}
    dimensions = _bbox_dimensions(record)
    return {
        "bbox_dimensions": sorted(dimensions) if dimensions is not None else None,
        "face_count": _exact_count(record.get("face_count")),
        "vertex_count": _exact_count(record.get("vertex_count")),
        "surface_area": _nonnegative_number(
            _first_value(record, "surface_area", "surface_area_mm2")
        ),
        "volume": _nonnegative_number(record.get("volume")),
        "volume_valid": _strict_bool(record.get("volume_valid")),
        "watertight": _strict_bool(record.get("watertight")),
    }


def records_match(a: Mapping[str, Any], b: Mapping[str, Any]) -> str | None:
    """Return ``HIGH``/``MEDIUM`` when two records are duplicate candidates.

    Counts are exact gates.  Dimensions use the Stage 01 0.1 mm / 0.5%
    tolerance, area and valid volume use 1% relative tolerance.  A volume is
    deliberately ignored when both records explicitly mark it invalid, which
    yields ``MEDIUM`` rather than treating two missing values as evidence of
    equality.  Unknown validity or any missing required comparison fact makes
    the records non-matchable.
    """
    left = geometry_signature(a)
    right = geometry_signature(b)

    for field in ("face_count", "vertex_count"):
        if left[field] is None or right[field] is None:
            return None
        if left[field] != right[field]:
            return None

    dimensions_left = left["bbox_dimensions"]
    dimensions_right = right["bbox_dimensions"]
    if dimensions_left is None or dimensions_right is None:
        return None
    if not bbox_dimensions_match(dimensions_left, dimensions_right):
        return None

    if left["surface_area"] is None or right["surface_area"] is None:
        return None
    if not relative_value_match(left["surface_area"], right["surface_area"]):
        return None

    if left["watertight"] is None or right["watertight"] is None:
        return None
    if left["watertight"] != right["watertight"]:
        return None

    left_valid = left["volume_valid"]
    right_valid = right["volume_valid"]
    if left_valid is None or right_valid is None or left_valid != right_valid:
        return None

    if left_valid:
        if left["volume"] is None or right["volume"] is None:
            return None
        if not relative_value_match(left["volume"], right["volume"]):
            return None
        return "HIGH"

    return "MEDIUM"


def group_duplicate_parts(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Build deterministic duplicate groups without changing input records.

    Candidate clusters are complete-link clusters: a record joins a group only
    when it matches the group's existing members.  This prevents a tolerance
    chain from silently grouping two records that do not match one another.
    """
    prepared: list[tuple[str, Mapping[str, Any], str]] = []
    for record in records:
        if not isinstance(record, Mapping):
            continue
        part_id = _part_id(record)
        if part_id is None:
            continue
        prepared.append((part_id, record, _signature_sort_key(record)))
    prepared.sort(key=lambda item: (item[0], item[2]))

    groups: list[dict[str, Any]] = []
    remaining = list(prepared)
    while remaining:
        anchor = remaining.pop(0)
        members = [anchor]
        candidate_remaining: list[tuple[str, Mapping[str, Any], str]] = []
        for candidate in remaining:
            confidences = [records_match(member[1], candidate[1]) for member in members]
            if confidences and all(confidence is not None for confidence in confidences):
                members.append(candidate)
            else:
                candidate_remaining.append(candidate)
        remaining = candidate_remaining

        if len(members) < 2:
            continue
        parts = sorted(member[0] for member in members)
        confidence_values = [
            records_match(left[1], right[1])
            for index, left in enumerate(members)
            for right in members[index + 1 :]
        ]
        confidence = (
            "HIGH"
            if confidence_values and all(value == "HIGH" for value in confidence_values)
            else "MEDIUM"
        )
        groups.append(
            {
                "quantity": len(parts),
                "confidence": confidence,
                "parts": parts,
                "signature": geometry_signature(anchor[1]),
            }
        )

    groups.sort(key=lambda group: (group["parts"][0], tuple(group["parts"])))
    for index, group in enumerate(groups, start=1):
        group["group_id"] = f"DG_{index:03d}"
        group["parts"] = sorted(group["parts"])
        # Keep the public group field order stable for readable JSON output.
        group_keys = ("group_id", "quantity", "confidence", "parts", "signature")
        groups[index - 1] = {key: group[key] for key in group_keys}

    return {"group_count": len(groups), "groups": groups}


def apply_duplicate_groups(
    records: Sequence[Mapping[str, Any]], report: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Return deep-copied records with duplicate fields recomputed from report."""
    updated = [copy.deepcopy(dict(record)) for record in records]
    assignments = _group_assignments(report)
    for record in updated:
        record["duplicate_group"] = None
        record["duplicate_confidence"] = None
        part_id = _part_id(record)
        if part_id is None or part_id not in assignments:
            continue
        record["duplicate_group"], record["duplicate_confidence"] = assignments[part_id]
    return updated


def main(argv: Sequence[str] | None = None) -> int:
    """Run duplicate grouping from a JSON manifest."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest-json", type=Path, required=True)
    parser.add_argument("--output-manifest", type=Path)
    parser.add_argument("--output-groups", type=Path)
    args = parser.parse_args(argv)

    try:
        source_path = args.manifest_json
        payload = _load_json(source_path)
        if not isinstance(payload, list):
            raise ValueError("manifest JSON must contain a list of records")
        if args.output_manifest is not None:
            _reject_source_overwrite(source_path, args.output_manifest)
        if args.output_groups is not None:
            _reject_source_overwrite(source_path, args.output_groups)
        if (
            args.output_manifest is not None
            and args.output_groups is not None
            and _same_path_or_file(args.output_manifest, args.output_groups)
        ):
            raise ValueError("output manifest and output groups must be different files")

        report = group_duplicate_parts(payload)
        updated = apply_duplicate_groups(payload, report)
        if args.output_manifest is not None:
            _write_json(args.output_manifest, updated)
        if args.output_groups is not None:
            _write_json(args.output_groups, report)
    except Exception as exc:
        print(f"Error detecting duplicate parts: {exc}", file=sys.stderr)
        return 1

    if args.output_manifest is not None:
        print(f"Wrote duplicate-group manifest to {args.output_manifest}")
    if args.output_groups is not None:
        print(f"Wrote duplicate groups to {args.output_groups}")
    return 0


def _bbox_dimensions(record: Mapping[str, Any]) -> list[float] | None:
    values: Any = record.get("bbox_dimensions")
    if not _is_sequence(values):
        bbox = record.get("bbox")
        if isinstance(bbox, Mapping):
            values = [bbox.get(axis) for axis in ("x", "y", "z")]
        else:
            values = [
                _first_value(record, "bbox_x_mm", "bbox_x"),
                _first_value(record, "bbox_y_mm", "bbox_y"),
                _first_value(record, "bbox_z_mm", "bbox_z"),
            ]
    if not _is_sequence(values) or len(values) != 3:
        return None
    normalized = [_nonnegative_number(value) for value in values]
    if any(value is None for value in normalized):
        return None
    return [value for value in normalized if value is not None]


def _group_assignments(report: Mapping[str, Any]) -> dict[str, tuple[str, str]]:
    if not isinstance(report, Mapping):
        return {}
    groups = report.get("groups")
    normalized: list[tuple[str, Mapping[str, Any]]] = []
    if _is_sequence(groups):
        normalized = [
            (str(index), item)
            for index, item in enumerate(groups)
            if isinstance(item, Mapping)
        ]
    else:
        normalized = [
            (str(group_id), value)
            for group_id, value in report.items()
            if str(group_id).startswith("DG_") and isinstance(value, Mapping)
        ]
    normalized.sort(key=lambda item: item[0])

    assignments: dict[str, tuple[str, str]] = {}
    for fallback_id, group in normalized:
        group_id = str(group.get("group_id") or fallback_id)
        confidence = str(group.get("confidence") or "MEDIUM")
        members = group.get("parts", group.get("part_ids", []))
        if not _is_sequence(members):
            continue
        for member in sorted(str(value) for value in members):
            assignments.setdefault(member, (group_id, confidence))
    return assignments


def _load_json(path: Path) -> Any:
    text = Path(path).read_text(encoding="utf-8")
    return json.loads(text, parse_constant=_reject_json_constant)


def _write_json(path: Path, payload: Any) -> None:
    normalized = _json_ready(payload)
    serialized = json.dumps(
        normalized,
        ensure_ascii=False,
        indent=2,
        allow_nan=False,
    )
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(serialized + "\n", encoding="utf-8")


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant is not allowed: {value}")


def _reject_source_overwrite(source: Path, output: Path) -> None:
    if _same_path_or_file(source, output):
        raise ValueError("output path must not overwrite the source manifest")


def _same_path_or_file(left: Path, right: Path) -> bool:
    left = Path(left)
    right = Path(right)
    try:
        if left.exists() and right.exists():
            return os.path.samefile(left, right)
    except OSError:
        pass
    return left.resolve(strict=False) == right.resolve(strict=False)


def _signature_sort_key(record: Mapping[str, Any]) -> str:
    return json.dumps(
        geometry_signature(record),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _part_id(record: Mapping[str, Any]) -> str | None:
    value = record.get("part_id")
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _first_value(record: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in record:
            return record[key]
    return None


def _exact_count(value: Any) -> int | None:
    number = _finite_number(value)
    if number is None or not number.is_integer() or number < 0.0:
        return None
    return int(number)


def _nonnegative_number(value: Any) -> float | None:
    number = _finite_number(value)
    if number is None or number < 0.0:
        return None
    return number


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _strict_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _is_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _json_ready(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("non-finite value cannot be written as strict JSON")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
