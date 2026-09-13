"""Apply Task 10-V2 story-state keyframes to parts and PCB components."""

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
from stage_10_product_story.scripts.apply_story_animation import KEYFRAME_STATES
from stage_10_product_story.scripts.build_story_scene import (
    EXPECTED_PART_IDS,
    HIDDEN_PART_IDS,
    VISIBLE_PART_IDS,
)
from stage_10V2_product_story.scripts.story_v2_data import SCENE_OUTPUT, STATE_OUTPUT

try:  # pragma: no cover - Blender-only implementation.
    import bpy  # type: ignore
except ImportError:  # pragma: no cover
    bpy = None  # type: ignore


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

    for part_id in VISIBLE_PART_IDS:
        _key_transforms(objects[part_id], state_data, lambda state: state["parts"][part_id])
        objects[part_id]["task10v2_animation_enabled"] = True
        objects[part_id]["task10v2_story_animation_enabled"] = True
        objects[part_id]["task10v2_story_state_source"] = STATE_OUTPUT
    for part_id in HIDDEN_PART_IDS:
        objects[part_id].animation_data_clear()
        objects[part_id]["task10v2_animation_enabled"] = False
        objects[part_id]["task10v2_story_animation_enabled"] = False
        objects[part_id]["task10v2_story_state_source"] = STATE_OUTPUT
    for component_id, obj in components.items():
        _key_transforms(obj, state_data, lambda state, cid=component_id: state["components"][cid])
        obj["task10v2_animation_enabled"] = True
        obj["task10v2_story_animation_enabled"] = True
        obj["task10v2_story_state_source"] = STATE_OUTPUT

    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = 900
    scene.render.fps = 30
    scene["task10v2_animation_created"] = True
    scene["task10v2_keyframe_state_count"] = len(KEYFRAME_STATES)
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
        "keyframe_states": len(KEYFRAME_STATES),
    }


def _key_transforms(obj: Any, state_data: Mapping[str, Any], transform_for) -> None:
    obj.animation_data_clear()
    for frame, state_id in KEYFRAME_STATES:
        transform = transform_for(state_data["states"][state_id])
        obj.location = transform["location"]
        obj.rotation_euler = transform["rotation_euler"]
        obj.scale = transform["scale"]
        obj.keyframe_insert(data_path="location", frame=frame, group="Task10V2 Story Location")
        obj.keyframe_insert(data_path="rotation_euler", frame=frame, group="Task10V2 Story Rotation")
        obj.keyframe_insert(data_path="scale", frame=frame, group="Task10V2 Story Scale")
    _set_bezier(obj)


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
