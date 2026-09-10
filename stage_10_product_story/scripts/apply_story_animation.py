"""Apply Task 10 story-state keyframes to the generated Blender scene."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.task08_data import load_json
from stage_10_product_story.scripts.build_story_scene import (
    EXPECTED_PART_IDS,
    HIDDEN_PART_IDS,
    SCENE_OUTPUT,
    VISIBLE_PART_IDS,
    _validate_geometry,
)

try:  # pragma: no cover - Blender-only implementation.
    import bpy  # type: ignore
except ImportError:  # pragma: no cover
    bpy = None  # type: ignore


KEYFRAME_STATES: tuple[tuple[int, str], ...] = (
    (1, "ASSEMBLED"),
    (60, "ASSEMBLED"),
    (75, "ASSEMBLED"),
    (150, "PRIMARY_ARCHITECTURE"),
    (165, "PRIMARY_ARCHITECTURE"),
    (210, "SENSOR_FOCUS"),
    (285, "SENSOR_FOCUS"),
    (330, "PCB_FOCUS"),
    (405, "PCB_FOCUS"),
    (450, "COMMUNICATION_FOCUS"),
    (495, "COMMUNICATION_FOCUS"),
    (550, "POWER_FOCUS"),
    (600, "POWER_FOCUS"),
    (650, "RUGGED_FOCUS"),
    (690, "RUGGED_FOCUS"),
    (705, "RUGGED_FOCUS"),
    (790, "REASSEMBLED"),
    (810, "FINAL_HERO"),
    (900, "FINAL_HERO"),
)


def apply_story_animation(project_root: Path) -> dict[str, Any]:
    if bpy is None:
        raise RuntimeError("Blender bpy is required to apply Task 10 animation")
    root = Path(project_root).expanduser().resolve()
    scene_path = root / SCENE_OUTPUT
    state_data = load_json(root / "stage_10_product_story/config/state_transforms.json")
    bpy.ops.wm.open_mainfile(filepath=str(scene_path))
    objects = _source_objects()
    _validate_geometry(objects)

    for part_id in VISIBLE_PART_IDS:
        obj = objects[part_id]
        obj.animation_data_clear()
        for frame, state_id in KEYFRAME_STATES:
            transform = state_data["states"][state_id]["parts"][part_id]
            obj.location = transform["location"]
            obj.rotation_euler = transform["rotation_euler"]
            obj.scale = transform["scale"]
            obj.keyframe_insert(data_path="location", frame=frame, group="Task10 Story Location")
            obj.keyframe_insert(data_path="rotation_euler", frame=frame, group="Task10 Story Rotation")
            obj.keyframe_insert(data_path="scale", frame=frame, group="Task10 Story Scale")
        _set_bezier(obj)
        obj["task10_animation_enabled"] = True
    for part_id in HIDDEN_PART_IDS:
        objects[part_id].animation_data_clear()
        objects[part_id]["task10_animation_enabled"] = False

    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = 900
    scene.render.fps = 30
    scene["task10_animation_created"] = True
    scene["task10_keyframe_state_count"] = len(KEYFRAME_STATES)
    scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=str(scene_path))
    return {
        "output": str(scene_path),
        "animation_created": True,
        "animated_part_count": len(VISIBLE_PART_IDS),
        "hidden_part_animation_count": 0,
        "frame_range": [1, 900],
        "fps": 30,
        "keyframe_states": len(KEYFRAME_STATES),
    }


def _source_objects() -> dict[str, Any]:
    objects = {
        str(obj.get("part_id")): obj
        for obj in bpy.data.objects
        if obj.type == "MESH" and obj.get("source") == "original_stl"
    }
    if set(objects) != set(EXPECTED_PART_IDS):
        raise ValueError("Task 10 scene source coverage changed")
    return objects


def _set_bezier(obj: Any) -> None:
    action = obj.animation_data.action if obj.animation_data is not None else None
    if action is None:
        raise ValueError(f"Task 10 keyframes missing for {obj.get('part_id')}")
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
    print(json.dumps(apply_story_animation(args.project_root), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

