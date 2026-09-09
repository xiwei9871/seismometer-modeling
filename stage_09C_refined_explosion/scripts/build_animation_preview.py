"""Build the review-only Task 9C keyframe plan and apply it in Blender."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import argparse
import json
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.task08_data import load_json, write_json
from stage_09C_refined_explosion.scripts.build_refined_layout import (
    EXPECTED_PART_IDS,
    VISIBLE_PART_IDS,
    build_refined_layout,
    validate_refined_layout,
)

try:  # pragma: no cover - executed by Blender.
    import bpy  # type: ignore
except ImportError:  # pragma: no cover
    bpy = None  # type: ignore


ANIMATION_PLAN_PATH = "stage_09C_refined_explosion/config/animation_plan.json"
BLEND_PATH = "stage_09C_refined_explosion/scene/exploded_animation_preview.blend"
FPS = 30
FRAME_START = 1
FRAME_END = 540


def build_animation_plan(project_root: Path) -> dict[str, Any]:
    root = Path(project_root).expanduser().resolve()
    layout_path = root / "stage_09C_refined_explosion/config/refined_layout.json"
    layout = validate_refined_layout(load_json(layout_path)) if layout_path.is_file() else build_refined_layout(root)
    parts = layout["parts"]
    ranges = {
        "MAIN_STACK": (60, 210),
        "TOP_INTERFACE_BRANCH": (110, 230),
        "PCB_BRANCH": (170, 330),
        "SENSOR_BRANCH": (190, 340),
        "BATTERY_BRANCH": (230, 360),
        "LEVELING_BRANCH": (300, 390),
    }
    part_tracks = []
    for part_id in VISIBLE_PART_IDS:
        record = parts[part_id]
        group = str(record["presentation_group"])
        start, end = ranges[group]
        if part_id == "PART_001":
            start = end = FRAME_START
        part_tracks.append(
            {
                "part_id": part_id,
                "group": group,
                "assembled_frame": FRAME_START,
                "move_start_frame": start,
                "move_end_frame": end,
                "refined_frame": FRAME_END,
                "interpolation": "BEZIER_EASE_IN_OUT",
                "overshoot": False,
            }
        )
    hidden = [part_id for part_id in EXPECTED_PART_IDS if part_id not in VISIBLE_PART_IDS]
    plan = {
        "plan_version": "9c_preview_v1",
        "fps": FPS,
        "frame_range": [FRAME_START, FRAME_END],
        "total_duration_seconds": FRAME_END / FPS,
        "animation_created": True,
        "animation_anchor": "PART_001",
        "easing": "BEZIER_EASE_IN_OUT",
        "overshoot": False,
        "keyframe_scope": "VISIBLE_MAJOR_MEDIUM_ONLY",
        "animated_part_ids": list(VISIBLE_PART_IDS),
        "hidden_part_ids": hidden,
        "tracks": part_tracks,
        "stages": [
            {"stage_id": "ASSEMBLED_HOLD", "frames": [1, 60]},
            {"stage_id": "PRIMARY_Z_STACK", "frames": [60, 210]},
            {"stage_id": "PCB_SENSOR_LOCAL", "frames": [170, 340]},
            {"stage_id": "BATTERY_LEVELING", "frames": [230, 390]},
            {"stage_id": "FULL_EXPLODED_HOLD", "frames": [420, 540]},
        ],
        "source": "Task 9C refined layout; review preview only",
    }
    return validate_animation_plan(plan)


def validate_animation_plan(plan: Mapping[str, Any]) -> dict[str, Any]:
    if plan.get("plan_version") != "9c_preview_v1":
        raise ValueError("Task 9C animation plan version is invalid")
    if plan.get("fps") != FPS or plan.get("frame_range") != [FRAME_START, FRAME_END]:
        raise ValueError("Task 9C animation timing is invalid")
    if float(plan.get("total_duration_seconds", 0.0)) < 15.0 or float(plan.get("total_duration_seconds", 0.0)) > 22.0:
        raise ValueError("Task 9C animation duration must be 15-22 seconds")
    if plan.get("overshoot") is not False or plan.get("easing") != "BEZIER_EASE_IN_OUT":
        raise ValueError("Task 9C animation easing policy is invalid")
    if list(plan.get("animated_part_ids") or []) != list(VISIBLE_PART_IDS):
        raise ValueError("Task 9C animation scope must contain exactly visible important parts")
    if set(plan.get("hidden_part_ids") or ()) & set(VISIBLE_PART_IDS):
        raise ValueError("Task 9C hidden part list overlaps animation scope")
    tracks = plan.get("tracks")
    if not isinstance(tracks, list) or len(tracks) != len(VISIBLE_PART_IDS):
        raise ValueError("Task 9C track count is invalid")
    for track in tracks:
        if track.get("part_id") not in VISIBLE_PART_IDS:
            raise ValueError("Task 9C track contains a hidden or unknown part")
        if track.get("overshoot") is not False or track.get("interpolation") != "BEZIER_EASE_IN_OUT":
            raise ValueError("Task 9C track easing policy is invalid")
    return dict(plan)


def write_animation_plan(project_root: Path, plan: Mapping[str, Any]) -> Path:
    root = Path(project_root).expanduser().resolve()
    path = root / ANIMATION_PLAN_PATH
    write_json(path, validate_animation_plan(plan))
    return path


def apply_animation_preview(project_root: Path) -> dict[str, Any]:
    if bpy is None:
        raise RuntimeError("Blender bpy is required to build Task 9C animation preview")
    root = Path(project_root).expanduser().resolve()
    layout = validate_refined_layout(
        load_json(root / "stage_09C_refined_explosion/config/refined_layout.json")
    )
    plan = build_animation_plan(root)
    bpy.ops.wm.open_mainfile(filepath=str(root / "stage_09C_refined_explosion/scene/exploded_animation_preview.blend"))
    objects = _source_objects()
    _validate_geometry(objects)
    bpy.context.scene.render.fps = FPS
    bpy.context.scene.frame_start = FRAME_START
    bpy.context.scene.frame_end = FRAME_END
    for track in plan["tracks"]:
        obj = objects[track["part_id"]]
        record = layout["parts"][track["part_id"]]
        obj.animation_data_clear()
        assembled = record["assembled_location"]
        refined = record["refined_presentation_location"]
        for frame, location in (
            (FRAME_START, assembled),
            (track["move_start_frame"], assembled),
            (track["move_end_frame"], refined),
            (FRAME_END, refined),
        ):
            obj.location = location
            obj.keyframe_insert(data_path="location", frame=frame, group="Task9C Location")
            obj.keyframe_insert(data_path="rotation_euler", frame=frame, group="Task9C Rotation")
        _set_bezier(obj)
        obj["task09c_animation_enabled"] = True
        obj["task09c_assembled_location"] = list(assembled)
        obj["task09c_refined_location"] = list(refined)
    for part_id, obj in objects.items():
        if part_id not in VISIBLE_PART_IDS:
            obj.animation_data_clear()
            obj["task09c_animation_enabled"] = False
    bpy.context.scene["task09c_animation_created"] = True
    bpy.context.scene["task09c_animation_plan_version"] = plan["plan_version"]
    output = root / BLEND_PATH
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output))
    return {
        "output": str(output),
        "animation_created": True,
        "animated_part_count": len(VISIBLE_PART_IDS),
        "hidden_part_animation_count": 0,
        "frame_range": [FRAME_START, FRAME_END],
        "fps": FPS,
    }


def _source_objects() -> dict[str, Any]:
    objects = {
        str(obj.get("part_id")): obj
        for obj in bpy.data.objects
        if obj.type == "MESH" and obj.get("source") == "original_stl"
    }
    if set(objects) != set(EXPECTED_PART_IDS):
        raise ValueError("Task 9C scene source coverage is not PART_001..PART_082")
    return objects


def _validate_geometry(objects: Mapping[str, Any]) -> None:
    vertices = sum(len(obj.data.vertices) for obj in objects.values())
    polygons = sum(len(obj.data.polygons) for obj in objects.values())
    if vertices != 221902 or polygons != 444296:
        raise ValueError("Task 9C frozen geometry totals changed")


def _set_bezier(obj: Any) -> None:
    if obj.animation_data is None or obj.animation_data.action is None:
        raise ValueError(f"Task 9C keyframes were not created for {obj.get('part_id')}")
    for curve in iter_action_fcurves(obj.animation_data.action):
        for key in curve.keyframe_points:
            key.interpolation = "BEZIER"
            key.handle_left_type = "AUTO"
            key.handle_right_type = "AUTO"


def iter_action_fcurves(action: Any):
    """Yield F-curves for both legacy and Blender 5.2 layered Actions.

    Blender 5.2 stores action curves below layers/strips/channelbags, while
    older Blender versions exposed them directly as ``action.fcurves``.
    Keeping this compatibility shim here makes the animation builder usable
    with the validated Blender 5.2 pipeline without changing scene geometry.
    """
    if hasattr(action, "fcurves"):
        yield from action.fcurves
        return
    for layer in action.layers:
        for strip in layer.strips:
            for channelbag in strip.channelbags:
                yield from channelbag.fcurves


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args(argv if argv is not None else _script_arguments())
    result = apply_animation_preview(args.project_root)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


def _script_arguments() -> list[str]:
    arguments = list(sys.argv[1:])
    return arguments[arguments.index("--") + 1 :] if "--" in arguments else arguments


if __name__ == "__main__":
    raise SystemExit(main())
