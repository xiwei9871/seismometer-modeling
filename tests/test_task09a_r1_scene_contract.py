from __future__ import annotations

import pytest

from stage_09A_R1_exploded_rework.scripts.apply_explosion_layout import (
    validate_r1_scene_facts,
)


def _facts(*, visible_ids=None, animation_ids=(), source_overrides=None):
    visible_ids = set(visible_ids or {f"PART_{index:03d}" for index in range(1, 23)})
    animation_ids = set(animation_ids)
    source_overrides = source_overrides or {}
    facts = []
    for index in range(1, 83):
        part_id = f"PART_{index:03d}"
        fact = {
            "part_id": part_id,
            "source": "original_stl",
            "type": "MESH",
            "hidden": part_id not in visible_ids,
            "animation_data": {} if part_id in animation_ids else None,
        }
        fact.update(source_overrides.get(part_id, {}))
        facts.append(fact)
    return facts


def test_r1_scene_facts_require_all_source_parts_frozen_geometry_and_no_animation():
    facts = _facts()

    result = validate_r1_scene_facts(facts, vertices=221902, polygons=444296)

    assert result["source_part_count"] == 82
    assert result["visible_part_count"] == 22
    assert result["animation_data_count"] == 0


@pytest.mark.parametrize(
    ("vertices", "polygons"),
    [(221901, 444296), (221902, 444295)],
)
def test_r1_scene_facts_reject_wrong_geometry_totals(vertices, polygons):
    with pytest.raises(ValueError):
        validate_r1_scene_facts(_facts(), vertices=vertices, polygons=polygons)


def test_r1_scene_facts_reject_missing_or_duplicate_part_ids():
    with pytest.raises(ValueError):
        validate_r1_scene_facts(_facts()[:-1], vertices=221902, polygons=444296)

    duplicate = _facts()
    duplicate[-1]["part_id"] = "PART_001"
    with pytest.raises(ValueError):
        validate_r1_scene_facts(duplicate, vertices=221902, polygons=444296)


def test_r1_scene_facts_reject_wrong_source_or_type():
    with pytest.raises(ValueError):
        validate_r1_scene_facts(
            _facts(source_overrides={"PART_001": {"source": "other"}}),
            vertices=221902,
            polygons=444296,
        )
    with pytest.raises(ValueError):
        validate_r1_scene_facts(
            _facts(source_overrides={"PART_001": {"type": "CURVE"}}),
            vertices=221902,
            polygons=444296,
        )


def test_r1_scene_facts_reject_wrong_visible_policy():
    with pytest.raises(ValueError):
        validate_r1_scene_facts(
            _facts(visible_ids={"PART_001", "PART_023"}),
            vertices=221902,
            polygons=444296,
        )


def test_r1_scene_facts_reject_animation_data_on_any_source_part():
    with pytest.raises(ValueError):
        validate_r1_scene_facts(
            _facts(animation_ids={"PART_001"}),
            vertices=221902,
            polygons=444296,
        )
