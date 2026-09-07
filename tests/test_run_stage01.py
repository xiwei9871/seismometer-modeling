from pathlib import Path

import pytest

from run_stage01 import choose_source_file, ensure_project_dirs


def test_choose_source_prefers_largest_stl_in_source_without_modifying_inputs(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    small = source_dir / "small.stl"
    large = source_dir / "large.stl"
    small.write_bytes(b"small")
    large.write_bytes(b"large-file")

    chosen, warnings = choose_source_file(tmp_path)

    assert chosen == large
    assert warnings == []
    assert small.read_bytes() == b"small"
    assert large.read_bytes() == b"large-file"


def test_choose_source_falls_back_to_root_and_reports_copy_candidate(tmp_path):
    root_file = tmp_path / "device.STL"
    root_file.write_bytes(b"stl")

    chosen, warnings = choose_source_file(tmp_path)

    assert chosen == root_file
    assert any("root" in warning.lower() for warning in warnings)


def test_ensure_project_dirs_creates_only_generated_directories(tmp_path):
    ensure_project_dirs(tmp_path)

    for relative in ("source", "scripts", "data", "output/reports", "logs"):
        assert (tmp_path / relative).is_dir()


def test_choose_source_rejects_project_with_no_stl(tmp_path):
    with pytest.raises(FileNotFoundError, match="No STL source file"):
        choose_source_file(tmp_path)
