"""Deterministic keyframe schedules for the Task 10-V4 motion language.

Pure Python — no bpy/mathutils — so pytest covers every schedule the
Blender stages consume: arrival windows (stagger + two-phase), isolate-shot
hide schedules, and idle-float offsets. See
``docs/superpowers/specs/2026-09-14-task10v4-motion-language-design.md``.
"""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

from stage_10V2_product_story.scripts.frustum_math import (
    assign_ranks,
    staggered_window,
    v_add,
    v_dot,
    v_len,
    v_norm,
    v_scale,
    v_sub,
)
from stage_10V2_product_story.scripts.story_v2_data import FOCUS_SHOT_POLICY

MOTION_TIMING: dict[str, Any] = {
    "arrive_len": 36,
    "rank_tolerance_mm": 8.0,
    "stagger_overlap": 0.35,
    "two_phase_gap": 12,
    "idle_amplitude_mm": 1.5,
    "idle_cycle_keys": 5,
    "camera_push_fraction": 0.10,
    "camera_orbit_deg": 7.0,
}

SHELL_PARTS = frozenset(FOCUS_SHOT_POLICY["RUGGED_FOCUS"]["parts"])

MOVE_EPSILON_MM = 0.5
COMPONENT_PREFIX = "PCB_COMP_"

Vec3 = tuple[float, float, float]


def shot_axis(
    prev: Mapping[str, Sequence[float]],
    nxt: Mapping[str, Sequence[float]],
) -> Vec3:
    """Dominant travel axis: normalize(sum of per-part displacements)."""
    total = (0.0, 0.0, 0.0)
    for part_id, end in nxt.items():
        start = prev.get(part_id)
        if start is None:
            continue
        total = v_add(total, v_sub(end, start))
    return v_norm(total)


def _phase_of(part_id: str, shell_first: bool) -> int:
    is_shell = part_id in SHELL_PARTS
    return 0 if is_shell == shell_first else 1


def arrival_windows(
    prev: Mapping[str, Sequence[float]],
    nxt: Mapping[str, Sequence[float]],
    frame_start: int,
    shell_first: bool,
    timing: Mapping[str, Any] = MOTION_TIMING,
) -> dict[str, tuple[float, float]]:
    """Per-part ``(window_start, window_end)`` inside the arrive span.

    Movers split into two phases by shell membership (``shell_first``
    controls which phase leads — explosions lead with shell, reassembly
    with interior). Each phase staggers its ranks across its slice via
    ``staggered_window``; phase 1 is offset by ``two_phase_gap``.
    """
    arrive_len = float(timing["arrive_len"])
    gap = float(timing["two_phase_gap"])
    movers = {
        pid: v_sub(nxt[pid], prev.get(pid, nxt[pid]))
        for pid in nxt
        if v_len(v_sub(nxt[pid], prev.get(pid, nxt[pid]))) > MOVE_EPSILON_MM
    }
    if not movers:
        return {}  # hold-only shot (ASSEMBLED, FINAL_HERO)
    axis = shot_axis(prev, nxt)
    windows: dict[str, tuple[float, float]] = {}
    for phase in (0, 1):
        members = [pid for pid in movers if _phase_of(pid, shell_first) == phase]
        if not members:
            continue
        ranks = assign_ranks(
            {pid: v_dot(movers[pid], axis) for pid in members},
            float(timing["rank_tolerance_mm"]),
        )
        lo = frame_start + (gap if phase == 1 else 0.0)
        hi = frame_start + arrive_len + (gap if phase == 1 else 0.0)
        n_ranks = max(ranks.values())
        for pid, rank in ranks.items():
            windows[pid] = staggered_window(
                rank - 1, n_ranks, lo, hi, float(timing["stagger_overlap"])
            )
    return windows


def hide_schedule(
    shots: Sequence[Mapping[str, Any]],
    part_ids: Sequence[str],
    policy: Mapping[str, Mapping[str, Any]] = FOCUS_SHOT_POLICY,
) -> dict[str, list[tuple[int, bool]]]:
    """``{id: [(frame, hidden)]}`` — context hidden during isolate shots.

    Shots share boundary frames (shot N's end = shot N+1's start), so the
    hidden intervals for each id are merged before emitting transition
    keys — otherwise a restore key at ``end+1`` lands inside the next
    isolate shot and the part flashes back on for its whole range.
    """
    isolate = sorted(
        (
            shot
            for shot in shots
            if policy.get(shot["shot_id"], {}).get("mode") == "isolate"
        ),
        key=lambda shot: int(shot["frame_start"]),
    )
    schedule: dict[str, list[tuple[int, bool]]] = {}
    for pid in part_ids:
        intervals: list[list[int]] = []
        for shot in isolate:
            spec = policy[shot["shot_id"]]
            is_subject = pid in spec["parts"] or (
                spec.get("focus_components") and pid.startswith(COMPONENT_PREFIX)
            )
            if is_subject:
                continue
            lo, hi = int(shot["frame_start"]), int(shot["frame_end"])
            if intervals and lo <= intervals[-1][1] + 1:
                intervals[-1][1] = max(intervals[-1][1], hi)
            else:
                intervals.append([lo, hi])
        keys: list[tuple[int, bool]] = [(1, False)]
        for lo, hi in intervals:
            keys.append((lo, True))
            keys.append((hi + 1, False))
        schedule[pid] = keys
    return schedule


def idle_offsets(sign: float, timing: Mapping[str, Any] = MOTION_TIMING) -> list[float]:
    """One sine cycle over the hold: ``0, ±A, 0, ∓A, 0`` (returns to pose)."""
    amp = float(timing["idle_amplitude_mm"]) * (1.0 if sign >= 0 else -1.0)
    count = int(timing["idle_cycle_keys"])
    return [round(amp * math.sin(math.pi * j / 2.0), 6) for j in range(count)]


def idle_frames(hold_start: float, hold_end: float, timing: Mapping[str, Any] = MOTION_TIMING) -> list[int]:
    count = int(timing["idle_cycle_keys"])
    if hold_end <= hold_start:
        return [int(hold_start)] * count
    step = (hold_end - hold_start) / (count - 1)
    return [int(round(hold_start + j * step)) for j in range(count)]
