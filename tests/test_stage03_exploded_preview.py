from __future__ import annotations

from pathlib import Path

import pytest

from scripts.build_stage03_exploded_preview import (
    VALID_STATES,
    build_stage03_scene,
    validate_stage03_source_scene,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_stage03_state_argument_accepts_only_assembled_or_exploded():
    assert VALID_STATES == ("assembled", "exploded")
    with pytest.raises(ValueError, match="state"):
        build_stage03_scene(PROJECT_ROOT, state="invalid")


def test_validate_stage03_source_scene_rejects_missing_source_part_or_animation():
    with pytest.raises(ValueError, match="source PART"):
        validate_stage03_source_scene([], vertices=0, polygons=0)

    facts = [
        {
            "part_id": f"PART_{index:03d}",
            "source": "original_stl",
            "type": "MESH",
            "animation_data": None,
        }
        for index in range(1, 83)
    ]
    facts[0]["animation_data"] = {"forbidden": True}
    with pytest.raises(ValueError, match="animation"):
        validate_stage03_source_scene(facts, vertices=221902, polygons=444296)


def test_validate_stage03_source_scene_accepts_frozen_source_totals():
    facts = [
        {
            "part_id": f"PART_{index:03d}",
            "source": "original_stl",
            "type": "MESH",
            "animation_data": None,
        }
        for index in range(1, 83)
    ]
    result = validate_stage03_source_scene(facts, vertices=221902, polygons=444296)
    assert result == {
        "source_part_count": 82,
        "vertices": 221902,
        "polygons": 444296,
        "animated_objects": [],
    }
