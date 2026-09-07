import hashlib
import json
import math

import pytest
import trimesh

from scripts.analyze_stl import analyze_source_file, analyze_source_mesh, main, write_json


def disconnected_boxes() -> trimesh.Trimesh:
    first = trimesh.creation.box(extents=[4, 4, 4])
    second = trimesh.creation.box(extents=[1, 2, 3])
    second.apply_translation([10, 0, 0])
    return trimesh.util.concatenate([first, second])


def test_analyze_source_mesh_reports_all_components_and_indexed_bounds():
    raw = disconnected_boxes()

    report = analyze_source_mesh(raw, source_file="fixture.stl", file_size_bytes=123)

    assert report["file_size_bytes"] == 123
    assert report["faces"] == len(raw.faces)
    assert report["raw_vertex_count"] == len(raw.vertices)
    assert report["vertices"] >= 0
    assert report["connected_component_count"] == 2
    assert len(report["components"]) == 2
    part_ids = [component["part_id"] for component in report["components"]]
    assert len(set(part_ids)) == 2
    assert all(part_id.startswith("PART_") for part_id in part_ids)
    assert report["unit_assumption"] == "mm"
    assert report["unit_confidence"] == "assumed"
    assert report["bounding_box"] == {
        "x": pytest.approx(12.5),
        "y": pytest.approx(4.0),
        "z": pytest.approx(4.0),
    }
    assert report["bounds_min"] == pytest.approx([-2.0, -2.0, -2.0])
    assert report["bounds_max"] == pytest.approx([10.5, 2.0, 2.0])
    assert "facet-expanded" in report["analysis_topology_note"]
    assert "in-memory" in report["analysis_topology_note"]

    expected_component_fields = {
        "source_component_index",
        "face_count",
        "vertex_count",
        "bbox_dimensions",
        "surface_area",
        "volume",
        "volume_valid",
        "watertight",
        "metric_errors",
    }
    assert all(
        expected_component_fields <= set(component)
        for component in report["components"]
    )
    assert {
        component["source_component_index"] for component in report["components"]
    } == {0, 1}
    json.dumps(report, allow_nan=False)


def test_write_json_creates_utf8_json_with_trailing_newline_and_rejects_nan(
    tmp_path,
):
    destination = tmp_path / "nested" / "报告.json"
    payload = {"source_file": "智能地震仪.STL", "value": 1}

    write_json(destination, payload)

    text = destination.read_text(encoding="utf-8")
    assert json.loads(text) == payload
    assert "智能地震仪.STL" in text
    assert not any(token in text for token in ("NaN", "Infinity", "-Infinity"))
    assert text.endswith("\n")

    with pytest.raises(ValueError):
        write_json(destination, {"value": math.nan})


def test_analyze_source_file_hashes_and_does_not_modify_real_stl(tmp_path):
    source = tmp_path / "fixture.stl"
    mesh = trimesh.creation.box(extents=[4, 4, 4])
    mesh.export(source, file_type="stl")
    original_bytes = source.read_bytes()
    expected_hash = hashlib.sha256(original_bytes).hexdigest()

    report = analyze_source_file(source)

    assert report["file_sha256"] == expected_hash
    assert report["file_size_bytes"] == len(original_bytes)
    assert source.read_bytes() == original_bytes
    assert report["raw_vertex_count"] >= 0
    assert report["vertices"] >= 0
    assert report["faces"] >= 0


def test_non_watertight_mesh_is_retained_without_repair_or_volume():
    mesh = trimesh.Trimesh(
        vertices=[[0, 0, 0], [1, 0, 0], [0, 1, 0]],
        faces=[[0, 1, 2]],
        process=False,
    )
    original_vertices = mesh.vertices.copy()
    original_faces = mesh.faces.copy()

    report = analyze_source_mesh(mesh, source_file="plane.stl", file_size_bytes=0)

    assert report["connected_component_count"] == 1
    assert len(report["components"]) == 1
    assert report["volume"] is None
    assert report["volume_valid"] is False
    assert report["is_watertight"] is False
    component = report["components"][0]
    assert component["watertight"] is False
    assert component["volume"] is None
    assert component["volume_valid"] is False
    assert (mesh.vertices == original_vertices).all()
    assert (mesh.faces == original_faces).all()


def test_main_returns_nonzero_without_report_for_unparseable_source(
    tmp_path,
    capsys,
):
    source = tmp_path / "missing.stl"
    output = tmp_path / "report.json"

    result = main(["--source", str(source), "--output", str(output)])

    assert result == 1
    assert not output.exists()
    assert "error" in capsys.readouterr().err.lower()
