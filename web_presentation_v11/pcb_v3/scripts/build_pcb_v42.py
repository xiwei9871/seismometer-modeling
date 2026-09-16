"""Phase A3 STEP 4 — surface / silkscreen / vias / pads pass.

Loads pcb_v41_semantic.blend (geometry baseline — all STEP1-3 parts are
FROZEN) and upgrades the *surface layer* only:

  * board faces -> MAT_PCB_GREEN_* with TEX42_* photo-derived textures
    (real traces/vias/pads/silkscreen baked from the registered photos;
    the procedural Manhattan line field is gone)
  * module + coil-daughterboard top faces get photo-crop textures
    (real module silkscreen / real daughterboard logo+markings)
  * photo-visible parts that were still missing:
      A front: white castellated edge module, two "2R2" inductors
      A back:  wire-harness connector + 8-wire fan, 3 LED squares,
               vertical SN sticker, metal shield plate + braided loop
      B back:  two polymer electrolytic capacitors
  * photo-density-guided SMT top-up (instanced shared meshes)
  * material differentiation per STEP4 spec

Saves pcb_v42_surface.blend + v42 manifests.

Run: blender -b pcb_v41_semantic.blend --python scripts/build_pcb_v42.py
"""
from __future__ import annotations

import json
import math
import random
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
TEX = ROOT / "textures"
OUT_BLEND = ROOT / "pcb_v42_surface.blend"
SEM_JSON = ROOT / "pcb_semantic_components.json"
SURF_MANIFEST = ROOT / "pcb_v42_surface_manifest.json"
MAT_MANIFEST = ROOT / "pcb_v42_material_manifest.json"

TOP_Z = 0.8


def _mat(name, base, rough, metal=0.0):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*base, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    return m


def tex_mat(name, img_name, rough=0.45, bump_strength=0.14):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    img = bpy.data.images.get(img_name) or bpy.data.images.load(
        str(TEX / f"{img_name}.png"))
    img.pack()
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = bump_strength
    bump.inputs["Distance"].default_value = 0.04
    nt.links.new(tex.outputs["Color"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    bsdf.inputs["Roughness"].default_value = rough
    return m


def _assign(obj, mat_name, sem, parent, props=None):
    if mat_name and obj.data and hasattr(obj.data, "materials"):
        obj.data.materials.append(bpy.data.materials[mat_name])
    obj["semantic"] = sem
    obj["presentation"] = "PCB_V42"
    if props:
        for k, v in props.items():
            obj[k] = v
    obj.parent = parent
    return obj


def box(name, loc, size, mk, sem, parent, bevel=0.2, rot_z=0.0, props=None):
    bpy.ops.mesh.primitive_cube_add(location=(0, 0, 0))
    o = bpy.context.object
    o.name = name
    o.scale = (size[0] / 2, size[1] / 2, size[2] / 2)
    bpy.ops.object.transform_apply(scale=True)
    o.rotation_euler.z = rot_z
    if bevel:
        mod = o.modifiers.new("bev", "BEVEL")
        mod.width, mod.segments = bevel, 2
        bpy.ops.object.modifier_apply(modifier=mod.name)
    for p in o.data.polygons:
        p.use_smooth = True
    _assign(o, mk, sem, parent, props)
    o.location = loc          # board-local coords under board parent
    return o


def cyl_at(name, loc, r, d, mk, sem, parent, verts=24, props=None):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=d,
                                        location=(0, 0, 0))
    o = bpy.context.object
    o.name = name
    for p in o.data.polygons:
        p.use_smooth = True
    _assign(o, mk, sem, parent, props)
    o.location = loc
    return o


def cable_curve(name, pts, radius, mk, sem, parent):
    cu = bpy.data.curves.new(name + "_c", "CURVE")
    cu.dimensions = "3D"
    cu.resolution_u = 12
    cu.bevel_depth = radius
    cu.bevel_resolution = 4
    spl = cu.splines.new("BEZIER")
    spl.bezier_points.add(len(pts) - 1)
    for bp, co in zip(spl.bezier_points, pts):
        bp.co = co
        bp.handle_left_type = "AUTO"
        bp.handle_right_type = "AUTO"
    o = bpy.data.objects.new(name, cu)
    bpy.context.scene.collection.objects.link(o)
    _assign(o, mk, sem, parent)
    return o


def top_marking(name, text, x, y, z, size, board, rot=0.0):
    cu = bpy.data.curves.new(name + "_c", "FONT")
    cu.body = text
    cu.size = size
    cu.extrude = 0.01
    cu.align_x, cu.align_y = "CENTER", "CENTER"
    o = bpy.data.objects.new(name, cu)
    bpy.context.scene.collection.objects.link(o)
    o.rotation_euler.z = rot
    o.location = (x, y, z)
    bpy.context.view_layer.objects.active = o
    o.select_set(True)
    bpy.ops.object.convert(target="MESH")
    o.select_set(False)
    _assign(o, "MAT_PRINT_DARK", "INDUCTOR_MARK", board)
    o.location = (x, y, z)
    return o


def _kill(names):
    for n in names:
        o = bpy.data.objects.get(n)
        if o:
            bpy.data.objects.remove(o)


def top_face_uv(obj, w, d, mat):
    """planar-map the object's top face (local ±w/2, ±d/2 -> 0..1) and
    give it its own material slot."""
    me = obj.data
    me.materials.append(mat)
    new_idx = len(me.materials) - 1
    uv = me.uv_layers.get("UVMap") or me.uv_layers.new(name="UVMap")
    for poly in me.polygons:
        if poly.normal.z > 0.85:
            poly.material_index = new_idx
            for li in poly.loop_indices:
                co = me.vertices[me.loops[li].vertex_index].co
                uv.data[li].uv = ((co.x + w / 2) / w, (co.y + d / 2) / d)


def swap_board_mats(board_name, mat_f, mat_b):
    board = bpy.data.objects[board_name]
    me = board.data
    me.materials[0] = mat_f
    me.materials[1] = mat_b
    return board


# ---------------------------------------------------------------------------
# photo-density SMT field
# ---------------------------------------------------------------------------

def existing_footprints(root_names):
    """(x0,y0,x1,y1) world-bboxes of all parts under roots (board mesh
    itself excluded — its bbox would cover everything)."""
    skip = ("PCB_A_MAIN_SYSTEM_BOARD", "PCB_B_AUXILIARY_INTERFACE_BOARD",
            "SEM_")
    boxes = []
    for rn in root_names:
        root = bpy.data.objects.get(rn)
        if root is None:
            continue
        stack = [root]
        while stack:
            o = stack.pop()
            stack += list(o.children)
            if o.type in ("MESH", "CURVE", "FONT") and \
                    not o.name.startswith(skip):
                xs, ys = [], []
                for c in o.bound_box:
                    w = o.matrix_world @ Vector(c)
                    xs.append(w.x)
                    ys.append(w.y)
                boxes.append((min(xs), min(ys), max(xs), max(ys)))
    return boxes


def scatter_field(name, field_json, z, parent, rng, max_n,
                  keep_out, min_gap=1.05, y_off=0.0, mirror_x=False):
    """place instanced chips on photo-dense cells.  Back-face photos are
    Y-flipped (x mirrored), so mirror_x maps image-x -> board-x."""
    cells = [c for c in field_json["cells"] if 0.10 < c[2] < 0.82]
    rng.shuffle(cells)
    placed = []
    made = []
    meshes = SMT_MESHES
    for cx, cy, d in cells:
        if len(made) >= max_n:
            break
        x = (-cx if mirror_x else cx) + rng.uniform(-0.4, 0.4)
        y = cy + rng.uniform(-0.4, 0.4) + y_off
        if any(x0 - 0.4 <= x <= x1 + 0.4 and y0 - 0.4 <= y <= y1 + 0.4
               for x0, y0, x1, y1 in keep_out):
            continue
        if any(math.hypot(x - px, y - py) < min_gap for px, py in placed):
            continue
        placed.append((x, y))
        kind = rng.random()
        me = meshes[2] if kind > 0.88 else (meshes[1] if kind > 0.55
                                          else meshes[0])
        o = bpy.data.objects.new(f"{name}_{len(made):03d}", me)
        bpy.context.scene.collection.objects.link(o)
        o.location = (x, y, z)
        o.rotation_euler.z = rng.choice([0.0, math.pi / 2]) + \
            rng.uniform(-0.12, 0.12)
        o["semantic"] = "SMT_PASSIVE"
        o["presentation"] = "PCB_V42"
        o["geometry_mode"] = "INSTANCED"
        o.parent = parent
        made.append(o)
    return made


def build_smt_meshes():
    """three shared chip meshes (no bpy.ops, from_pydata)."""
    meshes = []
    for name, (w, d, h), mat in (
            ("SMT42_CHIP_TAN", (1.5, 0.8, 0.5), "MAT_CHIP_TAN"),
            ("SMT42_CHIP_DARK", (1.8, 1.1, 0.6), "MAT_IC_BLACK_MATTE"),
            ("SMT42_SOIC", (3.6, 2.4, 1.1), "MAT_IC_BLACK_SEMIMATTE")):
        if name in bpy.data.meshes:
            meshes.append(bpy.data.meshes[name])
            continue
        v = [(x, y, z) for x in (-w / 2, w / 2) for y in (-d / 2, d / 2)
             for z in (-h / 2, h / 2)]
        f = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 2, 6, 4), (1, 5, 7, 3),
             (0, 4, 5, 1), (2, 3, 7, 6)]
        me = bpy.data.meshes.new(name)
        me.from_pydata(v, [], f)
        me.update()
        me.materials.append(bpy.data.materials[mat])
        meshes.append(me)
    return meshes


SMT_MESHES = []

# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main():
    global SMT_MESHES
    rng = random.Random(90210)

    # ---- materials ------------------------------------------------------
    _mat("MAT_CHIP_TAN", (0.42, 0.30, 0.16), 0.5)
    _mat("MAT_IC_BLACK_SEMIMATTE", (0.014, 0.015, 0.018), 0.34, 0.12)
    _mat("MAT_EDGEMOD_CREAM", (0.80, 0.75, 0.62), 0.55)
    _mat("MAT_GOLD_PAD", (0.55, 0.42, 0.16), 0.35, 0.9)
    _mat("MAT_LED_WHITE", (0.88, 0.87, 0.80), 0.32)
    _mat("MAT_CAP_SLEEVE_RED", (0.38, 0.05, 0.04), 0.5)
    _mat("MAT_CAP_TOP_METAL", (0.58, 0.60, 0.64), 0.3, 0.85)
    _mat("MAT_BRAID_METAL", (0.50, 0.52, 0.55), 0.38, 0.95)
    _mat("MAT_SHIELD_PLATE", (0.42, 0.44, 0.48), 0.35, 0.9)
    # retunes (STEP4 §12-16)
    _mat("MAT_CERAMIC_WHITE", (0.76, 0.74, 0.68), 0.58)     # technical white
    _mat("MAT_COPPER_PATCH", (0.44, 0.24, 0.08), 0.4, 0.8)
    _mat("MAT_METAL_SCREW", (0.18, 0.20, 0.24), 0.3, 0.95)

    m_af = tex_mat("MAT_PCB_GREEN_A_FRONT", "TEX42_pcb_a_front")
    m_ab = tex_mat("MAT_PCB_GREEN_A_BACK", "TEX42_pcb_a_back")
    m_bf = tex_mat("MAT_PCB_GREEN_B_FRONT", "TEX42_pcb_b_front")
    m_bb = tex_mat("MAT_PCB_GREEN_B_BACK", "TEX42_pcb_b_back")
    m_mod = tex_mat("MAT_MOD_TOP_SURF", "TEX42_mod_top", rough=0.42,
                    bump_strength=0.08)
    m_db = tex_mat("MAT_DB_TOP_SURF", "TEX42_db_top", rough=0.45,
                   bump_strength=0.08)

    board_a = swap_board_mats("PCB_A_MAIN_SYSTEM_BOARD", m_af, m_ab)
    board_b = swap_board_mats("PCB_B_AUXILIARY_INTERFACE_BOARD", m_bf, m_bb)

    made = []

    # ---- module top face -> real photo surface ---------------------------
    mod = bpy.data.objects["A_MOD_PCB"]
    top_face_uv(mod, 42.6, 30.1, m_mod)

    # ---- daughterboard top face -> real photo surface --------------------
    # the texture already carries logo / pads / SN / pin row / triangles,
    # so the STEP-3 placeholder decals come off (coil geometry stays).
    _kill(["A_DB_SN", "A_DB_SN_TXT"] +
          [f"A_DB_LOGO_{i}" for i in range(8)] +
          [f"A_DB_PAD_{i}" for i in range(6)] +
          [f"A_DB_PIN_{i}" for i in range(8)] +
          [f"A_DB_TRI_{i}" for i in range(2)])
    db = bpy.data.objects["A_DB_PCB"]
    top_face_uv(db, 27.0, 41.0, m_db)

    # ---- A front: white castellated edge module --------------------------
    # photo: ~11x14.5 cream module @ (-39.8,11.2), gold castellated pads
    # down both long edges, metal-grey top with faint print
    _kill(["PCB_A_LEFT_CONN"])
    em_root = bpy.data.objects.get("A_EDGE_MODULE") or \
        bpy.data.objects.new("A_EDGE_MODULE", None)
    if em_root.name not in bpy.context.scene.collection.objects:
        bpy.context.scene.collection.objects.link(em_root)
    em_root["semantic"] = "EDGE_MODULE"
    em = []
    em.append(box("A_EM_PCB", (-39.8, 11.2, TOP_Z + 0.8), (11.0, 14.5, 1.6),
                  "MAT_EDGEMOD_CREAM", "EDGE_MODULE", board_a, bevel=0.3,
                  props={"thickness_estimated": True}))
    em.append(box("A_EM_CAN", (-39.8, 11.2, TOP_Z + 1.95),
                  (9.6, 12.6, 0.9), "MAT_SHIELD_PLATE", "EDGE_MODULE",
                  board_a, bevel=0.4))
    for j, ty in enumerate((8.4, 11.2, 14.0)):      # faint print lines
        em.append(box(f"A_EM_TXT_{j}", (-39.8, ty, TOP_Z + 2.42),
                      (5.5 - j * 1.2, 0.5, 0.04), "MAT_PRINT_DARK",
                      "SILKSCREEN_TEXT", board_a, bevel=0.02))
    for s in (-1, 1):                              # castellated pad rows
        for k in range(7):
            em.append(box(f"A_EM_PAD_{s:+d}_{k}",
                          (-39.8 + s * 5.9, 5.3 + k * 1.9, TOP_Z + 0.1),
                          (1.0, 1.3, 0.2), "MAT_GOLD_PAD", "TEST_PAD",
                          board_a, bevel=0.08))
    for o in em:
        o.parent = em_root
    em_root.parent = bpy.data.objects["PCB_A_MAIN_BOARD_MODULES"]
    made += em

    # ---- A front: two 2R2 inductors right of the daughterboard -----------
    for i, (ix, iy) in enumerate(((16.7, 5.0), (16.7, -4.4))):
        made.append(box(f"A_IND_2R2_{i}_BODY", (ix, iy, TOP_Z + 1.3),
                        (5.2, 6.0, 2.6), "MAT_INDUCTOR_GREY", "INDUCTOR",
                        board_a, bevel=0.35,
                        props={"pkg": "MOLDED_POWER"}))
        for s in (-1, 1):
            made.append(box(f"A_IND_2R2_{i}_TERM_{s:+d}",
                            (ix, iy + s * 3.0, TOP_Z + 0.8),
                            (3.6, 0.9, 1.7), "MAT_TERMINAL_METAL",
                            "INDUCTOR_TERMINAL", board_a, bevel=0.08))
        made.append(top_marking(f"A_IND_2R2_{i}_PRINT", "2R2", ix, iy,
                                TOP_Z + 2.66, 1.9, board_a,
                                rot=math.pi / 2))

    # ---- module right column: a few more small ICs (photo density) -------
    for i, (ix, iy, iw, ih) in enumerate(((16.9, 39.6, 3.0, 3.0),
                                          (16.9, 34.6, 3.2, 3.4),
                                          (16.4, 28.4, 2.8, 3.4))):
        made.append(box(f"A_MOD_ICX_{i}", (ix, iy, TOP_Z + 3.4 + 0.45),
                        (iw, ih, 0.9), "MAT_IC_BLACK_SEMIMATTE", "IC",
                        board_a, bevel=0.15))

    # ---- A back: wire harness + LEDs + SN + shield plate -----------------
    _kill(["PCB_A_B_TAB", "PCB_A_B_LOOP", "PCB_A_B_SN"] +
          [f"PCB_A_B_WC_{i}" for i in range(3)])
    bk = []
    BZ = -TOP_Z
    # back photo is a page-flip (x mirrored): measured image-mm x is
    # negated to board coords.  Harness sits at board +36, wires exit +x.
    bk.append(box("A_BK_HARNESS_CONN", (36.0, 21.0, BZ - 2.4),
                  (7.0, 8.5, 4.8), "MAT_CONNECTOR_WHITE", "BACK_EDGE_CONN",
                  board_a, bevel=0.25))
    for i in range(8):                             # 8-wire white fan
        y0 = 17.8 + i * 0.85
        bk.append(cable_curve(f"A_BK_WIRE_{i}",
                              [(32.7, y0, BZ - 2.6),
                               (41.0, y0 - 1.2, BZ - 3.4),
                               (50.5, y0 - 4.0 - i * 0.35, BZ - 3.0)],
                              0.42, "MAT_CABLE_WHITE", "CABLE", board_a))
    # 3 white LED squares down the board-right column (image left)
    for i, ly in enumerate((7.8, -1.4, -10.2)):
        bk.append(box(f"A_BK_LED_{i}", (33.6 - i * 0.1, ly, BZ - 0.4),
                      (4.4, 5.0, 0.8), "MAT_LED_WHITE", "LED", board_a,
                      bevel=0.15))
    # vertical SN sticker at board (-33,9)
    bk.append(box("A_BK_SN", (-33.0, 9.0, BZ - 0.15), (4.2, 11.5, 0.25),
                  "MAT_LABEL_WHITE", "SN_LABEL", board_a, bevel=0.05,
                  props={"serial_real": True,
                         "public_replace": "SN: XXXXXXXX"}))
    bk.append(box("A_BK_SN_TXT", (-33.0, 9.0, BZ - 0.3), (1.4, 9.5, 0.08),
                  "MAT_PRINT_DARK", "SN_LABEL", board_a, bevel=0.02))
    # metal shield plate + braided cable loop exiting board bottom-left
    bk.append(box("A_BK_SHIELD", (-30.0, -32.0, BZ - 0.45),
                  (30.0, 24.0, 0.9), "MAT_SHIELD_PLATE", "METAL_SHIELD",
                  board_a, bevel=0.4))
    bk.append(cable_curve("A_BK_BRAID",
                          [(-34.0, -30.0, BZ - 1.0), (-40.0, -24.0, BZ - 1.4),
                           (-46.0, -18.0, BZ - 1.2), (-51.0, -12.0, BZ - 1.0)],
                          1.1, "MAT_BRAID_METAL", "CABLE", board_a))
    for o in bk:
        o.parent = bpy.data.objects["PCB_A_MAIN_BOARD_BOTTOM"]
    made += bk

    # ---- B back: two polymer electrolytic caps ---------------------------
    _kill(["PCB_B_B_CAP", "PCB_B_B_CAP_TOP"])
    BZB = -TOP_Z
    bb = []
    # photo positions mirrored to board coords (back photo = x-flip)
    bb.append(cyl_at("B_BK_CAP1", (3.7, -28.3, BZB - 3.5), 3.75, 7.0,
                     "MAT_CAP_SLEEVE_RED", "BULK_CAP", board_b))
    bb.append(cyl_at("B_BK_CAP1_TOP", (3.7, -28.3, BZB - 7.15), 3.5, 0.5,
                     "MAT_CAP_TOP_METAL", "BULK_CAP_TOP", board_b))
    bb.append(cyl_at("B_BK_CAP2", (5.0, -21.5, BZB - 2.8), 2.5, 5.5,
                     "MAT_CAP_SLEEVE_RED", "BULK_CAP", board_b))
    bb.append(cyl_at("B_BK_CAP2_TOP", (5.0, -21.5, BZB - 5.7), 2.3, 0.4,
                     "MAT_CAP_TOP_METAL", "BULK_CAP_TOP", board_b))
    for o in bb:
        o.parent = bpy.data.objects["PCB_B_AUXILIARY_BOARD_BOTTOM"]
    made += bb

    # ---- IC material variety (§15) ---------------------------------------
    for n in ("A_MOD_IC06", "A_MOD_IC09"):
        o = bpy.data.objects.get(n)
        if o and o.data.materials:
            o.data.materials[0] = bpy.data.materials["MAT_IC_BLACK_SEMIMATTE"]

    # ---- photo-density SMT top-up (instanced) -----------------------------
    SMT_MESHES = build_smt_meshes()
    hole_rects_a = [(x - r - 0.8, y - r - 0.8, x + r + 0.8, y + r + 0.8)
                    for x, y, r in
                    [(-41.46, -0.03, 3.07), (40.28, -1.35, 3.34),
                     (-32, 43, 2.2), (23, 44, 2.2), (-45.5, 0.5, 2.2),
                     (44, 0.5, 2.2), (-24, -42, 2.2), (23, -42.5, 2.2),
                     (-38, 36, 2), (38, 40, 2), (-46, -22, 2), (46, -30, 2)]]
    hole_rects_a.append((20, -19, 36, -9))            # the oblong slot
    hole_rects_b = [(x - r - 0.8, y - r - 0.8, x + r + 0.8, y + r + 0.8)
                    for x, y, r in
                    [(-0.97, -0.16, 2.3), (-23, 20, 2), (23, 20, 2),
                     (-23, -20, 2), (23, -19, 2), (-26.5, 0, 2)]]

    fields = {}
    for tag in ("a_front", "a_back", "b_front", "b_back"):
        fields[tag] = json.loads(
            (TEX / f"smt_field_{tag}.json").read_text())

    # footprints of existing parts in WORLD space (A at y=0, B at y=-80;
    # back-face photos are x-mirrored page-flips -> mirror_x)
    fp_a = existing_footprints(["PCB_A_MAIN_BOARD"])
    fp_b = existing_footprints(["PCB_B_AUXILIARY_BOARD"])
    hole_rects_b = [(x0, y0 - 80, x1, y1 - 80)
                    for x0, y0, x1, y1 in hole_rects_b]
    grp_a_top = bpy.data.objects["PCB_A_MAIN_BOARD_TOP"]
    grp_a_bot = bpy.data.objects["PCB_A_MAIN_BOARD_BOTTOM"]
    grp_b_top = bpy.data.objects["PCB_B_AUXILIARY_BOARD_TOP"]
    grp_b_bot = bpy.data.objects["PCB_B_AUXILIARY_BOARD_BOTTOM"]

    made += scatter_field("SMT42_AF", fields["a_front"], TOP_Z + 0.3,
                          grp_a_top, rng, 170, fp_a + hole_rects_a)
    made += scatter_field("SMT42_AB", fields["a_back"], BZ - 0.35,
                          grp_a_bot, rng, 80, fp_a + hole_rects_a,
                          mirror_x=True)
    made += scatter_field("SMT42_BF", fields["b_front"], TOP_Z + 0.3,
                          grp_b_top, rng, 230, fp_b + hole_rects_b,
                          y_off=-80.0)
    made += scatter_field("SMT42_BB", fields["b_back"], BZB - 0.35,
                          grp_b_bot, rng, 60, fp_b + hole_rects_b,
                          y_off=-80.0, mirror_x=True)

    # ---- manifests --------------------------------------------------------
    mat_manifest = {}
    for m in bpy.data.materials:
        b = m.node_tree.nodes.get("Principled BSDF") if m.use_nodes else None
        if not b:
            continue
        users = sum(1 for o in bpy.data.objects
                    if o.data and hasattr(o.data, "materials")
                    and m.name in [s.name if s else "" for s in
                                   o.data.materials])
        img_node = next((n for n in m.node_tree.nodes
                         if n.type == "TEX_IMAGE" and n.image), None)
        mat_manifest[m.name] = {
            "base": list(b.inputs["Base Color"].default_value)[:3],
            "rough": round(b.inputs["Roughness"].default_value, 3),
            "metal": round(b.inputs["Metallic"].default_value, 3),
            "texture": img_node.image.name if img_node else None,
            "used_by": users}
    MAT_MANIFEST.write_text(json.dumps(mat_manifest, indent=1))

    surf = {
        "stage": "STEP4_SURFACE",
        "blend": OUT_BLEND.name,
        "textures": {t: f"textures/{t}.png" for t in
                     ["TEX42_pcb_a_front", "TEX42_pcb_a_back",
                      "TEX42_pcb_b_front", "TEX42_pcb_b_back",
                      "TEX42_mod_top", "TEX42_db_top"]},
        "texture_source": "registered photos (real traces/vias/pads/"
                          "silkscreen extracted; no procedural routing)",
        "smt_fields": {t: len(fields[t]["cells"]) for t in fields},
        "new_parts": len(made),
        "frozen_geometry": [
            "PCB_A outline+holes", "PCB_B outline+holes",
            "PCB-B connectors/inductors (STEP1.1b)",
            "A_MAIN_BLACK_MODULE (STEP2)",
            "A_CERAMIC_PATCH_ANT (STEP3)", "A_COIL_SUBBOARD (STEP3)"],
        "removed_decals": "daughterboard logo/pads/SN/pinmarks/triangles "
                          "now carried by the real photo texture",
        "sn_policy": "master keeps real SN; objects flagged serial_real "
                     "must render 'SN: XXXXXXXX' in PUBLIC_WEB exports",
        "public_web_note": "replace serials: A_BK_SN, A_DB_SN(texture), "
                           "module CLMP157BI sticker region",
    }
    SURF_MANIFEST.write_text(json.dumps(surf, indent=1))

    bpy.ops.wm.save_as_mainfile(filepath=str(OUT_BLEND))
    print(json.dumps({"blend": OUT_BLEND.name, "new_parts": len(made),
                      "mats": len(mat_manifest)}))


if __name__ == "__main__":
    main()
