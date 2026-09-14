"""Contract tests for the Task 10-V3 frustum-aware focus solver.

The Blender-facing search itself runs inside the pipeline; these tests pin the
pure-Python policy, direction resolution, state application and the shared
camera planner's subject-tracking invariant.
"""

from __future__ import annotations

import copy
import math
from pathlib import Path

import pytest

from stage_10V2_product_story.scripts import frustum_math as fm
from stage_10V2_product_story.scripts import solve_focus_layouts as solver
from stage_10V2_product_story.scripts import story_v2_data as v2
from stage_10V2_product_story.scripts.camera_plan import (
    build_camera_records,
    module_bounds,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LAYOUT = v2.load_json(PROJECT_ROOT / solver.LAYOUT_PATH)


def _state_data():
    return v2.build_story_v2_state_transforms(PROJECT_ROOT)


def test_focus_policy_covers_every_focus_shot():
    assert set(v2.FOCUS_SHOT_POLICY) == {
        "SENSOR_FOCUS", "PCB_FOCUS", "COMMUNICATION_FOCUS",
        "POWER_FOCUS", "RUGGED_FOCUS",
    }
    for shot_id, spec in v2.FOCUS_SHOT_POLICY.items():
        assert spec["camera"] in {
            "CAM_STORY_HERO", "CAM_STORY_SENSOR", "CAM_STORY_PCB",
            "CAM_STORY_COMM", "CAM_STORY_POWER",
        }
        assert spec["parts"]
        assert math.isclose(fm.v_len(spec["direction"]), 1.0, abs_tol=0.02)
        assert spec["mode"] in {"isolate", "layer"}


def test_rugged_is_layer_mode_and_pcb_carries_components():
    assert v2.FOCUS_SHOT_POLICY["RUGGED_FOCUS"]["mode"] == "layer"
    pcb = v2.FOCUS_SHOT_POLICY["PCB_FOCUS"]
    assert pcb["mode"] == "isolate"
    assert pcb["focus_components"] is True
    assert pcb["parts"] == ("PART_019",)


def test_part_direction_shared_mode_ignores_part_offset():
    spec = {"per_part": False}
    record = {"offset_from_assembled_mm": [10.0, 0.0, 0.0]}
    direction = solver._part_direction(spec, "PART_003", record, (0.0, 0.0, 1.0))
    assert direction == pytest.approx((0.0, 0.0, 1.0))


def test_part_direction_per_part_continues_own_explode_direction():
    spec = {"per_part": True}
    record = {"offset_from_assembled_mm": [30.0, 0.0, 40.0]}
    direction = solver._part_direction(spec, "PART_005", record, (0.0, 0.0, 1.0))
    assert direction == pytest.approx((0.6, 0.0, 0.8))


def test_part_direction_per_part_falls_back_when_offset_is_zero():
    spec = {"per_part": True}
    record = {"offset_from_assembled_mm": [0.0, 0.0, 0.0]}
    direction = solver._part_direction(spec, "PART_005", record, (1.0, 0.0, 0.0))
    assert direction == pytest.approx((1.0, 0.0, 0.0))


def test_apply_travel_moves_focus_parts_and_updates_offsets():
    data = _state_data()
    state = data["states"]["SENSOR_FOCUS"]
    spec = v2.FOCUS_SHOT_POLICY["SENSOR_FOCUS"]
    before = {pid: list(state["parts"][pid]["location"]) for pid in spec["parts"]}
    solver._apply_travel(state, spec, 50.0, data)
    direction = fm.v_norm(spec["direction"])
    for part_id in spec["parts"]:
        delta = fm.v_sub(state["parts"][part_id]["location"], before[part_id])
        assert delta == pytest.approx(fm.v_scale(direction, 50.0))


def test_apply_travel_updates_offset_from_assembled():
    data = _state_data()
    state = data["states"]["SENSOR_FOCUS"]
    spec = v2.FOCUS_SHOT_POLICY["SENSOR_FOCUS"]
    offset_before = list(state["parts"]["PART_003"]["offset_from_assembled_mm"])
    solver._apply_travel(state, spec, 25.0, data)
    offset_after = state["parts"]["PART_003"]["offset_from_assembled_mm"]
    moved = fm.v_sub(offset_after, offset_before)
    assert fm.v_len(moved) == pytest.approx(25.0)


def test_apply_travel_leaves_context_parts_untouched():
    data = _state_data()
    snapshot = copy.deepcopy(data["states"]["SENSOR_FOCUS"]["parts"])
    spec = v2.FOCUS_SHOT_POLICY["SENSOR_FOCUS"]
    solver._apply_travel(data["states"]["SENSOR_FOCUS"], spec, 60.0, data)
    for part_id, record in data["states"]["SENSOR_FOCUS"]["parts"].items():
        if part_id in spec["parts"]:
            continue
        assert record["location"] == snapshot[part_id]["location"]


def test_apply_travel_remounts_pcb_components():
    data = _state_data()
    state = data["states"]["PCB_FOCUS"]
    spec = v2.FOCUS_SHOT_POLICY["PCB_FOCUS"]
    solver._apply_travel(state, spec, 40.0, data)
    board = state["parts"]["PART_019"]["location"]
    for component in data["presentation"]["components"]:
        local = component["board_local_location"]
        mounted = state["components"][component["component_id"]]["location"]
        assert mounted == pytest.approx(
            [board[i] + float(local[i]) for i in range(3)]
        )


def test_apply_travel_is_deterministic():
    first = _state_data()
    second = _state_data()
    spec = v2.FOCUS_SHOT_POLICY["SENSOR_FOCUS"]
    solver._apply_travel(first["states"]["SENSOR_FOCUS"], spec, 33.0, first)
    solver._apply_travel(second["states"]["SENSOR_FOCUS"], spec, 33.0, second)
    assert first["states"]["SENSOR_FOCUS"] == second["states"]["SENSOR_FOCUS"]


def test_camera_records_change_with_solved_input():
    """build_camera_records is a pure function of its input — solved part
    positions shift the derived cameras. The pipeline therefore freezes
    cameras on the deterministic baseline so later solves cannot
    retroactively invalidate earlier shots."""
    data = _state_data()
    before = build_camera_records(data, LAYOUT)["cameras"]["CAM_STORY_PCB"]
    spec = v2.FOCUS_SHOT_POLICY["PCB_FOCUS"]
    solver._apply_travel(data["states"]["PCB_FOCUS"], spec, 80.0, data)
    after = build_camera_records(data, LAYOUT)["cameras"]["CAM_STORY_PCB"]
    delta = fm.v_sub(after["target"], before["target"])
    assert delta == pytest.approx(
        fm.v_scale(fm.v_norm(spec["direction"]), 80.0), abs=1e-6
    )


def test_module_bounds_includes_mounted_components():
    data = _state_data()
    state = data["states"]["PCB_FOCUS"]
    bare = module_bounds(state, ("PART_019",), LAYOUT)
    with_comps = module_bounds(
        state, ("PART_019",), LAYOUT,
        component_registry=data["presentation"]["components"],
    )
    assert with_comps[1] >= bare[1]


def test_camera_records_are_deterministic():
    data = _state_data()
    first = build_camera_records(data, LAYOUT)
    second = build_camera_records(data, LAYOUT)
    assert first == second
