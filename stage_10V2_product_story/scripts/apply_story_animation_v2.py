"""Apply Task 10-V4 continuous-motion keyframes to parts and PCB components.

Replaces the V1 hold-tableau scheme (state keyed at both shot boundaries —
a 1-frame hard cut). Each shot now opens with a staggered two-phase arrival
(parts ease from the previous pose into the shot pose), then holds with a
full-cycle idle float while the camera drifts (see motion_timing.py and
docs/superpowers/specs/2026-09-14-task10v4-motion-language-design.md).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.task08_data import load_json
from stage_10_product_story.scripts.story_data import build_story_config
from stage_10_product_story.scripts.build_story_scene import (
    EXPECTED_PART_IDS,
    HIDDEN_PART_IDS,
    VISIBLE_PART_IDS,
)
from stage_10V2_product_story.scripts import frustum_math as fm
from stage_10V2_product_story.scripts.motion_timing import (
    arrival_windows,
    idle_frames,
    idle_offsets,
)
from stage_10V2_product_story.scripts.story_v2_data import SCENE_OUTPUT, STATE_OUTPUT

try:  # pragma: no cover - Blender-only implementation.
    import bpy  # type: ignore
except ImportError:  # pragma: no cover
    bpy = None  # type: ignore

# Parts closer than this to their ASSEMBLED pose do not float — the device
# never breathes while assembled.
IDLE_MIN_DISPLACEMENT_MM = 1.0
PCB_BOARD_PART_ID = "PART_019"
# Two-stage arrival (per the DCT teaching-manual reference): movers cover
# SETTLE_FRACTION of the travel quickly, then creep the last stretch so the
# landing reads as a mechanical seat rather than a hard stop.
SETTLE_FRACTION = 0.85
SETTLE_FRAMES = 10


def apply_story_animation_v2(project_root: Path) -> dict[str, Any]:
    if bpy is None:
        raise RuntimeError("Blender bpy is required to apply Task 10-V2 animation")
    root = Path(project_root).expanduser().resolve()
    scene_path = root / SCENE_OUTPUT
    state_data = load_json(root / STATE_OUTPUT)
    bpy.ops.wm.open_mainfile(filepath=str(scene_path))
    objects = _source_objects()
    _validate_geometry(objects)
    components = _component_objects()

    shots = build_story_config()["shots"]
    states = state_data["states"]
    windows = _shot_windows(shots, states)
    assembled = states["ASSEMBLED"]["parts"]
    assembled_components = states["ASSEMBLED"].get("components", {})

    sorted_parts = sorted(VISIBLE_PART_IDS)
    for part_id in VISIBLE_PART_IDS:
        sign = 1.0 if sorted_parts.index(part_id) % 2 == 0 else -1.0
        _key_part_motion(
            objects[part_id],
            part_id,
            shots,
            states,
            windows,
            assembled[part_id]["location"],
            sign,
        )
        objects[part_id]["task10v2_animation_enabled"] = True
        objects[part_id]["task10v2_story_animation_enabled"] = True
        objects[part_id]["task10v2_story_state_source"] = STATE_OUTPUT
        objects[part_id]["task10v2_motion_language"] = "v4_continuous"
    for part_id in HIDDEN_PART_IDS:
        objects[part_id].animation_data_clear()
        objects[part_id]["task10v2_animation_enabled"] = False
        objects[part_id]["task10v2_story_animation_enabled"] = False
        objects[part_id]["task10v2_story_state_source"] = STATE_OUTPUT
    board_axis = _idle_axis(
        states["PCB_FOCUS"]["parts"][PCB_BOARD_PART_ID]["location"],
        assembled[PCB_BOARD_PART_ID]["location"],
    )
    for component_id, obj in components.items():
        _key_component_motion(
            obj,
            component_id,
            shots,
            states,
            windows,
            assembled_components.get(component_id),
            board_axis,
        )
        obj["task10v2_animation_enabled"] = True
        obj["task10v2_story_animation_enabled"] = True
        obj["task10v2_story_state_source"] = STATE_OUTPUT
        obj["task10v2_motion_language"] = "v4_continuous"

    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = 900
    scene.render.fps = 30
    scene["task10v2_animation_created"] = True
    scene["task10v2_keyframe_state_count"] = len(shots)
    scene["task10v2_motion_language"] = "v4_continuous"
    scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=str(scene_path))
    return {
        "output": str(scene_path),
        "animation_created": True,
        "animated_part_count": len(VISIBLE_PART_IDS),
        "animated_component_count": len(components),
        "hidden_part_animation_count": 0,
        "frame_range": [1, 900],
        "fps": 30,
        "keyframe_states": len(shots),
        "motion_language": "v4_continuous",
    }


def _shot_windows(
    shots: Sequence[Mapping[str, Any]], states: Mapping[str, Any]
) -> list[dict[str, tuple[float, float]]]:
    """Arrival windows per shot, computed on source-part displacements."""
    per_shot: list[dict[str, tuple[float, float]]] = []
    for index, shot in enumerate(shots):
        prev_state = states[shots[index - 1]["state_id"]] if index else states[shot["state_id"]]
        next_state = states[shot["state_id"]]
        prev_locs = {pid: r["location"] for pid, r in prev_state["parts"].items()}
        next_locs = {pid: r["location"] for pid, r in next_state["parts"].items()}
        shell_first = shot["state_id"] != "REASSEMBLED"
        per_shot.append(
            arrival_windows(
                prev_locs,
                next_locs,
                int(shot["frame_start"]),
                shell_first,
                shot_id=shot["state_id"],
            )
        )
    return per_shot


def _idle_axis(
    state_location: Sequence[float], assembled_location: Sequence[float]
) -> tuple[float, float, float] | None:
    displacement = fm.v_sub(state_location, assembled_location)
    if fm.v_len(displacement) <= IDLE_MIN_DISPLACEMENT_MM:
        return None
    return fm.v_norm(displacement)


def _key_part_motion(
    obj: Any,
    part_id: str,
    shots: Sequence[Mapping[str, Any]],
    states: Mapping[str, Any],
    windows: Sequence[Mapping[str, tuple[float, float]]],
    assembled_location: Sequence[float],
    sign: float,
) -> None:
    obj.animation_data_clear()
    for index, shot in enumerate(shots):
        start = int(shot["frame_start"])
        end = int(shot["frame_end"])
        prev_state = states[shots[index - 1]["state_id"]] if index else states[shot["state_id"]]
        next_state = states[shot["state_id"]]
        prev_pose = prev_state["parts"][part_id]
        next_pose = next_state["parts"][part_id]
        _insert_pose(obj, start, prev_pose)
        window = windows[index].get(part_id)
        if window is not None:
            # Hold the previous pose until this part's stagger window opens —
            # without this key every part departs at the shot boundary and
            # the stagger only shows in arrival order.
            _insert_pose(obj, int(round(window[0])), prev_pose)
        arrive_end = int(round(window[1])) if window else start
        _key_settle(obj, prev_pose, next_pose, window, arrive_end)
        _insert_pose(obj, arrive_end, next_pose)
        axis = _idle_axis(next_pose["location"], assembled_location)
        if axis is not None:
            _key_idle(obj, next_pose, axis, sign, arrive_end, end)
        _insert_pose(obj, end, next_pose)
    _set_bezier(obj)


def _key_component_motion(
    obj: Any,
    component_id: str,
    shots: Sequence[Mapping[str, Any]],
    states: Mapping[str, Any],
    windows: Sequence[Mapping[str, tuple[float, float]]],
    assembled_record: Mapping[str, Any] | None,
    board_axis: tuple[float, float, float] | None,
) -> None:
    """Components fly and float rigidly with PART_019 (soldered assembly)."""
    obj.animation_data_clear()
    board_sign = 1.0
    for index, shot in enumerate(shots):
        start = int(shot["frame_start"])
        end = int(shot["frame_end"])
        prev_state = states[shots[index - 1]["state_id"]] if index else states[shot["state_id"]]
        next_state = states[shot["state_id"]]
        prev_pose = prev_state["components"][component_id]
        next_pose = next_state["components"][component_id]
        _insert_pose(obj, start, prev_pose)
        window = windows[index].get(PCB_BOARD_PART_ID)
        if window is not None:
            _insert_pose(obj, int(round(window[0])), prev_pose)
        arrive_end = int(round(window[1])) if window else start
        _key_settle(obj, prev_pose, next_pose, window, arrive_end)
        _insert_pose(obj, arrive_end, next_pose)
        if assembled_record is not None and board_axis is not None:
            own_axis = _idle_axis(next_pose["location"], assembled_record["location"])
            if own_axis is not None:
                _key_idle(obj, next_pose, board_axis, board_sign, arrive_end, end)
        _insert_pose(obj, end, next_pose)
    _set_bezier(obj)


def _key_idle(
    obj: Any,
    pose: Mapping[str, Any],
    axis: Sequence[float],
    sign: float,
    arrive_end: int,
    end: int,
) -> None:
    """Location-only float keys — one sine cycle, exact pose at both ends."""
    base = [float(v) for v in pose["location"]]
    for frame, offset in zip(idle_frames(arrive_end, end), idle_offsets(sign)):
        if frame <= arrive_end or frame >= end:
            continue  # endpoints already keyed with zero offset
        location = fm.v_add(base, fm.v_scale(axis, offset))
        obj.location = location
        obj.keyframe_insert(data_path="location", frame=frame, group="Task10V2 Idle Float")


def _key_settle(
    obj: Any,
    prev_pose: Mapping[str, Any],
    next_pose: Mapping[str, Any],
    window: tuple[float, float] | None,
    arrive_end: int,
) -> None:
    """Key the 85%-travel pose shortly before ``arrive_end``.

    The Bezier slope between the settle key and the landing key is much
    shallower than the main travel, so the part visibly decelerates into
    its seat — the 入位 beat from the reference manual.
    """
    if window is None:
        return
    window_start = int(round(window[0]))
    if arrive_end - window_start <= 2:
        return
    seat_frame = max(window_start + 1, arrive_end - SETTLE_FRAMES)
    mid = {
        "location": [
            float(prev_pose["location"][axis])
            + (float(next_pose["location"][axis]) - float(prev_pose["location"][axis]))
            * SETTLE_FRACTION
            for axis in range(3)
        ],
        "rotation_euler": list(next_pose["rotation_euler"]),
        "scale": list(next_pose["scale"]),
    }
    _insert_pose(obj, seat_frame, mid)


def _insert_pose(obj: Any, frame: int, pose: Mapping[str, Any]) -> None:
    obj.location = pose["location"]
    obj.rotation_euler = pose["rotation_euler"]
    obj.scale = pose["scale"]
    obj.keyframe_insert(data_path="location", frame=frame, group="Task10V2 Story Location")
    obj.keyframe_insert(data_path="rotation_euler", frame=frame, group="Task10V2 Story Rotation")
    obj.keyframe_insert(data_path="scale", frame=frame, group="Task10V2 Story Scale")


def _source_objects() -> dict[str, Any]:
    objects = {
        str(obj.get("part_id")): obj
        for obj in bpy.data.objects
        if obj.type == "MESH" and obj.get("source") == "original_stl"
    }
    if set(objects) != set(EXPECTED_PART_IDS):
        raise ValueError("Task 10-V2 scene source coverage changed")
    return objects


def _component_objects() -> dict[str, Any]:
    objects = {
        obj.name: obj
        for obj in bpy.data.objects
        if obj.type == "MESH" and obj.get("task10v2_presentation_component") is True
    }
    if len(objects) != 15:
        raise ValueError("Task 10-V2 presentation component coverage changed")
    return objects


def _validate_geometry(objects: Mapping[str, Any]) -> None:
    if len(objects) != 82:
        raise ValueError("Task 10-V2 source PART count changed")
    faces = sum(len(obj.data.polygons) for obj in objects.values())
    vertices = sum(len(obj.data.vertices) for obj in objects.values())
    if faces != 444296 or vertices != 221902:
        raise ValueError(f"Task 10-V2 frozen geometry totals changed: {faces}/{vertices}")


def _set_bezier(obj: Any) -> None:
    action = obj.animation_data.action if obj.animation_data is not None else None
    if action is None:
        raise ValueError(f"Task 10-V2 keyframes missing for {obj.name}")
    for curve in _iter_fcurves(action):
        for key in curve.keyframe_points:
            key.interpolation = "BEZIER"
            key.handle_left_type = "AUTO_CLAMPED"
            key.handle_right_type = "AUTO_CLAMPED"


def _iter_fcurves(action: Any):
    if hasattr(action, "fcurves"):
        yield from action.fcurves
        return
    for layer in action.layers:
        for strip in layer.strips:
            for channelbag in strip.channelbags:
                yield from channelbag.fcurves


def _script_arguments() -> list[str]:
    arguments = list(sys.argv[1:])
    return arguments[arguments.index("--") + 1 :] if "--" in arguments else arguments


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args(argv if argv is not None else _script_arguments())
    print(json.dumps(apply_story_animation_v2(args.project_root), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
