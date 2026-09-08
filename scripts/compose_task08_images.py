"""Compose labeled Task 8 preview images using Pillow."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from PIL import Image, ImageDraw, ImageFont


def annotate_image(input_path: Path, output_path: Path, label: str) -> None:
    image = Image.open(input_path).convert("RGB")
    draw = ImageDraw.Draw(image)
    font = _font(14)
    lines = label.splitlines() or [""]
    line_height = 19
    box_height = 10 + line_height * len(lines)
    draw.rectangle((0, 0, image.width, box_height), fill=(12, 12, 12))
    for index, line in enumerate(lines):
        draw.text(
            (8, 4 + index * line_height),
            line,
            fill=(245, 245, 245),
            font=font,
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, format="PNG")


def tile_images(
    input_paths: Sequence[Path],
    output_path: Path,
    *,
    columns: int = 5,
    rows: int = 5,
) -> None:
    if not input_paths:
        raise ValueError("cannot tile an empty image list")
    if columns <= 0 or rows <= 0:
        raise ValueError("contact-sheet dimensions must be positive")
    cell_width, cell_height = 260, 300
    sheet = Image.new(
        "RGB",
        (cell_width * columns, cell_height * rows),
        (232, 232, 232),
    )
    draw = ImageDraw.Draw(sheet)
    font = _font(16)
    for index, path in enumerate(input_paths[: columns * rows]):
        image = Image.open(path).convert("RGB")
        image.thumbnail((cell_width - 12, cell_height - 42))
        cell_x = (index % columns) * cell_width
        cell_y = (index // columns) * cell_height
        x = cell_x + (cell_width - image.width) // 2
        y = cell_y + 6
        sheet.paste(image, (x, y))
        draw.text(
            (cell_x + 8, cell_y + cell_height - 30),
            path.stem,
            fill=(15, 15, 15),
            font=font,
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path, format="PNG")


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in (
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ):
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    annotate = subparsers.add_parser("annotate")
    annotate.add_argument("--input", type=Path, required=True)
    annotate.add_argument("--output", type=Path, required=True)
    annotate.add_argument("--label", required=True)
    tile = subparsers.add_parser("tile")
    tile.add_argument("--output", type=Path, required=True)
    tile.add_argument("--columns", type=int, default=5)
    tile.add_argument("--rows", type=int, default=5)
    tile.add_argument("inputs", type=Path, nargs="+")
    args = parser.parse_args()
    if args.command == "annotate":
        annotate_image(args.input, args.output, args.label)
    else:
        tile_images(
            args.inputs,
            args.output,
            columns=args.columns,
            rows=args.rows,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
