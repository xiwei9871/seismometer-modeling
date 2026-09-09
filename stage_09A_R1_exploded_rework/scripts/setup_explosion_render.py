"""Render static R1 exploded presentation views."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import json
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.task08_data import load_json, write_json

from stage_09A_R1_exploded_rework.scripts.apply_explosion_layout import (
    validate_r1_scene_facts,
)
from stage_09A_R1_exploded_rework.scripts.setup_explosion_cameras import (
    CAMERA_NAMES,
    setup_r1_cameras,
)

try:  # pragma: no cover - exercised by Blender integration.
    import bpy  # type: ignore
except ImportError:  # pragma: no cover
    bpy = None  # type: ignore


R1_VIEW_NAMES = (
    "exploded_hero",
    "exploded_engineering",
    "exploded_top",
    "exploded_rear",
)
VIEW_TO_CAMERA = dict(zip(R1_VIEW_NAMES, CAMERA_NAMES))
OUTPUT_DIR = "stage_09A_R1_exploded_rework/renders"


def render_result_contract(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate that render metadata describes a static scene."""
    if payload.get("animation_created") is True:
        raise ValueError("R1 render contract forbids animation data")
    return dict(payload)


def render_r1_views(project_root: Path) -> dict[str, Any]:
    """Create cameras if needed and render all required static views."""
    if bpy is None:
        raise RuntimeError("Blender bpy is required to render R1 views")
    root = Path(project_root).expanduser().resolve()
    blend_path = root / "stage_09A_R1_exploded_rework/scene/exploded_layout_v2.blend"
    bpy.ops.wm.open_mainfile(filepath=str(blend_path))
    _validate_open_scene()
    setup_r1_cameras(root)
    bpy.ops.wm.open_mainfile(filepath=str(blend_path))
    _configure_render_scene()
    output_dir = root / OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    rendered: list[str] = []
    for view_name in R1_VIEW_NAMES:
        camera_name = VIEW_TO_CAMERA[view_name]
        camera = bpy.data.objects.get(camera_name)
        if camera is None:
            raise ValueError(f"missing R1 camera: {camera_name}")
        bpy.context.scene.camera = camera
        path = output_dir / f"{view_name}.png"
        bpy.context.scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        rendered.append(str(path))
    bpy.context.scene["r1_render_views"] = list(R1_VIEW_NAMES)
    bpy.context.scene["r1_animation_created"] = False
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    result = {
        "views": rendered,
        "view_count": len(rendered),
        "camera_names": list(CAMERA_NAMES),
        "animation_created": False,
        "scene_state": "STATIC_HIERARCHICAL_PRESENTATION_R1",
    }
    return render_result_contract(result)


def _validate_open_scene() -> None:
    source = [
        obj
        for obj in bpy.data.objects
        if obj.type == "MESH" and obj.get("source") == "original_stl"
    ]
    facts = [
        {
            "part_id": obj.get("part_id"),
            "source": obj.get("source"),
            "type": obj.type,
            "hidden": bool(obj.hide_viewport or obj.hide_render),
            "animation_data": obj.animation_data,
        }
        for obj in source
    ]
    validate_r1_scene_facts(
        facts,
        vertices=sum(len(obj.data.vertices) for obj in source),
        polygons=sum(len(obj.data.polygons) for obj in source),
    )


def _configure_render_scene() -> None:
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.resolution_x = 1200
    scene.render.resolution_y = 900
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.display.shading.light = "STUDIO"
    scene.display.shading.studio_light = "paint.sl"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_shadows = True
    scene.display.shading.show_cavity = True
    scene.display.shading.cavity_type = "WORLD"
    scene.display.shading.show_specular_highlight = False
    scene.display.shading.background_type = "WORLD"
    scene.world.color = (0.055, 0.065, 0.08)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args(argv if argv is not None else _script_arguments())
    print(json.dumps(render_r1_views(args.project_root), ensure_ascii=False, sort_keys=True))
    return 0


def _script_arguments() -> list[str]:
    arguments = list(sys.argv[1:])
    return arguments[arguments.index("--") + 1 :] if "--" in arguments else arguments


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
