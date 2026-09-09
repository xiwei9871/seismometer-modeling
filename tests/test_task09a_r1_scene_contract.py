from __future__ import annotations

from stage_09A_R1_exploded_rework.scripts.apply_explosion_layout import (
    validate_r1_scene_facts,
)


def test_r1_scene_facts_require_all_source_parts_frozen_geometry_and_no_animation():
    facts = [
        {
            "part_id": f"PART_{index:03d}",
            "source": "original_stl",
            "type": "MESH",
            "hidden": index > 22,
            "animation_data": None,
        }
        for index in range(1, 83)
    ]

    result = validate_r1_scene_facts(facts, vertices=221902, polygons=444296)

    assert result["source_part_count"] == 82
    assert result["visible_part_count"] == 22
    assert result["animation_data_count"] == 0
