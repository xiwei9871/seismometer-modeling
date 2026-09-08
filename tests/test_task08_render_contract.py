from __future__ import annotations

import pytest

from scripts.generate_part_previews import (
    CONTACT_SHEET_PAGE_SIZE,
    _format_dimensions,
    build_contact_sheet_pages,
    required_part_ids,
    required_part_highlight_names,
)
from scripts.generate_reference_views import (
    ISO_VIEWS,
    STANDARD_VIEWS,
    build_render_paths,
    inspection_light_energy,
    select_render_engine,
    validate_source_object_facts,
)


def test_standard_views_are_orthographic_contract_and_have_four_iso_views(tmp_path):
    assert STANDARD_VIEWS == ("front", "rear", "left", "right", "top", "bottom")
    assert len(ISO_VIEWS) == 4
    assert set(build_render_paths(tmp_path)) == set((*STANDARD_VIEWS, *ISO_VIEWS))


def test_render_outputs_stay_inside_task08_allowlisted_directories(tmp_path):
    paths = build_render_paths(tmp_path)
    assert all(path.parent == tmp_path / "output" / "reference_renders" for path in paths.values())
    assert (tmp_path / "output" / "stage01_split.blend") not in paths.values()


def test_source_object_contract_requires_82_original_stl_meshes_and_frozen_geometry():
    facts = [
        {
            "name": f"PART_{index:03d}",
            "part_id": f"PART_{index:03d}",
            "type": "MESH",
            "source": "original_stl",
            "vertices": 1,
            "polygons": 1,
            "location": [float(index), 0.0, 0.0],
            "rotation_euler": [0.0, 0.0, 0.0],
            "scale": [1.0, 1.0, 1.0],
            "animation_data": None,
        }
        for index in range(1, 83)
    ]
    result = validate_source_object_facts(facts)
    assert result["object_count"] == 82
    assert result["geometry_counts"] == {"vertices": 82, "polygons": 82}
    assert result["animated_objects"] == []
    assert result["transforms_changed"] == []


def test_part_preview_contract_covers_all_numeric_ids_and_5x5_pages():
    assert required_part_ids() == [f"PART_{index:03d}" for index in range(1, 83)]
    pages = build_contact_sheet_pages(required_part_ids())
    assert len(pages) == 4
    assert all(len(page) <= CONTACT_SHEET_PAGE_SIZE == 25 for page in pages)
    assert [part for page in pages for part in page] == required_part_ids()
    assert len(required_part_highlight_names()) == 82
    assert required_part_highlight_names()[0] == "PART_001_iso.png"


def test_source_contract_rejects_missing_or_modified_source_object():
    facts = [
        {
            "name": "PART_001",
            "part_id": "PART_001",
            "type": "MESH",
            "source": "original_stl",
            "vertices": 1,
            "polygons": 1,
            "location": [0.0, 0.0, 0.0],
            "rotation_euler": [0.0, 0.0, 0.0],
            "scale": [1.0, 1.0, 1.0],
            "animation_data": None,
        }
    ]
    with pytest.raises(ValueError, match="82"):
        validate_source_object_facts(facts)


def test_render_engine_selects_first_engine_available_in_this_blender_build():
    assert select_render_engine({"BLENDER_EEVEE"}) == "BLENDER_EEVEE"
    assert select_render_engine({"BLENDER_EEVEE_NEXT", "CYCLES"}) == "BLENDER_EEVEE_NEXT"


def test_inspection_lighting_is_visible_for_neutral_geometry():
    assert inspection_light_energy() > 0.0


def test_preview_script_can_bootstrap_project_package_path():
    from scripts.generate_part_previews import project_package_root

    assert project_package_root(__file__).name == "task08-checkpoint"


def test_preview_dimensions_use_one_shared_unit_suffix_to_fit_thumbnail():
    assert _format_dimensions([191.267, 168.791, 92.999]) == "191.3 × 168.8 × 93.0 mm"
