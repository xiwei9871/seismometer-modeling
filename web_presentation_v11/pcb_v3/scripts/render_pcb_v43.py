"""STEP 5 render set on pcb_v43_lookdev.blend.

  01_A_hero / 02_B_hero / 03_AB_hero          (Cycles)
  04_A_front_final / 05_A_back_final          (EEVEE, reg-match cams)
  06_B_front_final / 07_B_back_final
  08..12 macros                               (Cycles)
  13/14 raking-light material shots           (Cycles, grazing light)
  15_material_contact_sheet                   (Cycles swatch strip)

Back views flip the board root 180deg about world Y (page-flip, same as
the registered back photos).  Rake shots dim key/fill/rim/top and leave
only the grazing L43_RAKE light.

Run: blender -b pcb_v43_lookdev.blend --python scripts/render_pcb_v43.py
        [-- --eevee-all]   (fast preview pass)
"""
import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
RENDERS = ROOT / "renders_v43"

# filename, cam, board("A"/"B"/"AB"/None=swatch), flip, shift80, rake
SHOTS = [
    ("01_A_hero", "CAM_V43_HERO_A", "A", False, False, False),
    ("02_B_hero", "CAM_V43_HERO_B", "B", False, False, False),
    ("03_AB_hero", "CAM_V43_HERO_PAIR", "AB", False, False, False),
    ("04_A_front_final", "CAM_V4_A_TOP", "A", False, False, False),
    ("05_A_back_final", "CAM_V4_A_TOP", "A", True, False, False),
    ("06_B_front_final", "CAM_V4_B_TOP", "B", False, True, False),
    ("07_B_back_final", "CAM_V4_B_TOP", "B", True, True, False),
    ("08_A_module_macro", "CAM_V43_MACRO_MODULE", "A", False, False, False),
    ("09_A_antenna_macro", "CAM_V43_MACRO_ANT", "A", False, False, False),
    ("10_A_coil_macro", "CAM_V43_MACRO_COIL", "A", False, False, False),
    ("11_B_connector_macro", "CAM_V43_MACRO_B_CONN", "B", False, False,
     False),
    ("12_B_power_macro", "CAM_V43_MACRO_B_POWER", "B", False, False, False),
    ("13_A_material_raking_light", "CAM_V43_RAKE_A", "A", False, False,
     True),
    ("14_B_material_raking_light", "CAM_V43_RAKE_B", "B", False, False,
     True),
    ("15_material_contact_sheet", "CAM_V43_SWATCH", None, False, False,
     False),
]

RAKE_SET = ("L43_KEY", "L43_FILL", "L43_RIM", "L43_TOP")


def _under(o, name):
    while o is not None:
        if o.name.startswith(name):
            return True
        o = o.parent
    return False


def main():
    eevee_all = "--eevee-all" in sys.argv
    scn = bpy.context.scene
    RENDERS.mkdir(parents=True, exist_ok=True)
    roots = {"A": bpy.data.objects["PCB_A_MAIN_BOARD"],
             "B": bpy.data.objects["PCB_B_AUXILIARY_BOARD"]}
    rake = bpy.data.objects.get("L43_RAKE")
    if rake:
        rake.data.energy = 0.0            # off unless raking shot

    for filename, cam_name, show, flip, shift80, is_rake in SHOTS:
        for o in bpy.data.objects:
            if show is None:
                o.hide_render = _under(o, "PCB_A_MAIN_BOARD") or \
                    _under(o, "PCB_B_AUXILIARY_BOARD")
            else:
                hide = {"A": "PCB_B_AUXILIARY_BOARD",
                        "B": "PCB_A_MAIN_BOARD"}.get(show)
                sw = o.name.startswith("SW_")
                o.hide_render = sw or bool(hide and _under(o, hide))

        energies = {}
        if is_rake:
            for n in RAKE_SET:
                lo = bpy.data.objects.get(n)
                if lo:
                    energies[n] = lo.data.energy
                    lo.data.energy *= 0.06
            if rake:
                rake.data.energy = 42000.0

        root = roots[show] if show in roots else None
        if root:
            if shift80:
                root.location.y += 80.0
            if flip:
                root.rotation_euler.y = 3.141592653589793

        scn.render.engine = ("BLENDER_EEVEE" if eevee_all or
                             filename[1] == "0" and int(filename[:2]) in
                             (4, 5, 6, 7) else "CYCLES")
        scn.camera = bpy.data.objects[cam_name]
        scn.render.filepath = str(RENDERS / f"{filename}.png")
        bpy.ops.render.render(write_still=True)

        if root:
            if flip:
                root.rotation_euler.y = 0.0
            if shift80:
                root.location.y -= 80.0
        if is_rake:
            for n, e in energies.items():
                bpy.data.objects[n].data.energy = e
            if rake:
                rake.data.energy = 0.0
        print(f"[v43] rendered {filename} ({scn.render.engine})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
