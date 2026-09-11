from __future__ import annotations

from pathlib import Path

import pytest

from stage_10_product_story.scripts.pipeline import (
    require_task09c_pass,
    validate_preview_media,
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
        "source_geometry_fingerprint_verified": True,
        "animation_created": True,
        "animation_duration_seconds": 30.0,
        "communication_protocol_text": "PENDING_PRODUCT_CONFIRMATION",
        "preview_media": {
            "codec_name": "h264",
            "width": 1920,
            "height": 1080,
            "r_frame_rate": "30/1",
            "nb_frames": 900,
            "duration_seconds": 30.0,
        },
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
            "source_geometry_fingerprint_verified": True,
            "animation_created": True,
            "animation_duration_seconds": 30.0,
            "communication_protocol_text": "4G",
            "preview_media": {
                "codec_name": "h264",
                "width": 1920,
                "height": 1080,
                "r_frame_rate": "30/1",
                "nb_frames": 900,
                "duration_seconds": 30.0,
            },
        })


def test_task10_preview_media_contract_accepts_ffprobe_metadata(monkeypatch, tmp_path):
    preview = tmp_path / "product_story_preview.mp4"
    preview.write_bytes(b"valid-preview")

    class Completed:
        returncode = 0
        stdout = '{"streams":[{"codec_name":"h264","codec_type":"video","width":1920,"height":1080,"r_frame_rate":"30/1","nb_frames":900}],"format":{"duration":"30.000000"}}'
        stderr = ""

    monkeypatch.setattr("stage_10_product_story.scripts.pipeline.subprocess.run", lambda *args, **kwargs: Completed())
    metadata = validate_preview_media(preview, ffprobe_path="ffprobe")
    assert metadata["codec_name"] == "h264"
    assert metadata["duration_seconds"] == 30.0


def test_task10_preview_media_contract_rejects_invalid_container(monkeypatch, tmp_path):
    preview = tmp_path / "product_story_preview.mp4"
    preview.write_bytes(b"invalid-preview")

    class Completed:
        returncode = 1
        stdout = ""
        stderr = "moov atom not found"

    monkeypatch.setattr("stage_10_product_story.scripts.pipeline.subprocess.run", lambda *args, **kwargs: Completed())
    with pytest.raises(ValueError, match="ffprobe"):
        validate_preview_media(preview, ffprobe_path="ffprobe")
