"""End-to-end tests for the Python Stage 01 orchestrator."""

from __future__ import annotations

import hashlib
import json
import stat
from pathlib import Path

import pytest
import trimesh

from run_stage01 import copy_root_source_if_needed, find_blender, main, write_stage_log


STANDARD_OUTPUTS = (
    "data/source_model_report.json",
    "data/parts_manifest.csv",
    "data/parts_manifest.json",
    "data/duplicate_groups.json",
    "data/suspicious_fragments.json",
    "data/mesh_quality_report.json",
    "data/assembly_initial.json",
    "output/reports/stage01_report.md",
    "logs/stage01.log",
)


def _write_stl(path: Path, mesh: trimesh.Trimesh) -> bytes:
    mesh.export(path, file_type="stl")
    return path.read_bytes()


def _write_fake_blender(path: Path, return_code: int = 0) -> Path:
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib\n"
        "import sys\n"
        "args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []\n"
        "def value(name):\n"
        "    index = args.index(name)\n"
        "    return pathlib.Path(args[index + 1])\n"
        "if "
        + str(return_code)
        + ":\n"
        "    print('fake blender stdout')\n"
        "    print('fake blender stderr', file=sys.stderr)\n"
        "    raise SystemExit("
        + str(return_code)
        + ")\n"
        "value('--output').parent.mkdir(parents=True, exist_ok=True)\n"
        "value('--output').write_bytes(b'fake blend')\n"
        "print('fake blender stdout')\n"
        "print('fake blender stderr', file=sys.stderr)\n",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def test_python_only_run_copies_root_source_and_writes_all_python_outputs(tmp_path):
    root_source = tmp_path / "device.STL"
    original_bytes = _write_stl(root_source, trimesh.creation.box(extents=[2, 2, 2]))
    original_hash = hashlib.sha256(original_bytes).hexdigest()

    result = main(["--project-root", str(tmp_path), "--skip-blender"])

    assert result == 2
    canonical = tmp_path / "source" / root_source.name
    assert canonical.read_bytes() == original_bytes
    assert root_source.read_bytes() == original_bytes
    assert hashlib.sha256(root_source.read_bytes()).hexdigest() == original_hash
    assert all((tmp_path / relative).exists() for relative in STANDARD_OUTPUTS)
    assert not (tmp_path / "output/stage01_split.blend").exists()
    run_result = json.loads(
        (tmp_path / "data/stage01_run_result.json").read_text(encoding="utf-8")
    )
    assert run_result["status"] == "PARTIAL"
    assert run_result["blender_status"] == "SKIPPED"
    assert run_result["source_sha256_before"] == run_result["source_sha256_after"]
    assert run_result["component_count"] == run_result["manifest_count"] == 1
    assert run_result["face_count"] > 0
    assert run_result["indexed_vertex_count"] > 0
    assert run_result["finished_at"]
    report = (tmp_path / "data/source_model_report.json").read_text(encoding="utf-8")
    assert original_hash in report
    stage_report = (tmp_path / "output/reports/stage01_report.md").read_text(
        encoding="utf-8"
    )
    assert "blender_status=SKIPPED" in stage_report


def test_missing_blender_is_partial_success_and_is_explicit_in_log_and_report(
    tmp_path, monkeypatch
):
    source = tmp_path / "source" / "device.stl"
    source.parent.mkdir()
    _write_stl(source, trimesh.creation.box(extents=[2, 2, 2]))
    monkeypatch.delenv("BLENDER_PATH", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path / "empty-path"))
    monkeypatch.setattr("run_stage01.DEFAULT_BLENDER_PATH", tmp_path / "missing-blender")

    result = main(["--project-root", str(tmp_path)])

    assert result == 2
    log = (tmp_path / "logs/stage01.log").read_text(encoding="utf-8")
    report = (tmp_path / "output/reports/stage01_report.md").read_text(
        encoding="utf-8"
    )
    assert "BLENDER_NOT_FOUND" in log
    assert "blender_status=UNAVAILABLE" in report
    assert "component_count=" in log
    assert "duplicate_groups=" in log
    assert "subprocess" not in log.lower()
    assert not (tmp_path / "output/stage01_split.blend").exists()


def test_fake_blender_success_refreshes_report_and_writes_duplicate_groups(tmp_path):
    source = tmp_path / "source" / "device.stl"
    source.parent.mkdir()
    first = trimesh.creation.box(extents=[2, 2, 2])
    second = first.copy()
    second.apply_translation([8, 0, 0])
    source_bytes = _write_stl(source, trimesh.util.concatenate([first, second]))
    blender = _write_fake_blender(tmp_path / "fake-blender")

    result = main(
        [
            "--project-root",
            str(tmp_path),
            "--blender-path",
            str(blender),
        ]
    )

    assert result == 0
    assert source.read_bytes() == source_bytes
    duplicate_report = json.loads(
        (tmp_path / "data/duplicate_groups.json").read_text(encoding="utf-8")
    )
    assert duplicate_report["group_count"] == 1
    assert duplicate_report["groups"][0]["parts"] == ["PART_001", "PART_002"]
    manifest = json.loads(
        (tmp_path / "data/parts_manifest.json").read_text(encoding="utf-8")
    )
    assert {item["duplicate_group"] for item in manifest} == {"DG_001"}
    report = (tmp_path / "output/reports/stage01_report.md").read_text(
        encoding="utf-8"
    )
    assert "DG_001" in report
    assert "blender_status=AVAILABLE" in report
    assert (tmp_path / "output/stage01_split.blend").read_bytes() == b"fake blend"
    run_result = json.loads(
        (tmp_path / "data/stage01_run_result.json").read_text(encoding="utf-8")
    )
    assert run_result["status"] == "PASS"
    assert run_result["blender_status"] == "AVAILABLE"
    assert run_result["component_count"] == run_result["manifest_count"] == 2
    assert run_result["duplicate_group_count"] == 1
    assert run_result["blender_output"] == str(tmp_path / "output/stage01_split.blend")
    assert run_result["source_sha256_before"] == run_result["source_sha256_after"]
    log = (tmp_path / "logs/stage01.log").read_text(encoding="utf-8")
    assert "stdout=fake blender stdout" in log
    assert "stderr=fake blender stderr" in log
    assert "return_code=0" in log
    assert "output/stage01_split.blend" in log


def test_stage_failure_removes_stale_report_and_returns_nonzero(tmp_path):
    source = tmp_path / "source" / "broken.STL"
    source.parent.mkdir()
    source.write_bytes(b"not an STL")
    stale_report = tmp_path / "output/reports/stage01_report.md"
    stale_report.parent.mkdir(parents=True)
    stale_report.write_text("old successful run", encoding="utf-8")

    result = main(["--project-root", str(tmp_path), "--skip-blender"])

    assert result == 1
    assert not stale_report.exists()
    run_result = json.loads(
        (tmp_path / "data/stage01_run_result.json").read_text(encoding="utf-8")
    )
    assert run_result["status"] == "FAIL"
    assert run_result["failure_reason"]
    assert run_result["blender_status"] == "NOT_RUN"
    log = (tmp_path / "logs/stage01.log").read_text(encoding="utf-8")
    assert "stage=analyze_stl" in log
    assert "level=ERROR" in log
    assert not (tmp_path / "output/stage01_split.blend").exists()


def test_find_blender_prefers_environment_over_cli_and_path(tmp_path, monkeypatch):
    environment_blender = _write_fake_blender(tmp_path / "env-blender")
    cli_blender = _write_fake_blender(tmp_path / "cli-blender")
    monkeypatch.setenv("BLENDER_PATH", str(environment_blender))

    assert find_blender(str(cli_blender)) == environment_blender


def test_copy_root_source_refuses_different_existing_canonical_file(tmp_path):
    root_source = tmp_path / "device.STL"
    root_source.write_bytes(b"original")
    canonical = tmp_path / "source" / root_source.name
    canonical.parent.mkdir()
    canonical.write_bytes(b"different")

    with pytest.raises(ValueError, match="canonical.*different|different.*canonical"):
        copy_root_source_if_needed(tmp_path, root_source)

    assert root_source.read_bytes() == b"original"
    assert canonical.read_bytes() == b"different"


def test_blender_failure_is_nonzero_and_does_not_leave_stale_blend(tmp_path):
    source = tmp_path / "source" / "device.stl"
    source.parent.mkdir()
    _write_stl(source, trimesh.creation.box(extents=[2, 2, 2]))
    blender = _write_fake_blender(tmp_path / "fake-blender", return_code=7)
    stale_blend = tmp_path / "output/stage01_split.blend"
    stale_blend.parent.mkdir()
    stale_blend.write_bytes(b"stale")

    result = main(
        ["--project-root", str(tmp_path), "--blender-path", str(blender)]
    )

    assert result == 1
    assert not stale_blend.exists()
    report = (tmp_path / "output/reports/stage01_report.md").read_text(
        encoding="utf-8"
    )
    assert "blender_status=FAILED" in report
    assert "pipeline_complete=false" in report
    log = (tmp_path / "logs/stage01.log").read_text(encoding="utf-8")
    assert "return_code=7" in log
    assert "BLENDER_STAGE_FAILED" in log


def test_write_stage_log_includes_part_and_stage_context(tmp_path):
    log = tmp_path / "logs/stage01.log"

    write_stage_log(
        log,
        "WARNING",
        "duplicate mapping",
        part_id="PART_007",
        stage="blender",
    )

    text = log.read_text(encoding="utf-8")
    assert "level=WARNING" in text
    assert "part_id=PART_007" in text
    assert "stage=blender" in text
    assert "duplicate mapping" in text
