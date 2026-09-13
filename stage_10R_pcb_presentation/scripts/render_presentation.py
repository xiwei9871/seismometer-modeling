"""Render the Task 10-R-PCB-V1 presentation stills with Eevee."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from stage_10R_pcb_presentation.scripts.pcb_presentation_data import (
    RENDER_CAMERAS,
    RENDER_ROOT,
    REQUIRED_RENDERS,
    SCENE_OUTPUT,
)

try:  # pragma: no cover - executed through Blender.
    import bpy  # type: ignore
except ImportError:  # pragma: no cover
    bpy = None  # type: ignore


def render_presentation(project_root: Path) -> dict[str, Any]:
    if bpy is None:
        raise RuntimeError("Blender bpy is required to render the PCB presentation stills")
    root = Path(project_root).expanduser().resolve()
    scene_path = root / SCENE_OUTPUT
    if not scene_path.is_file():
        raise ValueError("presentation scene missing; run build_presentation_scene.py first")
    render_dir = root / RENDER_ROOT
    render_dir.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, Any] = {}
    for filename in REQUIRED_RENDERS:
        camera_name = RENDER_CAMERAS[filename]
        bpy.ops.wm.open_mainfile(filepath=str(scene_path))
        scene = bpy.context.scene
        if camera_name not in bpy.data.objects:
            raise ValueError(f"presentation camera missing: {camera_name}")
        _configure_render(scene)
        _apply_view_visibility(filename)
        scene.camera = bpy.data.objects[camera_name]
        output = render_dir / filename
        scene.render.filepath = str(output)
        bpy.ops.render.render(write_still=True)
        outputs[filename] = {
            "path": str(output),
            "camera": camera_name,
            "resolution": [scene.render.resolution_x, scene.render.resolution_y],
        }
    return {"render_root": str(render_dir), "renders": outputs, "required_renders": list(REQUIRED_RENDERS)}


def _apply_view_visibility(filename: str) -> None:
    view = filename.replace("pcb_presentation_", "").replace(".png", "")
    show_context = view == "context"
    visibility = {
        "TASK10R_PCB_HERO": True,
        "TASK10R_PCB_SECONDARY": show_context,
        "TASK10R_PCB_SUPPORT": show_context,
        "TASK10R_PCB_CONTEXT": show_context,
        "TASK10R_PCB_SOURCE_HIDDEN": False,
        "TASK10R_PCB_LIGHTS": True,
    }
    for name, visible in visibility.items():
        collection = bpy.data.collections.get(name)
        if collection is not None:
            collection.hide_render = not visible
            collection.hide_viewport = not visible


def _configure_render(scene: Any) -> None:
    scene.frame_set(1)
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.render.image_settings.media_type = "IMAGE"
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"


def _script_arguments() -> list[str]:
    arguments = list(sys.argv[1:])
    return arguments[arguments.index("--") + 1 :] if "--" in arguments else arguments


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args(argv if argv is not None else _script_arguments())
    print(json.dumps(render_presentation(args.project_root), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
