"""Create deterministic cameras for the static R1 exploded presentation."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import json
import math
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.task08_data import write_json

try:  # pragma: no cover - exercised by Blender integration.
    import bpy  # type: ignore
    from mathutils import Vector  # type: ignore
except ImportError:  # pragma: no cover
    bpy = None  # type: ignore
    Vector = None  # type: ignore


CAMERA_NAMES = (
    "CAM_EXPLODED_HERO",
    "CAM_EXPLODED_ENGINEERING",
    "CAM_EXPLODED_TOP",
    "CAM_EXPLODED_REAR",
)


def camera_configs_for_bounds(bounds: Mapping[str, Sequence[float]]) -> dict[str, dict[str, Any]]:
    """Return camera transforms/settings derived only from visible bounds."""
    low = _vector(bounds["min"], "bounds.min")
    high = _vector(bounds["max"], "bounds.max")
    target = [(left + right) / 2.0 for left, right in zip(low, high)]
    dimensions = [right - left for left, right in zip(low, high)]
    diagonal = math.sqrt(sum(value * value for value in dimensions))
    distance = max(diagonal * 1.75, 500.0)
    ortho_scale = max(dimensions[0], dimensions[1], dimensions[2]) * 1.22

    directions = {
        "CAM_EXPLODED_HERO": (0.70, -0.70, 0.48),
        "CAM_EXPLODED_ENGINEERING": (0.68, -0.68, 0.72),
        "CAM_EXPLODED_TOP": (0.0, 0.0, 1.0),
        "CAM_EXPLODED_REAR": (-0.70, 0.70, 0.48),
    }
    configs: dict[str, dict[str, Any]] = {}
    for name in CAMERA_NAMES:
        direction = _normalise(directions[name])
        location = [target[index] + direction[index] * distance for index in range(3)]
        configs[name] = {
            "name": name,
            "type": "ORTHO" if name in {"CAM_EXPLODED_ENGINEERING", "CAM_EXPLODED_TOP"} else "PERSP",
            "target": target,
            "location": location,
            "direction": list(direction),
            "lens_mm": 85.0 if name == "CAM_EXPLODED_HERO" else 70.0,
            "ortho_scale_mm": ortho_scale,
            "clip_start_mm": 0.1,
            "clip_end_mm": max(distance * 3.0, 10000.0),
        }
    return {
        "layout_version": "r1",
        "camera_names": list(CAMERA_NAMES),
        "visible_bounds": {"min": low, "max": high, "dimensions": dimensions},
        "render_resolution": [1200, 900],
        "cameras": configs,
    }


def setup_r1_cameras(project_root: Path) -> dict[str, Any]:
    """Open the R1 scene, create cameras, write config, and save the scene."""
    if bpy is None or Vector is None:
        raise RuntimeError("Blender bpy is required to create R1 cameras")
    root = Path(project_root).expanduser().resolve()
    blend_path = root / "stage_09A_R1_exploded_rework/scene/exploded_layout_v2.blend"
    bpy.ops.wm.open_mainfile(filepath=str(blend_path))
    visible = [
        obj
        for obj in bpy.data.objects
        if obj.type == "MESH" and obj.get("source") == "original_stl" and not obj.hide_render
    ]
    bounds = _object_bounds(visible)
    payload = camera_configs_for_bounds(bounds)
    camera_collection = _ensure_collection("R1_CAMERAS")
    for name in CAMERA_NAMES:
        old = bpy.data.objects.get(name)
        if old is not None:
            bpy.data.objects.remove(old, do_unlink=True)
        config = payload["cameras"][name]
        data = bpy.data.cameras.new(name)
        camera = bpy.data.objects.new(name, data)
        camera_collection.objects.link(camera)
        camera.location = config["location"]
        camera.rotation_euler = (
            Vector(config["target"]) - camera.location
        ).to_track_quat("-Z", "Y").to_euler()
        data.type = config["type"]
        data.lens = config["lens_mm"]
        data.ortho_scale = config["ortho_scale_mm"]
        data.clip_start = config["clip_start_mm"]
        data.clip_end = config["clip_end_mm"]
        camera["r1_camera_role"] = name.removeprefix("CAM_EXPLODED_").lower()
        camera["r1_animation_created"] = False
    bpy.context.scene.camera = bpy.data.objects["CAM_EXPLODED_HERO"]
    _configure_scene()
    config_path = root / "stage_09A_R1_exploded_rework/config/camera_config.json"
    write_json(config_path, payload)
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    return {"output": str(blend_path), "camera_config": str(config_path), "camera_names": list(CAMERA_NAMES)}


def _object_bounds(objects: Sequence[Any]) -> dict[str, list[float]]:
    if not objects:
        raise ValueError("R1 camera setup requires visible source objects")
    low = [float("inf")] * 3
    high = [float("-inf")] * 3
    for obj in objects:
        for corner in obj.bound_box:
            point = obj.matrix_world @ Vector(corner)
            for index in range(3):
                low[index] = min(low[index], float(point[index]))
                high[index] = max(high[index], float(point[index]))
    return {"min": low, "max": high}


def _ensure_collection(name: str) -> Any:
    collection = bpy.data.collections.get(name)
    if collection is None:
        collection = bpy.data.collections.new(name)
    if collection.name not in {child.name for child in bpy.context.scene.collection.children}:
        bpy.context.scene.collection.children.link(collection)
    return collection


def _configure_scene() -> None:
    scene = bpy.context.scene
    scene.render.resolution_x = 1200
    scene.render.resolution_y = 900
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.studio_light = "paint.sl"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_shadows = True
    scene.display.shading.show_cavity = True
    scene.display.shading.cavity_type = "WORLD"
    scene.display.shading.show_specular_highlight = False
    scene.display.shading.background_type = "WORLD"
    scene.world.color = (0.055, 0.065, 0.08)


def _vector(value: Any, label: str) -> list[float]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 3:
        raise ValueError(f"{label} must be a three-value vector")
    result = [float(item) for item in value]
    if not all(math.isfinite(item) for item in result):
        raise ValueError(f"{label} must be finite")
    return result


def _normalise(value: Sequence[float]) -> list[float]:
    length = math.sqrt(sum(float(item) * float(item) for item in value))
    if length <= 0.0:
        raise ValueError("camera direction cannot be zero")
    return [float(item) / length for item in value]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args(argv if argv is not None else _script_arguments())
    print(json.dumps(setup_r1_cameras(args.project_root), ensure_ascii=False, sort_keys=True))
    return 0


def _script_arguments() -> list[str]:
    arguments = list(sys.argv[1:])
    return arguments[arguments.index("--") + 1 :] if "--" in arguments else arguments


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
