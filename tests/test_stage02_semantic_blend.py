from __future__ import annotations

from pathlib import Path

from scripts.build_stage02_semantic_blend import (
    semantic_object_name,
    validate_source_scene_facts,
)


def test_semantic_object_name_retains_permanent_part_id():
    assert semantic_object_name("PART_023", "MAIN_PCB") == "PART_023__MAIN_PCB"
    assert semantic_object_name("PART_056", "UNKNOWN") == "PART_056__UNKNOWN"


def test_source_scene_contract_preserves_frozen_totals_and_transforms():
    facts = [
        {
            "part_id": f"PART_{index:03d}",
            "source": "original_stl",
            "type": "MESH",
            "vertices": 1,
            "polygons": 1,
            "location": [0.0, 0.0, 0.0],
            "rotation_euler": [0.0, 0.0, 0.0],
            "scale": [1.0, 1.0, 1.0],
            "animation_data": None,
        }
        for index in range(1, 83)
    ]
    result = validate_source_scene_facts(facts, vertices=221902, polygons=444296)
    assert result == {
        "source_part_count": 82,
        "vertices": 221902,
        "polygons": 444296,
        "animated_objects": [],
        "transforms_changed": [],
    }


def test_source_scene_contract_rejects_animation_or_transform_change():
    facts = [
        {
            "part_id": f"PART_{index:03d}",
            "source": "original_stl",
            "type": "MESH",
            "vertices": 1,
            "polygons": 1,
            "location": [0.0, 0.0, 0.0],
            "rotation_euler": [0.0, 0.0, 0.0],
            "scale": [1.0, 1.0, 1.0],
            "animation_data": None,
        }
        for index in range(1, 83)
    ]
    facts[0]["animation_data"] = {"action": "forbidden"}
    facts[1]["transforms_changed"] = True
    try:
        validate_source_scene_facts(facts, vertices=221902, polygons=444296)
    except ValueError as error:
        assert "animation" in str(error) or "transform" in str(error)
    else:
        raise AssertionError("changed source scene was accepted")
