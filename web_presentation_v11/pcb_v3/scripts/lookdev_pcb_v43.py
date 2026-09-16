"""Phase A3 STEP 5 — final industrial LookDev on pcb_v42_surface.blend.

Pure material / lighting / camera / color-management pass.  NO geometry
moves, no re-registration, no new scatter (frozen STEP1-4 geometry).

  * board soldermask materials rebuilt as a layered node graph:
      TEX42 base colour (unchanged registration)
      + roughness variation from texture luminance (±~0.05)
      + silk-mask -> warm off-white ink, rougher, dielectric
      + metal-mask -> solder/pad metallic response
      + very weak micro-bump + faint clear-coat (resin layer)
  * flat materials retuned into the STEP-5 spec ranges (IC variants,
    gold pads, copper ring, ceramic, wire polymer, caps, shield)
  * studio rig: KEY softbox + FILL + RIM + weak TOP + grazing RAKE
  * neutral grey world + ground contact plane
  * AgX Medium-High-Contrast, Cycles with denoise
  * new hero/macro/rake cameras — validation cams untouched
  * material swatch strip for the contact sheet

Saves pcb_v43_lookdev.blend.

Run: blender -b pcb_v42_surface.blend --python scripts/lookdev_pcb_v43.py
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
TEX = ROOT / "textures"
OUT_BLEND = ROOT / "pcb_v43_lookdev.blend"
MAT_MANIFEST = ROOT / "pcb_v43_material_manifest.json"


def img(name, noncolor=False):
    i = bpy.data.images.get(name) or bpy.data.images.load(
        str(TEX / f"{name}.png"))
    i.pack()
    if noncolor:
        i.colorspace_settings.name = "Non-Color"
    return i


def _mat(name, base, rough, metal=0.0, spec=None, coat=None):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*base, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if spec is not None and "Specular IOR Level" in b.inputs:
        b.inputs["Specular IOR Level"].default_value = spec
    if coat is not None:
        b.inputs["Coat Weight"].default_value = coat
        b.inputs["Coat Roughness"].default_value = 0.32
    return m


def _n(nt, kind, x, y):
    n = nt.nodes.new(kind)
    n.location = (x, y)
    return n


def soldermask_mat(name, tex_base):
    """layered soldermask: colour tex + lum-driven roughness + silk ink
    + exposed metal + micro-bump + light coat."""
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = _n(nt, "ShaderNodeOutputMaterial", 900, 0)
    bsdf = _n(nt, "ShaderNodeBsdfPrincipled", 620, 0)
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    tex = _n(nt, "ShaderNodeTexImage", -900, 120)
    tex.image = img(tex_base)
    silk = _n(nt, "ShaderNodeTexImage", -900, -220)
    silk.image = img(f"{tex_base}_silk", noncolor=True)
    met = _n(nt, "ShaderNodeTexImage", -900, -520)
    met.image = img(f"{tex_base}_metal", noncolor=True)

    # industrial deep green: pull saturation/value down
    hs = _n(nt, "ShaderNodeHueSaturation", -420, 120)
    hs.inputs["Saturation"].default_value = 0.78
    hs.inputs["Value"].default_value = 0.82
    nt.links.new(tex.outputs["Color"], hs.inputs["Color"])

    # base colour: silk pixels pulled toward warm off-white ink
    mixc = _n(nt, "ShaderNodeMixRGB", -160, 200)
    mixc.blend_type = "MIX"
    mixc.inputs[2].default_value = (0.74, 0.71, 0.66, 1.0)
    nt.links.new(hs.outputs["Color"], mixc.inputs[1])
    nt.links.new(silk.outputs["Color"], mixc.inputs["Fac"])
    nt.links.new(mixc.outputs["Color"], bsdf.inputs["Base Color"])

    # roughness: lum -> 0.32..0.50, silk -> 0.56, metal -> 0.28
    bw = _n(nt, "ShaderNodeRGBToBW", -680, 420)
    nt.links.new(tex.outputs["Color"], bw.inputs["Color"])
    mr = _n(nt, "ShaderNodeMapRange", -440, 420)
    mr.inputs["From Min"].default_value = 0.0
    mr.inputs["From Max"].default_value = 1.0
    mr.inputs["To Min"].default_value = 0.32
    mr.inputs["To Max"].default_value = 0.50
    mr.clamp = True
    nt.links.new(bw.outputs["Val"], mr.inputs["Value"])
    r_silk = _n(nt, "ShaderNodeMix", -140, -100)
    r_silk.data_type = "FLOAT"
    r_silk.inputs["B"].default_value = 0.56
    nt.links.new(silk.outputs["Color"], r_silk.inputs["Factor"])
    nt.links.new(mr.outputs["Result"], r_silk.inputs["A"])
    r_met = _n(nt, "ShaderNodeMix", 160, -160)
    r_met.data_type = "FLOAT"
    r_met.inputs["B"].default_value = 0.28
    nt.links.new(met.outputs["Color"], r_met.inputs["Factor"])
    nt.links.new(r_silk.outputs["Result"], r_met.inputs["A"])
    nt.links.new(r_met.outputs["Result"], bsdf.inputs["Roughness"])

    # metallic only on real pads/rings
    mm = _n(nt, "ShaderNodeMath", 160, -420)
    mm.operation = "MULTIPLY"
    mm.inputs[1].default_value = 0.92
    nt.links.new(met.outputs["Color"], mm.inputs[0])
    nt.links.new(mm.outputs[0], bsdf.inputs["Metallic"])

    # micro normal: very weak — texture lum + silk slightly proud
    h_add = _n(nt, "ShaderNodeMath", -140, -640)
    h_add.operation = "MULTIPLY_ADD"
    h_add.inputs[1].default_value = 0.30
    h_add.inputs[2].default_value = 0.0
    nt.links.new(silk.outputs["Color"], h_add.inputs[0])
    h_mix = _n(nt, "ShaderNodeMix", 60, -620)
    h_mix.data_type = "FLOAT"
    h_mix.blend_type = "ADD"
    h_mix.inputs["Factor"].default_value = 1.0
    nt.links.new(bw.outputs["Val"], h_mix.inputs["A"])
    nt.links.new(h_add.outputs[0], h_mix.inputs["B"])
    bump = _n(nt, "ShaderNodeBump", 380, -560)
    bump.inputs["Strength"].default_value = 0.10
    bump.inputs["Distance"].default_value = 0.03
    nt.links.new(h_mix.outputs["Result"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])

    bsdf.inputs["Coat Weight"].default_value = 0.15
    bsdf.inputs["Coat Roughness"].default_value = 0.32
    bsdf.inputs["IOR"].default_value = 1.46
    return m


def surface_mat(name, tex_base, rough=0.44, bump_strength=0.08,
                sat=0.90, val=0.92, spec=None):
    """simpler textured top surface (module / daughterboard)."""
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = _n(nt, "ShaderNodeOutputMaterial", 600, 0)
    bsdf = _n(nt, "ShaderNodeBsdfPrincipled", 320, 0)
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    tex = _n(nt, "ShaderNodeTexImage", -600, 80)
    tex.image = img(tex_base)
    hs = _n(nt, "ShaderNodeHueSaturation", -400, 80)
    hs.inputs["Saturation"].default_value = sat
    hs.inputs["Value"].default_value = val
    nt.links.new(tex.outputs["Color"], hs.inputs["Color"])
    nt.links.new(hs.outputs["Color"], bsdf.inputs["Base Color"])
    bw = _n(nt, "ShaderNodeRGBToBW", -420, 300)
    nt.links.new(tex.outputs["Color"], bw.inputs["Color"])
    mr = _n(nt, "ShaderNodeMapRange", -220, 300)
    mr.inputs["To Min"].default_value = rough - 0.05
    mr.inputs["To Max"].default_value = rough + 0.05
    nt.links.new(bw.outputs["Val"], mr.inputs["Value"])
    nt.links.new(mr.outputs["Result"], bsdf.inputs["Roughness"])
    bump = _n(nt, "ShaderNodeBump", 100, -300)
    bump.inputs["Strength"].default_value = bump_strength
    bump.inputs["Distance"].default_value = 0.03
    nt.links.new(bw.outputs["Val"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    bsdf.inputs["Coat Weight"].default_value = 0.04
    bsdf.inputs["Coat Roughness"].default_value = 0.38
    bsdf.inputs["Transmission Weight"].default_value = 0.0
    if spec is not None:
        bsdf.inputs["Specular IOR Level"].default_value = spec
    return m


# ---------------------------------------------------------------------------
# lighting / world / cameras
# ---------------------------------------------------------------------------


def area(name, loc, energy, size, target, color):
    ld = bpy.data.lights.get(name) or bpy.data.lights.new(name, "AREA")
    ld.energy = energy
    ld.shape = "DISK" if size < 60 else "RECTANGLE"
    ld.size = size
    if ld.shape == "RECTANGLE":
        ld.size_y = size * 0.7
    ld.color = color
    o = bpy.data.objects.get(name) or bpy.data.objects.new(name, ld)
    if o.name not in bpy.context.scene.collection.objects:
        bpy.context.scene.collection.objects.link(o)
    o.location = loc
    o.rotation_euler = (Vector(target) - o.location).to_track_quat(
        "-Z", "Y").to_euler()
    return o


def cam(name, target, direction, dist, lens, fstop=8.0):
    cd = bpy.data.cameras.get(name) or bpy.data.cameras.new(name)
    cd.lens, cd.sensor_width = lens, 36
    cd.dof.use_dof = True
    cd.dof.aperture_fstop = fstop
    o = bpy.data.objects.get(name) or bpy.data.objects.new(name, cd)
    if o.name not in bpy.context.scene.collection.objects:
        bpy.context.scene.collection.objects.link(o)
    t = Vector(target)
    o.location = t + Vector(direction).normalized() * dist
    o.rotation_euler = (t - o.location).to_track_quat("-Z", "Y").to_euler()
    cd.dof.focus_distance = dist
    return o


def swatch(name, loc, mat_name, kind="sphere"):
    if bpy.data.objects.get(name):
        return
    if kind == "sphere":
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3, radius=4.0,
                                            location=loc)
    else:
        bpy.ops.mesh.primitive_cube_add(location=loc)
        bpy.context.object.scale = (4.0, 4.0, 4.0)
        bpy.ops.object.transform_apply(scale=True)
        mod = bpy.context.object.modifiers.new("b", "BEVEL")
        mod.width, mod.segments = 0.8, 3
        bpy.ops.object.modifier_apply(modifier=mod.name)
    o = bpy.context.object
    o.name = name
    o.data.materials.append(bpy.data.materials[mat_name])
    o["presentation"] = "PCB_V43_SWATCH"


def main():
    # ---- material retune (STEP5 ranges) ----------------------------------
    soldermask_mat("MAT_PCB_GREEN_A_FRONT", "TEX42_pcb_a_front")
    soldermask_mat("MAT_PCB_GREEN_A_BACK", "TEX42_pcb_a_back")
    soldermask_mat("MAT_PCB_GREEN_B_FRONT", "TEX42_pcb_b_front")
    soldermask_mat("MAT_PCB_GREEN_B_BACK", "TEX42_pcb_b_back")
    surface_mat("MAT_MOD_TOP_SURF", "TEX42_mod_top", rough=0.58, sat=0.42, val=0.68, spec=0.25)
    surface_mat("MAT_DB_TOP_SURF", "TEX42_db_top", rough=0.48, sat=0.80, val=0.78)

    _mat("MAT_pcb_edge", (0.16, 0.22, 0.12), 0.5)
    _mat("MAT_IC_BLACK_MATTE", (0.020, 0.021, 0.024), 0.45, 0.08)
    _mat("MAT_IC_BLACK_SEMIMATTE", (0.016, 0.017, 0.020), 0.34, 0.10)
    _mat("MAT_IC_BLACK_02", (0.012, 0.013, 0.015), 0.40, 0.10)
    _mat("MAT_MODULE_PCB_BLACK", (0.012, 0.012, 0.013), 0.55, spec=0.28)
    _mat("MAT_CHIP_TAN", (0.34, 0.26, 0.17), 0.54)
    _mat("MAT_INDUCTOR_GREY", (0.115, 0.115, 0.13), 0.55, 0.05)
    _mat("MAT_PRINT_DARK", (0.06, 0.06, 0.07), 0.62)
    _mat("MAT_CONNECTOR_WHITE", (0.50, 0.47, 0.42), 0.55, spec=0.30)
    _mat("MAT_CONJ_CAVITY", (0.016, 0.015, 0.014), 0.72)
    _mat("MAT_CABLE_WHITE", (0.62, 0.59, 0.54), 0.44)
    _mat("MAT_ADHESIVE_WHITE", (0.66, 0.65, 0.61), 0.44)
    _mat("MAT_LABEL_WHITE", (0.66, 0.65, 0.62), 0.62, spec=0.28)
    _mat("MAT_CERAMIC_WHITE", (0.80, 0.77, 0.70), 0.48, spec=0.42)
    _mat("MAT_COPPER_PATCH", (0.38, 0.20, 0.065), 0.27, 1.0)
    _mat("MAT_GOLD_PAD", (0.42, 0.32, 0.12), 0.26, 1.0)
    _mat("MAT_TERMINAL_METAL", (0.52, 0.54, 0.58), 0.28, 0.95)
    _mat("MAT_METAL_SCREW", (0.14, 0.15, 0.18), 0.37, 0.95, spec=0.32)
    _mat("MAT_COIL_METAL", (0.58, 0.56, 0.51), 0.30, 0.95)
    _mat("MAT_SUBBOARD_GREEN", (0.020, 0.155, 0.058), 0.48)
    _mat("MAT_SUBBOARD_DARK", (0.016, 0.13, 0.048), 0.55)
    _mat("MAT_LOGO_DARK", (0.016, 0.14, 0.052), 0.55)
    _mat("MAT_LED_WHITE", (0.55, 0.54, 0.50), 0.38)
    _mat("MAT_CAP_SLEEVE_RED", (0.30, 0.045, 0.035), 0.48)
    _mat("MAT_CAP_TOP_METAL", (0.60, 0.62, 0.66), 0.27, 0.95)
    _mat("MAT_BRAID_METAL", (0.50, 0.52, 0.56), 0.34, 0.95)
    _mat("MAT_SHIELD_PLATE", (0.44, 0.46, 0.50), 0.38, 0.90)
    _mat("MAT_shield_metal", (0.44, 0.46, 0.50), 0.38, 0.90)
    _mat("MAT_EDGEMOD_CREAM", (0.78, 0.73, 0.60), 0.55)
    _mat("MAT_EDGE_GOLD", (0.42, 0.34, 0.18), 0.35, 0.85)
    _mat("MAT_v4_floor", (0.030, 0.032, 0.038), 0.85)

    # ---- lighting rig -----------------------------------------------------
    for n in ("V4_KEY", "V4_FILL", "V4_RIM", "V4_TOP"):
        if bpy.data.objects.get(n):
            bpy.data.objects.remove(bpy.data.objects[n])
    CENTER = (0, -40, 0)                       # between the two boards
    area("L43_KEY", (-170, -170, 240), 52000, 130, CENTER,
         (1.0, 0.97, 0.92))
    area("L43_FILL", (190, -120, 150), 22000, 150, CENTER,
         (0.92, 0.95, 1.0))
    area("L43_RIM", (60, 200, 230), 26000, 110, CENTER,
         (0.98, 0.99, 1.0))
    area("L43_TOP", (0, -30, 330), 9000, 260, CENTER,
         (1.0, 1.0, 1.0))
    area("L43_RAKE", (210, -60, 22), 42000, 160, (0, -40, 0),
         (1.0, 0.98, 0.95))
    # rake stays off for normal shots; render script toggles it

    # world: neutral industrial grey
    w = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.048, 0.050, 0.058, 1.0)
    bg.inputs[1].default_value = 1.0
    bpy.context.scene.world = w

    # ground contact plane just under the lowest parts
    fl = bpy.data.objects.get("Plane") or bpy.data.objects.get("Floor")
    if fl is None:
        bpy.ops.mesh.primitive_plane_add(size=4000, location=(0, -40, -9.5))
        fl = bpy.context.object
        fl.name = "Ground"
        fl.data.materials.append(bpy.data.materials["MAT_v4_floor"])
    else:
        fl.location = (0, -40, -9.5)

    # ---- color management + renderer -------------------------------------
    scn = bpy.context.scene
    scn.render.engine = "BLENDER_EEVEE"
    scn.render.resolution_x, scn.render.resolution_y = 1920, 1080
    scn.view_settings.look = "AgX - Medium High Contrast"
    scn.view_settings.exposure = 3.3
    scn.render.image_settings.file_format = "PNG"
    scn.cycles.samples = 96
    scn.cycles.use_denoising = True
    scn.cycles.use_adaptive_sampling = True

    # ---- new cameras -------------------------------------------------------
    # hero: strong industrial 3/4 views; macros reuse proven closeup angles
    cam("CAM_V43_HERO_A", (0, 2, 3), (0.58, -0.72, 0.62), 175, 58, 8.0)
    cam("CAM_V43_HERO_B", (0, -80, 4), (0.55, -0.70, 0.68), 160, 60, 8.0)
    cam("CAM_V43_HERO_PAIR", (0, -38, 2), (0.42, -0.62, 0.70), 330, 52,
        9.0)
    cam("CAM_V43_MACRO_MODULE", (-4, 30, 4), (0.5, -0.72, 0.55), 70, 88,
        6.3)
    cam("CAM_V43_MACRO_ANT", (-22, -31, 3), (0.45, -0.7, 0.7), 78, 85,
        7.1)
    cam("CAM_V43_MACRO_COIL", (2, -30, 3), (0.35, -0.72, 0.72), 95, 72,
        7.1)
    cam("CAM_V43_MACRO_B_CONN", (-16, -86, 4), (0.75, -0.85, 0.75), 92,
        78, 7.1)
    cam("CAM_V43_MACRO_B_POWER", (7, -87, 4), (0.65, -0.8, 0.8), 85, 80,
        7.1)
    cam("CAM_V43_RAKE_A", (0, 0, 2), (0.5, -0.65, 0.45), 150, 55, 11)
    cam("CAM_V43_RAKE_B", (0, -80, 2), (0.5, -0.65, 0.45), 150, 55, 11)
    cam("CAM_V43_SWATCH", (0, 146, 30), (0, -0.28, 1), 165, 62, 8.0)

    # validation cams: DOF off (spec §22 — validation must be fully sharp)
    for n in ("CAM_V4_A_TOP", "CAM_V4_B_TOP", "CAM_V41_A_MOD_TOP",
              "CAM_V41_A_MOD_34", "CAM_V41_A_MOD_CLOSE", "CAM_V41_A_ANT",
              "CAM_V41_A_COIL", "CAM_V41_B_CONN", "CAM_V41_B_POWER",
              "CAM_V41_B_HERO"):
        c = bpy.data.cameras.get(n)
        if c:
            c.dof.use_dof = False

    # ---- material swatch strip (contact-sheet source) ---------------------
    mats = [("MAT_PCB_GREEN_A_FRONT", "cube"), ("MAT_IC_BLACK_MATTE", "s"),
            ("MAT_CONNECTOR_WHITE", "s"), ("MAT_GOLD_PAD", "s"),
            ("MAT_TERMINAL_METAL", "s"), ("MAT_CERAMIC_WHITE", "s"),
            ("MAT_INDUCTOR_GREY", "s"), ("MAT_CAP_SLEEVE_RED", "s"),
            ("MAT_CABLE_WHITE", "s"), ("MAT_SHIELD_PLATE", "s"),
            ("MAT_COPPER_PATCH", "s"), ("MAT_MODULE_PCB_BLACK", "cube"),
            ("MAT_LED_WHITE", "cube"), ("MAT_BRAID_METAL", "s")]
    for i, (mn, k) in enumerate(mats):
        col = i % 7
        row = i // 7
        swatch(f"SW_{i:02d}", ((col - 3) * 11.5, 140 + row * 11.5, 30),
               mn, k)

    # ---- STEP4 placement bugfix (rendering bug found in review) -------
    # B_BK_CAP* were built at image coords without the -80 board offset
    # -> floated 24-70mm off the board edge.  Photo-verified targets:
    fix = {"B_BK_CAP1": (4.1, -99.9), "B_BK_CAP1_TOP": (4.1, -99.9),
           "B_BK_CAP2": (3.5, -96.6), "B_BK_CAP2_TOP": (3.5, -96.6)}
    for n, (x, y) in fix.items():
        o = bpy.data.objects.get(n)
        if o:
            o.matrix_world.translation.x = x
            o.matrix_world.translation.y = y

    # ---- material manifest -------------------------------------------------
    mm = {}
    for m in bpy.data.materials:
        b = m.node_tree.nodes.get("Principled BSDF") if m.use_nodes else None
        if not b:
            continue
        img_node = next((n for n in m.node_tree.nodes
                         if n.type == "TEX_IMAGE" and n.image), None)
        mm[m.name] = {
            "base": [round(v, 4) for v in
                     b.inputs["Base Color"].default_value[:3]],
            "rough": round(b.inputs["Roughness"].default_value, 3),
            "metal": round(b.inputs["Metallic"].default_value, 3),
            "coat": round(b.inputs["Coat Weight"].default_value, 3),
            "texture": img_node.image.name if img_node else None,
            "layered": "silk+metal masks" if "MAT_PCB_GREEN" in m.name
                       else ("photo crop" if "SURF" in m.name else "flat"),
        }
    MAT_MANIFEST.write_text(json.dumps(mm, indent=1))

    bpy.ops.wm.save_as_mainfile(filepath=str(OUT_BLEND))
    print(json.dumps({"blend": OUT_BLEND.name, "materials": len(mm)}))


if __name__ == "__main__":
    main()
