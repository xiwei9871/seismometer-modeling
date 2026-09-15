"""Render the A3 STEP-1 review set on pcb_v41_semantic.blend.

Shots (per A3 spec §51 subset for STEP 1):
  09_B_hero               full B board, hero angle
  10_B_closeup_connector  connector cluster closeup
  11_B_closeup_power      3R3 / inductor power-zone closeup
  v41_topdown_b_front     ortho top-down for photo overlay validation

Run: blender -b pcb_v41_semantic.blend --python scripts/render_pcb_v41.py
"""
import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
RENDERS = ROOT / "renders_v41"

SHOTS = [
    ("09_B_hero", "CAM_V41_B_HERO"),
    ("10_B_closeup_connector", "CAM_V41_B_CONN"),
    ("11_B_closeup_power", "CAM_V41_B_POWER"),
    ("v41_topdown_b_front", "CAM_V4_B_TOP"),
]


def main():
    scn = bpy.context.scene
    RENDERS.mkdir(parents=True, exist_ok=True)

    # hide the whole A branch — hide_render does not propagate, so walk
    # the parent chain and flag every descendant of the A root
    def under_a(o):
        while o is not None:
            if o.name.startswith("PCB_A_MAIN_BOARD"):
                return True
            o = o.parent
        return False

    for o in bpy.data.objects:
        if under_a(o):
            o.hide_render = True

    # CAM_V4_B_TOP points at the world origin — bring the whole B assembly
    # (root empty carries board mesh + components) to origin for that shot
    b_root = bpy.data.objects["PCB_B_AUXILIARY_BOARD"]
    for filename, cam_name in SHOTS:
        if cam_name == "CAM_V4_B_TOP":
            b_root.location.y += 80.0
        scn.camera = bpy.data.objects[cam_name]
        scn.render.filepath = str(RENDERS / f"{filename}.png")
        bpy.ops.render.render(write_still=True)
        if cam_name == "CAM_V4_B_TOP":
            b_root.location.y -= 80.0
        print(f"[v41] rendered {filename}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
