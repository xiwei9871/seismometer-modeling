from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.task08_data import (
    BASELINE,
    load_json,
    load_manifest,
    strict_confidence,
    validate_stage01_baseline,
    write_json,
)


def _write_stage01_fixture(root: Path) -> None:
    (root / "data").mkdir(parents=True)
    (root / "output").mkdir()
    run_result = {
        "status": "PASS",
        "source_sha256_before": BASELINE["source_sha256"],
        "source_sha256_after": BASELINE["source_sha256"],
        "component_count": 82,
        "manifest_count": 82,
        "face_count": 444296,
        "indexed_vertex_count": 221902,
    }
    write_json(root / "data/stage01_run_result.json", run_result)
    write_json(
        root / "data/parts_manifest.json",
        [{"part_id": f"PART_{index:03d}"} for index in range(1, 83)],
    )
    for path in (
        "data/source_model_report.json",
        "data/parts_manifest.csv",
        "data/duplicate_groups.json",
        "data/suspicious_fragments.json",
        "data/mesh_quality_report.json",
        "data/assembly_initial.json",
        "output/stage01_split.blend",
    ):
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"fixture")


def test_validate_stage01_baseline_requires_pass_and_exact_counts(tmp_path):
    _write_stage01_fixture(tmp_path)

    result = validate_stage01_baseline(tmp_path)

    assert result["source_sha256"] == BASELINE["source_sha256"]
    assert result["source_parts"] == 82
    assert result["faces"] == 444296
    assert result["indexed_vertices"] == 221902
    assert result["components"] == 82


def test_validate_stage01_baseline_rejects_changed_hash(tmp_path):
    _write_stage01_fixture(tmp_path)
    result_path = tmp_path / "data/stage01_run_result.json"
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    payload["source_sha256_before"] = "changed"
    write_json(result_path, payload)

    with pytest.raises(ValueError, match="immutable baseline"):
        validate_stage01_baseline(tmp_path)


def test_load_manifest_requires_all_stable_part_ids(tmp_path):
    _write_stage01_fixture(tmp_path)
    manifest = load_manifest(tmp_path)

    assert len(manifest) == 82
    assert manifest[0]["part_id"] == "PART_001"
    assert manifest[-1]["part_id"] == "PART_082"

    manifest[0]["part_id"] = "PART_000"
    write_json(tmp_path / "data/parts_manifest.json", manifest)
    with pytest.raises(ValueError, match="PART_001"):
        load_manifest(tmp_path)


def test_strict_json_rejects_nan_and_writes_utf8_json(tmp_path):
    (tmp_path / "nan.json").write_text('{"value": NaN}', encoding="utf-8")
    with pytest.raises(ValueError, match="invalid JSON constant"):
        load_json(tmp_path / "nan.json")

    path = tmp_path / "nested/数据.json"
    write_json(path, {"label": "测试", "value": 1.25})
    assert json.loads(path.read_text(encoding="utf-8"))["label"] == "测试"


def test_strict_confidence_accepts_known_values_and_rejects_unknown():
    assert strict_confidence("HIGH") == "HIGH"
    with pytest.raises(ValueError, match="confidence"):
        strict_confidence("GUESS")
