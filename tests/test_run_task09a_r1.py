from __future__ import annotations

from stage_09A_R1_exploded_rework.scripts.pipeline import blender_stage_succeeded


def test_blender_stage_succeeded_accepts_empty_zero_exit_output():
    assert blender_stage_succeeded(0, "") is True


def test_blender_stage_succeeded_rejects_traceback_with_zero_exit_code():
    assert blender_stage_succeeded(
        0, "Traceback (most recent call last):\nValueError"
    ) is False


def test_blender_stage_succeeded_rejects_nonzero_process_code():
    assert blender_stage_succeeded(1, "") is False
