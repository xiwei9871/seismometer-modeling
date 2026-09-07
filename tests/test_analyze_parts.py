"""Tests for Stage 01 pure classification and report generation."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.analyze_parts import (
    build_mesh_quality_report,
    build_part_records,
    classify_complexity,
    classify_size,
    detect_suspicious_fragment,
    manifest_fieldnames,
    render_stage01_report,
    write_manifest_csv,
    write_manifest_json,
    write_mesh_quality_report,
    write_suspicious_fragments,
)


def record(
    part_id: str,
    faces: int,
    diagonal: float,
    bbox_volume: float,
    area: float,
    *,
    centroid: list[float] | None = None,
    volume: float | None = None,
    volume_valid: bool = False,
    watertight: bool = False,
    source_component_index: int = 0,
    metric_errors: dict | None = None,
) -> dict:
    return {
        "part_id": part_id,
        "source_component_index": source_component_index,
        "face_count": faces,
        "vertex_count": faces * 3,
        "bbox_dimensions": [diagonal, diagonal, diagonal],
        "bbox_diagonal": diagonal,
        "bbox_volume": bbox_volume,
        "centroid": centroid or [0.0, 0.0, 0.0],
        "surface_area": area,
        "volume": volume,
        "volume_valid": volume_valid,
        "watertight": watertight,
        "euler_number": 2 if watertight else 1,
        "winding_consistent": watertight,
        "boundary_edge_count": 0 if watertight else 3,
        "non_manifold_edge_count": 0,
        "duplicate_face_count": 0,
        "metric_errors": metric_errors or {},
    }


def source_report(records: list[dict]) -> dict:
    return {
        "source_file": "fixture.stl",
        "file_size_bytes": 1234,
        "raw_vertex_count": sum(item["vertex_count"] for item in records),
        "vertices": sum(item["vertex_count"] for item in records),
        "faces": sum(item["face_count"] for item in records),
        "bbox_dimensions": [190.0, 170.0, 180.0],
        "bounds_min": [-95.0, -85.0, -90.0],
        "bounds_max": [95.0, 85.0, 90.0],
        "centroid": [0.0, 0.0, 0.0],
        "surface_area": 1000.0,
        "volume": None,
        "volume_valid": False,
        "is_watertight": False,
        "winding_consistent": False,
        "euler_number": 1,
        "connected_component_count": len(records),
        "unit_assumption": "mm",
        "unit_confidence": "assumed",
        "global_metric_errors": {},
        "components": records,
    }


def test_size_classifier_uses_multiple_features_not_volume_only():
    records = [
        record("PART_001", 200, 100, 1, 500),
        record("PART_002", 20, 10, 20, 30),
        record("PART_003", 4, 4, 0.1, 16),
    ]

    classes = classify_size(records)

    assert classes["PART_001"] in {"MAJOR", "MEDIUM"}
    assert classes["PART_003"] == "FRAGMENT"


def test_low_volume_thin_plate_is_not_automatically_tiny():
    records = [
        record("PLATE", 500, 100, 0.001, 1000),
        record("BLOCK", 80, 20, 100, 80),
    ]

    classes = classify_size(records)

    assert classes["PLATE"] in {"MAJOR", "MEDIUM"}


def test_size_classifier_renormalizes_missing_features_without_mutating_records():
    records = [
        record("A", 100, 10, 10, 100),
        record("B", 50, 5, 5, 50),
        record("MISSING", 20, 2, 2, 20),
    ]
    records[2]["surface_area"] = None
    before = json.loads(json.dumps(records))

    classes = classify_size(records)

    assert set(classes) == {"A", "B", "MISSING"}
    assert records == before


def test_fragment_detection_marks_without_delete_instruction():
    tiny = record("PART_010", 3, 0.2, 0.001, 0.1)

    result = detect_suspicious_fragment(tiny, median_faces=100, median_diagonal=20)

    assert result["suspected_fragment"] is True
    assert result["part_id"] == "PART_010"
    assert result["reason"]
    assert result["bbox"] == {"x": 0.2, "y": 0.2, "z": 0.2}
    assert result["centroid"] == [0.0, 0.0, 0.0]
    assert "suspected_fragment" not in tiny


def test_low_face_and_tiny_diagonal_rule_is_explicit():
    tiny = record("PART_011", 20, 0.05, 0.0001, 0.1)

    result = detect_suspicious_fragment(tiny, median_faces=100, median_diagonal=20)

    assert result["suspected_fragment"] is True
    assert "low face count" in result["reason"]
    assert "tiny bbox diagonal" in result["reason"]


def test_complexity_thresholds_are_explicit():
    assert classify_complexity(10, 100, 200) == "TRIVIAL"
    assert classify_complexity(100, 100, 200) == "SIMPLE"
    assert classify_complexity(150, 100, 200) == "MODERATE"
    assert classify_complexity(201, 100, 200) == "COMPLEX"


def test_build_part_records_contains_required_manifest_fields_and_metadata():
    source = source_report(
        [
            record("PART_001", 100, 10, 8, 100, source_component_index=4),
            record("PART_002", 3, 0.2, 0.001, 0.1, source_component_index=8),
        ]
    )

    records, metadata = build_part_records(source)

    required = {
        "part_id",
        "source_component_index",
        "face_count",
        "vertex_count",
        "bbox_x_mm",
        "bbox_y_mm",
        "bbox_z_mm",
        "bbox_volume",
        "centroid_x_mm",
        "centroid_y_mm",
        "centroid_z_mm",
        "surface_area",
        "volume",
        "volume_valid",
        "watertight",
        "euler_number",
        "complexity_class",
        "size_class",
        "duplicate_group",
        "duplicate_confidence",
        "suspected_fragment",
        "notes",
    }
    assert required.issubset(records[0])
    assert len(records) == 2
    assert records[1]["size_class"] == "FRAGMENT"
    assert metadata["size_thresholds"] == {
        "major": 0.75,
        "medium": 0.40,
        "small": 0.15,
    }
    assert metadata["feature_weights"] == {
        "bbox_diagonal": 0.30,
        "bbox_volume": 0.20,
        "surface_area": 0.25,
        "face_count": 0.25,
    }


def test_mesh_quality_aggregates_diagnostics_without_repair():
    records = [
        record("PART_001", 20, 2, 8, 10, watertight=True),
        record("PART_002", 5, 1, 1, 2, metric_errors={"surface_area": "failed"}),
    ]
    report = build_mesh_quality_report(source_report(records))

    assert report["component_count"] == 2
    assert report["watertight_count"] == 1
    assert report["non_watertight_count"] == 1
    assert report["boundary_edge_count"] == 3
    assert report["non_manifold_edge_count"] == 0
    assert report["duplicate_face_count"] == 0
    assert report["metric_errors"]["PART_002"]["surface_area"] == "failed"
    assert report["possible_broken_components"][0]["part_id"] == "PART_002"
    assert report["repair_performed"] is False


def test_writers_emit_strict_utf8_json_and_manifest_csv(tmp_path):
    records, _ = build_part_records(source_report([record("零件", 3, 0.2, 0.001, 0.1)]))
    json_path = tmp_path / "parts_manifest.json"
    csv_path = tmp_path / "parts_manifest.csv"
    fragments_path = tmp_path / "suspicious_fragments.json"
    quality_path = tmp_path / "mesh_quality_report.json"

    write_manifest_json(json_path, records)
    write_manifest_csv(csv_path, records)
    write_suspicious_fragments(fragments_path, records)
    quality = build_mesh_quality_report(source_report([record("PART_001", 3, 0.2, 0.001, 0.1)]))
    write_mesh_quality_report(quality_path, quality)

    parsed = json.loads(json_path.read_text(encoding="utf-8"))
    assert parsed[0]["part_id"] == "零件"
    assert "NaN" not in json_path.read_text(encoding="utf-8")
    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["part_id"] == "零件"
    assert set(manifest_fieldnames()).issubset(rows[0])
    assert {"bbox_volume", "surface_area", "volume"}.issubset(rows[0])
    assert json.loads(fragments_path.read_text(encoding="utf-8"))[0]["part_id"] == "零件"
    assert json.loads(quality_path.read_text(encoding="utf-8"))["repair_performed"] is False


def test_manifest_csv_includes_canonical_measurement_fields_and_aliases(tmp_path):
    records, _ = build_part_records(
        source_report([record("PART_001", 12, 10, 100, 12, volume=42.5, volume_valid=True)])
    )
    csv_path = tmp_path / "parts_manifest.csv"

    write_manifest_csv(csv_path, records)

    fieldnames = set(manifest_fieldnames())
    required_fields = {
        "bbox_volume",
        "surface_area",
        "volume",
        "bbox_volume_mm3",
        "surface_area_mm2",
        "volume_mm3",
    }
    assert required_fields.issubset(fieldnames)
    with csv_path.open(newline="", encoding="utf-8") as handle:
        row = next(csv.DictReader(handle))
    assert required_fields.issubset(row)
    assert row["bbox_volume"] == row["bbox_volume_mm3"] == "100"
    assert row["surface_area"] == row["surface_area_mm2"] == "12"
    assert row["volume"] == row["volume_mm3"] == "42.5"


def test_report_contains_required_sections_top_parts_duplicate_groups_and_manual_checks():
    records = [record("PART_001", 12, 10, 100, 12)]
    duplicate_report = {
        "groups": [
            {"group_id": "DG_001", "quantity": 3, "confidence": "HIGH", "parts": ["PART_001"]}
        ],
        "group_count": 1,
    }
    quality = {"component_count": 1, "watertight_count": 0, "issues": []}

    text = render_stage01_report(
        {"source_file": "fixture.stl", "faces": 12, "vertices": 8},
        records,
        duplicate_report,
        quality,
    )

    assert "## Source" in text
    assert "## Component recovery" in text
    assert "## Duplicate analysis" in text
    assert "DG_001" in text
    assert "## Mesh quality" in text
    assert "## Important findings" in text
    assert text.count("人工确认") >= 5
    assert set(["part_id", "source_component_index", "size_class"]).issubset(
        manifest_fieldnames()
    )


def test_cli_generates_all_task4_outputs(tmp_path):
    source_json = tmp_path / "source_model_report.json"
    source_json.write_text(
        json.dumps(source_report([record("PART_001", 12, 10, 100, 12)]), ensure_ascii=False),
        encoding="utf-8",
    )
    manifest_json = tmp_path / "parts_manifest.json"
    manifest_csv = tmp_path / "parts_manifest.csv"
    suspicious = tmp_path / "suspicious_fragments.json"
    quality = tmp_path / "mesh_quality_report.json"
    report = tmp_path / "stage01_report.md"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.analyze_parts",
            "--source-report",
            str(source_json),
            "--manifest-json",
            str(manifest_json),
            "--manifest-csv",
            str(manifest_csv),
            "--suspicious",
            str(suspicious),
            "--quality",
            str(quality),
            "--report",
            str(report),
        ],
        cwd=Path(__file__).parents[1],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert all(path.exists() for path in (manifest_json, manifest_csv, suspicious, quality, report))
    assert json.loads(manifest_json.read_text(encoding="utf-8"))[0]["part_id"] == "PART_001"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_manifest_json_rejects_non_finite_values(tmp_path, value):
    invalid = record("BAD", 3, 1, 1, 1)
    invalid["surface_area"] = value

    with pytest.raises(ValueError):
        write_manifest_json(tmp_path / "manifest.json", [invalid])
