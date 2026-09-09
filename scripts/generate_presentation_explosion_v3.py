"""Render four fixed inspection views of the v3 static presentation scene."""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.build_presentation_explosion_v3 import (
    _object_facts,
    _source_objects,
    validate_presentation_scene_facts,
)
from scripts.presentation_explosion_v3 import EXPECTED_PART_IDS
from scripts.task09_data import validate_task09_baseline

try:  # Blender is optional for contract tests.
    import bpy  # type: ignore
    from mathutils import Vector  # type: ignore
except ImportError:  # pragma: no cover
    bpy = None  # type: ignore
    Vector = None  # type: ignore


V3_VIEW_NAMES = (
    "exploded_iso_front_v3",
    "exploded_iso_rear_v3",
    "exploded_front_v3",
    "exploded_top_v3",
)
OUTPUT_BLEND = "output/stage03_presentation_exploded_v3.blend"
CAMERA_CLIP_END_MM = 10000.0


def render_result_contract(result: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the static-render result contract without requiring Blender."""
    if result.get("animation_created") is not False:
        raise ValueError("v3 presentation rendering must not create animation")
    return dict(result)


def generate_presentation_views(project_root: Path) -> dict[str, Any]:
    """Render the required v3 views without saving camera or scene changes."""
    if bpy is None or Vector is None:
        raise RuntimeError("Blender bpy is required for v3 presentation renders")
    root = Path(project_root).expanduser().resolve()
    baseline = validate_task09_baseline(root)
    blend = root / OUTPUT_BLEND
    if not blend.is_file():
        raise ValueError("stage03_presentation_exploded_v3.blend is missing")
    output_dir = root / "output/explosion_validation_v3"
    output_dir.mkdir(parents=True, exist_ok=True)

    bpy.ops.wm.open_mainfile(filepath=str(blend))
    objects = _source_objects()
    facts = [_object_facts(obj) for obj in objects.values()]
    scene_validation = validate_presentation_scene_facts(
        facts,
        vertices=sum(len(obj.data.vertices) for obj in objects.values()),
        polygons=sum(len(obj.data.polygons) for obj in objects.values()),
    )
    if any(obj.animation_data is not None for obj in bpy.data.objects):
        raise ValueError("v3 scene contains animation data before rendering")
    visible = [obj for obj in objects.values() if not obj.hide_render]
    if len(visible) != 44:
        raise ValueError(f"v3 render expected 44 visible source PARTs, got {len(visible)}")
    camera = _make_camera()
    bpy.context.scene.camera = camera
    _configure_scene()
    try:
        bounds = _bounds(visible)
        target = Vector(
            [(low + high) / 2.0 for low, high in zip(bounds[0], bounds[1])]
        )
        extent = max(high - low for low, high in zip(bounds[0], bounds[1]))
        radius = max(extent * 1.4, 1.0)
        directions = {
            "exploded_iso_front_v3": Vector((1.0, -1.0, 0.8)),
            "exploded_iso_rear_v3": Vector((-1.0, 1.0, 0.8)),
            "exploded_front_v3": Vector((0.0, -1.0, 0.0)),
            "exploded_top_v3": Vector((0.0, 0.0, 1.0)),
        }
        rendered: list[str] = []
        for view_name in V3_VIEW_NAMES:
            _aim_camera(camera, target, directions[view_name], radius)
            path = output_dir / f"{view_name}.png"
            bpy.context.scene.render.filepath = str(path)
            bpy.ops.render.render(write_still=True)
            rendered.append(str(path))
        return render_result_contract(
            {
                "views": rendered,
                "view_count": len(rendered),
                "source_baseline": baseline,
                "scene_validation": scene_validation,
                "visible_source_part_count": len(visible),
                "scene_state": "STATIC_HIERARCHICAL_PRESENTATION_V3",
                "animation_created": False,
            }
        )
    finally:
        _remove_temporary_objects(camera)


def _make_camera() -> Any:
    data = bpy.data.cameras.new("PresentationV3_Inspection_Camera")
    camera = bpy.data.objects.new("PresentationV3_Inspection_Camera", data)
    bpy.context.scene.collection.objects.link(camera)
    data.type = "ORTHO"
    data.lens = 50
    data.clip_start = 0.1
    data.clip_end = CAMERA_CLIP_END_MM
    return camera


def _configure_scene() -> None:
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.studio_light = "paint.sl"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_shadows = True
    scene.display.shading.show_cavity = True
    scene.display.shading.background_type = "WORLD"
    scene.display.shading.show_specular_highlight = False
    scene.render.resolution_x = 1100
    scene.render.resolution_y = 850
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
        raise ValueError("v3 visible source bounds are not finite")
    return lows, highs


def _aim_camera(camera: Any, target: Any, direction: Any, radius: float) -> None:
    vector = direction.normalized()
    camera.location = target + vector * radius
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera.data.ortho_scale = radius * 1.15


def _remove_temporary_objects(camera: Any) -> None:
    if bpy.data.objects.get(camera.name) is not None:
        bpy.data.objects.remove(camera, do_unlink=True)


def _script_arguments() -> list[str]:
    arguments = list(sys.argv[1:])
    return arguments[arguments.index("--") + 1 :] if "--" in arguments else arguments


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args(argv if argv is not None else _script_arguments())
    print(json.dumps(generate_presentation_views(args.project_root), ensure_ascii=False))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
