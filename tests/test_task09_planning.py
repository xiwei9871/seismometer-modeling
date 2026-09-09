from __future__ import annotations

from pathlib import Path

import pytest

from scripts.task09_planning import (
    build_exploded_state,
    build_explosion_guides,
    build_disassembly_graph,
    build_fastener_group_mapping,
    build_future_visual_assets,
    build_explosion_review_queue,
    check_swept_aabb_collisions,
    kahn_topological_sort,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_disassembly_graph_contains_all_semantic_and_virtual_nodes_in_stable_dag_order():
    graph = build_disassembly_graph(PROJECT_ROOT)

    assert graph["directed_acyclic"] is True
    node_ids = [node["node_id"] for node in graph["nodes"]]
    assert node_ids == sorted(node_ids)
    assert graph["topological_order"] == kahn_topological_sort(
        node_ids, graph["edges"]
    )
    assert {node["kind"] for node in graph["nodes"]} == {
        "semantic_group",
        "virtual_group",
    }
    assert {node["node_id"] for node in graph["nodes"]} >= {
        "EXTERNAL_HOUSING_FASTENERS",
        "PCB_FASTENERS",
    }
    assert len({part_id for node in graph["nodes"] for part_id in node["parts"]}) == 82


def test_disassembly_graph_preserves_current_task08_dependency_edges_and_evidence():
    graph = build_disassembly_graph(PROJECT_ROOT)

    upper_to_pcb = next(
        edge
        for edge in graph["edges"]
        if edge["before"] == "UPPER_HOUSING" and edge["after"] == "MAIN_PCB"
    )
    assert upper_to_pcb["confidence"] == "LOW"
    assert upper_to_pcb["requires_manual_confirmation"] is True
    assert upper_to_pcb["evidence"] == ["REF_EXT_003"]

    fixture_to_sensor = next(
        edge
        for edge in graph["edges"]
        if edge["before"] == "TRI_AXIS_SENSOR_FIXTURE"
        and edge["after"] == "SENSOR_CORE_FIXTURE_X"
    )
    assert fixture_to_sensor["confidence"] == "MEDIUM"
    assert fixture_to_sensor["requires_manual_confirmation"] is True


def test_kahn_topological_sort_rejects_a_cycle():
    with pytest.raises(ValueError, match="cycle"):
        kahn_topological_sort(
            ["A", "B"],
            [
                {"before": "A", "after": "B"},
                {"before": "B", "after": "A"},
            ],
        )


def test_fastener_mapping_preserves_dg011_members_quantity_and_representative():
    mapping = build_fastener_group_mapping(PROJECT_ROOT)

    assert [group["group_id"] for group in mapping["groups"]] == sorted(
        group["group_id"] for group in mapping["groups"]
    )
    dg011 = next(group for group in mapping["groups"] if group["group_id"] == "DG_011")
    assert dg011["quantity"] == 29
    assert dg011["member_parts"] == [f"PART_{index:03d}" for index in range(44, 73)]
    assert dg011["representative_part"] == "PART_044"
    assert dg011["signature"]["volume"] == pytest.approx(115.69350058370765)
    assert dg011["motion_policy"] in {"GROUP_LINEAR", "UNASSIGNED"}
    assert dg011["confidence"] in {"HIGH", "MEDIUM", "LOW", "UNKNOWN"}
    assert dg011["reason"]


def test_task09_planning_outputs_are_deterministic():
    assert build_disassembly_graph(PROJECT_ROOT) == build_disassembly_graph(PROJECT_ROOT)
    assert build_fastener_group_mapping(PROJECT_ROOT) == build_fastener_group_mapping(
        PROJECT_ROOT
    )


def test_exploded_state_covers_all_parts_and_preserves_assembled_values():
    state = build_exploded_state(PROJECT_ROOT)

    assert state["state"] == "EXPLODED"
    assert state["source_baseline"] == {
        "source_parts": 82,
        "faces": 444296,
        "indexed_vertices": 221902,
    }
    assert list(state["parts"]) == [f"PART_{index:03d}" for index in range(1, 83)]
    assert state["parts"]["PART_004"]["explode_vector"] == [0.0, 0.0, 1.0]
    assert state["parts"]["PART_004"]["motion_type"] == "LINEAR"
    assert state["parts"]["PART_004"]["explode_distance_mm"] > 0
    assert state["parts"]["PART_004"]["exploded_location"] != state["parts"]["PART_004"]["assembled_location"]


def test_group_members_share_axis_and_small_parts_are_reviewable():
    state = build_exploded_state(PROJECT_ROOT)

    assert state["parts"]["PART_020"]["explode_vector"] == state["parts"]["PART_021"]["explode_vector"]
    assert state["parts"]["PART_022"]["confidence"] == "MEDIUM"
    assert state["parts"]["PART_039"]["requires_manual_confirmation"] is True
    assert 20 <= state["parts"]["PART_039"]["explode_distance_mm"] <= 60


def test_collision_check_reports_new_overlaps_not_initial_touching():
    records = [
        {
            "part_id": "PART_A",
            "assembled_location": [0.0, 0.0, 0.0],
            "exploded_location": [0.0, 0.0, 20.0],
            "bbox_dimensions_mm": [10.0, 10.0, 10.0],
        },
        {
            "part_id": "PART_B",
            "assembled_location": [0.0, 0.0, 30.0],
            "exploded_location": [0.0, 0.0, 10.0],
            "bbox_dimensions_mm": [10.0, 10.0, 10.0],
        },
    ]

    result = check_swept_aabb_collisions(records)

    assert result["checked_samples"] == [0.0, 0.25, 0.5, 0.75, 1.0]
    assert "collisions" in result
    assert result["collision_count"] == 1
    assert result["collisions"][0]["sample_t"] == 0.75
    assert all("part_a" in item and "part_b" in item and "sample_t" in item for item in result["collisions"])
    assert all("group_a" in item and "group_b" in item for item in result["collisions"])


def test_collision_check_ignores_initial_contact_and_initial_overlap():
    touching = [
        {"part_id": "PART_A", "assembled_location": [0, 0, 0], "exploded_location": [0, 0, 0], "bbox_dimensions_mm": [10, 10, 10]},
        {"part_id": "PART_B", "assembled_location": [0, 0, 10], "exploded_location": [0, 0, 30], "bbox_dimensions_mm": [10, 10, 10]},
    ]
    assert check_swept_aabb_collisions(touching)["collision_count"] == 0

    initial_overlap = [
        {"part_id": "PART_A", "assembled_location": [0, 0, 0], "exploded_location": [0, 0, 20], "bbox_dimensions_mm": [10, 10, 10]},
        {"part_id": "PART_B", "assembled_location": [0, 0, 4], "exploded_location": [0, 0, 40], "bbox_dimensions_mm": [10, 10, 10]},
    ]
    result = check_swept_aabb_collisions(initial_overlap)
    assert result["initial_overlap_pair_count"] == 1
    assert result["collision_count"] == 0


@pytest.mark.parametrize(
    "bad_record",
    [
        {"part_id": "PART_A", "assembled_location": [float("nan"), 0, 0], "exploded_location": [0, 0, 0], "bbox_dimensions_mm": [1, 1, 1]},
        {"part_id": "PART_A", "assembled_location": [0, 0, 0], "exploded_location": [0, 0, 0], "bbox_dimensions_mm": [True, 1, 1]},
    ],
)
def test_collision_check_rejects_non_finite_and_boolean_values(bad_record):
    with pytest.raises(ValueError, match="finite numbers"):
        check_swept_aabb_collisions([bad_record])


def test_collision_check_rejects_duplicate_part_ids():
    record = {"part_id": "PART_A", "assembled_location": [0, 0, 0], "exploded_location": [0, 0, 0], "bbox_dimensions_mm": [1, 1, 1]}
    with pytest.raises(ValueError, match="duplicate"):
        check_swept_aabb_collisions([record, dict(record)])


def test_guides_future_assets_and_review_queue_are_deterministic():
    state = build_exploded_state(PROJECT_ROOT)
    guides = build_explosion_guides(state)
    assets = build_future_visual_assets(PROJECT_ROOT)
    queue = build_explosion_review_queue(state)

    assert len(guides["guides"]) == 82
    assert guides["guides"][0]["source"] == "PART_001"
    assert assets["features"]
    queued_parts = {item["part"] for item in queue}
    assert {"PART_017", "PART_018", "PART_022", "PART_082"} <= queued_parts
    assert all("review_question" in item for item in queue)


def test_group_motion_preserves_common_translation_distance():
    state = build_exploded_state(PROJECT_ROOT)
    for part_ids in (
        [f"PART_{index:03d}" for index in range(8, 12)]
        + ["PART_015", "PART_016"],
        ["PART_012", "PART_013", "PART_014"],
        ["PART_020", "PART_021", "PART_022"],
    ):
        records = [state["parts"][part_id] for part_id in part_ids]
        assert len({tuple(record["explode_vector"]) for record in records}) == 1
        assert len({record["explode_distance_mm"] for record in records}) == 1


def test_explosion_guides_include_group_targets():
    guides = build_explosion_guides(build_exploded_state(PROJECT_ROOT))
    guide = next(item for item in guides["guides"] if item["source"] == "PART_019")
    assert guide["source_part"] == "PART_019"
    assert guide["target_group"] == "PCB_ASSEMBLY"
