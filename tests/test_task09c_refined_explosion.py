from __future__ import annotations

from pathlib import Path

import pytest

from scripts.task08_data import load_json
from stage_09C_refined_explosion.scripts.build_animation_preview import (
    build_animation_plan,
    iter_action_fcurves,
    validate_animation_plan,
)
from stage_09C_refined_explosion.scripts.build_refined_layout import (
    build_refined_layout,
    validate_refined_layout,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_IDS = [f"PART_{index:03d}" for index in range(1, 83)]
VISIBLE_IDS = [f"PART_{index:03d}" for index in range(1, 23)]


def test_refined_layout_preserves_all_source_parts_and_only_presents_important_parts():
    layout = build_refined_layout(PROJECT_ROOT)

    assert list(layout["parts"]) == EXPECTED_IDS
    assert [
        part_id
        for part_id, record in layout["parts"].items()
        if record["presentation_visibility"] == "VISIBLE"
    ] == VISIBLE_IDS
    assert layout["source_baseline"] == {
        "source_parts": 82,
        "faces": 444296,
        "indexed_vertices": 221902,
    }
    assert layout["animation_created"] is False
    assert validate_refined_layout(layout) == layout


def test_refined_main_stack_spacing_is_larger_than_r1():
    refined = build_refined_layout(PROJECT_ROOT)["parts"]
    r1 = load_json(
        PROJECT_ROOT / "stage_09A_R1_exploded_rework/config/explosion_layout_config.json"
    )["parts"]

    for left_id, right_id in (
        ("PART_001", "PART_002"),
        ("PART_002", "PART_004"),
        ("PART_004", "PART_005"),
    ):
        refined_gap = _z_gap(refined[left_id], refined[right_id])
        r1_gap = _z_gap(r1[left_id], r1[right_id], location_key="presentation_location")
        assert refined_gap > r1_gap


def test_refined_keeps_leveling_xy_and_moves_feet_further_down():
    refined = build_refined_layout(PROJECT_ROOT)["parts"]
    r1 = load_json(
        PROJECT_ROOT / "stage_09A_R1_exploded_rework/config/explosion_layout_config.json"
    )["parts"]

    for part_id in ("PART_020", "PART_021", "PART_022"):
        assert refined[part_id]["refined_presentation_location"][:2] == pytest.approx(
            r1[part_id]["presentation_location"][:2]
        )
        assert refined[part_id]["refined_presentation_location"][2] < r1[part_id]["presentation_location"][2]


def test_animation_plan_is_review_length_and_excludes_hidden_parts():
    plan = build_animation_plan(PROJECT_ROOT)

    assert plan["fps"] == 30
    assert plan["frame_range"] == [1, 540]
    assert 15.0 <= plan["total_duration_seconds"] <= 22.0
    assert plan["easing"] == "BEZIER_EASE_IN_OUT"
    assert plan["overshoot"] is False
    assert len(plan["animated_part_ids"]) == 22
    assert not set(plan["animated_part_ids"]) & set(plan["hidden_part_ids"])
    assert validate_animation_plan(plan) == plan


def test_action_curve_iterator_supports_blender_52_layered_actions():
    class Bag:
        fcurves = ["x", "y"]

    class Strip:
        channelbags = [Bag()]

    class Layer:
        strips = [Strip()]

    class Action:
        layers = [Layer()]

    assert list(iter_action_fcurves(Action())) == ["x", "y"]


def _z_gap(left, right, *, location_key="refined_presentation_location"):
    left_z = float(left[location_key][2])
    right_z = float(right[location_key][2])
    left_h = float(left["bbox_dimensions_mm"][2])
    right_h = float(right["bbox_dimensions_mm"][2])
    return abs(right_z - left_z) - (left_h + right_h) / 2.0
