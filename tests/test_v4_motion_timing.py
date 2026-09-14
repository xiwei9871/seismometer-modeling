"""Contract tests for the Task 10-V4 motion timing schedules."""

from __future__ import annotations

import pytest

from stage_10V2_product_story.scripts.motion_timing import (
    MOTION_TIMING,
    SHELL_PARTS,
    arrival_windows,
    hide_schedule,
    idle_frames,
    idle_offsets,
    shot_axis,
)
from stage_10V2_product_story.scripts.story_v2_data import FOCUS_SHOT_POLICY


def _shots():
    return [
        {"shot_id": "SENSOR_FOCUS", "frame_start": 165, "frame_end": 299},
        {"shot_id": "PCB_FOCUS", "frame_start": 300, "frame_end": 419},
        {"shot_id": "RUGGED_FOCUS", "frame_start": 615, "frame_end": 704},
    ]


def test_shell_parts_match_rugged_policy():
    assert SHELL_PARTS == frozenset(FOCUS_SHOT_POLICY["RUGGED_FOCUS"]["parts"])


def test_shot_axis_normalizes_summed_displacement():
    prev = {"A": (0, 0, 0), "B": (0, 0, 0)}
    nxt = {"A": (0, 0, 30), "B": (0, 0, 10)}
    axis = shot_axis(prev, nxt)
    assert axis == pytest.approx((0.0, 0.0, 1.0))


def test_arrival_windows_stagger_shell_first():
    prev = {p: (0, 0, 0) for p in ("PART_001", "PART_003", "PART_008")}
    nxt = {"PART_001": (0, 0, 80), "PART_003": (0, 0, 40), "PART_008": (0, 0, 20)}
    wins = arrival_windows(prev, nxt, frame_start=100, shell_first=True)
    # PART_001 is a shell part; PART_003/PART_008 are not.
    assert wins["PART_001"][0] <= wins["PART_003"][0]
    assert wins["PART_001"][0] <= wins["PART_008"][0]
    # every mover arrives within start + arrive_len + gap
    limit = 100 + MOTION_TIMING["arrive_len"] + MOTION_TIMING["two_phase_gap"]
    for lo, hi in wins.values():
        assert 100 <= lo < hi <= limit


def test_arrival_windows_reassembled_shell_last():
    prev = {"PART_001": (0, 0, 80), "PART_003": (0, 0, 40)}
    nxt = {"PART_001": (0, 0, 0), "PART_003": (0, 0, 0)}
    wins = arrival_windows(prev, nxt, frame_start=705, shell_first=False)
    assert wins["PART_003"][0] <= wins["PART_001"][0]


def test_arrival_windows_skips_non_movers():
    prev = {"A": (0, 0, 0), "B": (1, 1, 1)}
    nxt = {"A": (0, 0, 50), "B": (1, 1, 1)}
    wins = arrival_windows(prev, nxt, frame_start=10, shell_first=True)
    assert "A" in wins and "B" not in wins


def _hidden_at(keys, frame):
    state = False
    for key_frame, hidden in keys:
        if key_frame > frame:
            break
        state = hidden
    return state


def test_hide_schedule_isolate_only():
    ids = ["PART_001", "PART_003", "PART_019", "PCB_COMP_IC_B1"]
    sched = hide_schedule(_shots(), ids)
    # PART_001 (context for both isolate shots) hidden through both ranges.
    assert _hidden_at(sched["PART_001"], 1) is False
    assert _hidden_at(sched["PART_001"], 200) is True
    assert _hidden_at(sched["PART_001"], 350) is True
    assert _hidden_at(sched["PART_001"], 420) is False
    # PART_003 is the SENSOR subject: visible there, hidden during PCB_FOCUS.
    assert _hidden_at(sched["PART_003"], 200) is False
    assert _hidden_at(sched["PART_003"], 350) is True
    assert _hidden_at(sched["PART_003"], 500) is False
    # Components are subjects only when focus_components is set (PCB shot).
    assert _hidden_at(sched["PCB_COMP_IC_B1"], 200) is True
    assert _hidden_at(sched["PCB_COMP_IC_B1"], 350) is False
    assert _hidden_at(sched["PCB_COMP_IC_B1"], 500) is False
    # RUGGED is a layer shot: nothing hides inside its range.
    assert _hidden_at(sched["PART_001"], 660) is False


def test_hide_schedule_frames_sorted_and_minimal():
    sched = hide_schedule(_shots(), ["PART_001"])
    frames = [f for f, _ in sched["PART_001"]]
    assert frames == sorted(frames)
    # no adjacent duplicate hidden states
    hiddens = [h for _, h in sched["PART_001"]]
    assert all(a != b for a, b in zip(hiddens, hiddens[1:]))


def test_idle_offsets_full_cycle():
    plus = idle_offsets(+1)
    minus = idle_offsets(-1)
    amp = MOTION_TIMING["idle_amplitude_mm"]
    assert plus == [0.0, amp, 0.0, -amp, 0.0]
    assert minus == [0.0, -amp, 0.0, amp, 0.0]


def test_idle_frames_cover_hold():
    frames = idle_frames(200, 299)
    assert frames[0] == 200 and frames[-1] == 299 and len(frames) == 5
    assert frames == sorted(frames)


def test_camera_drift_pushes_in_and_orbits():
    import math

    from stage_10V2_product_story.scripts.camera_plan import drifted_pose

    record = {"location": (100.0, 0.0, 40.0), "target": (0.0, 0.0, 40.0)}
    end = drifted_pose(record, push_fraction=0.10, orbit_deg=7.0)
    start_dist = math.dist(record["location"], record["target"])
    end_dist = math.dist(end, record["target"])
    assert end_dist == pytest.approx(start_dist * 0.9)
    azimuth = math.degrees(math.atan2(end[1], end[0]))
    assert azimuth == pytest.approx(7.0)
