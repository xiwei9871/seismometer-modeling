"""Render the 9-shot PCB Presentation V3 validation set.

Run: blender -b pcb_presentation_v3.blend --python render_pcb_v3.py
Outputs into web_presentation_v11/pcb_v3/renders/.
"""
import argparse
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
RENDERS = ROOT / "renders"


def get(name):
    return bpy.data.objects[name]


def place(a_loc=(0, 0, 0), a_rot=0.0, b_loc=(0, -80, 0), b_rot=0.0,
          a_hide=False, b_hide=False):
    a, b = get("PCB_A_MAIN_SYSTEM_BOARD"), get("PCB_B_AUXILIARY_INTERFACE_BOARD")
    a.location, b.location = a_loc, b_loc
    # flip about Y = page-turn: x→-x, matches photo back-side layout
    a.rotation_euler.y = a_rot
    b.rotation_euler.y = b_rot
    a.hide_render = a_hide
    b.hide_render = b_hide
    for o in bpy.data.objects:
        if o.parent is a:
            o.hide_render = a_hide
        elif o.parent is b:
            o.hide_render = b_hide


SHOTS = [
    ("01_pcb_overview", "CAM_V3_OVERVIEW", dict()),
    ("02_pcb_architecture", "CAM_V3_ARCH",
     dict(a_loc=(0, -40, 26), b_loc=(0, -40, -14))),
    ("03_pcb_main_board_front", "CAM_V3_A_FRONT", dict(b_hide=True)),
    ("04_pcb_main_board_back", "CAM_V3_A_BACK",
     dict(a_rot=math.pi, b_hide=True)),
    ("05_pcb_secondary_board_front", "CAM_V3_B_FRONT",
     dict(b_loc=(0, 0, 0), a_hide=True)),
    ("06_pcb_secondary_board_back", "CAM_V3_B_BACK",
     dict(b_loc=(0, 0, 0), b_rot=math.pi, a_hide=True)),
    ("07_pcb_closeup_main", "CAM_V3_A_CLOSE", dict(b_hide=True)),
    ("08_pcb_closeup_secondary", "CAM_V3_B_CLOSE",
     dict(b_loc=(0, 0, 0), a_hide=True)),
]


def render_all(out_dir: Path):
    scn = bpy.context.scene
    out_dir.mkdir(parents=True, exist_ok=True)
    for filename, cam_name, cfg in SHOTS:
        place(**cfg)
        cam = get(cam_name)
        scn.camera = cam
        scn.render.filepath = str(out_dir / f"{filename}.png")
        bpy.ops.render.render(write_still=True)
        print(f"[pcb_v3] rendered {filename}")


def contact_sheet(out_dir: Path):
    """4x2 grid of the 8 shots; each cell 480x270, centred in a 480x540 slot."""
    W, H = 1920, 1080
    cols, rows = 4, 2
    cw, ch = W // cols, H // rows
    tw, th = cw, cw * 9 // 16            # 480x270, letterboxed in cell
    files = [s[0] for s in SHOTS]
    sheet = bpy.data.images.new("CONTACT", width=W, height=H, alpha=False)
    px = [0.02, 0.02, 0.025, 1.0] * (W * H)
    for idx, stem in enumerate(files):
        src = bpy.data.images.load(str(out_dir / f"{stem}.png"))
        sw, sh = src.size
        spx = list(src.pixels[:])
        ox = (idx % cols) * cw
        oy = (rows - 1 - idx // cols) * ch + (ch - th) // 2
        step = max(1, sw // tw)
        for ty in range(th):
            sy = min(ty * step, sh - 1)
            base = sy * sw * 4
            for tx in range(tw):
                si = base + min(tx * step, sw - 1) * 4
                di = ((oy + ty) * W + ox + tx) * 4
                if si + 3 <= len(spx):
                    px[di:di + 3] = spx[si:si + 3]
        bpy.data.images.remove(src)
    sheet.pixels.foreach_set(px)
    sheet.filepath_raw = str(out_dir / "09_pcb_contact_sheet.png")
    sheet.file_format = "PNG"
    sheet.save()
    print("[pcb_v3] wrote 09_pcb_contact_sheet")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=RENDERS)
    parser.add_argument("--contact-only", action="store_true")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:]
                             if "--" in sys.argv else [])
    if not args.contact_only:
        render_all(args.out)
    contact_sheet(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
