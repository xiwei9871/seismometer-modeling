"""Render the subtitle-free Task 10-R inspection stills."""

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
from stage_10R_functional_inspection.scripts.build_inspection_scenes import SCENE_OUTPUTS
from stage_10R_functional_inspection.scripts.build_inspection_plan import CAMERA_OUTPUT

try:  # pragma: no cover - executed through Blender.
    import bpy  # type: ignore
except ImportError:  # pragma: no cover
    bpy = None  # type: ignore


RENDER_ROOT = "stage_10R_functional_inspection/renders"
REQUIRED_RENDERS = (
    "01_primary_architecture_hero.png",
    "01_primary_architecture_front.png",
    "01_primary_architecture_side.png",
    "02_sensor_inspection_clean.png",
    "02_sensor_inspection_context.png",
    "02_sensor_inspection_top.png",
    "03_pcb_inspection_clean.png",
    "03_pcb_inspection_context.png",
    "03_pcb_inspection_top.png",
    "04_power_inspection_clean.png",
    "04_power_inspection_context.png",
)

RENDER_CAMERAS = {
    "01_primary_architecture_hero.png": ("STATE_01_PRIMARY_ARCHITECTURE", "CAM_INSPECTION_PRIMARY_HERO"),
    "01_primary_architecture_front.png": ("STATE_01_PRIMARY_ARCHITECTURE", "CAM_INSPECTION_PRIMARY_FRONT"),
    "01_primary_architecture_side.png": ("STATE_01_PRIMARY_ARCHITECTURE", "CAM_INSPECTION_PRIMARY_SIDE"),
    "02_sensor_inspection_clean.png": ("STATE_02_SENSOR_INSPECTION", "CAM_INSPECTION_SENSOR_CLEAN"),
    "02_sensor_inspection_context.png": ("STATE_02_SENSOR_INSPECTION", "CAM_INSPECTION_SENSOR_CONTEXT"),
    "02_sensor_inspection_top.png": ("STATE_02_SENSOR_INSPECTION", "CAM_INSPECTION_SENSOR_TOP"),
    "03_pcb_inspection_clean.png": ("STATE_03_PCB_INSPECTION", "CAM_INSPECTION_PCB_CLEAN"),
    "03_pcb_inspection_context.png": ("STATE_03_PCB_INSPECTION", "CAM_INSPECTION_PCB_CONTEXT"),
    "03_pcb_inspection_top.png": ("STATE_03_PCB_INSPECTION", "CAM_INSPECTION_PCB_TOP"),
    "04_power_inspection_clean.png": ("STATE_04_POWER_INSPECTION", "CAM_INSPECTION_POWER_CLEAN"),
    "04_power_inspection_context.png": ("STATE_04_POWER_INSPECTION", "CAM_INSPECTION_POWER_CONTEXT"),
}


def render_inspection_states(project_root: Path) -> dict[str, Any]:
    if bpy is None:
        raise RuntimeError("Blender bpy is required to render Task 10-R inspection states")
    root = Path(project_root).expanduser().resolve()
    camera_config = load_json(root / CAMERA_OUTPUT)["cameras"]
    render_dir = root / RENDER_ROOT
    render_dir.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, Any] = {}
    scene_cache: dict[str, Any] = {}
    for filename in REQUIRED_RENDERS:
        state_id, camera_name = RENDER_CAMERAS[filename]
        scene_path = root / SCENE_OUTPUTS[state_id]
        if state_id not in scene_cache:
            bpy.ops.wm.open_mainfile(filepath=str(scene_path))
            scene_cache[state_id] = bpy.context.scene
        else:
            # Reopen each state after the preceding render so the render pass is
            # independent of any Blender-side transient state.
            bpy.ops.wm.open_mainfile(filepath=str(scene_path))
            scene_cache[state_id] = bpy.context.scene
        scene = scene_cache[state_id]
        if camera_name not in bpy.data.objects:
            raise ValueError(f"Task 10-R camera missing from {scene_path.name}: {camera_name}")
        _configure_render(scene)
        _set_context_visibility(scene, show_context_for_render(filename))
        scene.camera = bpy.data.objects[camera_name]
        output = render_dir / filename
        scene.render.filepath = str(output)
        bpy.ops.render.render(write_still=True)
        outputs[filename] = {
            "path": str(output),
            "state_id": state_id,
            "camera": camera_name,
            "resolution": [scene.render.resolution_x, scene.render.resolution_y],
            "text_policy": "NO_TEXT_OR_ANNOTATIONS",
        }
    return {
        "render_root": str(render_dir),
        "renders": outputs,
        "required_renders": list(REQUIRED_RENDERS),
        "text_policy": "NO_TEXT_OR_ANNOTATIONS",
    }


def show_context_for_render(filename: str) -> bool:
    """Return whether a render should retain the weak device context."""
    return "_context." in str(filename)


def _set_context_visibility(scene: Any, show_context: bool) -> None:
    state_id = str(scene.get("task10r_state_id", ""))
    collection = bpy.data.collections.get(f"TASK10R_{state_id}_CONTEXT")
    if collection is not None:
        collection.hide_render = not show_context


def _configure_render(scene: Any) -> None:
    scene.frame_set(1)
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.render.image_settings.media_type = "IMAGE"
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.studio_light = "paint.sl"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_shadows = True
    scene.display.shading.show_cavity = True
    scene.display.shading.show_specular_highlight = True
    scene.display.shading.background_type = "WORLD"


def _script_arguments() -> list[str]:
    arguments = list(sys.argv[1:])
    return arguments[arguments.index("--") + 1 :] if "--" in arguments else arguments


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args(argv if argv is not None else _script_arguments())
    print(json.dumps(render_inspection_states(args.project_root), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
