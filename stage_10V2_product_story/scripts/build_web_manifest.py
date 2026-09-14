"""Emit the story manifest the web viewer consumes.

Shots, camera presets and the isolate policy — everything the viewer needs
to reproduce the video's camera cuts and per-shot visibility without the
glTF visibility channel.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.task08_data import load_json
from stage_10_product_story.scripts.story_data import build_story_config
from stage_10V2_product_story.scripts.camera_plan import build_camera_records
from stage_10V2_product_story.scripts.story_v2_data import (
    FOCUS_SHOT_POLICY,
    build_story_v2_state_transforms,
)

MANIFEST_OUTPUT = "stage_10V2_product_story/web/story_manifest.json"
LAYOUT_PATH = "stage_09C_refined_explosion/config/refined_layout.json"


def build_web_manifest(project_root: Path) -> dict[str, object]:
    root = Path(project_root).expanduser().resolve()
    layout = load_json(root / LAYOUT_PATH)
    baseline = build_story_v2_state_transforms(root)
    cameras = build_camera_records(baseline, layout)["cameras"]
    shots = []
    for shot in build_story_config()["shots"]:
        spec = FOCUS_SHOT_POLICY.get(shot["shot_id"], {})
        shots.append(
            {
                "shot_id": shot["shot_id"],
                "frame_start": int(shot["frame_start"]),
                "frame_end": int(shot["frame_end"]),
                "title": shot["title"],
                "camera": spec.get("camera", "CAM_STORY_HERO"),
                "mode": spec.get("mode", "full"),
                "subject_parts": list(spec.get("parts", [])),
                "focus_components": bool(spec.get("focus_components", False)),
            }
        )
    def yup(coords):
        # GLB is exported Y-up for three.js: Blender (x, y, z) -> (x, z, -y).
        return [coords[0], coords[2], -coords[1]]

    manifest = {
        "fps": 30,
        "frame_start": 1,
        "frame_end": 900,
        "glb": "product_story_v2.glb",
        "cameras": {
            name: {
                "location": yup(record["location"]),
                "target": yup(record["target"]),
                "lens_mm": record["lens_mm"],
            }
            for name, record in cameras.items()
        },
        "shots": shots,
    }
    output = root / MANIFEST_OUTPUT
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return {"output": str(output), "shot_count": len(shots), "camera_count": len(cameras)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args(argv)
    print(json.dumps(build_web_manifest(args.project_root), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
