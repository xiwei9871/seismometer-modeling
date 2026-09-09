"""Compose the Task 9C animation keyframe contact sheet."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.compose_task08_images import tile_images


FRAME_DIR = "stage_09C_refined_explosion/renders/animation_keyframes"
OUTPUT_PATH = "stage_09C_refined_explosion/renders/exploded_keyframes_contact_sheet.png"
FRAMES = (1, 120, 240, 360, 480, 540)


def compose_keyframes_contact_sheet(project_root: Path) -> Path:
    root = Path(project_root).expanduser().resolve()
    inputs = [root / FRAME_DIR / f"frame_{frame:03d}.png" for frame in FRAMES]
    missing = [str(path) for path in inputs if not path.is_file() or path.stat().st_size == 0]
    if missing:
        raise FileNotFoundError(f"Task 9C keyframe renders are missing: {missing}")
    output = root / OUTPUT_PATH
    tile_images(inputs, output, columns=3, rows=2)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args()
    print(compose_keyframes_contact_sheet(args.project_root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
