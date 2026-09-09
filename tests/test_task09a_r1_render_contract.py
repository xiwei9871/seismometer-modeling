from __future__ import annotations

import pytest

from stage_09A_R1_exploded_rework.scripts.setup_explosion_cameras import (
    CAMERA_NAMES,
    _validate_camera_payload,
    camera_configs_for_bounds,
)
from stage_09A_R1_exploded_rework.scripts.validate_explosion import build_explosion_validation
from stage_09A_R1_exploded_rework.scripts.build_explosion_groups import build_explosion_layout
from pathlib import Path
from stage_09A_R1_exploded_rework.scripts.setup_explosion_render import (
    R1_VIEW_NAMES,
    render_result_contract,
)


def test_r1_required_render_view_names_are_stable_and_static():
    assert R1_VIEW_NAMES == (
        "exploded_hero",
        "exploded_engineering",
        "exploded_top",
        "exploded_rear",
    )
    assert CAMERA_NAMES == (
        "CAM_EXPLODED_HERO",
        "CAM_EXPLODED_ENGINEERING",
        "CAM_EXPLODED_TOP",
        "CAM_EXPLODED_REAR",
    )
    assert render_result_contract({"animation_created": False})[
        "animation_created"
    ] is False


def test_r1_render_contract_rejects_animation_data():
    with pytest.raises(ValueError):
        render_result_contract({"animation_created": True})


def test_r1_camera_config_is_full_and_derived_from_bounds():
    bounds = {"min": [-200.0, -50.0, 70.0], "max": [430.0, 250.0, 440.0]}
    payload = camera_configs_for_bounds(bounds)

    assert set(payload["cameras"]) == set(CAMERA_NAMES)
    assert all("location" in payload["cameras"][name] for name in CAMERA_NAMES)
    _validate_camera_payload(payload, bounds | {"dimensions": [630.0, 300.0, 370.0]})


def test_r1_validation_requires_actual_blender_scene_facts(tmp_path):
    layout = build_explosion_layout(Path(__file__).resolve().parents[1])
    result = build_explosion_validation(layout, render_paths=())

    assert result["status"] == "REVIEW"
    assert result["actual_scene_validation"] is False
    assert {item["code"] for item in result["warnings"]} >= {
        "BLENDER_SCENE_VALIDATION_NOT_RUN"
    }
