from __future__ import annotations

import pytest

from stage_09A_R1_exploded_rework.scripts.setup_explosion_cameras import (
    CAMERA_NAMES,
)
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
