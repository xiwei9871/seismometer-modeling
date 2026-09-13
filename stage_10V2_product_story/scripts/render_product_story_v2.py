"""Render Task 10-V2 story stills and the Eevee review MP4."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from stage_10V2_product_story.scripts.story_v2_data import (
    PREVIEW_VIDEO,
    RENDER_DIR,
    RENDER_ENGINE,
    SCENE_OUTPUT,
)

try:  # pragma: no cover - Blender-only implementation.
    import bpy  # type: ignore
except ImportError:  # pragma: no cover
    bpy = None  # type: ignore


REQUIRED_STILLS = (
    "01_assembled.png",
    "02_primary_explosion.png",
    "03_sensor_focus.png",
    "04_pcb_focus.png",
    "05_communication_focus.png",
    "06_power_focus.png",
    "07_rugged_focus.png",
    "08_final_hero.png",
)
REQUIRED_OUTPUTS = REQUIRED_STILLS + (
    "storyboard_contact_sheet.png",
    PREVIEW_VIDEO,
    "product_story_v2.blend",
)
STILL_FRAMES = {
    "01_assembled.png": 40,
    "02_primary_explosion.png": 145,
    "03_sensor_focus.png": 245,
    "04_pcb_focus.png": 365,
    "05_communication_focus.png": 465,
    "06_power_focus.png": 570,
    "07_rugged_focus.png": 660,
    "08_final_hero.png": 850,
}


def storyboard_inputs(paths: Sequence[Path]) -> list[str]:
    """Return contact-sheet inputs in the fixed story order."""
    by_name = {Path(path).name: Path(path) for path in paths}
    missing = [name for name in REQUIRED_STILLS if name not in by_name]
    if missing:
        raise ValueError(f"storyboard is missing stills: {missing}")
    return [by_name[name].name for name in REQUIRED_STILLS]


def render_product_story_v2(project_root: Path) -> dict[str, Any]:
    if bpy is None:
        raise RuntimeError("Blender bpy is required to render Task 10-V2")
    root = Path(project_root).expanduser().resolve()
    scene_path = root / SCENE_OUTPUT
    bpy.ops.wm.open_mainfile(filepath=str(scene_path))
    render_dir = root / RENDER_DIR
    render_dir.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = 900
    scene.render.fps = 30
    _configure_preview(scene, 1920, 1080)

    still_paths: dict[str, str] = {}
    for name, frame in STILL_FRAMES.items():
        scene.frame_set(frame)
        scene.camera = _camera_for_frame(scene, frame)
        _configure_image(scene, 1920, 1080)
        scene.render.filepath = str(render_dir / name)
        bpy.ops.render.render(write_still=True)
        still_paths[name] = str(render_dir / name)

    preview = render_dir / PREVIEW_VIDEO
    scene.frame_start = 1
    scene.frame_end = 900
    scene.frame_set(1)
    scene.camera = bpy.data.objects.get("CAM_STORY_HERO")
    _configure_video(scene, 1920, 1080)
    scene.render.filepath = str(preview)
    bpy.ops.render.render(animation=True)
    scene.frame_set(850)
    _configure_image(scene, 1920, 1080)
    scene.render.filepath = str(render_dir / "08_final_hero.png")
    bpy.ops.wm.save_as_mainfile(filepath=str(scene_path))
    return {
        "still_paths": still_paths,
        "preview": str(preview),
        "blend": str(scene_path),
        "frame_range": [1, 900],
        "fps": 30,
        "resolution": [1920, 1080],
        "engine": RENDER_ENGINE,
    }


def _camera_for_frame(scene: Any, frame: int) -> Any:
    mapping = {
        245: "CAM_STORY_SENSOR",
        365: "CAM_STORY_PCB",
    }
    return bpy.data.objects.get(mapping.get(frame, "CAM_STORY_HERO"))


def _configure_preview(scene: Any, width: int, height: int) -> None:
    scene.render.engine = RENDER_ENGINE
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.render.fps = 30


def _configure_image(scene: Any, width: int, height: int) -> None:
    _configure_preview(scene, width, height)
    scene.render.image_settings.media_type = "IMAGE"
    scene.render.image_settings.file_format = "PNG"


def _configure_video(scene: Any, width: int, height: int) -> None:
    _configure_preview(scene, width, height)
    scene.render.image_settings.media_type = "VIDEO"
    scene.render.image_settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    scene.render.ffmpeg.constant_rate_factor = "MEDIUM"
    scene.render.ffmpeg.audio_codec = "NONE"


def _script_arguments() -> list[str]:
    arguments = list(sys.argv[1:])
    return arguments[arguments.index("--") + 1 :] if "--" in arguments else arguments


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args(argv if argv is not None else _script_arguments())
    print(json.dumps(render_product_story_v2(args.project_root), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
