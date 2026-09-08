"""TDD coverage for tolerant, non-destructive duplicate-part grouping."""

from __future__ import annotations

import copy
import csv
import json
import subprocess
import sys
from pathlib import Path

from scripts.detect_duplicate_parts import (
    apply_duplicate_groups,
    geometry_signature,
    group_duplicate_parts,
    records_match,
)


def part(
    part_id: str,
    *,
    dims: list[float] | None = None,
    faces: int | None = 100,
    vertices: int | None = 60,
    area: float | None = 250.0,
    volume: float | None = 1000.0,
    volume_valid: bool | None = True,
    watertight: bool | None = True,
) -> dict:
    return {
        "part_id": part_id,
        "bbox_dimensions": dims if dims is not None else [10.0, 5.0, 20.0],
        "face_count": faces,
        "vertex_count": vertices,
        "surface_area": area,
        "volume": volume,
        "volume_valid": volume_valid,
        "watertight": watertight,
        "notes": {"keep": True},
    }


def test_geometry_signature_sorts_bbox_dimensions_and_sanitizes_invalid_values():
    record = part("PART_002", dims=[20.0, 5.0, 10.0])

    signature = geometry_signature(record)

    assert signature["bbox_dimensions"] == [5.0, 10.0, 20.0]
    assert signature["face_count"] == 100
    assert signature["vertex_count"] == 60
    assert signature["surface_area"] == 250.0
    assert signature["volume"] == 1000.0
    assert signature["volume_valid"] is True
    assert signature["watertight"] is True

    invalid = geometry_signature({"bbox_dimensions": [None, float("nan"), "bad"]})
    assert invalid == {
        "bbox_dimensions": None,
        "face_count": None,
        "vertex_count": None,
        "surface_area": None,
        "volume": None,
        "volume_valid": None,
        "watertight": None,
    }


def test_records_match_accepts_rotation_and_requested_tolerance_boundaries():
    base = part("A")
    rotated = part(
        "B",
        dims=[20.0, 10.0, 5.0],
        area=252.5,
        volume=1010.0,
    )

    assert records_match(base, rotated) == "HIGH"

    dimension_boundary = part("C", dims=[100.5, 5.0, 20.0])
    assert records_match(part("D", dims=[100.0, 5.0, 20.0]), dimension_boundary) == "HIGH"

    area_boundary = part("E", area=252.5)
    assert records_match(base, area_boundary) == "HIGH"
    volume_boundary = part("F", volume=1010.0)
    assert records_match(base, volume_boundary) == "HIGH"

    assert records_match(part("G", dims=[100.0, 5.0, 20.0]), part("G2", dims=[100.51, 5.0, 20.0])) is None
    assert records_match(base, part("H", area=252.6)) is None
    assert records_match(base, part("I", volume=1010.2)) is None


def test_records_match_requires_exact_counts_and_watertight_match():
    base = part("A")

    assert records_match(base, part("B", faces=101)) is None
    assert records_match(base, part("C", vertices=61)) is None
    assert records_match(base, part("D", watertight=False)) is None
    assert records_match(base, part("E", watertight=None)) is None


def test_invalid_volume_is_not_compared_or_promoted_to_high_confidence():
    left = part("A", volume=None, volume_valid=False)
    right = part("B", volume=999999.0, volume_valid=False)

    assert records_match(left, right) == "MEDIUM"
    assert records_match(left, part("C", volume=1000.0, volume_valid=True)) is None

    invalid = part("D", volume=float("nan"), volume_valid=True)
    assert records_match(part("E"), invalid) is None


def test_group_duplicate_parts_is_stable_does_not_merge_records_and_ignores_singletons():
    records = [
        part("PART_010"),
        part("PART_002"),
        part("PART_001"),
        part("PART_020", dims=[2.0, 3.0, 4.0], faces=12, vertices=8, area=40.0, volume=20.0),
        part("PART_021", dims=[4.0, 3.0, 2.0], faces=12, vertices=8, area=40.0, volume=20.0),
        part("PART_999", dims=[1.0, 2.0, 3.0], faces=9, vertices=6, area=6.0, volume=None, volume_valid=False),
    ]

    report = group_duplicate_parts(records)
    reversed_report = group_duplicate_parts(list(reversed(records)))

    assert report == reversed_report
    assert report["group_count"] == 2
    assert [group["group_id"] for group in report["groups"]] == ["DG_001", "DG_002"]
    assert report["groups"][0]["parts"] == ["PART_001", "PART_002", "PART_010"]
    assert report["groups"][0]["quantity"] == 3
    assert report["groups"][0]["confidence"] == "HIGH"
    assert report["groups"][1]["parts"] == ["PART_020", "PART_021"]
    assert report["groups"][1]["confidence"] == "HIGH"
    assert all("PART_999" not in group["parts"] for group in report["groups"])
    assert len(records) == 6
    assert all("duplicate_group" not in record for record in records)


def test_group_duplicate_parts_reports_explicit_comparison_tolerances():
    report = group_duplicate_parts([part("PART_001"), part("PART_002")])

    assert report["tolerances"] == {
        "dimensions_absolute_mm": 0.1,
        "dimensions_relative_ratio": 0.005,
        "surface_area_relative_ratio": 0.01,
        "volume_relative_ratio": 0.01,
    }


def test_group_with_invalid_volume_is_medium_and_keeps_all_physical_parts():
    records = [
        part("PART_001", volume=None, volume_valid=False),
        part("PART_002", volume=12345.0, volume_valid=False),
    ]

    report = group_duplicate_parts(records)

    assert report["group_count"] == 1
    assert report["groups"][0]["confidence"] == "MEDIUM"
    assert report["groups"][0]["parts"] == ["PART_001", "PART_002"]


def test_apply_duplicate_groups_returns_deep_copy_and_writes_all_members():
    records = [
        part("PART_002"),
        part("PART_001"),
        part("PART_003", dims=[1.0, 2.0, 3.0], faces=12, vertices=8, area=12.0, volume=6.0),
    ]
    original = copy.deepcopy(records)
    report = group_duplicate_parts(records)

    updated = apply_duplicate_groups(records, report)

    assert records == original
    assert updated is not records
    assert updated[0] is not records[0]
    assert updated[0]["duplicate_group"] == "DG_001"
    assert updated[1]["duplicate_group"] == "DG_001"
    assert updated[2]["duplicate_group"] is None
    updated[0]["notes"]["keep"] = False
    assert records[0]["notes"]["keep"] is True


def test_cli_writes_strict_utf8_json_and_never_overwrites_source_manifest(tmp_path):
    source = tmp_path / "parts_manifest.json"
    records = [part("零件A"), part("PART_002"), part("PART_003", dims=[1, 2, 3], faces=7)]
    source_bytes = json.dumps(records, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    source.write_bytes(source_bytes)
    output_manifest = tmp_path / "out" / "parts_manifest.json"
    output_groups = tmp_path / "out" / "duplicate_groups.json"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.detect_duplicate_parts",
            "--manifest-json",
            str(source),
            "--output-manifest",
            str(output_manifest),
            "--output-groups",
            str(output_groups),
        ],
        cwd=Path(__file__).parents[1],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert source.read_bytes() == source_bytes
    assert output_manifest.exists()
    assert output_groups.exists()
    parsed_manifest = json.loads(output_manifest.read_text(encoding="utf-8"))
    parsed_groups = json.loads(output_groups.read_text(encoding="utf-8"))
    assert parsed_manifest[0]["duplicate_group"] == "DG_001"
    assert parsed_groups["group_count"] == 1
    assert parsed_groups["groups"][0]["parts"] == ["PART_002", "零件A"]
    assert "NaN" not in output_manifest.read_text(encoding="utf-8")
    assert "NaN" not in output_groups.read_text(encoding="utf-8")


def test_cli_writes_json_and_csv_manifests_with_duplicate_fields(tmp_path):
    source = tmp_path / "parts_manifest.json"
    records = [part("PART_001"), part("PART_002")]
    source.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    output_manifest = tmp_path / "out" / "parts_manifest.json"
    output_csv = tmp_path / "out" / "parts_manifest.csv"
    output_groups = tmp_path / "out" / "duplicate_groups.json"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.detect_duplicate_parts",
            "--manifest-json",
            str(source),
            "--output-manifest",
            str(output_manifest),
            "--output-csv",
            str(output_csv),
            "--output-groups",
            str(output_groups),
        ],
        cwd=Path(__file__).parents[1],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(output_manifest.read_text(encoding="utf-8"))[0]["duplicate_group"] == "DG_001"
    with output_csv.open(newline="", encoding="utf-8") as handle:
        rows = {row["part_id"]: row for row in csv.DictReader(handle)}
    assert rows["PART_001"]["duplicate_group"] == "DG_001"
    assert rows["PART_001"]["duplicate_confidence"] == "HIGH"
    assert rows["PART_002"]["duplicate_group"] == "DG_001"
    assert rows["PART_002"]["duplicate_confidence"] == "HIGH"
    assert json.loads(output_groups.read_text(encoding="utf-8"))["tolerances"]["volume_relative_ratio"] == 0.01


def test_cli_rejects_hardlink_csv_output_without_touching_source(tmp_path):
    source = tmp_path / "manifest.json"
    source.write_text(json.dumps([part("PART_001")]), encoding="utf-8")
    hardlink = tmp_path / "hardlink.csv"
    hardlink.hardlink_to(source)
    before = source.read_bytes()

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.detect_duplicate_parts",
            "--manifest-json",
            str(source),
            "--output-csv",
            str(hardlink),
        ],
        cwd=Path(__file__).parents[1],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert source.read_bytes() == before


def test_cli_rejects_source_manifest_as_output_and_returns_nonzero(tmp_path):
    source = tmp_path / "manifest.json"
    source.write_text(json.dumps([part("PART_001")]), encoding="utf-8")
    before = source.read_bytes()

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.detect_duplicate_parts",
            "--manifest-json",
            str(source),
            "--output-manifest",
            str(source),
        ],
        cwd=Path(__file__).parents[1],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert source.read_bytes() == before


def test_cli_rejects_non_strict_json_input(tmp_path):
    source = tmp_path / "manifest.json"
    source.write_text('[{"part_id": "PART_001", "face_count": NaN}]', encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.detect_duplicate_parts",
            "--manifest-json",
            str(source),
        ],
        cwd=Path(__file__).parents[1],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0


def test_cli_rejects_hardlink_output_without_touching_source(tmp_path):
    source = tmp_path / "manifest.json"
    source.write_text(json.dumps([part("PART_001")]), encoding="utf-8")
    hardlink = tmp_path / "hardlink.json"
    hardlink.hardlink_to(source)
    before = source.read_bytes()

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.detect_duplicate_parts",
            "--manifest-json",
            str(source),
            "--output-manifest",
            str(hardlink),
        ],
        cwd=Path(__file__).parents[1],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert source.read_bytes() == before
