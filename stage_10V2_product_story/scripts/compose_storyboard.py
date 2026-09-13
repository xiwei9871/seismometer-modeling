"""Compose the eight Task 10-V2 story stills into a contact sheet."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.compose_task08_images import tile_images
from stage_10V2_product_story.scripts.render_product_story_v2 import (
    RENDER_DIR,
    REQUIRED_STILLS,
    storyboard_inputs,
)


def compose_storyboard(project_root: Path) -> Path:
    root = Path(project_root).expanduser().resolve()
    render_dir = root / RENDER_DIR
    paths = [render_dir / name for name in REQUIRED_STILLS]
    storyboard_inputs(paths)
    missing = [str(path) for path in paths if not path.is_file() or path.stat().st_size == 0]
    if missing:
        raise FileNotFoundError(f"Task 10-V2 stills are missing: {missing}")
    output = render_dir / "storyboard_contact_sheet.png"
    tile_images(paths, output, columns=4, rows=2)
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args(argv)
    print(compose_storyboard(args.project_root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
