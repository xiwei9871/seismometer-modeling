from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.task08_data import BASELINE, write_json
from scripts.task09_data import (
    TASK09_BASELINE,
    is_allowed_task09_output,
    validate_task09_baseline,
    write_task09_json,
)


def _write_stage01_fixture(root: Path) -> None:
    (root / "data").mkdir(parents=True)
    (root / "output").mkdir()
    stage01_result = {
        "status": "PASS",
        "source_sha256_before": BASELINE["source_sha256"],
        "source_sha256_after": BASELINE["source_sha256"],
        "component_count": 82,
        "manifest_count": 82,
        "face_count": 444296,
        "indexed_vertex_count": 221902,
    }
    write_json(root / "data/stage01_run_result.json", stage01_result)
    write_json(
        root / "data/parts_manifest.json",
        [{"part_id": f"PART_{index:03d}"} for index in range(1, 83)],
    )
    for relative in (
        "data/source_model_report.json",
        "data/parts_manifest.csv",
        "data/duplicate_groups.json",
        "data/suspicious_fragments.json",
        "data/mesh_quality_report.json",
        "data/assembly_initial.json",
        "output/stage01_split.blend",
    ):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fixture")


def _write_task08_fixture(root: Path) -> None:
    write_json(
        root / "data/task08_run_result.json",
        {
            "status": "PASS",
            "baseline": {
                "source_sha256": TASK09_BASELINE["source_sha256"],
                "source_parts": TASK09_BASELINE["source_parts"],
                "faces": TASK09_BASELINE["faces"],
                "indexed_vertices": TASK09_BASELINE["indexed_vertices"],
            },
            "semantic_blend": {
                "source_part_count": TASK09_BASELINE["source_parts"],
                "polygons": TASK09_BASELINE["faces"],
                "vertices": TASK09_BASELINE["indexed_vertices"],
                "animation_created": False,
                "source_geometry_modified": False,
            },
        },
    )
    (root / "output/stage02_semantic.blend").write_bytes(b"fixture")


def _write_valid_fixture(root: Path) -> None:
    _write_stage01_fixture(root)
    _write_task08_fixture(root)


def test_task09_baseline_exports_the_frozen_task08_facts():
    assert TASK09_BASELINE == {
        "source_sha256": "fd2a7b78540245fd098724206d5ddf169fd2f44c07638e9a6459cd92fea717d1",
        "source_parts": 82,
        "faces": 444296,
        "indexed_vertices": 221902,
    }


def test_task09_baseline_accepts_frozen_task08_inputs(tmp_path):
    _write_valid_fixture(tmp_path)

    result = validate_task09_baseline(tmp_path)

    assert result["source_parts"] == 82
    assert result["faces"] == 444296
    assert result["indexed_vertices"] == 221902


def test_task09_baseline_rejects_changed_stage02_facts(tmp_path):
    _write_valid_fixture(tmp_path)
    result_path = tmp_path / "data/task08_run_result.json"
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    payload["semantic_blend"]["polygons"] = 1
    write_json(result_path, payload)

    with pytest.raises(ValueError, match="baseline"):
        validate_task09_baseline(tmp_path)


def test_task09_baseline_rejects_non_pass_task08_result(tmp_path):
    _write_valid_fixture(tmp_path)
    result_path = tmp_path / "data/task08_run_result.json"
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    payload["status"] = "PARTIAL"
    write_json(result_path, payload)

    with pytest.raises(ValueError, match="Task 8.*PASS"):
        validate_task09_baseline(tmp_path)


def test_task09_baseline_requires_stage02_blend(tmp_path):
    _write_valid_fixture(tmp_path)
    (tmp_path / "output/stage02_semantic.blend").unlink()

    with pytest.raises(ValueError, match="stage02_semantic.blend"):
        validate_task09_baseline(tmp_path)


@pytest.mark.parametrize(
    "relative, expected",
    [
        ("data/exploded_state.json", True),
        ("data/disassembly_graph.json", True),
        ("output/stage03_exploded_preview.blend", True),
        ("output/explosion_validation/exploded_iso_front.png", True),
        ("output/reports/task09a_explosion_plan.md", True),
        ("output/task09a_review/index.html", True),
        ("logs/task09a.log", True),
        ("data/stage01_run_result.json", False),
        ("data/parts_manifest.json", False),
        ("data/parts_manifest.csv", False),
        ("data/semantic_parts.json", False),
        ("output/stage01_split.blend", False),
        ("output/stage02_semantic.blend", False),
        ("source/智能地震仪-221128(1).STL", False),
        ("智能地震仪-221128(1).STL", False),
    ],
)
def test_task09_output_allowlist_is_strict(tmp_path, relative, expected):
    _write_stage01_fixture(tmp_path)
    assert is_allowed_task09_output(tmp_path / relative) is expected


def test_task09_output_allowlist_rejects_paths_outside_project_root(tmp_path):
    _write_stage01_fixture(tmp_path)
    assert not is_allowed_task09_output(tmp_path.parent / "data/exploded_state.json")


def test_write_task09_json_creates_deterministic_utf8_json(tmp_path):
    path = tmp_path / "nested/状态.json"

    write_task09_json(path, {"z": 1, "label": "拆解", "a": [2, 1]})

    assert path.read_text(encoding="utf-8") == (
        '{\n  "a": [\n    2,\n    1\n  ],\n  "label": "拆解",\n  "z": 1\n}\n'
    )


def test_write_task09_json_rejects_non_standard_float_values(tmp_path):
    with pytest.raises(ValueError, match="Out of range float values are not JSON compliant"):
        write_task09_json(tmp_path / "invalid.json", {"value": float("nan")})
