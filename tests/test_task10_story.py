from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from pypdf import PdfWriter

from stage_10_product_story.scripts.build_product_reference import build_product_reference_manifest
from stage_10_product_story.scripts.story_data import (
    build_annotation_config,
    build_camera_sequence,
    build_functional_modules,
    build_material_roles,
    build_story_config,
)
from stage_10_product_story.scripts.build_story_scene import (
    build_state_transforms,
    build_story_visibility_policy,
)
from stage_10_product_story.scripts.render_product_story import (
    REQUIRED_OUTPUTS,
    REQUIRED_STILLS,
    storyboard_inputs,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_product_reference_manifest_records_pdf_hash_and_claim_pages(tmp_path):
    pdf = tmp_path / "幔壳迅勘智能勘察设备.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.add_blank_page(width=100, height=100)
    with pdf.open("wb") as handle:
        writer.write(handle)
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    manifest = build_product_reference_manifest(tmp_path, pdf_path=pdf, expected_sha256=digest)

    assert manifest["pdf_status"] == "VERIFIED_LOCAL_REFERENCE"
    assert manifest["page_count"] == 2
    assert manifest["sha256"] == digest
    assert manifest["claims"]["channels"]["value"] == 3
    assert manifest["claims"]["adc_resolution"]["value"] == "32-bit"
    assert manifest["claims"]["standby_days"]["value"] == 10
    assert manifest["claims"]["charging_hours"]["value"] == 3
    assert manifest["claims"]["weight_kg"]["value"] == 2.5
    assert manifest["claims"]["temperature_range_c"]["value"] == [-40, 80]
    assert manifest["communication_protocol"]["status"] == "CONFLICT_REQUIRES_CONFIRMATION"


def test_product_reference_manifest_is_fail_closed_for_missing_pdf(tmp_path):
    manifest = build_product_reference_manifest(tmp_path, pdf_path=tmp_path / "missing.pdf")
    assert manifest["pdf_status"] == "MISSING_LOCAL_REFERENCE"
    assert manifest["claims_source"] == "USER_PRODUCT_BRIEF_2026-09-10"


def test_functional_modules_cover_exactly_the_22_story_parts():
    modules = build_functional_modules()
    members = [part_id for module in modules.values() for part_id in module["part_ids"]]
    assert len(members) == 22
    assert len(set(members)) == 22
    assert modules["SMART_3_AXIS_SENSING_SYSTEM"]["part_ids"] == [
        "PART_003", "PART_012", "PART_013", "PART_014"
    ]
    assert modules["HIGH_PRECISION_ACQUISITION_CORE"]["part_ids"] == [
        "PART_006", "PART_007", "PART_019"
    ]
    assert modules["REAL_TIME_COMMUNICATION_SYSTEM"]["part_ids"] == [
        "PART_005", "PART_017", "PART_018"
    ]


def test_story_shots_are_30_seconds_and_keep_protocol_pending():
    story = build_story_config()
    assert story["fps"] == 30
    assert story["frame_range"] == [1, 900]
    assert story["duration_seconds"] == 30.0
    assert [shot["shot_id"] for shot in story["shots"]] == [
        "ASSEMBLED", "PRIMARY_ARCHITECTURE", "SENSOR_FOCUS", "PCB_FOCUS",
        "COMMUNICATION_FOCUS", "POWER_FOCUS", "RUGGED_FOCUS", "REASSEMBLED",
        "FINAL_HERO",
    ]
    assert story["communication_protocol_text"] == "PENDING_PRODUCT_CONFIRMATION"
    assert all("4G" not in shot["title"] for shot in story["shots"])
    assert all("Bluetooth" not in " ".join(shot["metrics"]) for shot in story["shots"])


def test_state_transforms_cover_all_22_story_parts_and_nine_states():
    state_data = build_state_transforms(PROJECT_ROOT)
    assert state_data["source_baseline"] == {
        "source_part_count": 82,
        "faces": 444296,
        "indexed_vertices": 221902,
    }
    assert list(state_data["states"]) == [
        "ASSEMBLED", "PRIMARY_ARCHITECTURE", "SENSOR_FOCUS", "PCB_FOCUS",
        "COMMUNICATION_FOCUS", "POWER_FOCUS", "RUGGED_FOCUS", "REASSEMBLED",
        "FINAL_HERO",
    ]
    for state in state_data["states"].values():
        assert list(state["parts"]) == [f"PART_{i:03d}" for i in range(1, 23)]
    assert state_data["states"]["ASSEMBLED"]["parts"]["PART_001"]["location"] == pytest.approx(
        state_data["states"]["FINAL_HERO"]["parts"]["PART_001"]["location"]
    )


def test_story_scene_policy_keeps_all_source_parts_and_hides_small_parts():
    policy = build_story_visibility_policy()
    assert len(policy["visible_part_ids"]) == 22
    assert policy["visible_part_ids"] == [f"PART_{i:03d}" for i in range(1, 23)]
    assert len(policy["hidden_part_ids"]) == 60
    assert policy["hidden_part_ids"][-1] == "PART_082"


def test_material_roles_match_product_story():
    materials = build_material_roles()
    assert materials["LOWER_HOUSING"]["base_color"] == [0.95, 0.18, 0.02, 1.0]
    assert materials["UPPER_HOUSING"]["base_color"] == [0.025, 0.03, 0.035, 1.0]
    assert materials["MAIN_PCB"]["base_color"] == [0.02, 0.32, 0.10, 1.0]
    assert materials["SENSOR"]["role"] == "DARK_METALLIC"


def test_camera_sequence_has_one_controlled_hero_camera_and_no_fast_orbit():
    config = build_camera_sequence()
    assert config["fps"] == 30
    assert config["hero_camera"] == "CAM_STORY_HERO"
    assert config["camera_motion_policy"] == "SLOW_CONTROLLED"
    assert config["max_orbit_degrees_per_second"] <= 8
    assert {shot["camera_id"] for shot in config["shots"]} <= {
        "CAM_STORY_HERO", "CAM_STORY_SENSOR", "CAM_STORY_PCB"
    }


def test_camera_sequence_has_only_two_focus_transitions():
    config = build_camera_sequence()
    assert config["camera_segments"] == [
        {"frame_start": 1, "frame_end": 165, "camera_id": "CAM_STORY_HERO"},
        {"frame_start": 165, "frame_end": 300, "camera_id": "CAM_STORY_SENSOR"},
        {"frame_start": 300, "frame_end": 420, "camera_id": "CAM_STORY_PCB"},
        {"frame_start": 420, "frame_end": 900, "camera_id": "CAM_STORY_HERO"},
    ]


def test_annotations_never_render_unconfirmed_protocol_names():
    config = build_annotation_config()
    rendered_text = " ".join(item["text"] for item in config["items"])
    assert "PENDING_PRODUCT_CONFIRMATION" not in rendered_text
    assert "4G" not in rendered_text
    assert "Bluetooth" not in rendered_text
    assert "Multi-network communication" in rendered_text


def test_task10_render_outputs_are_exactly_the_eight_story_stills_and_preview():
    assert REQUIRED_STILLS == (
        "01_assembled.png", "02_primary_explosion.png", "03_sensor_focus.png",
        "04_pcb_focus.png", "05_communication_focus.png", "06_power_focus.png",
        "07_rugged_focus.png", "08_final_hero.png",
    )
    assert REQUIRED_OUTPUTS == REQUIRED_STILLS + (
        "storyboard_contact_sheet.png", "product_story_preview.mp4", "product_story_preview.blend"
    )


def test_storyboard_contact_sheet_uses_the_eight_story_stills(tmp_path):
    paths = [tmp_path / name for name in REQUIRED_STILLS]
    for path in paths:
        path.write_bytes(b"png")
    assert storyboard_inputs(paths) == [path.name for path in paths]
