from __future__ import annotations

from pathlib import Path

import pytest

from stage_10_product_story.scripts.pipeline import (
    require_task09c_pass,
    validate_run_result,
)


def test_task10_run_contract_rejects_missing_outputs(tmp_path):
    with pytest.raises(ValueError):
        validate_run_result({"status": "PASS", "outputs": {}})


def test_task10_run_contract_requires_geometry_baseline_and_pending_protocol(tmp_path):
    outputs = {}
    for name in (
        "01_assembled.png", "02_primary_explosion.png", "03_sensor_focus.png",
        "04_pcb_focus.png", "05_communication_focus.png", "06_power_focus.png",
        "07_rugged_focus.png", "08_final_hero.png", "storyboard_contact_sheet.png",
        "product_story_preview.mp4", "product_story_preview.blend",
    ):
        path = tmp_path / name
        path.write_bytes(b"review-output")
        outputs[name] = str(path)
    result = validate_run_result({
        "status": "PASS",
        "outputs": outputs,
        "source_geometry_modified": False,
        "source_part_count": 82,
        "source_faces": 444296,
        "source_indexed_vertices": 221902,
        "animation_created": True,
        "animation_duration_seconds": 30.0,
        "communication_protocol_text": "PENDING_PRODUCT_CONFIRMATION",
    })
    assert result["source_part_count"] == 82


def test_task10_pipeline_reads_task09c_before_running(tmp_path):
    with pytest.raises(ValueError, match="Task 9C"):
        require_task09c_pass(tmp_path)


def test_task10_validate_run_result_rejects_non_pending_protocol(tmp_path):
    outputs = {}
    for name in (
        "01_assembled.png", "02_primary_explosion.png", "03_sensor_focus.png",
        "04_pcb_focus.png", "05_communication_focus.png", "06_power_focus.png",
        "07_rugged_focus.png", "08_final_hero.png", "storyboard_contact_sheet.png",
        "product_story_preview.mp4", "product_story_preview.blend",
    ):
        path = tmp_path / name
        path.write_bytes(b"review-output")
        outputs[name] = str(path)
    with pytest.raises(ValueError, match="protocol"):
        validate_run_result({
            "status": "PASS",
            "outputs": outputs,
            "source_geometry_modified": False,
            "source_part_count": 82,
            "source_faces": 444296,
            "source_indexed_vertices": 221902,
            "animation_created": True,
            "animation_duration_seconds": 30.0,
            "communication_protocol_text": "4G",
        })
