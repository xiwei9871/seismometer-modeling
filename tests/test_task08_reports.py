from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts.generate_part_previews import required_part_ids
from scripts.build_task08_reports import build_reports


def _load(root: Path, name: str):
    return json.loads((root / "data" / name).read_text(encoding="utf-8"))


@pytest.fixture
def report_root(tmp_path: Path) -> Path:
    project = Path(__file__).resolve().parent.parent
    for relative in (
        "data/parts_manifest.json",
        "data/duplicate_groups.json",
        "data/mesh_quality_report.json",
        "data/suspicious_fragments.json",
        "data/reference_manifest.json",
        "data/stage01_run_result.json",
    ):
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((project / relative).read_bytes())
    (tmp_path / "output/part_previews").mkdir(parents=True)
    (tmp_path / "output/part_highlights").mkdir(parents=True)
    (tmp_path / "output/reports").mkdir(parents=True)
    for part_id in required_part_ids():
        (tmp_path / "output/part_previews" / f"{part_id}.png").touch()
        (tmp_path / "output/part_highlights" / f"{part_id}_iso.png").touch()
    return tmp_path


def test_semantic_records_cover_all_parts_and_major_records_are_exactly_18(report_root):
    result = build_reports(report_root)
    records = _load(report_root, "semantic_parts.json")
    assert result["status"] == "CHECKPOINT"
    assert [record["part_id"] for record in records] == required_part_ids()
    assert sum(record["size_class"] == "MAJOR" for record in records) == 18
    assert all(record["semantic_name"] for record in records)
    for record in records:
        assert record["confidence"] in {"HIGH", "MEDIUM", "LOW", "UNKNOWN"}
        if record["semantic_name"] != "UNKNOWN":
            assert record["evidence"]
            assert record["reason"]


def test_non_watertight_review_is_non_destructive_and_covers_both_parts(report_root):
    build_reports(report_root)
    review = _load(report_root, "non_watertight_semantic_review.json")
    assert review["repair_performed"] is False
    assert {item["part_id"] for item in review["components"]} == {
        "PART_003",
        "PART_005",
    }
    assert all(item["requires_manual_confirmation"] for item in review["components"])


def test_fragment_review_contains_neighbors_and_keeps_unknown_default(report_root):
    build_reports(report_root)
    review = _load(report_root, "fragment_review.json")
    assert review["part_id"] == "PART_082"
    assert review["classification"] == "UNKNOWN"
    assert review["nearest_neighbour_parts"]
    records = _load(report_root, "semantic_parts.json")
    fragment = next(item for item in records if item["part_id"] == "PART_082")
    assert fragment["semantic_name"] == "UNKNOWN"


def test_pcb_validation_is_explicit_and_candidate_is_traceable(report_root):
    build_reports(report_root)
    pcb = _load(report_root, "pcb_validation.json")
    assert pcb["candidate_parts"]
    assert pcb["candidate_parts"] == ["PART_004"]
    assert pcb["confidence"] in {"MEDIUM", "LOW", "UNKNOWN"}
    assert pcb["evidence"]
    assert pcb["precision_dimensions_from_photos"] is False


def test_manual_queue_contains_only_uncertain_confidences_and_valid_preview_paths(report_root):
    build_reports(report_root)
    with (report_root / "data/manual_review_queue.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows
    assert {row["confidence"] for row in rows} <= {"MEDIUM", "LOW", "UNKNOWN"}
    assert all(row["preview_path"].startswith("output/") for row in rows)


def test_required_findings_files_are_written(report_root):
    build_reports(report_root)
    required = {
        "semantic_parts.json",
        "feature_validation.json",
        "reference_missing_features.json",
        "pcb_validation.json",
        "non_watertight_semantic_review.json",
        "reference_conflicts.json",
        "assembly_semantic.json",
        "mounting_relationships.json",
        "disassembly_dependencies.json",
        "fragment_review.json",
        "task08_checkpoint.json",
        "manual_review_queue.csv",
    }
    assert {path.name for path in (report_root / "data").iterdir()} >= required
