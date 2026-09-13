"""Generate the deterministic PCB soldermask surface-detail texture.

The texture is mapped onto PART_019 through Generated coordinates, so the
1024 px image spans the board's own bounding box (102 mm). A plain border is
kept so the chamfered board edges read cleanly. All randomness is seeded;
the PNG output is byte-stable across runs.
"""

from __future__ import annotations

import argparse
import random
from pathlib import Path
import sys
from typing import Any, Mapping

from PIL import Image, ImageDraw

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from stage_10R_pcb_presentation.scripts.pcb_presentation_data import (
    ASSET_TEXTURE,
    BOARD_HALF_EXTENT_MM,
    build_component_plan,
    component_footprint_rect,
)

TEXTURE_SIZE = 1024
TEXTURE_SEED = 0x10C8
BORDER_PX = 28
MM_TO_PX = TEXTURE_SIZE / (BOARD_HALF_EXTENT_MM * 2.0)

BASE = (20, 96, 22)
TRACE_DARK = (12, 70, 16)
TRACE_LIGHT = (44, 132, 48)
VIA_GOLD = (176, 148, 62)
PAD_GOLD = (198, 168, 68)
SILKSCREEN = (200, 208, 196)


def board_to_px(x_mm: float, y_mm: float) -> tuple[float, float]:
    return (
        (x_mm + BOARD_HALF_EXTENT_MM) * MM_TO_PX,
        (BOARD_HALF_EXTENT_MM - y_mm) * MM_TO_PX,
    )


def generate_surface_texture(project_root: Path) -> Path:
    root = Path(project_root).expanduser().resolve()
    image = Image.new("RGB", (TEXTURE_SIZE, TEXTURE_SIZE), BASE)
    draw = ImageDraw.Draw(image)
    rng = random.Random(TEXTURE_SEED)

    _mottle(draw, rng)
    _traces(draw, rng)
    _vias(draw, rng)
    _component_pads(draw)
    _silkscreen(draw, rng)
    _restore_border(draw)

    output = root / ASSET_TEXTURE
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, format="PNG")
    return output


def _mottle(draw: ImageDraw.ImageDraw, rng: random.Random) -> None:
    for _ in range(2600):
        x = rng.uniform(BORDER_PX, TEXTURE_SIZE - BORDER_PX)
        y = rng.uniform(BORDER_PX, TEXTURE_SIZE - BORDER_PX)
        delta = rng.randint(-9, 9)
        draw.point((x, y), fill=tuple(max(0, min(255, c + delta)) for c in BASE))


def _traces(draw: ImageDraw.ImageDraw, rng: random.Random) -> None:
    for _ in range(520):
        x = rng.uniform(BORDER_PX + 6, TEXTURE_SIZE - BORDER_PX - 6)
        y = rng.uniform(BORDER_PX + 6, TEXTURE_SIZE - BORDER_PX - 6)
        color = TRACE_DARK if rng.random() < 0.72 else TRACE_LIGHT
        width = 2 if rng.random() < 0.85 else 3
        for _ in range(rng.randint(2, 5)):
            length = rng.uniform(18, 130)
            horizontal = rng.random() < 0.5
            sign = 1.0 if rng.random() < 0.5 else -1.0
            x2 = x + sign * length if horizontal else x
            y2 = y if horizontal else y + sign * length
            x2 = min(max(x2, BORDER_PX), TEXTURE_SIZE - BORDER_PX)
            y2 = min(max(y2, BORDER_PX), TEXTURE_SIZE - BORDER_PX)
            draw.line([(x, y), (x2, y2)], fill=color, width=width)
            x, y = x2, y2


def _vias(draw: ImageDraw.ImageDraw, rng: random.Random) -> None:
    for _ in range(850):
        x = rng.uniform(BORDER_PX + 4, TEXTURE_SIZE - BORDER_PX - 4)
        y = rng.uniform(BORDER_PX + 4, TEXTURE_SIZE - BORDER_PX - 4)
        r = rng.uniform(0.8, 1.7)
        draw.ellipse([x - r, y - r, x + r, y + r], fill=VIA_GOLD)


def _component_pads(draw: ImageDraw.ImageDraw) -> None:
    for component in build_component_plan():
        rect = component_footprint_rect(component)
        role = component["material_role"]
        if role == "connector":
            _pad_row(draw, rect, axis="y")
        elif role == "ic":
            _pad_row(draw, rect, axis="x")


def _pad_row(draw: ImageDraw.ImageDraw, rect: Mapping[str, float], axis: str) -> None:
    if axis == "y":
        # Long connector: pad strips above and below the footprint.
        length_mm = rect["x_max"] - rect["x_min"]
        count = max(4, int(length_mm / 2.4))
        for side in (-1.0, 1.0):
            for index in range(count):
                x_mm = rect["x_min"] + (index + 0.5) * length_mm / count
                y_mm = (rect["y_max"] if side > 0 else rect["y_min"]) + side * 0.9
                _pad(draw, x_mm, y_mm, 0.9, 1.8)
    else:
        # IC: pad strips on the left and right edges.
        depth_mm = rect["y_max"] - rect["y_min"]
        count = max(3, int(depth_mm / 1.8))
        for side in (-1.0, 1.0):
            for index in range(count):
                x_mm = (rect["x_max"] if side > 0 else rect["x_min"]) + side * 0.9
                y_mm = rect["y_min"] + (index + 0.5) * depth_mm / count
                _pad(draw, x_mm, y_mm, 1.8, 0.9)


def _pad(draw: ImageDraw.ImageDraw, x_mm: float, y_mm: float, w_mm: float, h_mm: float) -> None:
    cx, cy = board_to_px(x_mm, y_mm)
    w, h = w_mm * MM_TO_PX / 2.0, h_mm * MM_TO_PX / 2.0
    draw.rectangle([cx - w, cy - h, cx + w, cy + h], fill=PAD_GOLD)


def _silkscreen(draw: ImageDraw.ImageDraw, rng: random.Random) -> None:
    for component in build_component_plan():
        rect = component_footprint_rect(component)
        grow = 1.6
        x0, y0 = board_to_px(rect["x_min"] - grow, rect["y_max"] + grow)
        x1, y1 = board_to_px(rect["x_max"] + grow, rect["y_min"] - grow)
        draw.rectangle([x0, y0, x1, y1], outline=SILKSCREEN, width=1)
    for _ in range(46):
        x = rng.uniform(BORDER_PX + 8, TEXTURE_SIZE - BORDER_PX - 30)
        y = rng.uniform(BORDER_PX + 8, TEXTURE_SIZE - BORDER_PX - 8)
        draw.line([(x, y), (x + rng.uniform(8, 26), y)], fill=SILKSCREEN, width=1)


def _restore_border(draw: ImageDraw.ImageDraw) -> None:
    b = BORDER_PX
    w = TEXTURE_SIZE
    draw.rectangle([0, 0, w, b], fill=BASE)
    draw.rectangle([0, w - b, w, w], fill=BASE)
    draw.rectangle([0, 0, b, w], fill=BASE)
    draw.rectangle([w - b, 0, w, w], fill=BASE)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args(argv)
    print(generate_surface_texture(args.project_root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
