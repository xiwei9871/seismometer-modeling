from pathlib import Path

import pytest

from scripts.presentation_explosion_v3 import (
    ALLOWED_ZONES,
    REVIEW_QUESTION,
    build_presentation_layout,
    write_presentation_outputs,
    validate_zone_name,
)
from scripts.build_presentation_explosion_v3 import validate_presentation_scene_facts
from scripts.generate_presentation_explosion_v3 import (
    CAMERA_CLIP_END_MM,
    V3_VIEW_NAMES,
    render_result_contract,
)
from scripts.run_presentation_v3 import build_presentation_report


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_PART_IDS = [f"PART_{index:03d}" for index in range(1, 83)]
SMALL_OR_FRAGMENT_IDS = {
    "PART_039",
    *(f"PART_{index:03d}" for index in range(46, 83)),
}


def test_layout_preserves_all_source_parts():
    result = build_presentation_layout(PROJECT_ROOT)

    assert list(result["parts"]) == EXPECTED_PART_IDS
    assert result["source_baseline"] == {
        "source_parts": 82,
        "faces": 444296,
        "indexed_vertices": 221902,
    }
    assert result["animation_created"] is False
    assert result["animation_anchor"] == "PART_001"


def test_only_major_and_medium_parts_are_visible():
    result = build_presentation_layout(PROJECT_ROOT)

    visible = [
        part
        for part in result["parts"].values()
        if part["presentation_visibility"] == "VISIBLE"
    ]
    hidden = [
        part
        for part in result["parts"].values()
        if part["presentation_visibility"] == "HIDDEN"
    ]

    assert len(visible) == 44
    assert len(hidden) == 38
    assert {part["size_class"] for part in visible} == {"MAJOR", "MEDIUM"}
    assert {part["size_class"] for part in hidden} <= {"SMALL", "FRAGMENT"}


def test_small_and_fragment_parts_are_hidden_and_absent_from_review_queue():
    result = build_presentation_layout(PROJECT_ROOT)

    for part_id in SMALL_OR_FRAGMENT_IDS:
        record = result["parts"][part_id]
        assert record["presentation_visibility"] == "HIDDEN"
        assert record["presentation_mode"] == "HIDDEN_NO_PARENT"
        assert record["presentation_parent"] is None

    queued = {item["part_id"] for item in result["review_queue"]}
    assert not queued.intersection(SMALL_OR_FRAGMENT_IDS)
    assert all(
        item["size_class"] in {"MAJOR", "MEDIUM"}
        for item in result["review_queue"]
    )


def test_allowed_zones_are_fixed():
    assert ALLOWED_ZONES == (
        "top",
        "bottom",
        "left",
        "right",
        "front-left",
        "front-right",
    )
    for zone in ALLOWED_ZONES:
        assert validate_zone_name(zone) == zone


def test_unknown_zone_is_rejected():
    with pytest.raises(ValueError, match="zone"):
        validate_zone_name("diagonal")


def test_sensor_pcb_and_battery_use_hierarchical_offsets():
    result = build_presentation_layout(PROJECT_ROOT)

    assert result["assemblies"]["SENSOR_ASSEMBLY"]["zone"] == "front-left"
    assert result["assemblies"]["PCB_ASSEMBLY"]["zone"] == "front-right"
    assert result["assemblies"]["BATTERY_ASSEMBLY"]["zone"] == "left"

    sensor_fixture = result["parts"]["PART_003"]
    sensor_core_offsets = [
        tuple(result["parts"][part_id]["local_offset_mm"])
        for part_id in ("PART_012", "PART_013", "PART_014")
    ]
    assert sensor_fixture["hierarchy_level"] == 2
    assert len(set(sensor_core_offsets)) == 3
    assert all(any(value != 0.0 for value in offset) for offset in sensor_core_offsets)

    pcb_offsets = [
        tuple(result["parts"][part_id]["local_offset_mm"])
        for part_id in ("PART_006", "PART_007", "PART_019")
    ]
    assert len(set(pcb_offsets)) == 3
    assert result["parts"]["PART_019"]["semantic_name"] == "MAIN_PCB"

    battery_offsets = [
        tuple(result["parts"][f"PART_{index:03d}"]["local_offset_mm"])
        for index in (8, 9, 10, 11, 15, 16)
    ]
    assert len(set(battery_offsets)) == 6


def test_lower_housing_is_the_assembled_anchor():
    result = build_presentation_layout(PROJECT_ROOT)
    anchor = result["parts"]["PART_001"]

    assert anchor["presentation_mode"] == "ANCHOR"
    assert anchor["assembly_zone_offset_mm"] == [0.0, 0.0, 0.0]
    assert anchor["local_offset_mm"] == [0.0, 0.0, 0.0]
    assert anchor["presentation_location"] == anchor["assembled_location"]


def test_layout_has_visible_only_review_question():
    result = build_presentation_layout(PROJECT_ROOT)
    expected_question = (
        "Is the important component visible, unobstructed, and clearly laid out?"
    )

    assert result["review_queue"]
    assert all(item["review_question"] == expected_question for item in result["review_queue"])


def test_write_presentation_outputs_is_deterministic():
    result = build_presentation_layout(PROJECT_ROOT)

    paths = write_presentation_outputs(PROJECT_ROOT, result)
    first_layout = paths["layout"].read_bytes()
    first_queue = paths["review_queue"].read_bytes()
    write_presentation_outputs(PROJECT_ROOT, result)

    assert paths["layout"].read_bytes() == first_layout
    assert paths["review_queue"].read_bytes() == first_queue


def test_review_queue_contains_only_visible_major_medium_parts():
    result = build_presentation_layout(PROJECT_ROOT)

    assert len(result["review_queue"]) == 44
    assert all(
        item["size_class"] in {"MAJOR", "MEDIUM"}
        for item in result["review_queue"]
    )
    assert all(
        item["review_question"] == REVIEW_QUESTION
        for item in result["review_queue"]
    )


def test_presentation_scene_facts_reject_animation():
    facts = [
        {
            "part_id": f"PART_{index:03d}",
            "source": "original_stl",
            "type": "MESH",
            "animation_data": True if index == 1 else None,
        }
        for index in range(1, 83)
    ]
    with pytest.raises(ValueError, match="animation"):
        validate_presentation_scene_facts(
            facts,
            vertices=221902,
            polygons=444296,
        )


def test_presentation_scene_facts_require_frozen_geometry():
    facts = [
        {
            "part_id": f"PART_{index:03d}",
            "source": "original_stl",
            "type": "MESH",
            "animation_data": None,
        }
        for index in range(1, 83)
    ]
    with pytest.raises(ValueError, match="frozen geometry"):
        validate_presentation_scene_facts(facts, vertices=0, polygons=0)


def test_v3_view_names_are_fixed():
    assert V3_VIEW_NAMES == (
        "exploded_iso_front_v3",
        "exploded_iso_rear_v3",
        "exploded_front_v3",
        "exploded_top_v3",
    )


def test_v3_camera_clip_covers_presentation_layout():
    assert CAMERA_CLIP_END_MM >= 10000.0


def test_render_result_contract_is_static():
    result = render_result_contract({"animation_created": False})
    assert result["animation_created"] is False


def test_presentation_report_mentions_layout_contract():
    layout = build_presentation_layout(PROJECT_ROOT)
    report = build_presentation_report(layout, scene_result=None, render_result=None)

    assert "STATIC_HIERARCHICAL_PRESENTATION" in report
    assert "44 visible" in report
    assert "38 hidden" in report
    assert "PART_001" in report
    assert "exploded_iso_front_v3.png" in report
    assert "No keyframes" in report


def test_v3_generated_outputs_are_ignored_without_ignoring_reference_photos():
    gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "data/presentation_explosion_v3.json" in gitignore
    assert "data/presentation_review_queue_v3.csv" in gitignore
    assert "output/explosion_validation_v3/" in gitignore
    assert "output/stage03_presentation_exploded_v3.blend" in gitignore
    assert "*.png" not in gitignore
