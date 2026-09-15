"""Render the V4 validation set + photo-matched top-down shots.

Run: blender -b pcb_presentation_v4.blend --python render_pcb_v4.py
"""
import argparse
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
RENDERS = ROOT / "renders_v4"


def get(name):
    return bpy.data.objects[name]


def place(a_loc=(0, 0, 0), a_rot=0.0, b_loc=(0, -80, 0), b_rot=0.0,
          a_hide=False, b_hide=False, hide_names=()):
    a = get("PCB_A_MAIN_SYSTEM_BOARD")
    b = get("PCB_B_AUXILIARY_INTERFACE_BOARD")
    a.location, b.location = a_loc, b_loc
    a.rotation_euler.y = a_rot          # page-turn flip matches photos
    b.rotation_euler.y = b_rot
    a.hide_render = a_hide
    b.hide_render = b_hide
    for o in bpy.data.objects:
        if o.parent is a:
            o.hide_render = a_hide or (o.name in hide_names)
        elif o.parent is b:
            o.hide_render = b_hide or (o.name in hide_names)


SHOTS = [
    ("01_pcb_overview", "CAM_V4_OVERVIEW", dict()),
    ("02_pcb_architecture", "CAM_V4_ARCH",
     dict(a_loc=(0, -40, 26), b_loc=(0, -40, -14))),
    ("03_pcb_main_board_front", "CAM_V4_A_FRONT", dict(b_hide=True)),
    ("04_pcb_main_board_back", "CAM_V4_A_BACK",
     dict(a_rot=math.pi, b_hide=True)),
    ("05_pcb_secondary_board_front", "CAM_V4_B_FRONT",
     dict(b_loc=(0, 0, 0), a_hide=True)),
    ("06_pcb_secondary_board_back", "CAM_V4_B_BACK",
     dict(b_loc=(0, 0, 0), b_rot=math.pi, a_hide=True)),
    ("07_pcb_closeup_main", "CAM_V4_A_CLOSE", dict(b_hide=True)),
    ("08_pcb_closeup_secondary", "CAM_V4_B_CLOSE",
     dict(b_loc=(0, 0, 0), a_hide=True)),
    # ortho-style top-downs for photo overlay validation — hide the
    # free-floating cable/plug so only the board registers
    ("v4_topdown_a_front", "CAM_V4_A_TOP",
     dict(b_hide=True,
          hide_names=("PCB_A_RIBBON", "PCB_A_RIBBON_PLUG", "PCB_A_COAX"))),
    ("v4_topdown_b_front", "CAM_V4_B_TOP",
     dict(b_loc=(0, 0, 0), a_hide=True)),
]


def render_all(out_dir: Path):
    scn = bpy.context.scene
    out_dir.mkdir(parents=True, exist_ok=True)
    for filename, cam_name, cfg in SHOTS:
        place(**cfg)
        scn.camera = get(cam_name)
        scn.render.filepath = str(out_dir / f"{filename}.png")
        bpy.ops.render.render(write_still=True)
        print(f"[v4] rendered {filename}")


def contact_sheet(out_dir: Path):
    W, H = 1920, 1080
    cols, rows = 4, 2
    cw, ch = W // cols, H // rows
    tw, th = cw, cw * 9 // 16
    sheet = bpy.data.images.new("CONTACT", width=W, height=H, alpha=False)
    px = [0.02, 0.02, 0.025, 1.0] * (W * H)
    for idx, (stem, _c, _cfg) in enumerate(SHOTS[:8]):
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
    print("[v4] wrote 09_pcb_contact_sheet")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, default=RENDERS)
    args = p.parse_args(sys.argv[sys.argv.index("--") + 1:]
                        if "--" in sys.argv else [])
    render_all(args.out)
    contact_sheet(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
