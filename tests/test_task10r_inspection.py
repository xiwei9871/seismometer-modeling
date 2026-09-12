from __future__ import annotations

from pathlib import Path

import pytest

from stage_10R_functional_inspection.scripts.inspection_data import (
    BASELINE,
    EXPECTED_PART_IDS,
    HIDDEN_PART_IDS,
    INSPECTION_STATE_IDS,
    STORY_PART_IDS,
    build_inspection_states,
    build_inspection_camera_contract,
    build_module_groups,
    build_status_contract,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_task10r_has_frozen_baseline_and_preserves_all_source_parts():
    assert BASELINE == {"source_part_count": 82, "faces": 444296, "indexed_vertices": 221902}
    assert len(EXPECTED_PART_IDS) == 82
    assert STORY_PART_IDS == tuple(f"PART_{index:03d}" for index in range(1, 23))
    assert HIDDEN_PART_IDS == tuple(f"PART_{index:03d}" for index in range(23, 83))


def test_task10r_macro_modules_cover_exactly_the_22_visible_story_parts():
    modules = build_module_groups()
    assert list(modules) == ["MODULE_A", "MODULE_B", "MODULE_C", "MODULE_D"]
    members = [part_id for module in modules.values() for part_id in module["part_ids"]]
    assert len(members) == 22
    assert len(set(members)) == 22
    assert modules["MODULE_A"]["part_ids"] == [
        "PART_002", "PART_004", "PART_005", "PART_017", "PART_018"
    ]
    assert modules["MODULE_B"]["part_ids"] == [
        "PART_006", "PART_007", "PART_019", "PART_008", "PART_009",
        "PART_010", "PART_011", "PART_015", "PART_016",
    ]
    assert modules["MODULE_C"]["part_ids"] == [
        "PART_003", "PART_012", "PART_013", "PART_014"
    ]
    assert modules["MODULE_D"]["part_ids"] == [
        "PART_001", "PART_020", "PART_021", "PART_022"
    ]


def test_task10r_defines_only_four_subtitle_free_inspection_states():
    states = build_inspection_states()
    assert list(states) == list(INSPECTION_STATE_IDS)
    assert all(state["text_policy"] == "NO_TEXT" for state in states.values())
    assert all(state["animation_policy"] == "NO_KEYFRAMES" for state in states.values())
    assert all(state["camera_id"] for state in states.values())
    assert states["STATE_01_PRIMARY_ARCHITECTURE"]["hero_output"] == "01_primary_architecture_hero.png"
    assert states["STATE_02_SENSOR_INSPECTION"]["hero_output"] == "02_sensor_inspection_clean.png"
    assert states["STATE_03_PCB_INSPECTION"]["hero_output"] == "03_pcb_inspection_clean.png"
    assert states["STATE_04_POWER_INSPECTION"]["hero_output"] == "04_power_inspection_clean.png"


def test_task10r_status_separates_technical_and_visual_review():
    contract = build_status_contract()
    assert contract == {
        "technical_status": "PASS",
        "visual_status": "PENDING_HUMAN_REVIEW",
        "overall_status": "REVIEW_REQUIRED",
    }


def test_task10r_planner_uses_frozen_9c_layout_and_not_task10_state_transforms():
    from stage_10R_functional_inspection.scripts.build_inspection_plan import build_inspection_plan

    plan = build_inspection_plan(PROJECT_ROOT)
    assert plan["source_layout"] == "stage_09C_refined_explosion/config/refined_layout.json"
    assert "stage_10_product_story/config/state_transforms.json" not in str(plan)
    assert plan["source_baseline"] == BASELINE
    assert set(plan["states"]) == set(INSPECTION_STATE_IDS)
    for state in plan["states"].values():
        assert list(state["parts"]) == list(STORY_PART_IDS)


def test_task10r_state_planner_keeps_primary_layers_and_power_cells_structured():
    from stage_10R_functional_inspection.scripts.build_inspection_plan import build_inspection_plan

    plan = build_inspection_plan(PROJECT_ROOT)
    primary = plan["states"]["STATE_01_PRIMARY_ARCHITECTURE"]
    assert primary["module_layout"] == ["MODULE_A", "MODULE_B", "MODULE_C", "MODULE_D"]
    sensor = plan["states"]["STATE_02_SENSOR_INSPECTION"]
    assert sensor["local_axes"] == {"PART_012": "X", "PART_013": "Y", "PART_014": "Z"}
    pcb = plan["states"]["STATE_03_PCB_INSPECTION"]
    assert pcb["layer_order"] == ["PART_006", "PART_019", "PART_007"]
    power = plan["states"]["STATE_04_POWER_INSPECTION"]
    assert power["array_shape"] == [3, 2]


def test_task10r_diagnostics_never_claim_visual_approval():
    from stage_10R_functional_inspection.scripts.build_inspection_plan import build_inspection_plan

    plan = build_inspection_plan(PROJECT_ROOT)
    assert plan["visual_status"] == "PENDING_HUMAN_REVIEW"
    assert all("module_screen_occupancy" in state["diagnostics"] for state in plan["states"].values())
    assert all("projected_overlap_ratio" in state["diagnostics"] for state in plan["states"].values())


def test_task10r_has_independent_cameras_for_primary_and_each_focus_state():
    cameras = build_inspection_camera_contract()
    assert cameras["CAM_INSPECTION_PRIMARY_HERO"]["lens_mm"] == 65
    assert cameras["CAM_INSPECTION_SENSOR_CLEAN"]["lens_mm"] == 60
    assert cameras["CAM_INSPECTION_PCB_CLEAN"]["lens_mm"] == 60
    assert cameras["CAM_INSPECTION_POWER_CLEAN"]["lens_mm"] == 60
    assert len({record["name"] for record in cameras.values()}) == len(cameras)


def test_task10r_scene_builder_declares_four_independent_scene_outputs():
    from stage_10R_functional_inspection.scripts.build_inspection_scenes import SCENE_OUTPUTS

    assert list(SCENE_OUTPUTS) == list(INSPECTION_STATE_IDS)
    assert all(path.endswith(".blend") for path in SCENE_OUTPUTS.values())


def test_task10r_render_contract_has_clean_context_and_top_outputs():
    from stage_10R_functional_inspection.scripts.render_inspection_states import REQUIRED_RENDERS

    assert REQUIRED_RENDERS == (
        "01_primary_architecture_hero.png",
        "01_primary_architecture_front.png",
        "01_primary_architecture_side.png",
        "02_sensor_inspection_clean.png",
        "02_sensor_inspection_context.png",
        "02_sensor_inspection_top.png",
        "03_pcb_inspection_clean.png",
        "03_pcb_inspection_context.png",
        "03_pcb_inspection_top.png",
        "04_power_inspection_clean.png",
        "04_power_inspection_context.png",
    )


def test_task10r_contact_sheet_contains_only_the_four_clean_states():
    from stage_10R_functional_inspection.scripts.compose_inspection_contact_sheet import CONTACT_SHEET_INPUTS

    assert CONTACT_SHEET_INPUTS == (
        "01_primary_architecture_hero.png",
        "02_sensor_inspection_clean.png",
        "03_pcb_inspection_clean.png",
        "04_power_inspection_clean.png",
    )


def test_task10r_validation_contract_keeps_visual_review_pending():
    from stage_10R_functional_inspection.scripts.validate_inspection import REQUIRED_SCENE_STATES

    assert REQUIRED_SCENE_STATES == tuple(INSPECTION_STATE_IDS)


def test_task10r_pipeline_can_never_auto_approve_visual_quality():
    from stage_10R_functional_inspection.scripts.pipeline import status_from_technical

    assert status_from_technical(True) == {
        "technical_status": "PASS",
        "visual_status": "PENDING_HUMAN_REVIEW",
        "overall_status": "REVIEW_REQUIRED",
    }
    assert status_from_technical(False) == {
        "technical_status": "FAIL",
        "visual_status": "PENDING_HUMAN_REVIEW",
        "overall_status": "FAIL",
    }


def test_task10r_clean_and_top_renders_suppress_context_geometry():
    from stage_10R_functional_inspection.scripts.render_inspection_states import show_context_for_render

    assert show_context_for_render("02_sensor_inspection_clean.png") is False
    assert show_context_for_render("02_sensor_inspection_top.png") is False
    assert show_context_for_render("03_pcb_inspection_clean.png") is False
    assert show_context_for_render("04_power_inspection_clean.png") is False
    assert show_context_for_render("02_sensor_inspection_context.png") is True


def test_task10r_focus_cameras_use_full_3d_bounds_and_safe_perspective_distance():
    from stage_10R_functional_inspection.scripts.build_inspection_plan import build_inspection_cameras

    cameras = build_inspection_cameras(PROJECT_ROOT)["cameras"]
    for name in (
        "CAM_INSPECTION_PRIMARY_HERO",
        "CAM_INSPECTION_SENSOR_CLEAN",
        "CAM_INSPECTION_PCB_CLEAN",
        "CAM_INSPECTION_POWER_CLEAN",
    ):
        record = cameras[name]
        assert record["framing_method"] == "PERSPECTIVE_BOUNDING_SPHERE"
        assert record["framing_margin"] >= 1.15
        assert record["camera_distance_mm"] >= 700.0


def test_task10r_primary_architecture_has_real_layer_clearance():
    from stage_10R_functional_inspection.scripts.build_inspection_plan import build_inspection_plan, _bounds

    plan = build_inspection_plan(PROJECT_ROOT)
    state = plan["states"]["STATE_01_PRIMARY_ARCHITECTURE"]
    layout = __import__("json").loads((PROJECT_ROOT / "stage_09C_refined_explosion/config/refined_layout.json").read_text())
    dimensions = {part_id: layout["parts"][part_id]["bbox_dimensions_mm"] for part_id in state["parts"]}
    modules = build_module_groups()
    bounds = {
        module_id: _bounds(state["parts"], dimensions, module["part_ids"])
        for module_id, module in modules.items()
    }
    assert bounds["MODULE_A"]["z_min"] - bounds["MODULE_B"]["z_max"] >= 50.0
    assert bounds["MODULE_B"]["z_min"] - bounds["MODULE_C"]["z_max"] >= 50.0
    assert bounds["MODULE_C"]["z_min"] - bounds["MODULE_D"]["z_max"] >= 40.0


def test_task10r_screen_space_overlap_helper_is_bounded_and_symmetric():
    from stage_10R_functional_inspection.scripts.validate_inspection import rect_overlap_ratio

    left = {"x_min": 0.0, "x_max": 0.5, "y_min": 0.0, "y_max": 0.5}
    right = {"x_min": 0.25, "x_max": 0.75, "y_min": 0.25, "y_max": 0.75}
    assert rect_overlap_ratio(left, right) == rect_overlap_ratio(right, left)
    assert 0.0 < rect_overlap_ratio(left, right) < 1.0
    assert rect_overlap_ratio(left, left) == 1.0


def test_task10r_pipeline_json_parser_accepts_large_validation_payloads():
    import json
    from stage_10R_functional_inspection.scripts.pipeline import _last_json

    payload = {"technical_status": "PASS", "projected_rects": {str(index): [index] * 8 for index in range(1000)}}
    encoded = json.dumps(payload)
    assert len(encoded) > 8000
    assert _last_json("Blender log\n" + encoded + "\n") == payload


def test_task10r_review_report_exposes_visual_gate_and_diagnostics():
    from stage_10R_functional_inspection.scripts.pipeline import _report

    report = _report({
        "technical_status": "PASS",
        "visual_status": "PENDING_HUMAN_REVIEW",
        "overall_status": "REVIEW_REQUIRED",
        "source_part_count": 82,
        "source_faces": 444296,
        "source_indexed_vertices": 221902,
        "validation": {
            "warnings": [],
            "scenes": {
                "STATE_01_PRIMARY_ARCHITECTURE": {
                    "screen_space_metrics": {
                        "projected_overlap_ratio": 0.0843,
                        "component_projected_overlap_ratio": 0.1,
                        "frame_occupancy_ratio": 0.2,
                    }
                }
            },
        },
    })
    assert "PENDING_HUMAN_REVIEW" in report
    assert "0.0843" in report
    assert "PRIMARY" in report
