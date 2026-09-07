import copy
import json

import numpy as np
import pytest
import trimesh

from scripts.stage01_core import (
    assign_part_ids,
    bbox_dimensions_match,
    build_exact_indexed_mesh,
    component_metrics,
    relative_value_match,
    sorted_bbox_dimensions,
)


EXPECTED_METRIC_FIELDS = {
    "source_component_index",
    "face_count",
    "vertex_count",
    "bbox_dimensions",
    "bbox_volume",
    "bbox_diagonal",
    "centroid",
    "min_bound",
    "max_bound",
    "surface_area",
    "volume",
    "volume_valid",
    "watertight",
    "euler_number",
    "winding_consistent",
    "boundary_edge_count",
    "non_manifold_edge_count",
    "duplicate_face_count",
    "metric_errors",
}


def duplicate_vertex_mesh() -> trimesh.Trimesh:
    vertices = np.array(
        [
            [0, 0, 0],
            [1, 0, 0],
            [0, 1, 0],
            [0, 0, 0],
            [1, 0, 0],
            [0, 1, 0],
            [10, 0, 0],
            [11, 0, 0],
            [10, 1, 0],
        ],
        dtype=float,
    )
    faces = np.array([[0, 1, 2], [3, 4, 5], [6, 7, 8]], dtype=np.int64)
    return trimesh.Trimesh(vertices=vertices, faces=faces, process=False)


def test_build_exact_indexed_mesh_only_indexes_equal_coordinates_without_mutation():
    raw = duplicate_vertex_mesh()
    original_vertices = np.asarray(raw.vertices).copy()
    original_faces = np.asarray(raw.faces).copy()

    indexed = build_exact_indexed_mesh(raw)

    assert indexed is not raw
    assert len(raw.vertices) == 9
    assert len(indexed.vertices) == 6
    assert len(indexed.faces) == 3
    assert np.array_equal(indexed.faces[0], indexed.faces[1])
    assert np.array_equal(raw.vertices, original_vertices)
    assert np.array_equal(raw.faces, original_faces)


def test_component_metrics_reports_json_safe_geometry_without_repair():
    indexed = build_exact_indexed_mesh(duplicate_vertex_mesh())

    metrics = component_metrics(indexed, source_component_index=4)

    assert set(metrics) == EXPECTED_METRIC_FIELDS
    assert metrics["source_component_index"] == 4
    assert metrics["face_count"] == 3
    assert metrics["vertex_count"] == 6
    assert metrics["min_bound"] == [0.0, 0.0, 0.0]
    assert metrics["max_bound"] == [11.0, 1.0, 0.0]
    assert metrics["bbox_dimensions"] == [11.0, 1.0, 0.0]
    assert metrics["bbox_volume"] == 0.0
    assert metrics["bbox_diagonal"] == pytest.approx(np.sqrt(122.0))
    assert metrics["surface_area"] == pytest.approx(1.5)
    assert metrics["volume"] is None
    assert metrics["volume_valid"] is False
    assert metrics["watertight"] is False
    assert metrics["boundary_edge_count"] == 3
    assert metrics["non_manifold_edge_count"] == 0
    assert metrics["duplicate_face_count"] == 1
    assert metrics["metric_errors"] == {}
    json.dumps(metrics, allow_nan=False)


def test_assign_part_ids_orders_larger_bbox_first_and_breaks_full_ties_by_source():
    records = [
        {
            "source_component_index": 1,
            "bbox_volume": 2.0,
            "volume": None,
            "volume_valid": False,
            "face_count": 4,
            "centroid": [1.0, 0.0, 0.0],
            "vertex_count": 4,
        },
        {
            "source_component_index": 0,
            "bbox_volume": 2.0,
            "volume": None,
            "volume_valid": False,
            "face_count": 4,
            "centroid": [1.0, 0.0, 0.0],
            "vertex_count": 4,
        },
        {
            "source_component_index": 2,
            "bbox_volume": 8.0,
            "volume": None,
            "volume_valid": False,
            "face_count": 1,
            "centroid": [0.0, 0.0, 0.0],
            "vertex_count": 3,
        },
    ]
    original = copy.deepcopy(records)

    assigned = assign_part_ids(records)

    assert [record["part_id"] for record in assigned] == [
        "PART_001",
        "PART_002",
        "PART_003",
    ]
    assert [record["source_component_index"] for record in assigned] == [2, 0, 1]
    assert records == original
    assert all(output is not source for output in assigned for source in records)


def test_assign_part_ids_puts_invalid_volume_below_valid_volume_and_normalizes_empty_values():
    records = [
        {
            "source_component_index": 2,
            "bbox_volume": np.nan,
            "volume": "",
            "volume_valid": True,
            "face_count": "",
            "centroid": [np.nan, "", None],
            "vertex_count": np.nan,
        },
        {
            "source_component_index": 1,
            "bbox_volume": 4.0,
            "volume": 50.0,
            "volume_valid": False,
            "face_count": 12,
            "centroid": [0.0, 0.0, 0.0],
            "vertex_count": 8,
        },
        {
            "source_component_index": 0,
            "bbox_volume": 4.0,
            "volume": 2.0,
            "volume_valid": True,
            "face_count": 6,
            "centroid": [0.0, 0.0, 0.0],
            "vertex_count": 5,
        },
    ]

    assigned = assign_part_ids(records)

    assert [record["source_component_index"] for record in assigned] == [0, 1, 2]
    invalid = assigned[-1]
    assert invalid["bbox_volume"] is None
    assert invalid["volume"] is None
    assert invalid["face_count"] is None
    assert invalid["centroid"] == [None, None, None]
    assert invalid["vertex_count"] is None


def test_sorted_bbox_dimensions_are_rotation_invariant():
    assert sorted_bbox_dimensions([10.0, 5.0, 20.0]) == [5.0, 10.0, 20.0]
    assert sorted_bbox_dimensions([20.0, 10.0, 5.0]) == [5.0, 10.0, 20.0]


def test_bbox_dimension_tolerance_accepts_boundaries_and_rejects_outliers():
    assert bbox_dimensions_match([10.0, 5.0, 20.0], [20.0, 10.1, 5.0])
    assert bbox_dimensions_match([100.0, 5.0, 20.0], [20.0, 100.5, 5.0])
    assert not bbox_dimensions_match([10.0, 5.0, 20.0], [20.0, 10.11, 5.0])
    assert not bbox_dimensions_match([100.0, 5.0, 20.0], [20.0, 100.6, 5.0])
    assert not bbox_dimensions_match([10.0, 5.0], [10.0, 5.0, 1.0])


def test_relative_value_tolerance_accepts_one_percent_boundary_and_rejects_outlier():
    assert relative_value_match(100.0, 101.0)
    assert not relative_value_match(100.0, 101.02)
    assert not relative_value_match(None, 100.0)
    assert not relative_value_match(np.nan, 100.0)
