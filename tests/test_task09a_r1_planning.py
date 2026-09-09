from __future__ import annotations

from pathlib import Path

from stage_09A_R1_exploded_rework.scripts.build_explosion_groups import (
    IMPORTANT_PART_IDS,
    build_explosion_layout,
    validate_explosion_layout,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_SOURCE_BASELINE = {
    "source_parts": 82,
    "faces": 444296,
    "indexed_vertices": 221902,
    "source_sha256": "fd2a7b78540245fd098724206d5ddf169fd2f44c07638e9a6459cd92fea717d1",
}


def test_r1_preserves_82_source_parts_but_shows_only_22_important_parts():
    layout = build_explosion_layout(PROJECT_ROOT)

    assert list(layout["parts"]) == [f"PART_{index:03d}" for index in range(1, 83)]
    visible = [
        part
        for part in layout["parts"].values()
        if part["presentation_visibility"] == "VISIBLE"
    ]
    assert len(visible) == 22
    assert {part["part_id"] for part in visible} == set(IMPORTANT_PART_IDS)


def test_r1_main_stack_shares_part_001_xy_and_increases_strictly_on_z():
    layout = build_explosion_layout(PROJECT_ROOT)
    parts = layout["parts"]
    anchor = parts["PART_001"]["presentation_location"]

    for part_id in ("PART_002", "PART_004", "PART_005"):
        location = parts[part_id]["presentation_location"]
        assert abs(location[0] - anchor[0]) < 1e-6
        assert abs(location[1] - anchor[1]) < 1e-6

    stack_z = [
        parts[part_id]["presentation_location"][2]
        for part_id in ("PART_001", "PART_002", "PART_004", "PART_005")
    ]
    assert stack_z == sorted(stack_z)
    assert len(set(stack_z)) == len(stack_z)


def test_r1_leveling_parts_stay_near_assembled_xy_and_move_downward():
    layout = build_explosion_layout(PROJECT_ROOT)

    for part_id in ("PART_020", "PART_021", "PART_022"):
        part = layout["parts"][part_id]
        original = part["assembled_location"]
        shown = part["presentation_location"]
        assert abs(shown[0] - original[0]) <= 80.0
        assert abs(shown[1] - original[1]) <= 80.0
        assert shown[2] < original[2]


def test_r1_hidden_parts_are_excluded_from_review_and_collision_scope():
    layout = build_explosion_layout(PROJECT_ROOT)
    hidden = [
        part
        for part in layout["parts"].values()
        if part["presentation_visibility"] == "HIDDEN"
    ]

    assert len(hidden) == 60
    assert all(part["review_scope"] is None for part in hidden)
    assert all(part["collision_scope"] is False for part in hidden)
    assert {item["part_id"] for item in layout["review_queue"]} == set(
        IMPORTANT_PART_IDS
    )


def test_r1_layout_is_deterministic_and_matches_the_frozen_static_baseline():
    first = validate_explosion_layout(build_explosion_layout(PROJECT_ROOT))
    second = validate_explosion_layout(build_explosion_layout(PROJECT_ROOT))

    assert first == second
    assert first["source_baseline"] == {
        "source_parts": EXPECTED_SOURCE_BASELINE["source_parts"],
        "faces": EXPECTED_SOURCE_BASELINE["faces"],
        "indexed_vertices": EXPECTED_SOURCE_BASELINE["indexed_vertices"],
    }
    assert first["source_sha256"] == EXPECTED_SOURCE_BASELINE["source_sha256"]
    assert first["animation_created"] is False
