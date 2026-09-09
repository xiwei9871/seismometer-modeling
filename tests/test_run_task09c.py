from __future__ import annotations

from pathlib import Path

import pytest

from stage_09C_refined_explosion.scripts.pipeline import (
    REQUIRED_OUTPUTS,
    validate_run_result_contract,
)


def test_task09c_required_outputs_are_stable():
    assert REQUIRED_OUTPUTS == (
        "exploded_hero_refined.png",
        "exploded_engineering_refined.png",
        "pcb_detail_refined.png",
        "sensor_detail_refined.png",
        "exploded_animation_preview.blend",
        "exploded_preview.mp4",
        "exploded_keyframes_contact_sheet.png",
    )


def test_task09c_run_contract_is_fail_closed_without_pass_status():
    with pytest.raises(ValueError):
        validate_run_result_contract({"status": "PASS", "outputs": {}})


def test_task09c_run_contract_accepts_pass_with_all_outputs(tmp_path):
    outputs = {}
    for name in REQUIRED_OUTPUTS:
        path = tmp_path / name
        path.write_bytes(b"review-output")
        outputs[name] = str(path)

    result = validate_run_result_contract(
        {
            "status": "PASS",
            "outputs": outputs,
            "source_geometry_modified": False,
            "source_part_count": 82,
            "source_faces": 444296,
            "source_indexed_vertices": 221902,
            "animation_created": True,
            "animation_duration_seconds": 18.0,
        }
    )
    assert result["status"] == "PASS"
