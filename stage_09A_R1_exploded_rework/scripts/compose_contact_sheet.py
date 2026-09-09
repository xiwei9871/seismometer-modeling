"""Compose the four R1 renders into a labeled contact sheet."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from PIL import Image, ImageDraw, ImageFont


VIEW_NAMES = ("exploded_hero", "exploded_engineering", "exploded_top", "exploded_rear")


def compose_contact_sheet(input_dir: Path, output_path: Path) -> Path:
    """Tile four required view PNGs in a deterministic 2x2 sheet."""
    paths = [Path(input_dir) / f"{name}.png" for name in VIEW_NAMES]
    missing = [str(path) for path in paths if not path.is_file() or path.stat().st_size == 0]
    if missing:
        raise ValueError(f"missing R1 render inputs: {missing}")
    cell_width, cell_height = 600, 500
    sheet = Image.new("RGB", (cell_width * 2, cell_height * 2), (228, 231, 235))
    draw = ImageDraw.Draw(sheet)
    font = _font(22)
    for index, path in enumerate(paths):
        image = Image.open(path).convert("RGB")
        image.thumbnail((cell_width - 20, cell_height - 60))
        cell_x = (index % 2) * cell_width
        cell_y = (index // 2) * cell_height
        x = cell_x + (cell_width - image.width) // 2
        y = cell_y + 8
        sheet.paste(image, (x, y))
        draw.text((cell_x + 14, cell_y + cell_height - 38), path.stem, fill=(20, 24, 30), font=font)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, format="PNG")
    return output


def _font(size: int):
    for candidate in (
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ):
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(compose_contact_sheet(args.input_dir, args.output))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
