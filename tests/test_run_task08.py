from __future__ import annotations

import json
from pathlib import Path

import pytest

from run_task08 import (
    REQUIRED_TASK08_DATA,
    build_blender_command,
    build_blender_script_command,
    find_blender,
    validate_task08_outputs,
    validate_task08_render_outputs,
)


def test_blender_command_keeps_project_root_and_script_arguments_after_separator():
    command = build_blender_command(
        Path("/opt/homebrew/bin/blender"),
        Path("/tmp/project"),
        "scripts/generate_reference_views.py",
        240,
    )
    assert command[:4] == ["/opt/homebrew/bin/blender", "-b", "--python", "scripts/generate_reference_views.py"]
    assert "--" in command
    assert command[-4:] == ["--project-root", "/tmp/project", "--resolution", "240"]


def test_semantic_builder_command_does_not_inject_render_only_arguments():
    command = build_blender_script_command(
        Path("/opt/homebrew/bin/blender"),
        Path("/tmp/project"),
        "scripts/build_stage02_semantic_blend.py",
    )
    assert command == [
        "/opt/homebrew/bin/blender",
        "-b",
        "--python",
        "scripts/build_stage02_semantic_blend.py",
        "--",
        "--project-root",
        "/tmp/project",
    ]


def test_validate_task08_outputs_requires_checkpoint_files(tmp_path):
    with pytest.raises(ValueError, match="missing Task 8 output"):
        validate_task08_outputs(tmp_path)

    for relative in REQUIRED_TASK08_DATA:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{}", encoding="utf-8")
    result = validate_task08_outputs(tmp_path)
    assert result["missing"] == []


def test_validate_task08_render_outputs_requires_checkpoint_render_counts(tmp_path):
    (tmp_path / "output/reference_renders").mkdir(parents=True)
    (tmp_path / "output/part_previews").mkdir(parents=True)
    (tmp_path / "output/part_highlights").mkdir(parents=True)
    (tmp_path / "output/reports/duplicate_groups").mkdir(parents=True)
    (tmp_path / "output/reports").mkdir(exist_ok=True)
    for index in range(10):
        (tmp_path / "output/reference_renders" / f"view_{index}.png").touch()
    for index in range(82):
        (tmp_path / "output/part_previews" / f"PART_{index + 1:03d}.png").touch()
        (tmp_path / "output/part_highlights" / f"PART_{index + 1:03d}_iso.png").touch()
    for index in range(13):
        (tmp_path / "output/reports/duplicate_groups" / f"DG_{index + 1:03d}.png").touch()
    for index in range(4):
        (tmp_path / "output/reports" / f"part_contact_sheet_{index + 1:02d}.png").touch()
    result = validate_task08_render_outputs(tmp_path)
    assert result == {
        "standard_views": 10,
        "part_previews": 82,
        "part_highlights": 82,
        "duplicate_group_sheets": 13,
        "part_contact_sheets": 4,
    }


def test_find_blender_honors_explicit_executable(tmp_path):
    executable = tmp_path / "blender"
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o755)
    assert find_blender(executable) == executable.resolve()


def test_skip_blender_is_not_claimed_as_complete():
    assert "PARTIAL" in Path("run_task08.py").read_text(encoding="utf-8")
