"""Contract tests for the Blender-only Stage 01 scripts.

These tests intentionally run in the project Python environment.  They do not
import Blender or require ``bpy``; runtime Blender behavior is guarded by
source contracts and pure helpers that are also used by the Blender scripts.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from scripts.import_and_split_blender import (
    build_assembly_initial_payload,
    manifest_custom_properties,
    match_object_facts,
    part_object_name,
    stable_part_color,
)
from scripts.inspect_part import format_inspection_report


PROJECT_ROOT = Path(__file__).parents[1]
IMPORT_SCRIPT = PROJECT_ROOT / "scripts" / "import_and_split_blender.py"
INSPECT_SCRIPT = PROJECT_ROOT / "scripts" / "inspect_part.py"


def _record(part_id: str, centroid: list[float]) -> dict:
    return {
        "part_id": part_id,
        "source_component_index": 7 if part_id.endswith("1") else 8,
        "bbox_x_mm": 2.0,
        "bbox_y_mm": 2.0,
        "bbox_z_mm": 2.0,
        "bbox_dimensions": [2.0, 2.0, 2.0],
        "centroid": centroid,
        "face_count": 12,
        "vertex_count": 24,
        "surface_area": 24.0,
        "volume": 8.0,
        "volume_valid": True,
        "watertight": True,
        "duplicate_group": "DG_001",
        "duplicate_confidence": "HIGH",
        "suspected_fragment": False,
        "size_class": "MEDIUM",
    }


def _object_facts(object_id: str, centroid: list[float]) -> dict:
    return {
        "object_id": object_id,
        "centroid": centroid,
        "bbox_dimensions": [2.0, 2.0, 2.0],
        "face_count": 12,
        # Blender STL import may retain facet-expanded vertices.
        "vertex_count": 36,
        "surface_area": 24.0,
        "volume": 8.0,
        "volume_valid": True,
        "watertight": True,
    }


def test_blender_scripts_are_importable_without_bpy():
    assert IMPORT_SCRIPT.exists()
    assert INSPECT_SCRIPT.exists()


def test_part_name_and_color_are_stable_and_json_safe():
    assert part_object_name("PART_037") == "PART_037"
    assert stable_part_color("PART_037") == stable_part_color("PART_037")
    color = stable_part_color("PART_037")
    assert len(color) == 4
    assert all(0.0 <= channel <= 1.0 for channel in color)
    assert color[3] == 1.0
    with pytest.raises(ValueError, match="PART ID"):
        part_object_name("SENSOR")


def test_manifest_custom_properties_preserve_required_geometry_and_status():
    properties = manifest_custom_properties(_record("PART_001", [1.0, 2.0, 3.0]))

    assert properties == {
        "part_id": "PART_001",
        "source_component_index": 7,
        "bbox_x": 2.0,
        "bbox_y": 2.0,
        "bbox_z": 2.0,
        "face_count": 12,
        "vertex_count": 24,
        "duplicate_group": "DG_001",
        "duplicate_confidence": "HIGH",
        "suspected_fragment": False,
        "source": "original_stl",
    }


def test_assembly_payload_records_identity_inference_and_source_identity():
    payload = build_assembly_initial_payload(
        [_record("PART_001", [1.0, 2.0, 3.0])],
        source_file="source/device.stl",
        source_sha256="abc123",
    )

    assert payload["source_file"] == "source/device.stl"
    assert payload["source_sha256"] == "abc123"
    assert payload["part_count"] == 1
    item = payload["objects"]["PART_001"]
    assert item["location"] == [1.0, 2.0, 3.0]
    assert item["rotation_euler"] == [0.0, 0.0, 0.0]
    assert item["scale"] == [1.0, 1.0, 1.0]
    assert item["world_matrix"] == [
        [1.0, 0.0, 0.0, 1.0],
        [0.0, 1.0, 0.0, 2.0],
        [0.0, 0.0, 1.0, 3.0],
        [0.0, 0.0, 0.0, 1.0],
    ]
    assert item["transform_source"] == "stl_identity_inference"
    json.dumps(payload, ensure_ascii=False, allow_nan=False)


def test_object_matching_uses_geometry_and_centroid_not_iteration_order():
    records = [
        _record("PART_001", [0.0, 0.0, 0.0]),
        _record("PART_002", [10.0, 0.0, 0.0]),
    ]
    objects = [
        _object_facts("imported_object_b", [10.0, 0.0, 0.0]),
        _object_facts("imported_object_a", [0.0, 0.0, 0.0]),
    ]

    mapping = match_object_facts(objects, records)

    assert mapping["imported_object_a"]["part_id"] == "PART_001"
    assert mapping["imported_object_b"]["part_id"] == "PART_002"


def test_object_matching_rejects_unresolvable_duplicate_ambiguity():
    records = [
        _record("PART_001", [0.0, 0.0, 0.0]),
        _record("PART_002", [0.0, 0.0, 0.0]),
    ]
    objects = [
        _object_facts("imported_object_a", [0.0, 0.0, 0.0]),
        _object_facts("imported_object_b", [0.0, 0.0, 0.0]),
    ]

    with pytest.raises(ValueError, match="ambiguous"):
        match_object_facts(objects, records)


def test_inspection_report_contains_part_geometry_and_duplicate_group():
    text = format_inspection_report(
        "PART_037",
        {
            "bbox": {"x": 2.0, "y": 3.0, "z": 4.0},
            "face_count": 12,
            "duplicate_group": "DG_002",
        },
    )

    assert "PART_037" in text
    assert "bbox" in text
    assert "face_count" in text
    assert "DG_002" in text


def test_blender_script_contract_has_import_split_collections_props_and_save():
    source = IMPORT_SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert any(
        isinstance(node, ast.Import) and any(alias.name == "bpy" for alias in node.names)
        for node in ast.walk(tree)
    )
    for required in (
        "bpy.ops.wm.stl_import",
        "bpy.ops.import_mesh.stl",
        "bpy.ops.mesh.separate",
        "type='LOOSE'",
        "DEVICE",
        "MAJOR",
        "MEDIUM",
        "SMALL",
        "TINY",
        "SUSPECTED_FRAGMENT",
        "source_component_index",
        "duplicate_confidence",
        "original_stl",
        "matrix_world",
        "save_as_mainfile",
        "source_sha256",
    ):
        assert required in source
    inspect_source = INSPECT_SCRIPT.read_text(encoding="utf-8")
    for required in ("--part", "--isolate", "view_selected", "hide_set"):
        assert required in inspect_source


def test_blender_scripts_do_not_contain_destructive_mesh_operations():
    source = IMPORT_SCRIPT.read_text(encoding="utf-8") + INSPECT_SCRIPT.read_text(
        encoding="utf-8"
    )
    banned = (
        "remove_doubles",
        "decimate",
        "remesh",
        "boolean",
        "fill_holes",
        "smooth_vertices",
        "voxel_remesh",
        "merge_by_distance",
    )
    for token in banned:
        assert token not in source
