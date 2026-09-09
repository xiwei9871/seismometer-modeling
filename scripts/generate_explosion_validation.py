"""Render fixed, neutral inspection views from the Stage 03 Blender scene."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.task09_data import validate_task09_baseline

try:  # Blender is optional for import/contract tests.
    import bpy  # type: ignore
    from mathutils import Vector  # type: ignore
except ImportError:  # pragma: no cover
    bpy = None  # type: ignore
    Vector = None  # type: ignore


VIEW_NAMES = (
    "exploded_front",
    "exploded_side",
    "exploded_top",
    "exploded_iso_front",
    "exploded_iso_rear",
)


def generate_explosion_validation(project_root: Path) -> dict[str, Any]:
    """Render five fixed views without saving scene changes."""
    if bpy is None or Vector is None:
        raise RuntimeError("Blender bpy is required for validation renders")
    root = Path(project_root).expanduser().resolve()
    baseline = validate_task09_baseline(root)
    blend = root / "output/stage03_exploded_preview.blend"
    if not blend.is_file():
        raise ValueError("stage03_exploded_preview.blend is missing")
    output_dir = root / "output/explosion_validation"
    output_dir.mkdir(parents=True, exist_ok=True)

    bpy.ops.wm.open_mainfile(filepath=str(blend))
    source_objects = [
        obj
        for obj in bpy.data.objects
        if obj.type == "MESH" and obj.get("source") == "original_stl"
    ]
    if len(source_objects) != baseline["source_parts"]:
        raise ValueError("Stage 03 source object count does not match frozen baseline")
    camera = _make_camera()
    bpy.context.scene.camera = camera
    _make_neutral_world()
    try:
        bounds = _bounds(source_objects)
        target = Vector([(low + high) / 2.0 for low, high in zip(bounds[0], bounds[1])])
        radius = max((high - low for low, high in zip(bounds[0], bounds[1]))) * 1.25
        directions = {
            "exploded_front": Vector((0.0, -1.0, 0.0)),
            "exploded_side": Vector((1.0, 0.0, 0.0)),
            "exploded_top": Vector((0.0, 0.0, 1.0)),
            "exploded_iso_front": Vector((1.0, -1.0, 0.8)),
            "exploded_iso_rear": Vector((-1.0, 1.0, 0.8)),
        }
        rendered: list[str] = []
        for view_name in VIEW_NAMES:
            _aim_camera(camera, target, directions[view_name], radius)
            path = output_dir / f"{view_name}.png"
            bpy.context.scene.render.filepath = str(path)
            bpy.ops.render.render(write_still=True)
            rendered.append(str(path))
        return {
            "views": rendered,
            "view_count": len(rendered),
            "source_baseline": baseline,
            "scene_state": "exploded",
            "materials": "neutral_workbench_inspection_only",
            "animation_created": False,
        }
    finally:
        _remove_temporary_objects(camera)


def _make_camera() -> Any:
    data = bpy.data.cameras.new("Task09A_Validation_Camera")
    camera = bpy.data.objects.new("Task09A_Validation_Camera", data)
    bpy.context.scene.collection.objects.link(camera)
    data.type = "ORTHO"
    data.lens = 50
    return camera


def _make_neutral_world() -> None:
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.studio_light = "paint.sl"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_shadows = True
    scene.display.shading.show_cavity = True
    scene.display.shading.background_type = "WORLD"
    scene.display.shading.show_specular_highlight = False
    scene.render.resolution_x = 900
    scene.render.resolution_y = 700
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.world.color = (0.055, 0.065, 0.08)


def _bounds(objects: Sequence[Any]) -> tuple[list[float], list[float]]:
    lows = [float("inf")] * 3
    highs = [float("-inf")] * 3
    for obj in objects:
        for corner in obj.bound_box:
            world = obj.matrix_world @ Vector(corner)
            for index in range(3):
                lows[index] = min(lows[index], world[index])
                highs[index] = max(highs[index], world[index])
    if any(not math.isfinite(value) for value in lows + highs):
        raise ValueError("source object bounds are not finite")
    return lows, highs


def _aim_camera(camera: Any, target: Any, direction: Any, radius: float) -> None:
    vector = direction.normalized()
    camera.location = target + vector * radius
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera.data.ortho_scale = radius * 1.25


def _remove_temporary_objects(camera: Any) -> None:
    if bpy.data.objects.get(camera.name) is not None:
        bpy.data.objects.remove(camera, do_unlink=True)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args(argv)
    result = generate_explosion_validation(args.project_root)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else None))
