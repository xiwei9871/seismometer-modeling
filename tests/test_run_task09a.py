from __future__ import annotations

import json
from pathlib import Path

import pytest

from run_task09a import build_blender_command, run_task09a


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_run_task09a_refuses_nonpass_task08(tmp_path):
    with pytest.raises(ValueError, match="Task 8"):
        run_task09a(tmp_path, skip_blender=True)


def test_run_task09a_writes_checkpoint_result_without_animation():
    result = run_task09a(PROJECT_ROOT, skip_blender=True)

    assert result["status"] == "PARTIAL"
    assert result["animation_created"] is False
    assert result["blender_status"] == "SKIPPED"
    assert result["keyframe_count"] == 0
    saved = json.loads(
        (PROJECT_ROOT / "data/task09a_run_result.json").read_text(encoding="utf-8")
    )
    assert saved == result


def test_run_task09a_command_keeps_project_root_after_blender_separator():
    command = build_blender_command(
        Path("/opt/homebrew/bin/blender"),
        Path("/tmp/project"),
        "scripts/build_stage03_exploded_preview.py",
        "exploded",
    )

    assert command[-4:] == ["--project-root", "/tmp/project", "--state", "exploded"]
