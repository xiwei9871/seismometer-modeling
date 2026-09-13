"""Contract tests for the Task 10-R-PCB-V1 presentation PCB layer."""

from __future__ import annotations

from pathlib import Path

import pytest

from stage_10R_pcb_presentation.scripts import pcb_presentation_data as data


def test_frozen_baseline_and_source_scene():
    assert data.BASELINE == {
        "source_part_count": 82,
        "faces": 444296,
        "indexed_vertices": 221902,
    }
    assert data.SOURCE_SCENE.endswith("exploded_animation_preview.blend")
    assert len(data.SOURCE_SCENE_SHA256) == 64
    assert len(data.EXPECTED_PART_IDS) == 82


def test_component_plan_matches_reference_driven_contract():
    components = data.build_component_plan()
    assert 8 <= len(components) <= 16
    ids = [component["component_id"] for component in components]
    assert len(ids) == len(set(ids))
    assert all(component["component_id"].startswith("PCB_COMP_") for component in components)
    shapes = {component["shape"] for component in components}
    assert shapes <= {"bevel_box", "cylinder"}
    # Reference-driven roles: long connectors, shield cans, caps, IC rows.
    roles = {component["visual_role"] for component in components}
    assert {"connector", "shield", "capacitor", "ic"} <= roles
    for component in components:
        assert component["reference_source"].startswith("REF_PCB_")
        assert component["source"] == "photographic_presentation_reconstruction"


def test_component_footprints_respect_board_keepout():
    margin = data.BOARD_EDGE_MARGIN_MM
    for component in data.build_component_plan():
        for corner in data.component_footprint_corners(component):
            x, y = corner
            assert abs(x) <= data.BOARD_HALF_EXTENT_MM - margin
            assert abs(y) <= data.BOARD_HALF_EXTENT_MM - margin
            assert abs(x) + abs(y) <= data.BOARD_DIAGONAL_LIMIT_MM - margin


def test_component_footprints_do_not_overlap():
    components = data.build_component_plan()
    for index, left in enumerate(components):
        left_rect = data.component_footprint_rect(left)
        for right in components[index + 1:]:
            right_rect = data.component_footprint_rect(right)
            assert not data.rects_intersect(left_rect, right_rect), (
                left["component_id"],
                right["component_id"],
            )


def test_part007_demotion_contract():
    demotion = data.build_part_reclassification()["PART_007"]
    assert demotion["presentation_priority"] == "SUPPORT"
    assert demotion["independent_focus"] is False
    assert demotion["follow_parent"] == "PCB_ASSEMBLY"
    assert demotion["functional_importance"] == "LOW"
    assert demotion["presentation_weight"] == pytest.approx(0.10)


def test_presentation_hierarchy_weights():
    weights = data.build_presentation_hierarchy()
    assert weights["MAIN_PCB_PRESENTATION"]["tier"] == "HERO"
    assert weights["MAIN_PCB_PRESENTATION"]["presentation_weight"] == pytest.approx(0.75)
    assert weights["PART_006"]["tier"] == "SECONDARY"
    assert weights["PART_006"]["presentation_weight"] == pytest.approx(0.15)
    assert weights["PART_007"]["tier"] == "SUPPORT"
    assert weights["PART_007"]["presentation_weight"] == pytest.approx(0.10)


def test_visibility_policy_per_view():
    policy = data.build_view_visibility_policy()
    assert policy["clean"]["hidden"] == ["PART_006", "PART_007"]
    assert "PART_007" not in policy["top"]["visible_focus"]
    assert policy["context"]["support_visible"] is True
    assert policy["context"]["secondary_visible"] is True


def test_camera_contract():
    cameras = data.build_camera_contract()
    assert set(cameras) == {"CAM_PCB_CLEAN", "CAM_PCB_TOP", "CAM_PCB_CONTEXT"}
    for camera in cameras.values():
        assert camera["projection"] == "PERSP"


def test_required_outputs_contract():
    assert data.REQUIRED_RENDERS == (
        "pcb_presentation_clean.png",
        "pcb_presentation_context.png",
        "pcb_presentation_top.png",
    )
    assert data.COMPARISON_RENDER == "pcb_presentation_reference_comparison.png"
    assert data.SCENE_OUTPUT.endswith("pcb_presentation_assembly.blend")


def test_status_contract():
    status = data.build_status_contract()
    assert status["technical_status"] == "PASS"
    assert status["visual_status"] == "PENDING_HUMAN_REVIEW"
    assert status["overall_status"] == "REVIEW_REQUIRED"


def test_reference_manifest_entries_exist():
    refs = data.build_reference_manifest()
    root = Path(__file__).resolve().parents[1]
    for ref in refs.values():
            assert (root / ref["path"]).is_file()
            assert len(ref["sha256"]) == 64
            assert ref["role"] in {"primary_layout", "detail_supplement"}
