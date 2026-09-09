"""Render Task 9C refined stills, detail views, and review MP4."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import argparse
import json
import math
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.task08_data import load_json, write_json
from stage_09C_refined_explosion.scripts.build_refined_layout import validate_refined_layout

try:  # pragma: no cover - executed by Blender.
    import bpy  # type: ignore
    from mathutils import Vector  # type: ignore
except ImportError:  # pragma: no cover
    bpy = None  # type: ignore
    Vector = None  # type: ignore


BLEND_PATH = "stage_09C_refined_explosion/scene/exploded_animation_preview.blend"
LAYOUT_PATH = "stage_09C_refined_explosion/config/refined_layout.json"
CAMERA_CONFIG_PATH = "stage_09C_refined_explosion/config/camera_config.json"
RENDER_DIR = "stage_09C_refined_explosion/renders"
CAMERA_NAMES = (
    "CAM_REFINED_HERO",
    "CAM_REFINED_ENGINEERING",
    "CAM_REFINED_PCB_DETAIL",
    "CAM_REFINED_SENSOR_DETAIL",
)
STILL_OUTPUTS = {
    "hero": "exploded_hero_refined.png",
    "engineering": "exploded_engineering_refined.png",
    "pcb": "pcb_detail_refined.png",
    "sensor": "sensor_detail_refined.png",
}
KEYFRAME_FRAMES = (1, 120, 240, 360, 480, 540)


def camera_config_for_layout(layout: Mapping[str, Any]) -> dict[str, Any]:
    """Build deterministic cameras from the refined layout bbox."""
    visible = [
        record for record in layout["parts"].values()
        if record["presentation_visibility"] == "VISIBLE"
    ]
    bounds = _bounds(visible)
    low, high = bounds["min"], bounds["max"]
    target = [(low[index] + high[index]) / 2.0 for index in range(3)]
    dimensions = bounds["dimensions"]
    diagonal = math.sqrt(sum(value * value for value in dimensions))
    max_dimension = max(dimensions)
    hero_direction = _normalise((0.70, -0.70, 0.48))
    engineering_direction = _normalise((0.68, -0.68, 0.72))
    detail_distance = max(diagonal * 0.62, 260.0)

    def camera(name: str, direction: Sequence[float], distance: float, camera_type: str, lens: float, ortho: float, camera_target: Sequence[float]) -> dict[str, Any]:
        unit = _normalise(direction)
        location = [float(camera_target[index]) + unit[index] * distance for index in range(3)]
        return {
            "name": name,
            "type": camera_type,
            "target": [float(value) for value in camera_target],
            "location": location,
            "direction": unit,
            "lens_mm": lens,
            "ortho_scale_mm": ortho,
            "clip_start_mm": 0.1,
            "clip_end_mm": max(distance * 4.0, 10000.0),
        }

    group_targets = {
        "pcb": _group_target(layout, "PCB_BRANCH"),
        "sensor": _group_target(layout, "SENSOR_BRANCH"),
    }
    return {
        "layout_version": "9c_refined_v1",
        "camera_names": list(CAMERA_NAMES),
        "render_resolution": [1200, 900],
        "visible_bounds": bounds,
        "cameras": {
            "CAM_REFINED_HERO": camera("CAM_REFINED_HERO", hero_direction, max(diagonal * 2.30, 500.0), "PERSP", 85.0, max_dimension * 1.45, target),
            "CAM_REFINED_ENGINEERING": camera("CAM_REFINED_ENGINEERING", engineering_direction, max(diagonal * 2.20, 500.0), "ORTHO", 70.0, max_dimension * 1.46, target),
            "CAM_REFINED_PCB_DETAIL": camera("CAM_REFINED_PCB_DETAIL", (0.70, -0.70, 0.42), detail_distance, "PERSP", 72.0, max_dimension * 0.72, group_targets["pcb"]),
            "CAM_REFINED_SENSOR_DETAIL": camera("CAM_REFINED_SENSOR_DETAIL", (-0.70, -0.70, 0.42), detail_distance, "PERSP", 72.0, max_dimension * 0.72, group_targets["sensor"]),
        },
    }


def write_camera_config(project_root: Path, layout: Mapping[str, Any]) -> Path:
    root = Path(project_root).expanduser().resolve()
    path = root / CAMERA_CONFIG_PATH
    write_json(path, camera_config_for_layout(validate_refined_layout(layout)))
    return path


def render_refined_outputs(project_root: Path) -> dict[str, Any]:
    if bpy is None or Vector is None:
        raise RuntimeError("Blender bpy is required to render Task 9C outputs")
    root = Path(project_root).expanduser().resolve()
    blend_path = root / BLEND_PATH
    bpy.ops.wm.open_mainfile(filepath=str(blend_path))
    config = load_json(root / CAMERA_CONFIG_PATH)
    _create_cameras(config)
    _configure_scene()
    output_dir = root / RENDER_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    still_paths: dict[str, str] = {}
    bpy.context.scene.frame_set(540)
    for role, filename in STILL_OUTPUTS.items():
        camera_name = {
            "hero": "CAM_REFINED_HERO",
            "engineering": "CAM_REFINED_ENGINEERING",
            "pcb": "CAM_REFINED_PCB_DETAIL",
            "sensor": "CAM_REFINED_SENSOR_DETAIL",
        }[role]
        bpy.context.scene.camera = bpy.data.objects[camera_name]
        path = output_dir / filename
        _configure_png(1200, 900)
        bpy.context.scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        still_paths[role] = str(path)

    frame_dir = output_dir / "animation_keyframes"
    frame_dir.mkdir(parents=True, exist_ok=True)
    bpy.context.scene.camera = bpy.data.objects["CAM_REFINED_HERO"]
    for frame in KEYFRAME_FRAMES:
        bpy.context.scene.frame_set(frame)
        _configure_png(600, 450)
        path = frame_dir / f"frame_{frame:03d}.png"
        bpy.context.scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)

    mp4_path = output_dir / "exploded_preview.mp4"
    bpy.context.scene.frame_start = 1
    bpy.context.scene.frame_end = 540
    bpy.context.scene.frame_set(1)
    scene = bpy.context.scene
    scene.render.resolution_x = 600
    scene.render.resolution_y = 450
    scene.render.resolution_percentage = 100
    # Blender 5.2 separates the output media selector from the image format.
    # Select VIDEO before requesting the FFmpeg format; otherwise the dynamic
    # enum intentionally exposes image formats only.
    scene.render.image_settings.media_type = "VIDEO"
    scene.render.image_settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    scene.render.ffmpeg.constant_rate_factor = "MEDIUM"
    scene.render.filepath = str(mp4_path)
    bpy.ops.render.render(animation=True)

    bpy.context.scene.frame_set(540)
    _configure_png(1200, 900)
    bpy.context.scene.render.filepath = str(output_dir / STILL_OUTPUTS["hero"])
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    outputs = {**still_paths, "mp4": str(mp4_path), "keyframe_dir": str(frame_dir)}
    return {"outputs": outputs, "camera_names": list(CAMERA_NAMES), "frame_range": [1, 540], "fps": 30}


def _create_cameras(config: Mapping[str, Any]) -> None:
    collection = bpy.data.collections.get("9C_CAMERAS")
    if collection is None:
        collection = bpy.data.collections.new("9C_CAMERAS")
        bpy.context.scene.collection.children.link(collection)
    for name in CAMERA_NAMES:
        old = bpy.data.objects.get(name)
        if old is not None:
            bpy.data.objects.remove(old, do_unlink=True)
        record = config["cameras"][name]
        data = bpy.data.cameras.new(name)
        camera = bpy.data.objects.new(name, data)
        collection.objects.link(camera)
        camera.location = record["location"]
        camera.rotation_euler = (Vector(record["target"]) - camera.location).to_track_quat("-Z", "Y").to_euler()
        data.type = record["type"]
        data.lens = float(record["lens_mm"])
        data.ortho_scale = float(record["ortho_scale_mm"])
        data.clip_start = float(record["clip_start_mm"])
        data.clip_end = float(record["clip_end_mm"])
        camera["task09c_camera_role"] = name.removeprefix("CAM_REFINED_").lower()


def _configure_scene() -> None:
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.film_transparent = False
    scene.render.image_settings.color_mode = "RGBA"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.studio_light = "paint.sl"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_shadows = True
    scene.display.shading.show_cavity = True
    scene.display.shading.cavity_type = "WORLD"
    scene.display.shading.show_specular_highlight = False
    scene.display.shading.background_type = "WORLD"
    scene.world.color = (0.055, 0.065, 0.08)
    scene.render.fps = 30


def _configure_png(width: int, height: int) -> None:
    scene = bpy.context.scene
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.media_type = "IMAGE"
    scene.render.image_settings.file_format = "PNG"


def _bounds(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    low = [float("inf")] * 3
    high = [float("-inf")] * 3
    for record in records:
        location = record["refined_presentation_location"]
        dimensions = record["bbox_dimensions_mm"]
        for index in range(3):
            half = float(dimensions[index]) / 2.0
            low[index] = min(low[index], float(location[index]) - half)
            high[index] = max(high[index], float(location[index]) + half)
    return {"min": low, "max": high, "dimensions": [high[index] - low[index] for index in range(3)]}


def _group_target(layout: Mapping[str, Any], group_id: str) -> list[float]:
    records = [
        record for record in layout["parts"].values()
        if record.get("presentation_group") == group_id and record.get("presentation_visibility") == "VISIBLE"
    ]
    if not records:
        raise ValueError(f"no visible parts for detail camera group {group_id}")
    return [sum(float(record["refined_presentation_location"][axis]) for record in records) / len(records) for axis in range(3)]


def _normalise(value: Sequence[float]) -> list[float]:
    length = math.sqrt(sum(float(item) ** 2 for item in value))
    if length <= 0.0:
        raise ValueError("camera direction cannot be zero")
    return [float(item) / length for item in value]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args(argv if argv is not None else _script_arguments())
    print(json.dumps(render_refined_outputs(args.project_root), ensure_ascii=False, sort_keys=True))
    return 0


def _script_arguments() -> list[str]:
    arguments = list(sys.argv[1:])
    return arguments[arguments.index("--") + 1 :] if "--" in arguments else arguments


if __name__ == "__main__":
    raise SystemExit(main())
