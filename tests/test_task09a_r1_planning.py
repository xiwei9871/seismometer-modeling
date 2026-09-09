from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import math

import pytest

import stage_09A_R1_exploded_rework.scripts.analyze_assembly as analyze_module

from stage_09A_R1_exploded_rework.scripts.build_explosion_groups import (
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
EXPECTED_IMPORTANT_PART_IDS = tuple(f"PART_{index:03d}" for index in range(1, 23))
EXPECTED_GROUPS = {
    "MAIN_STACK": ("PART_001", "PART_002", "PART_004", "PART_005"),
    "SENSOR_BRANCH": ("PART_003", "PART_012", "PART_013", "PART_014"),
    "PCB_BRANCH": ("PART_006", "PART_007", "PART_019"),
    "BATTERY_BRANCH": (
        "PART_008", "PART_009", "PART_010", "PART_011", "PART_015", "PART_016"
    ),
    "TOP_INTERFACE_BRANCH": ("PART_017", "PART_018"),
    "LEVELING_BRANCH": ("PART_020", "PART_021", "PART_022"),
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
    assert {part["part_id"] for part in visible} == set(EXPECTED_IMPORTANT_PART_IDS)
    assert layout["layout_version"] == "r1"
    assert layout["mode"] == "STATIC_HIERARCHICAL_PRESENTATION_R1"
    assert layout["animation_created"] is False


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
        EXPECTED_IMPORTANT_PART_IDS
    )
    hidden_ids = {part["part_id"] for part in hidden}
    for key in ("motion_review_queue", "animation_queue", "collision_queue"):
        assert not set(layout.get(key, [])) & hidden_ids


def test_r1_groups_have_exact_approved_membership():
    layout = build_explosion_layout(PROJECT_ROOT)
    groups = layout["groups"]
    assert {
        group_id: tuple(groups[group_id]["part_ids"])
        for group_id in EXPECTED_GROUPS
    } == EXPECTED_GROUPS
    assigned = [part_id for members in EXPECTED_GROUPS.values() for part_id in members]
    assert sorted(assigned) == list(EXPECTED_IMPORTANT_PART_IDS)


def test_r1_presentation_locations_are_finite():
    layout = build_explosion_layout(PROJECT_ROOT)
    for part in layout["parts"].values():
        assert all(math.isfinite(float(value)) for value in part["presentation_location"])


def test_r1_validator_rejects_non_list_or_malformed_motion_queue():
    layout = build_explosion_layout(PROJECT_ROOT)
    layout["animation_queue"] = {"part_id": "PART_082"}
    with pytest.raises(ValueError):
        validate_explosion_layout(layout)

    layout = build_explosion_layout(PROJECT_ROOT)
    layout["animation_queue"] = [{"part_id": "PART_082"}]
    with pytest.raises(ValueError):
        validate_explosion_layout(layout)


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


def _analysis_fixture():
    root = PROJECT_ROOT / "data"
    manifest = json.loads((root / "parts_manifest.json").read_text(encoding="utf-8"))
    semantic = json.loads((root / "semantic_parts.json").read_text(encoding="utf-8"))
    initial = json.loads((root / "assembly_initial.json").read_text(encoding="utf-8"))
    return manifest, semantic, initial


@pytest.mark.parametrize(
    ("record_set", "field", "value"),
    [
        ("manifest", "face_count", True),
        ("manifest", "vertex_count", 1.0),
        ("manifest", "source_component_index", "64"),
        ("semantic", "semantic_name", 123),
        ("semantic", "semantic_category", 123),
        ("semantic", "confidence", 1),
        ("semantic", "confidence", "NOT_A_CONFIDENCE"),
        ("semantic", "evidence", "REF_EXT_001"),
        ("semantic", "evidence", ["REF_EXT_001", 1]),
    ],
)
def test_analysis_rejects_non_strict_source_and_semantic_types(
    monkeypatch, record_set, field, value
):
    manifest, semantic, initial = _analysis_fixture()
    records = manifest if record_set == "manifest" else semantic
    records[0][field] = value

    monkeypatch.setattr(
        analyze_module,
        "validate_task09_baseline",
        lambda _root: {
            "source_sha256": EXPECTED_SOURCE_BASELINE["source_sha256"],
            "source_parts": 82,
            "faces": 444296,
            "indexed_vertices": 221902,
        },
    )
    monkeypatch.setattr(analyze_module, "load_manifest", lambda _root: manifest)

    def fake_load_json(path):
        if Path(path).name == "semantic_parts.json":
            return semantic
        if Path(path).name == "assembly_initial.json":
            return initial
        raise AssertionError(path)

    monkeypatch.setattr(analyze_module, "load_json", fake_load_json)

    with pytest.raises(ValueError):
        analyze_module.analyze_assembled_state(PROJECT_ROOT)


def test_analysis_rejects_bbox_mismatch_and_nonfinite_values(monkeypatch):
    manifest, semantic, initial = _analysis_fixture()
    initial["objects"]["PART_001"]["bbox"]["x"] += 1.0

    monkeypatch.setattr(
        analyze_module,
        "validate_task09_baseline",
        lambda _root: {
            "source_sha256": EXPECTED_SOURCE_BASELINE["source_sha256"],
            "source_parts": 82,
            "faces": 444296,
            "indexed_vertices": 221902,
        },
    )
    monkeypatch.setattr(analyze_module, "load_manifest", lambda _root: manifest)

    def fake_load_json(path):
        if Path(path).name == "semantic_parts.json":
            return semantic
        if Path(path).name == "assembly_initial.json":
            return initial
        raise AssertionError(path)

    monkeypatch.setattr(analyze_module, "load_json", fake_load_json)
    with pytest.raises(ValueError, match="bbox"):
        analyze_module.analyze_assembled_state(PROJECT_ROOT)

    initial["objects"]["PART_001"]["bbox"]["x"] = True
    with pytest.raises(ValueError, match="bbox"):
        analyze_module.analyze_assembled_state(PROJECT_ROOT)


@pytest.mark.parametrize(
    "queue_value",
    [
        None,
        ("PART_001",),
        [123],
        [{}],
        [{"part_id": 123}],
        ["PART_023"],
        [{"part_id": "PART_023"}],
        ["NOT_A_PART"],
    ],
)
def test_layout_rejects_invalid_or_hidden_review_queues(queue_value):
    layout = deepcopy(build_explosion_layout(PROJECT_ROOT))
    layout["motion_review_queue"] = queue_value
    with pytest.raises(ValueError):
        validate_explosion_layout(layout)


def test_layout_accepts_string_and_mapping_queue_items_for_visible_parts():
    layout = deepcopy(build_explosion_layout(PROJECT_ROOT))
    layout["motion_review_queue"] = ["PART_001", {"part_id": "PART_002"}]
    assert validate_explosion_layout(layout)["motion_review_queue"] == layout[
        "motion_review_queue"
    ]
