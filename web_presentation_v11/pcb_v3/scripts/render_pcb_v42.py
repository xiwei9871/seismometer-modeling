"""STEP 4 surface-pass render set on pcb_v42_surface.blend.

  01_A_front_surface / 02_A_back_surface
  03_B_front_surface / 04_B_back_surface
  05_A_module_closeup_surface / 06_A_antenna_closeup_surface /
  07_A_coil_closeup_surface
  08_B_connector_closeup_surface / 09_B_power_closeup_surface
  10_A_photo_match_surface  (== 01, explicit photo-match filename)
  11_B_photo_match_surface  (== 03)

Back views: the board root is flipped 180deg about world Y — the same
page-flip the registered back photos were taken with (registration
validates front/back holes after an x-flip).

Run: blender -b pcb_v42_surface.blend --python scripts/render_pcb_v42.py
"""
import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
RENDERS = ROOT / "renders_v42"

# filename, camera, board("A"/"B"), flip_back
SHOTS = [
    ("01_A_front_surface", "CAM_V4_A_TOP", "A", False),
    ("02_A_back_surface", "CAM_V4_A_TOP", "A", True),
    ("03_B_front_surface", "CAM_V4_B_TOP", "B", False),
    ("04_B_back_surface", "CAM_V4_B_TOP", "B", True),
    ("05_A_module_closeup_surface", "CAM_V41_A_MOD_CLOSE", "A", False),
    ("06_A_antenna_closeup_surface", "CAM_V41_A_ANT", "A", False),
    ("07_A_coil_closeup_surface", "CAM_V41_A_COIL", "A", False),
    ("08_B_connector_closeup_surface", "CAM_V41_B_CONN", "B", False),
    ("09_B_power_closeup_surface", "CAM_V41_B_POWER", "B", False),
    ("10_A_photo_match_surface", "CAM_V4_A_TOP", "A", False),
    ("11_B_photo_match_surface", "CAM_V4_B_TOP", "B", False),
]


def _under(o, name):
    while o is not None:
        if o.name.startswith(name):
            return True
        o = o.parent
    return False


def main():
    scn = bpy.context.scene
    RENDERS.mkdir(parents=True, exist_ok=True)
    roots = {"A": bpy.data.objects["PCB_A_MAIN_BOARD"],
             "B": bpy.data.objects["PCB_B_AUXILIARY_BOARD"]}

    for filename, cam_name, show, flip in SHOTS:
        hide_root = ("PCB_B_AUXILIARY_BOARD" if show == "A"
                     else "PCB_A_MAIN_BOARD")
        for o in bpy.data.objects:
            o.hide_render = _under(o, hide_root)
        root = roots[show]
        # B lives at y=-80 via its board mesh; bring it under the
        # world-origin top camera for the top-down shots
        shift = 80.0 if cam_name == "CAM_V4_B_TOP" else 0.0
        root.location.y += shift
        if flip:
            root.rotation_euler.y = 3.141592653589793
        scn.camera = bpy.data.objects[cam_name]
        scn.render.filepath = str(RENDERS / f"{filename}.png")
        bpy.ops.render.render(write_still=True)
        if flip:
            root.rotation_euler.y = 0.0
        root.location.y -= shift
        print(f"[v42] rendered {filename}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
