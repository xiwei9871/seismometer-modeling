from pathlib import Path

import pytest

from scripts.presentation_explosion_v4 import (
    V4_VIEW_NAMES,
    build_presentation_layout_v4,
    validate_v4_layout,
)
from scripts.build_presentation_explosion_v4 import validate_v4_scene_facts
from scripts.generate_presentation_explosion_v4 import (
    CAMERA_CLIP_END_MM,
    V4_VIEW_NAMES as RENDER_VIEW_NAMES,
    render_result_contract_v4,
)
from scripts.run_presentation_v4 import (
    blender_stage_succeeded,
    build_presentation_report_v4,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
UNRESOLVED_MEDIUM_IDS = {
    *(f"PART_{index:03d}" for index in range(23, 39)),
    *(f"PART_{index:03d}" for index in range(40, 46)),
}
SMALL_OR_FRAGMENT_IDS = {
    "PART_039",
    *(f"PART_{index:03d}" for index in range(46, 83)),
}


def test_v4_keeps_all_source_parts_but_shows_only_important_components():
    layout = build_presentation_layout_v4(PROJECT_ROOT)
    visible = [
        record
        for record in layout["parts"].values()
        if record["presentation_visibility"] == "VISIBLE"
    ]
    hidden = [
        record
        for record in layout["parts"].values()
        if record["presentation_visibility"] == "HIDDEN"
    ]

    assert list(layout["parts"]) == [f"PART_{index:03d}" for index in range(1, 83)]
    assert len(visible) == 22
    assert len(hidden) == 60
    assert {record["size_class"] for record in visible} <= {"MAJOR", "MEDIUM"}
    assert set(layout["assemblies"]) == {
        "ENCLOSURE_ASSEMBLY",
        "HANDLE_ASSEMBLY",
        "TOP_INTERFACE_ASSEMBLY",
        "PCB_ASSEMBLY",
        "SENSOR_ASSEMBLY",
        "BATTERY_ASSEMBLY",
        "LEVELING_ASSEMBLY",
    }


def test_v4_hides_unresolved_medium_parts_without_guessing_semantics():
    layout = build_presentation_layout_v4(PROJECT_ROOT)

    for part_id in UNRESOLVED_MEDIUM_IDS:
        record = layout["parts"][part_id]
        assert record["presentation_visibility"] == "HIDDEN"
        assert record["presentation_mode"] == "HIDDEN_UNRESOLVED_MEDIUM"
        assert record["presentation_parent"] is None
        assert record["semantic_name"] == "UNKNOWN"


def test_v4_excludes_unimportant_and_small_parts_from_review_queue():
    layout = build_presentation_layout_v4(PROJECT_ROOT)
    queued = {item["part_id"] for item in layout["review_queue"]}

    assert len(queued) == 22
    assert not queued.intersection(UNRESOLVED_MEDIUM_IDS)
    assert not queued.intersection(SMALL_OR_FRAGMENT_IDS)
    assert all(item["review_scope"] == "IMPORTANT_COMPONENT_LAYOUT_ONLY" for item in layout["review_queue"])


def test_v4_leveling_cones_use_a_clear_triangle_layout():
    layout = build_presentation_layout_v4(PROJECT_ROOT)
    assembly = layout["assemblies"]["LEVELING_ASSEMBLY"]
    offsets = {
        part_id: layout["parts"][part_id]["local_offset_mm"]
        for part_id in ("PART_020", "PART_021", "PART_022")
    }

    assert assembly["zone"] == "bottom"
    assert offsets["PART_020"][0] < 0 and offsets["PART_020"][1] < 0
    assert offsets["PART_021"][1] > 0
    assert offsets["PART_022"][0] > 0 and offsets["PART_022"][1] < 0
    assert len({tuple(offset) for offset in offsets.values()}) == 3
    assert assembly["zone_anchor_mm"][1] <= -200.0
    assert abs(offsets["PART_020"][0]) >= 150.0
    assert abs(offsets["PART_022"][0]) >= 150.0


def test_v4_rejects_non_v4_layouts():
    with pytest.raises(ValueError, match="v4"):
        validate_v4_layout({"layout_version": "v3"})


def test_v4_render_names_are_stable():
    assert V4_VIEW_NAMES == (
        "exploded_iso_front_v4",
        "exploded_iso_rear_v4",
        "exploded_front_v4",
        "exploded_top_v4",
    )
    assert RENDER_VIEW_NAMES == V4_VIEW_NAMES


def test_v4_render_contract_is_static():
    assert render_result_contract_v4({"animation_created": False})["animation_created"] is False


def test_v4_camera_clip_covers_layout():
    assert CAMERA_CLIP_END_MM >= 10000.0


def test_v4_report_focuses_on_visibility_and_layout_only():
    layout = build_presentation_layout_v4(PROJECT_ROOT)
    report = build_presentation_report_v4(layout, scene_result=None, render_result=None)

    assert "22 visible important parts" in report
    assert "60 hidden source parts" in report
    assert "No keyframes" in report
    assert "exploded_iso_front_v4.png" in report
    assert "realistic disassembly order" not in report.lower()


def test_v4_scene_facts_reject_unresolved_medium_visibility():
    facts = [
        {
            "part_id": f"PART_{index:03d}",
            "source": "original_stl",
            "type": "MESH",
            "hidden": index >= 23,
        }
        for index in range(1, 83)
    ]
    facts[22]["hidden"] = False
    with pytest.raises(ValueError, match="unresolved"):
        validate_v4_scene_facts(facts, vertices=221902, polygons=444296)


def test_v4_scene_facts_require_22_visible_important_parts():
    facts = [
        {
            "part_id": f"PART_{index:03d}",
            "source": "original_stl",
            "type": "MESH",
            "hidden": index > 22,
        }
        for index in range(1, 83)
    ]
    result = validate_v4_scene_facts(facts, vertices=221902, polygons=444296)
    assert result["visible_part_count"] == 22
    assert result["hidden_part_count"] == 60


def test_v4_input_scene_allows_stage02_visibility_before_policy_is_applied():
    facts = [
        {
            "part_id": f"PART_{index:03d}",
            "source": "original_stl",
            "type": "MESH",
            "hidden": False,
        }
        for index in range(1, 83)
    ]
    result = validate_v4_scene_facts(
        facts,
        vertices=221902,
        polygons=444296,
        require_visibility_policy=False,
    )
    assert result["source_part_count"] == 82


def test_blender_traceback_is_failure_even_with_zero_process_code():
    assert blender_stage_succeeded(0, "") is True
    assert blender_stage_succeeded(0, "Traceback (most recent call last):\nValueError") is False
    assert blender_stage_succeeded(1, "") is False
