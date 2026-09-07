"""Classify analyzed STL components and write Stage 01 reports.

This module consumes the read-only facts produced by ``analyze_stl.py``.  It
does not load, repair, simplify, or otherwise modify mesh geometry.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections.abc import Mapping, Sequence
from numbers import Real
from pathlib import Path
from typing import Any


FEATURE_WEIGHTS = {
    "bbox_diagonal": 0.30,
    "bbox_volume": 0.20,
    "surface_area": 0.25,
    "face_count": 0.25,
}
SIZE_THRESHOLDS = {"major": 0.75, "medium": 0.40, "small": 0.15}
ABSOLUTE_TINY_DIAGONAL_MM = 0.1

_MANIFEST_FIELDS = [
    "part_id",
    "source_component_index",
    "face_count",
    "vertex_count",
    "bbox_x_mm",
    "bbox_y_mm",
    "bbox_z_mm",
    "bbox_volume",
    "bbox_volume_mm3",
    "centroid_x_mm",
    "centroid_y_mm",
    "centroid_z_mm",
    "surface_area",
    "surface_area_mm2",
    "volume",
    "volume_mm3",
    "volume_valid",
    "watertight",
    "euler_number",
    "complexity_class",
    "size_class",
    "duplicate_group",
    "duplicate_confidence",
    "suspected_fragment",
    "notes",
]


def classify_complexity(
    face_count: int | float | None,
    median_faces: float | None,
    p90_faces: float | None,
) -> str:
    """Classify topology complexity using explicit face-count thresholds."""
    faces = _finite_number(face_count)
    median = _finite_number(median_faces)
    p90 = _finite_number(p90_faces)
    if faces is None or faces < 0.0:
        return "UNKNOWN"
    if faces <= 10.0:
        return "TRIVIAL"
    if median is not None and faces <= median:
        return "SIMPLE"
    if p90 is not None and faces <= p90:
        return "MODERATE"
    return "COMPLEX"


def detect_suspicious_fragment(
    record: Mapping[str, Any],
    median_faces: float | None,
    median_diagonal: float | None,
) -> dict[str, Any]:
    """Return a review flag for a possible fragment without changing ``record``."""
    faces = _finite_number(record.get("face_count"))
    diagonal = _record_diagonal(record)
    median_face_value = _finite_number(median_faces)
    median_diagonal_value = _finite_number(median_diagonal)

    reasons: list[str] = []
    if faces is not None and faces <= 10.0:
        reasons.append(f"face count <= 10 ({_display_number(faces)})")

    low_face_limit = None
    if median_face_value is not None and median_face_value >= 0.0:
        low_face_limit = max(10.0, median_face_value * 0.25)
    diagonal_limit = None
    if median_diagonal_value is not None and median_diagonal_value >= 0.0:
        diagonal_limit = max(
            ABSOLUTE_TINY_DIAGONAL_MM,
            median_diagonal_value * 0.25,
        )
    if (
        faces is not None
        and low_face_limit is not None
        and diagonal is not None
        and diagonal_limit is not None
        and faces <= low_face_limit
        and diagonal <= diagonal_limit
    ):
        reasons.append(
            "low face count and tiny bbox diagonal "
            f"({_display_number(faces)} <= {_display_number(low_face_limit)}, "
            f"{_display_number(diagonal)} <= {_display_number(diagonal_limit)})"
        )

    dimensions = _record_dimensions(record)
    centroid = _json_ready(record.get("centroid"))
    return {
        "part_id": record.get("part_id"),
        "reason": "; ".join(reasons),
        "face_count": _json_ready(record.get("face_count")),
        "bbox": {
            "x": dimensions[0],
            "y": dimensions[1],
            "z": dimensions[2],
        },
        "centroid": centroid,
        "suspected_fragment": bool(reasons),
    }


def classify_size(records: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    """Classify components using weighted log1p feature percentile ranks.

    Missing or invalid feature values are omitted and the remaining weights are
    renormalized per component.  Fragment flags have precedence over the size
    score and produce ``FRAGMENT``.
    """
    records_list = list(records)
    median_faces = _median(
        value
        for value in (_finite_number(item.get("face_count")) for item in records_list)
        if value is not None and value >= 0.0
    )
    median_diagonal = _median(
        value
        for value in (_record_diagonal(item) for item in records_list)
        if value is not None and value >= 0.0
    )

    feature_values: dict[str, list[float]] = {}
    for feature in FEATURE_WEIGHTS:
        values = [
            transformed
            for item in records_list
            for transformed in [_log1p_feature(item, feature)]
            if transformed is not None
        ]
        feature_values[feature] = values

    result: dict[str, str] = {}
    for item in records_list:
        part_id = str(item.get("part_id", ""))
        fragment = detect_suspicious_fragment(item, median_faces, median_diagonal)
        if fragment["suspected_fragment"]:
            result[part_id] = "FRAGMENT"
            continue

        weighted_sum = 0.0
        weight_sum = 0.0
        for feature, weight in FEATURE_WEIGHTS.items():
            value = _log1p_feature(item, feature)
            if value is None:
                continue
            rank = _percentile_rank(value, feature_values[feature])
            weighted_sum += weight * rank
            weight_sum += weight
        score = weighted_sum / weight_sum if weight_sum else 0.0
        result[part_id] = _size_class_from_score(score)
    return result


def build_part_records(source_report: Mapping[str, Any]) -> tuple[list[dict], dict]:
    """Build manifest-ready records and classification metadata."""
    source_components = source_report.get("components", [])
    if not isinstance(source_components, Sequence) or isinstance(
        source_components, (str, bytes)
    ):
        raise ValueError("source report components must be a list")
    components = [dict(item) for item in source_components]

    face_values = [
        value
        for value in (_finite_number(item.get("face_count")) for item in components)
        if value is not None and value >= 0.0
    ]
    diagonal_values = [
        value
        for value in (_record_diagonal(item) for item in components)
        if value is not None and value >= 0.0
    ]
    median_faces = _median(face_values)
    p90_faces = _percentile(face_values, 90.0)
    median_diagonal = _median(diagonal_values)
    sizes = classify_size(components)

    records: list[dict] = []
    for component in components:
        part_id = component.get("part_id")
        fragment = detect_suspicious_fragment(
            component,
            median_faces=median_faces,
            median_diagonal=median_diagonal,
        )
        dimensions = _record_dimensions(component)
        centroid = _record_centroid(component)
        metric_errors = component.get("metric_errors")
        if not isinstance(metric_errors, Mapping):
            metric_errors = {}
        notes = _component_notes(component, metric_errors)
        record = {
            "part_id": part_id,
            "source_component_index": component.get("source_component_index"),
            "face_count": component.get("face_count"),
            "vertex_count": component.get("vertex_count"),
            "bbox_dimensions": dimensions,
            "bbox_diagonal": _record_diagonal(component),
            "bbox": {"x": dimensions[0], "y": dimensions[1], "z": dimensions[2]},
            "bbox_x_mm": dimensions[0],
            "bbox_y_mm": dimensions[1],
            "bbox_z_mm": dimensions[2],
            "bbox_volume": component.get("bbox_volume"),
            "centroid": centroid,
            "centroid_x_mm": _sequence_item(centroid, 0),
            "centroid_y_mm": _sequence_item(centroid, 1),
            "centroid_z_mm": _sequence_item(centroid, 2),
            "surface_area": component.get("surface_area"),
            "volume": component.get("volume") if component.get("volume_valid") else None,
            "volume_valid": bool(component.get("volume_valid") is True),
            "watertight": component.get("watertight"),
            "euler_number": component.get("euler_number"),
            "winding_consistent": component.get("winding_consistent"),
            "boundary_edge_count": component.get("boundary_edge_count"),
            "non_manifold_edge_count": component.get("non_manifold_edge_count"),
            "duplicate_face_count": component.get("duplicate_face_count"),
            "complexity_class": classify_complexity(
                component.get("face_count"), median_faces, p90_faces
            ),
            "size_class": sizes.get(str(part_id), "TINY"),
            "duplicate_group": component.get("duplicate_group"),
            "duplicate_confidence": component.get("duplicate_confidence"),
            "suspected_fragment": fragment["suspected_fragment"],
            "notes": notes,
            "metric_errors": dict(metric_errors),
        }
        records.append(_json_ready(record))

    metadata = {
        "component_count": len(records),
        "feature_weights": dict(FEATURE_WEIGHTS),
        "size_thresholds": dict(SIZE_THRESHOLDS),
        "absolute_tiny_diagonal_mm": ABSOLUTE_TINY_DIAGONAL_MM,
        "median_faces": median_faces,
        "p90_faces": p90_faces,
        "median_diagonal": median_diagonal,
        "classification_note": (
            "Size score uses log1p feature values and empirical percentile ranks; "
            "missing features renormalize available weights."
        ),
    }
    return records, metadata


def build_mesh_quality_report(source_report: Mapping[str, Any]) -> dict:
    """Aggregate existing mesh diagnostics without performing any repair."""
    components = source_report.get("components", [])
    if not isinstance(components, Sequence) or isinstance(components, (str, bytes)):
        raise ValueError("source report components must be a list")

    watertight_count = 0
    non_watertight_count = 0
    unknown_watertight_count = 0
    boundary_total = 0
    non_manifold_total = 0
    duplicate_face_total = 0
    metric_errors: dict[str, dict] = {}
    diagnostics: list[dict] = []
    possible_broken: list[dict] = []

    for index, component in enumerate(components):
        item = dict(component)
        part_id = item.get("part_id", f"COMPONENT_{index:03d}")
        watertight = item.get("watertight")
        if watertight is True:
            watertight_count += 1
        elif watertight is False:
            non_watertight_count += 1
        else:
            unknown_watertight_count += 1

        boundary = _nonnegative_integer(item.get("boundary_edge_count"))
        non_manifold = _nonnegative_integer(item.get("non_manifold_edge_count"))
        duplicate_faces = _nonnegative_integer(item.get("duplicate_face_count"))
        boundary_total += boundary or 0
        non_manifold_total += non_manifold or 0
        duplicate_face_total += duplicate_faces or 0

        errors = item.get("metric_errors")
        errors = dict(errors) if isinstance(errors, Mapping) else {}
        if errors:
            metric_errors[str(part_id)] = errors

        diagnostic = {
            "part_id": part_id,
            "source_component_index": item.get("source_component_index", index),
            "watertight": watertight,
            "winding_consistent": item.get("winding_consistent"),
            "boundary_edge_count": item.get("boundary_edge_count"),
            "non_manifold_edge_count": item.get("non_manifold_edge_count"),
            "duplicate_face_count": item.get("duplicate_face_count"),
            "metric_errors": errors,
        }
        diagnostics.append(_json_ready(diagnostic))
        issue_reasons = _quality_issue_reasons(item, errors)
        if issue_reasons:
            possible_broken.append(
                {
                    "part_id": part_id,
                    "source_component_index": item.get("source_component_index", index),
                    "reasons": issue_reasons,
                }
            )

    global_errors = source_report.get("global_metric_errors", {})
    if not isinstance(global_errors, Mapping):
        global_errors = {}
    issues: list[str] = []
    if non_watertight_count:
        issues.append(f"{non_watertight_count} component(s) are non-watertight")
    if boundary_total:
        issues.append(f"{boundary_total} boundary edge(s) were observed")
    if non_manifold_total:
        issues.append(f"{non_manifold_total} non-manifold edge(s) were observed")
    if duplicate_face_total:
        issues.append(f"{duplicate_face_total} duplicate face(s) were observed")
    if global_errors or metric_errors:
        issues.append("one or more metric calculations reported errors")

    return {
        "source_file": source_report.get("source_file"),
        "component_count": len(components),
        "watertight_count": watertight_count,
        "non_watertight_count": non_watertight_count,
        "unknown_watertight_count": unknown_watertight_count,
        "boundary_edge_count": boundary_total,
        "non_manifold_edge_count": non_manifold_total,
        "duplicate_face_count": duplicate_face_total,
        "global_metric_errors": _json_ready(dict(global_errors)),
        "metric_errors": metric_errors,
        "components": diagnostics,
        "possible_broken_components": _json_ready(possible_broken),
        "issues": issues,
        "repair_performed": False,
        "repair_note": "Diagnostics only; no mesh repair or geometry modification was performed.",
    }


def manifest_fieldnames() -> list[str]:
    """Return the stable CSV column order."""
    return list(_MANIFEST_FIELDS)


def write_manifest_csv(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    """Write the flat manifest with empty cells for unavailable values."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=_MANIFEST_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            writer.writerow(_csv_row(record))


def write_manifest_json(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    """Write manifest records as strict UTF-8 JSON."""
    _write_json(path, [_json_ready(dict(record)) for record in records])


def write_suspicious_fragments(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    """Write only flagged fragment review records; never delete source records."""
    fragments = []
    for record in records:
        if record.get("suspected_fragment") is not True:
            continue
        dimensions = _record_dimensions(record)
        fragments.append(
            {
                "part_id": record.get("part_id"),
                "reason": record.get("notes") or "suspected fragment",
                "face_count": record.get("face_count"),
                "bbox": {"x": dimensions[0], "y": dimensions[1], "z": dimensions[2]},
                "centroid": _json_ready(record.get("centroid")),
            }
        )
    _write_json(path, fragments)


def write_mesh_quality_report(path: Path, report: Mapping[str, Any]) -> None:
    """Write the diagnostic-only mesh quality report."""
    _write_json(path, dict(report))


def render_stage01_report(
    source_report: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
    duplicate_report: Mapping[str, Any] | None,
    quality_report: Mapping[str, Any],
) -> str:
    """Render the human-readable Stage 01 summary, including review questions."""
    records_list = list(records)
    duplicate_groups = _duplicate_groups(duplicate_report)
    class_counts = _counts(records_list, "size_class")
    complexity_counts = _counts(records_list, "complexity_class")
    fragments = [item for item in records_list if item.get("suspected_fragment") is True]
    top_parts = sorted(
        records_list,
        key=lambda item: (
            -(_finite_number(item.get("bbox_volume")) or -math.inf),
            -(_finite_number(item.get("face_count")) or -math.inf),
            str(item.get("part_id", "")),
        ),
    )[:15]
    top_groups = sorted(
        duplicate_groups,
        key=lambda item: (
            -(_finite_number(item.get("quantity")) or 0.0),
            str(item.get("group_id", "")),
        ),
    )[:20]

    lines = [
        "# Stage 01 Report",
        "",
        "## Source",
        "",
        f"- File: `{source_report.get('source_file', '')}`",
        f"- File size: {source_report.get('file_size_bytes', 'unknown')} bytes",
        f"- Vertices: {source_report.get('vertices', source_report.get('raw_vertex_count', 'unknown'))}",
        f"- Faces: {source_report.get('faces', 'unknown')}",
        f"- Overall dimensions: {_format_value(source_report.get('bbox_dimensions', source_report.get('bounding_box', 'unknown')))} mm",
        f"- Unit assumption: {source_report.get('unit_assumption', 'mm')} ({source_report.get('unit_confidence', 'assumed')})",
        "",
        "## Component recovery",
        "",
        f"- Connected components: {len(records_list)}",
        f"- Size classes: {_format_counts(class_counts)}",
        f"- Complexity classes: {_format_counts(complexity_counts)}",
        f"- Suspected fragments (marked only): {len(fragments)}",
        "",
        "### Largest 15 PART",
        "",
    ]
    if top_parts:
        lines.append("| PART | Size class | Faces | BBox volume | Watertight |")
        lines.append("|---|---|---:|---:|---:|")
        for item in top_parts:
            lines.append(
                f"| {item.get('part_id', '')} | {item.get('size_class', '')} | "
                f"{_format_value(item.get('face_count'))} | {_format_value(item.get('bbox_volume'))} | "
                f"{_format_value(item.get('watertight'))} |"
            )
    else:
        lines.append("No component records were available.")

    lines.extend(["", "## Duplicate analysis", ""])
    group_count = duplicate_report.get("group_count", len(duplicate_groups)) if duplicate_report else 0
    lines.append(f"- Duplicate groups: {group_count}")
    if top_groups:
        lines.extend(["", "| Group | Quantity | Confidence | Parts |", "|---|---:|---|---|"])
        for group in top_groups:
            parts = group.get("parts", group.get("part_ids", []))
            if isinstance(parts, Sequence) and not isinstance(parts, (str, bytes)):
                part_text = ", ".join(str(part) for part in parts)
            else:
                part_text = str(parts)
            lines.append(
                f"| {group.get('group_id', '')} | {_format_value(group.get('quantity', len(parts) if isinstance(parts, Sequence) else ''))} | "
                f"{group.get('confidence', '')} | {part_text} |"
            )
    else:
        lines.append("No duplicate groups have been supplied yet; Task 5 may append them.")

    lines.extend([
        "",
        "## Mesh quality",
        "",
        f"- Watertight components: {quality_report.get('watertight_count', 0)}",
        f"- Non-watertight components: {quality_report.get('non_watertight_count', 0)}",
        f"- Boundary edges: {quality_report.get('boundary_edge_count', 0)}",
        f"- Non-manifold edges: {quality_report.get('non_manifold_edge_count', 0)}",
        f"- Duplicate faces: {quality_report.get('duplicate_face_count', 0)}",
        f"- Possible broken components: {len(quality_report.get('possible_broken_components', []))}",
        f"- Repair performed: {quality_report.get('repair_performed', False)}",
    ])
    issues = quality_report.get("issues", [])
    if issues:
        lines.append("- Issues: " + "; ".join(str(issue) for issue in issues))

    lines.extend([
        "",
        "## Important findings",
        "",
        "- This is a geometry-only recovery report; semantic part names are intentionally absent.",
        "- Suspected fragments remain in the manifest and are only flagged for review.",
        "- Identical geometry, when supplied by duplicate analysis, remains separate physical PART objects.",
        "- No repair, simplification, remesh, boolean, or geometry cleanup was performed.",
        "",
        "### 人工确认",
        "",
        "1. 人工确认整体单位和坐标方向是否与设备实测尺寸一致。",
        "2. 人工确认薄板或细长结构件是否被合理保留，而不是误判为碎片。",
        "3. 人工确认疑似碎片清单中的每个组件是否是真实装配件。",
        "4. 人工确认重复几何组中的成员是否确实是独立、可拆分的物理对象。",
        "5. 人工确认大型组件之间是否存在 STL 中已经焊接/连成整体、无法自动拆开的部分。",
    ])
    return "\n".join(lines) + "\n"


def write_stage01_report(path: Path, text: str) -> None:
    """Write the Markdown report as UTF-8."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    """Generate Task 4 outputs from a source model report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-report", type=Path, required=True)
    parser.add_argument("--manifest-json", type=Path)
    parser.add_argument("--manifest-csv", type=Path)
    parser.add_argument("--suspicious", type=Path)
    parser.add_argument("--quality", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--duplicate-groups", type=Path)
    args = parser.parse_args(argv)

    base = args.source_report.parent
    manifest_json = args.manifest_json or base / "parts_manifest.json"
    manifest_csv = args.manifest_csv or base / "parts_manifest.csv"
    suspicious = args.suspicious or base / "suspicious_fragments.json"
    quality_path = args.quality or base / "mesh_quality_report.json"
    report_path = args.report or base / "stage01_report.md"

    try:
        source = json.loads(args.source_report.read_text(encoding="utf-8"))
        if not isinstance(source, Mapping):
            raise ValueError("source report must contain a JSON object")
        duplicate_report = None
        if args.duplicate_groups is not None:
            duplicate_report = json.loads(
                args.duplicate_groups.read_text(encoding="utf-8")
            )
            if not isinstance(duplicate_report, Mapping):
                raise ValueError("duplicate groups report must contain a JSON object")
        records, _metadata = build_part_records(source)
        quality = build_mesh_quality_report(source)
        write_manifest_json(manifest_json, records)
        write_manifest_csv(manifest_csv, records)
        write_suspicious_fragments(suspicious, records)
        write_mesh_quality_report(quality_path, quality)
        write_stage01_report(
            report_path,
            render_stage01_report(source, records, duplicate_report, quality),
        )
    except Exception as exc:
        print(f"Error generating Stage 01 part reports: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote Stage 01 part reports to {base}")
    return 0


def _log1p_feature(record: Mapping[str, Any], feature: str) -> float | None:
    if feature == "bbox_diagonal":
        value = _record_diagonal(record)
    else:
        value = _finite_number(record.get(feature))
    if value is None or value < 0.0:
        return None
    return math.log1p(value)


def _percentile_rank(value: float, values: Sequence[float]) -> float:
    if not values:
        return 0.0
    less = sum(candidate < value for candidate in values)
    equal = sum(candidate == value for candidate in values)
    return (less + 0.5 * equal) / len(values)


def _percentile(values: Sequence[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * (percentile / 100.0)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _median(values: Sequence[float] | Any) -> float | None:
    values_list = list(values)
    return _percentile(values_list, 50.0)


def _size_class_from_score(score: float) -> str:
    if score >= SIZE_THRESHOLDS["major"]:
        return "MAJOR"
    if score >= SIZE_THRESHOLDS["medium"]:
        return "MEDIUM"
    if score >= SIZE_THRESHOLDS["small"]:
        return "SMALL"
    return "TINY"


def _record_dimensions(record: Mapping[str, Any]) -> list[float | None]:
    dimensions = record.get("bbox_dimensions")
    if not isinstance(dimensions, Sequence) or isinstance(dimensions, (str, bytes)):
        dimensions = [
            record.get("bbox_x_mm"),
            record.get("bbox_y_mm"),
            record.get("bbox_z_mm"),
        ]
    values = list(dimensions[:3])
    values.extend([None] * (3 - len(values)))
    return [_json_ready(value) for value in values[:3]]


def _record_diagonal(record: Mapping[str, Any]) -> float | None:
    direct = _finite_number(record.get("bbox_diagonal"))
    if direct is not None and direct >= 0.0:
        return direct
    dimensions = _record_dimensions(record)
    if any(value is None or value < 0.0 for value in dimensions):
        return None
    return math.sqrt(sum(value * value for value in dimensions if value is not None))


def _record_centroid(record: Mapping[str, Any]) -> list[Any]:
    centroid = record.get("centroid")
    if not isinstance(centroid, Sequence) or isinstance(centroid, (str, bytes)):
        centroid = [
            record.get("centroid_x_mm"),
            record.get("centroid_y_mm"),
            record.get("centroid_z_mm"),
        ]
    values = list(centroid[:3])
    values.extend([None] * (3 - len(values)))
    return [_json_ready(value) for value in values[:3]]


def _component_notes(component: Mapping[str, Any], errors: Mapping[str, Any]) -> str:
    notes: list[str] = []
    if errors:
        notes.append("metric errors: " + ", ".join(sorted(str(key) for key in errors)))
    if component.get("winding_consistent") is False:
        notes.append("winding is not consistent")
    return "; ".join(notes)


def _quality_issue_reasons(item: Mapping[str, Any], errors: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    if item.get("watertight") is False:
        reasons.append("non-watertight")
    if item.get("winding_consistent") is False:
        reasons.append("inconsistent winding")
    for field, label in (
        ("boundary_edge_count", "boundary edges"),
        ("non_manifold_edge_count", "non-manifold edges"),
        ("duplicate_face_count", "duplicate faces"),
    ):
        value = _nonnegative_integer(item.get(field))
        if value:
            reasons.append(f"{label}: {value}")
    if errors:
        reasons.append("metric errors: " + ", ".join(sorted(str(key) for key in errors)))
    return reasons


def _duplicate_groups(report: Mapping[str, Any] | None) -> list[dict]:
    if not report:
        return []
    groups = report.get("groups")
    if isinstance(groups, Sequence) and not isinstance(groups, (str, bytes)):
        normalized = [dict(group) for group in groups if isinstance(group, Mapping)]
    else:
        normalized = []
        for group_id, value in report.items():
            if not str(group_id).startswith("DG_") or not isinstance(value, Mapping):
                continue
            item = dict(value)
            item.setdefault("group_id", group_id)
            normalized.append(item)
    for item in normalized:
        item.setdefault("group_id", item.get("duplicate_group", ""))
        parts = item.get("parts", item.get("part_ids", []))
        if not isinstance(parts, Sequence) or isinstance(parts, (str, bytes)):
            parts = []
        item["parts"] = list(parts)
        item.setdefault("quantity", len(parts))
    return normalized


def _counts(records: Sequence[Mapping[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        value = str(record.get(field, "UNKNOWN"))
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _format_counts(counts: Mapping[str, int]) -> str:
    return ", ".join(f"{key}={value}" for key, value in counts.items()) or "none"


def _format_value(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, float):
        if not math.isfinite(value):
            return "null"
        return f"{value:.6g}"
    if isinstance(value, (list, tuple, dict)):
        return json.dumps(_json_ready(value), ensure_ascii=False, separators=(",", ":"))
    return str(value)


def _csv_row(record: Mapping[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for field in _MANIFEST_FIELDS:
        if field.endswith("_mm3"):
            source_field = "bbox_volume" if field == "bbox_volume_mm3" else "volume"
        elif field.endswith("_mm2"):
            source_field = "surface_area"
        else:
            source_field = field
        value = record.get(source_field)
        if isinstance(value, bool):
            row[field] = str(value).lower()
        elif value is None:
            row[field] = ""
        else:
            row[field] = _format_value(value)
    return row


def _write_json(path: Path, payload: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = _json_ready(payload)
    serialized = json.dumps(
        normalized,
        ensure_ascii=False,
        indent=2,
        allow_nan=False,
    )
    path.write_text(serialized + "\n", encoding="utf-8")


def _json_ready(value: Any) -> Any:
    """Convert numpy-like scalar containers while preserving NaN for strict dumps."""
    if hasattr(value, "tolist") and not isinstance(value, (str, bytes, bytearray)):
        return _json_ready(value.tolist())
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if isinstance(value, Real) and not isinstance(value, bool):
        numeric = float(value)
        return numeric if math.isfinite(numeric) else value
    return value


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    numeric = float(value)
    return numeric if math.isfinite(numeric) else None


def _nonnegative_integer(value: Any) -> int | None:
    numeric = _finite_number(value)
    if numeric is None or numeric < 0.0 or not numeric.is_integer():
        return None
    return int(numeric)


def _sequence_item(value: Any, index: int) -> Any:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return value[index] if index < len(value) else None
    return None


def _display_number(value: float) -> str:
    return f"{value:.6g}"


if __name__ == "__main__":
    raise SystemExit(main())
