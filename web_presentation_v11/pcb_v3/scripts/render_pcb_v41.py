"""Render the A3 review sets on pcb_v41_semantic.blend.

STEP 1 shots (B board):
  09_B_hero / 10_B_closeup_connector / 11_B_closeup_power /
  v41_topdown_b_front

STEP 2 shots (A main black module):
  01_A_module_topdown / 02_A_module_3quarter / 03_A_module_closeup /
  v41_topdown_a_front (ortho top-down for the module overlay)

Run: blender -b pcb_v41_semantic.blend --python scripts/render_pcb_v41.py \
        [-- --only b|a]
"""
import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
RENDERS = ROOT / "renders_v41"

SHOTS = [
    ("09_B_hero", "CAM_V41_B_HERO", "B"),
    ("10_B_closeup_connector", "CAM_V41_B_CONN", "B"),
    ("11_B_closeup_power", "CAM_V41_B_POWER", "B"),
    ("v41_topdown_b_front", "CAM_V4_B_TOP", "B"),
    ("01_A_module_topdown", "CAM_V41_A_MOD_TOP", "A"),
    ("02_A_module_3quarter", "CAM_V41_A_MOD_34", "A"),
    ("03_A_module_closeup", "CAM_V41_A_MOD_CLOSE", "A"),
    ("07_A_closeup_gnss", "CAM_V41_A_ANT", "A"),
    ("08_A_closeup_coil", "CAM_V41_A_COIL", "A"),
    ("v41_topdown_a_front", "CAM_V4_A_TOP", "A"),
]


def _under(o, name):
    """hide_render does not propagate — test the whole parent chain."""
    while o is not None:
        if o.name.startswith(name):
            return True
        o = o.parent
    return False


def main():
    only = None
    if "--" in sys.argv and "--only" in sys.argv:
        only = sys.argv[sys.argv.index("--only") + 1].upper()
    scn = bpy.context.scene
    RENDERS.mkdir(parents=True, exist_ok=True)
    b_root = bpy.data.objects["PCB_B_AUXILIARY_BOARD"]

    for filename, cam_name, show in SHOTS:
        if only and show != only:
            continue
        hide_root = ("PCB_B_AUXILIARY_BOARD" if show == "A"
                     else "PCB_A_MAIN_BOARD")
        for o in bpy.data.objects:
            o.hide_render = _under(o, hide_root)
        # the V4 top-down cams point at the world origin; B lives at y=-80
        shift = 80.0 if cam_name == "CAM_V4_B_TOP" else 0.0
        b_root.location.y += shift
        scn.camera = bpy.data.objects[cam_name]
        scn.render.filepath = str(RENDERS / f"{filename}.png")
        bpy.ops.render.render(write_still=True)
        b_root.location.y -= shift
        print(f"[v41] rendered {filename}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
