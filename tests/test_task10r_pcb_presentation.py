"""Contract tests for the Task 10-R-PCB-V1 presentation PCB layer."""

from __future__ import annotations

from pathlib import Path

import pytest

from stage_10R_pcb_presentation.scripts import pcb_presentation_data as data


PROJECT_ROOT = Path(__file__).resolve().parents[1]


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


def test_planner_moves_board_to_dedicated_zone(tmp_path):
    from stage_10R_pcb_presentation.scripts.build_presentation_plan import (
        build_presentation_manifest,
    )

    manifest = build_presentation_manifest(PROJECT_ROOT)
    board = manifest["part_transforms"]["PART_019"]
    plate = manifest["part_transforms"]["PART_006"]
    frame = manifest["part_transforms"]["PART_007"]
    zone = manifest["board_zone_center_mm"]
    # Board and plate move +175 mm in X at assembled Z; frame stays assembled.
    assert board["location"][0] == pytest.approx(zone[0])
    assert board["location"][2] == pytest.approx(zone[2])
    assert plate["location"][2] < board["location"][2]
    assert frame["location"][0] == pytest.approx(zone[0] - 175.0, abs=1.0)
    assert manifest["component_count"] == len(manifest["components"])
    for component in manifest["components"]:
        # Components sit on the board top surface in the inspection zone.
        assert component["world_location"][2] > board["location"][2]
        assert component["world_location"][0] == pytest.approx(
            zone[0] + component["center_xy_mm"][0]
        )
        assert component["mounted_on"] == "PART_019"


def test_planner_manifest_registry_and_provenance():
    from stage_10R_pcb_presentation.scripts.build_presentation_plan import (
        build_presentation_manifest,
    )

    manifest = build_presentation_manifest(PROJECT_ROOT)
    assert set(manifest["part_transforms"]) == set(data.STORY_PART_IDS)
    assert manifest["part_reclassification"]["PART_007"]["presentation_priority"] == "SUPPORT"
    hierarchy = manifest["presentation_hierarchy"]["MAIN_PCB_PRESENTATION"]
    assert "PART_019" in hierarchy["members"]
    assert len(hierarchy["members"]) == 1 + manifest["component_count"]
    refs = manifest["reference_images"]
    assert refs["REF_PCB_002"]["role"] == "primary_layout"


def test_camera_plan_frames_board_and_context():
    from stage_10R_pcb_presentation.scripts.build_presentation_plan import (
        build_presentation_cameras,
    )

    cameras = build_presentation_cameras(PROJECT_ROOT)["cameras"]
    assert set(cameras) == {"CAM_PCB_CLEAN", "CAM_PCB_TOP", "CAM_PCB_CONTEXT"}
    # Context camera must frame the device too: farther than the clean camera.
    assert cameras["CAM_PCB_CONTEXT"]["camera_distance_mm"] > cameras["CAM_PCB_CLEAN"]["camera_distance_mm"]
    # Clean camera looks at the inspection zone, not the device.
    assert cameras["CAM_PCB_CLEAN"]["target"][0] > 200.0


def test_surface_texture_is_deterministic(tmp_path):
    from stage_10R_pcb_presentation.scripts.generate_surface_texture import (
        generate_surface_texture,
    )

    first = generate_surface_texture(PROJECT_ROOT).read_bytes()
    second = generate_surface_texture(PROJECT_ROOT).read_bytes()
    assert first == second
    from PIL import Image
    import io

    image = Image.open(io.BytesIO(first))
    assert image.size == (1024, 1024)


def test_reference_manifest_entries_exist():
    refs = data.build_reference_manifest()
    root = Path(__file__).resolve().parents[1]
    for ref in refs.values():
            assert (root / ref["path"]).is_file()
            assert len(ref["sha256"]) == 64
            assert ref["role"] in {"primary_layout", "detail_supplement"}
