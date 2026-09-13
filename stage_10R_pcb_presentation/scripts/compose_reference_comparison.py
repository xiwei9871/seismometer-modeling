"""Compose the generated clean render next to the primary reference image."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from PIL import Image, ImageDraw, ImageOps

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from stage_10R_pcb_presentation.scripts.pcb_presentation_data import (
    COMPARISON_RENDER,
    RENDER_ROOT,
)

REFERENCE_PRIMARY = "references/pcb/REF_PCB_002.png"
GENERATED_INPUT = "pcb_presentation_clean.png"


def compose_reference_comparison(project_root: Path) -> Path:
    root = Path(project_root).expanduser().resolve()
    generated = root / RENDER_ROOT / GENERATED_INPUT
    reference = root / REFERENCE_PRIMARY
    for path in (generated, reference):
        if not path.is_file() or path.stat().st_size <= 0:
            raise FileNotFoundError(f"comparison input missing: {path}")

    cell = (960, 540)
    gutter = 16
    header = 46
    sheet = Image.new("RGB", (cell[0] * 2 + gutter * 3, cell[1] + header + gutter * 2), (238, 240, 243))
    draw = ImageDraw.Draw(sheet)
    panels = ((generated, "GENERATED"), (reference, "REFERENCE REF_PCB_002"))
    for index, (path, label) in enumerate(panels):
        x = gutter + index * (cell[0] + gutter)
        image = ImageOps.contain(Image.open(path).convert("RGB"), cell)
        canvas = Image.new("RGB", cell, (24, 26, 30))
        canvas.paste(image, ((cell[0] - image.width) // 2, (cell[1] - image.height) // 2))
        sheet.paste(canvas, (x, header + gutter // 2))
        draw.text((x + 8, header // 2 - 6), label, fill=(40, 44, 50))
    output = root / RENDER_ROOT / COMPARISON_RENDER
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, format="PNG")
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args(argv)
    print(compose_reference_comparison(args.project_root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
