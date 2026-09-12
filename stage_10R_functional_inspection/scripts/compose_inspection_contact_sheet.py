"""Compose the four clean Task 10-R inspection renders into one review sheet."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from PIL import Image, ImageOps

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from stage_10R_functional_inspection.scripts.render_inspection_states import RENDER_ROOT


CONTACT_SHEET_INPUTS = (
    "01_primary_architecture_hero.png",
    "02_sensor_inspection_clean.png",
    "03_pcb_inspection_clean.png",
    "04_power_inspection_clean.png",
)
CONTACT_SHEET_OUTPUT = "task10R_contact_sheet.png"


def compose_inspection_contact_sheet(project_root: Path) -> Path:
    root = Path(project_root).expanduser().resolve()
    render_dir = root / RENDER_ROOT
    paths = [render_dir / name for name in CONTACT_SHEET_INPUTS]
    missing = [str(path) for path in paths if not path.is_file() or path.stat().st_size <= 0]
    if missing:
        raise FileNotFoundError(f"Task 10-R clean inspection renders are missing: {missing}")

    cell_size = (960, 540)
    gutter = 18
    sheet = Image.new("RGB", (cell_size[0] * 2 + gutter * 3, cell_size[1] * 2 + gutter * 3), (238, 240, 243))
    for index, path in enumerate(paths):
        image = Image.open(path).convert("RGB")
        fitted = ImageOps.contain(image, cell_size)
        canvas = Image.new("RGB", cell_size, (238, 240, 243))
        canvas.paste(fitted, ((cell_size[0] - fitted.width) // 2, (cell_size[1] - fitted.height) // 2))
        x = gutter + (index % 2) * (cell_size[0] + gutter)
        y = gutter + (index // 2) * (cell_size[1] + gutter)
        sheet.paste(canvas, (x, y))
    output = render_dir / CONTACT_SHEET_OUTPUT
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, format="PNG")
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args(argv)
    print(compose_inspection_contact_sheet(args.project_root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
