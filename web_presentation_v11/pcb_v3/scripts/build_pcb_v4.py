"""Build pcb_presentation_v4.blend — registration-driven PCB rebuild (A2.2).

Differences from V3:
  * board outlines come straight from registration/board_map.json
    (real traced polygons, all notches/slots included)
  * hole set = detected through-holes + perimeter plated holes read
    from the registration overlays + the right-centre kidney slot
  * board-surface texture samples the REGISTERED photos: real
    silkscreen marks (thin white features only), tonal mottling and
    faint real trace shadows are repainted onto soldermask green
  * Level-A components sit at measured positions/sizes

Run: blender -b --python build_pcb_v4.py -- --project-root <repo>
"""
from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path
import sys

import bpy
from mathutils import Vector

random.seed(20260915)

ROOT = Path(__file__).resolve().parents[1]
REG = ROOT / "registration"
OUT_BLEND = ROOT / "pcb_presentation_v4.blend"
TEX_DIR = ROOT / "textures"
BOARD_T = 1.6
TOP_Z = BOARD_T / 2

# ---------------------------------------------------------------------------
# Load registration data
# ---------------------------------------------------------------------------

BMAP = json.loads((REG / "board_map.json").read_text())["detail"]
# earcut-triangulated rings produced by precompute_board_geometry.py —
# the traced contours self-touch at 1px necks and break Blender's own
# curve tessellator, so the mesh arrives fully triangulated
BMESH = json.loads((REG / "board_mesh.json").read_text())


def outline_centered(key: str):
    d = BMAP[key]
    w, h = d["board_size_px"]
    return [(x - w / 2, h / 2 - y) for x, y in d["outline_points_mm"]], (w, h)


A_OUTLINE, A_SIZE = outline_centered("a_front")
B_OUTLINE, B_SIZE = outline_centered("b_front")

# Hole sets (board-centred mm). v44: re-detected from the corrected AI top
# view — old hole4 merged into the single left big hole, hole11 moved onto
# the real large cutout at (32.9,-24.4), kidney slot removed (absent in the
# corrected image), bottom-edge holes added/snapped.
A_HOLES = [                                        # detected (front, centred)
    (-45.6, 2.6, 3.0),                             # big left
    (47.8, -12.8, 3.1),                            # big right-mid
    (46.0, 3.2, 2.9),                              # big right-upper
    (32.9, -24.4, 5.0),                            # largest lower-right
]
A_HOLES += [                                       # plated perimeter holes
    (-39.0, 38.0, 2.0), (-26.7, 42.7, 2.2),        # top-left edge
    (23.0, 44.0, 2.2), (43.0, 29.0, 2.0),          # top-right edge
    (-46.0, -22.0, 2.0),                           # left edge
    (-24.0, -42.0, 2.2), (28.1, -43.7, 2.2),       # bottom edge
    (-29.3, -48.2, 2.2),                           # bottom-left edge
]
A_SLOT = None                                      # v44: no slot in corrected image

B_HOLES = [
    (30.03 - 31.0, 28.1 - 28.26, 2.3),             # centre hole
    (-23, 20, 2.0), (23, 20, 2.0),                 # top corners
    (-23, -20, 2.0), (23, -19, 2.0),               # bottom corners
    (-26.5, 0, 2.0),                               # left edge
]

# ---------------------------------------------------------------------------
# Materials
# ---------------------------------------------------------------------------


def _mat(name, base, rough, metal=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*base, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    return m


MATS = {}


def build_materials():
    MATS.update({
        "edge":       _mat("MAT_pcb_edge",       (0.30, 0.42, 0.26), 0.55),
        "ic":         _mat("MAT_ic_black",       (0.012, 0.013, 0.016), 0.34, 0.15),
        "module":     _mat("MAT_module_black",   (0.020, 0.021, 0.024), 0.30, 0.10),
        "conn_white": _mat("MAT_connector_white",(0.80, 0.78, 0.73), 0.55),
        "conn_dark":  _mat("MAT_connector_dark", (0.028, 0.030, 0.034), 0.40, 0.30),
        "inductor":   _mat("MAT_inductor_gray",  (0.30, 0.30, 0.31), 0.45, 0.10),
        "shield":     _mat("MAT_shield_metal",   (0.48, 0.50, 0.54), 0.32, 0.90),
        "cap_silver": _mat("MAT_cap_silver",     (0.46, 0.48, 0.52), 0.38, 0.85),
        "cap_red":    _mat("MAT_cap_red",        (0.45, 0.05, 0.04), 0.42),
        "ceramic":    _mat("MAT_ceramic_tan",    (0.72, 0.62, 0.45), 0.55),
        "ceramic_w":  _mat("MAT_ceramic_white",  (0.85, 0.82, 0.75), 0.50),
        "cable":      _mat("MAT_cable_white",    (0.82, 0.81, 0.78), 0.60),
        "label":      _mat("MAT_label_white",    (0.82, 0.81, 0.78), 0.65),
        "tantalum":   _mat("MAT_tantalum",       (0.45, 0.24, 0.09), 0.45),
        "coil":       _mat("MAT_coil_silver",    (0.62, 0.63, 0.65), 0.28, 0.92),
        "daughter":   _mat("MAT_daughter_green", (0.10, 0.24, 0.11), 0.42, 0.10),
        "pins":       _mat("MAT_pin_metal",      (0.55, 0.55, 0.58), 0.35, 0.9),
    })


def soldermask_material(name, tex_image):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = tex_image
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.15
    bump.inputs["Distance"].default_value = 0.05
    nt.links.new(tex.outputs["Color"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return m

def load_texture(name):
    """Load a baked PNG produced by bake_textures_v4.py (venv, cv2)."""
    img = bpy.data.images.load(str(TEX_DIR / f"{name}.png"))
    img.pack()
    return img

# ---------------------------------------------------------------------------
# Board + component builders
# ---------------------------------------------------------------------------


def build_board(name, geom_key, mat_f, mat_b):
    """mesh straight from board_mesh.json: earcut top/bottom tris + wall
    quads around the outer ring and every hole ring."""
    g = BMESH[geom_key]
    v2 = g["verts"]
    ends = g["ring_ends"]                       # ring boundary indices
    tris = g["tris"]
    n = len(v2)
    zt, zb = BOARD_T / 2, -BOARD_T / 2

    verts = [(x, y, zt) for x, y in v2] + [(x, y, zb) for x, y in v2]
    faces = []
    for i in range(0, len(tris), 3):
        a, b, c = tris[i], tris[i + 1], tris[i + 2]
        faces.append((a, b, c))                 # top
        faces.append((a + n, c + n, b + n))     # bottom (flipped)
    starts = [0] + ends[:-1]
    for s0, e0 in zip(starts, ends):            # walls: outer + holes
        for i in range(s0, e0):
            j = s0 + (i + 1 - s0) % (e0 - s0)
            faces.append((i, j, j + n, i + n))

    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    me.materials.append(mat_f)
    me.materials.append(mat_b)
    me.materials.append(MATS["edge"])

    # fix winding so caps point outward, then assign materials by normal
    for poly in me.polygons:
        is_cap = all(abs(me.vertices[me.loops[li].vertex_index].co.z)
                     == zt for li in poly.loop_indices)
        if is_cap and (poly.normal.z > 0) != (poly.center.z > 0):
            poly.flip()

    xs = [p[0] for p in g["outline"]]
    ys = [p[1] for p in g["outline"]]
    bw, bh = max(xs) - min(xs), max(ys) - min(ys)
    cx0, cy0 = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    uv = me.uv_layers.new(name="UVMap")
    for poly in me.polygons:
        if poly.normal.z > 0.5:
            poly.material_index = 0
        elif poly.normal.z < -0.5:
            poly.material_index = 1
        else:
            poly.material_index = 2
            continue
        for li in poly.loop_indices:
            co = me.vertices[me.loops[li].vertex_index].co
            uv.data[li].uv = ((co.x - cx0) / bw + 0.5,
                              (co.y - cy0) / bh + 0.5)
    obj["presentation"] = "PCB_V4"
    return obj


def _in_poly(outline, x, y, margin=1.5):
    """pure-python point-in-polygon so SMT scatter stays on the board."""
    inside = False
    j = len(outline) - 1
    for i in range(len(outline)):
        xi, yi = outline[i]
        xj, yj = outline[j]
        if (yi > y) != (yj > y) and \
                x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _min_edge_dist(outline, x, y):
    return min(math.hypot(x - px, y - py) for px, py in outline[::6])


def _assign(obj, mk, semantic, level, parent):
    if obj.data and hasattr(obj.data, "materials"):
        obj.data.materials.append(MATS[mk])
    obj["semantic"] = semantic
    obj["level"] = level
    obj["presentation"] = "PCB_V4"
    obj.parent = parent
    return obj


def box(name, loc, size, mk, semantic, level, parent, bevel=0.25, rot_z=0.0):
    bpy.ops.mesh.primitive_cube_add(location=loc)
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
    return _assign(o, mk, semantic, level, parent)


def cyl(name, loc, r, d, mk, semantic, level, parent):
    bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=r, depth=d,
                                        location=loc)
    o = bpy.context.object
    o.name = name
    for p in o.data.polygons:
        p.use_smooth = True
    return _assign(o, mk, semantic, level, parent)


def torus(name, loc, major, minor, mk, semantic, level, parent):
    bpy.ops.mesh.primitive_torus_add(major_radius=major, minor_radius=minor,
                                     major_segments=32, minor_segments=10,
                                     location=loc)
    o = bpy.context.object
    o.name = name
    for p in o.data.polygons:
        p.use_smooth = True
    return _assign(o, mk, semantic, level, parent)


def cable(name, pts, radius, mk, semantic, parent):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.resolution_u = 8
    cu.bevel_depth = radius
    cu.bevel_resolution = 3
    spl = cu.splines.new("BEZIER")
    spl.bezier_points.add(len(pts) - 1)
    for bp, co in zip(spl.bezier_points, pts):
        bp.co = co
        bp.handle_left_type = "AUTO"
        bp.handle_right_type = "AUTO"
    obj = bpy.data.objects.new(name, cu)
    bpy.context.scene.collection.objects.link(obj)
    return _assign(obj, mk, semantic, "A", parent)


def ic_with_pins(name, x, y, w, h, ht, parent, rot=0.0):
    """IC body + two pin rows — the detail that makes it read as a chip."""
    b = box(name, (x, y, TOP_Z + ht / 2 + 0.15), (w, h, ht), "ic", "IC",
            "B", parent, bevel=0.15, rot_z=rot)
    if w > h:  # pins on the long sides
        pw = w * 0.92
        for s_ in (-1, 1):
            dx, dy = -math.sin(rot) * s_ * (h / 2 + 0.18), \
                math.cos(rot) * s_ * (h / 2 + 0.18)
            box(name + f"_pins{s_}", (x + dx, y + dy, TOP_Z + 0.3),
                (pw, 0.32, 0.55), "pins", "IC_PINS", "C", parent,
                bevel=0.05, rot_z=rot)
    return b


# ---------------------------------------------------------------------------
# Population — positions in board-centred mm, from registered overlays
# ---------------------------------------------------------------------------


def build_pcb_a(board):
    P, z = [], TOP_Z

    # CLMP compute module — measured ~44x32 top-centre (-3, 31)
    P.append(box("PCB_A_MAIN_MODULE", (-3, 31, z + 2.4), (44, 32, 4.8),
                 "module", "MAIN_COMPUTE_MODULE", "A", board, bevel=0.8))
    P.append(box("PCB_A_MODULE_DIE_1", (-12, 35, z + 5.0), (12, 13, 0.8),
                 "ic", "MODULE_DIE", "A", board, bevel=0.1))
    P.append(box("PCB_A_MODULE_DIE_2", (-12, 20, z + 5.0), (11, 11, 0.8),
                 "ic", "MODULE_DIE", "A", board, bevel=0.1))
    P.append(box("PCB_A_MODULE_LABEL", (-2, 15, z + 4.95), (18, 4, 0.3),
                 "label", "MODULE_LABEL", "A", board, bevel=0.05))

    # coax antenna lead arcs off the module top, up toward the top edge
    P.append(cable("PCB_A_COAX", [(-6, 43, z + 3), (-2, 48, z + 5),
                                (6, 51, z + 4), (16, 52, z + 3)],
                   0.7, "cable", "COAX_ANTENNA_LEAD", board))

    # ceramic patch antenna — white frame + tan patch, ~18x18 at (-25,-28)
    P.append(box("PCB_A_CERAMIC_ANT", (-25, -28, z + 2.2), (18, 18, 4.4),
                 "ceramic_w", "CERAMIC_PATCH_ANTENNA", "A", board, bevel=0.6))
    P.append(box("PCB_A_ANT_PATCH", (-25, -28, z + 4.45), (12, 12, 0.4),
                 "ceramic", "ANTENNA_PATCH", "A", board, bevel=0.3))
    P.append(cyl("PCB_A_ANT_DOT", (-25, -28, z + 4.7), 1.6, 0.3,
                 "cap_silver", "ANTENNA_FEED", "A", board))

    # green shield/daughter zone — big, flush to bottom edge (1,-29), ~28x40
    P.append(box("PCB_A_SHIELD_ZONE", (1, -29, z + 1.4), (28, 40, 2.8),
                 "daughter", "SHIELDED_ZONE", "A", board, bevel=0.4))
    P.append(box("PCB_A_SHIELD_IC", (8, -16, z + 3.1), (6, 5, 1.2),
                 "inductor", "SHIELD_COMPONENT", "A", board, bevel=0.15))
    # vertical SN strip on the zone's left edge + text strip at its base
    P.append(box("PCB_A_ZONE_SN", (-11.5, -30, z + 2.85), (2.5, 16, 0.1),
                 "label", "SN_LABEL", "B", board, bevel=0.02))
    P.append(box("PCB_A_ZONE_TEXT", (1, -45.5, z + 2.85), (12, 1.6, 0.1),
                 "label", "SILKSCREEN_TEXT", "B", board, bevel=0.02))
    # the big wound silver spiral sits inside the zone's bottom (1,-36) Ø~16
    P.append(cyl("PCB_A_COIL_BASE", (1, -36, z + 2.9), 8.0, 1.0,
                 "coil", "POWER_COIL", "A", board))
    for i, r in enumerate((7.0, 5.4, 3.8, 2.2)):
        P.append(torus(f"PCB_A_COIL_{i}", (1, -36, z + 3.5 + i * 0.55),
                       r, 0.5, "coil", "POWER_COIL", "A", board))

    # white JST in the left-edge lobe + top edge connector
    P.append(box("PCB_A_LEFT_CONN", (-44, 18, z + 2.4), (8, 12, 4.8),
                 "conn_white", "EDGE_CONNECTOR", "A", board, bevel=0.5))
    P.append(box("PCB_A_TOP_CONN", (6, 46.5, z + 2.4), (14, 6, 4.8),
                 "conn_white", "EDGE_CONNECTOR", "A", board, bevel=0.5))

    # 2R2 power inductors right-of-centre (printed "2R2" in photo)
    for i, (x, y) in enumerate([(19, 4), (19, -5)]):
        P.append(box(f"PCB_A_2R2_{i}", (x, y, z + 1.9), (6, 6, 3.8),
                     "inductor", "POWER_INDUCTOR_2R2", "A", board, bevel=0.3))
        P.append(box(f"PCB_A_2R2_{i}_mark", (x, y, z + 3.85),
                     (3.4, 2.4, 0.15), "label", "INDUCTOR_MARK", "B", board,
                     bevel=0.05))

    # white ribbon exits right edge — plug caps the cable end
    P.append(cable("PCB_A_RIBBON", [(48, -14, z + 1), (54, -15, z + 1.6),
                                    (59, -13, z + 1.2)],
                   2.2, "cable", "RIBBON_CABLE", board))
    P.append(box("PCB_A_RIBBON_PLUG", (61, -12.5, z + 2.0), (8, 6, 4),
                 "conn_white", "RIBBON_PLUG", "A", board, bevel=0.5,
                 rot_z=0.15))

    # Level B — ICs with pin rows at measured-ish positions
    ics = [(-36, 22, 8, 5, 2.0, 0), (-22, 38, 7, 7, 2.4, 0),
           (30, 34, 9, 6, 2.2, 0.2), (-38, -12, 7, 5, 2.0, 0),
           (34, -26, 8, 6, 2.2, 0), (-14, -34, 7, 5, 2.0, 0),
           (38, 12, 6, 5, 2.0, 0), (-28, 40, 6, 5, 2.0, 0),
           (20, -34, 6, 4, 1.8, 0), (-6, -40, 7, 4, 1.8, 0)]
    for i, (x, y, w_, h_, t, r) in enumerate(ics):
        P.append(ic_with_pins(f"PCB_A_IC_{i:02d}", x, y, w_, h_, t, board, r))

    for i, (x, y) in enumerate([(-16, -16), (36, 20), (40, -30)]):
        P.append(box(f"PCB_A_IND_{i}", (x, y, z + 1.6), (5, 4, 3.2),
                     "inductor", "POWER_INDUCTOR", "B", board, bevel=0.2))
    for i, (x, y) in enumerate([(-16, 30), (16, -32), (42, 24), (-44, -20)]):
        P.append(box(f"PCB_A_TANT_{i}", (x, y, z + 0.9), (3.2, 1.8, 1.8),
                     "tantalum", "TANT_CAP", "B", board, bevel=0.1))
    P.append(box("PCB_A_CRYSTAL", (-12, -24, z + 0.9), (5, 3.2, 1.8),
                 "cap_silver", "CRYSTAL", "B", board, bevel=0.15))

    # Level C — dense passives, keep clear of holes/module/zone
    def clear(x, y):
        for hx, hy, hr in A_HOLES:
            if hr >= 2.9 and (x - hx) ** 2 + (y - hy) ** 2 < (hr + 7) ** 2:
                return False
        if -26 < x < 20 and 13 < y < 48:        # module
            return False
        if -14 < x < 16 and -49 < y < -8:       # shield zone
            return False
        if -36 < x < -15 and -38 < y < -18:     # ceramic antenna
            return False
        if not _in_poly(BMESH["a"]["outline"], x, y):
            return False
        if _min_edge_dist(BMESH["a"]["outline"], x, y) < 1.8:
            return False
        return True

    for i in range(130):
        x, y = random.uniform(-46, 46), random.uniform(-46, 46)
        if not clear(x, y):
            continue
        P.append(box(f"PCB_A_SMT_{i:02d}", (x, y, z + 0.4),
                     (random.uniform(1.2, 2.2), random.uniform(0.8, 1.3),
                      0.8), "ic", "SMT_PASSIVE", "C", board, bevel=0.05))

    # back: sparse — shield tab + wire loop + white edge conns + SN label
    bz = -TOP_Z
    P.append(box("PCB_A_B_TAB", (28, -22, bz - 0.5), (11, 7, 1.0),
                 "shield", "BACK_GROUND_TAB", "A", board, bevel=0.2))
    P.append(cable("PCB_A_B_LOOP", [(30, -20, bz - 1), (38, -18, bz - 2),
                                    (46, -12, bz - 1), (50, -6, bz - 0.5)],
                   0.45, "cap_silver", "GROUND_WIRE_LOOP", board))
    for i, (x, y) in enumerate([(-44, 12), (-44, 6), (-44, 0)]):
        P.append(box(f"PCB_A_B_WC_{i}", (x, y, bz - 1.4), (4, 5, 2.8),
                     "conn_white", "BACK_EDGE_CONN", "A", board, bevel=0.3))
    P.append(box("PCB_A_B_SN", (0, 38, bz - 0.15), (20, 4, 0.3),
                 "label", "SN_LABEL", "B", board, bevel=0.05))
    return P


def build_pcb_b(board):
    P, z = [], TOP_Z

    # 7 white JSTs at measured positions (centred mm, rot from overlay)
    jsts = [((-11, 14), (15, 7, 5.2), 0.0),
            ((5.5, 16), (5, 6, 4.8), 0.0),
            ((-26, -3.5), (6, 11, 4.8), 0.0),
            ((-11.5, -12), (16, 7, 5.2), -0.4),
            ((20.5, 8.75), (9, 6.5, 4.8), -0.5),
            ((15, -10), (8.5, 6, 4.8), 0.0),
            ((4, -22.7), (10, 6.5, 4.8), 0.0)]
    for i, ((x, y), s, rz) in enumerate(jsts):
        P.append(box(f"PCB_B_JST_{i}", (x, y, z + s[2] / 2), s,
                     "conn_white", "JST_CONNECTOR", "A", board, bevel=0.5,
                     rot_z=rz))
        P.append(box(f"PCB_B_JST_{i}_SLOT", (x, y, z + s[2] + 0.1),
                     (s[0] * 0.8, 1.8, 0.5), "conn_dark", "JST_SLOT", "A",
                     board, bevel=0.1, rot_z=rz))

    # measured inductors: 3R3 (10x7.5 @ (9.9,-4.75)), 6R8, plus one more
    P.append(box("PCB_B_INDUCTOR_3R3", (9.9, -4.75, z + 2.1), (10, 7.5, 4.2),
                 "inductor", "POWER_INDUCTOR_3R3", "A", board, bevel=0.3,
                 rot_z=-0.15))
    P.append(box("PCB_B_3R3_MARK", (9.9, -4.75, z + 4.3), (4.5, 3, 0.15),
                 "label", "INDUCTOR_MARK", "B", board, bevel=0.05,
                 rot_z=-0.15))
    P.append(box("PCB_B_INDUCTOR_6R8", (-2.2, -9.6, z + 1.7), (6.5, 4, 3.4),
                 "inductor", "POWER_INDUCTOR_6R8", "A", board, bevel=0.25))
    P.append(box("PCB_B_INDUCTOR_3", (-3.2, -23, z + 1.6), (5.5, 3.5, 3.2),
                 "inductor", "POWER_INDUCTOR", "B", board, bevel=0.25))

    # Level B ICs with pins
    ics = [(-16, 8, 7, 7, 2.2, 0), (-4, 20, 6, 5, 2.0, 0),
           (16, 14, 7, 6, 2.2, 0.3), (-18, -14, 6, 5, 2.0, -0.2),
           (12, -16, 8, 6, 2.2, 0), (-8, -18, 6, 5, 2.0, 0),
           (20, 2, 5, 5, 2.0, 0)]
    for i, (x, y, w_, h_, t, r) in enumerate(ics):
        P.append(ic_with_pins(f"PCB_B_IC_{i:02d}", x, y, w_, h_, t, board, r))

    for i in range(6):
        P.append(box(f"PCB_B_TANT_{i}", (-14 + i * 4.5, -18, z + 0.9),
                     (3.4, 2.0, 1.8), "tantalum", "TANT_CAP_ROW", "B",
                     board, bevel=0.08))

    # Level C passives
    for i in range(120):
        x, y = random.uniform(-27, 27), random.uniform(-24, 24)
        if (x + 0.97) ** 2 + (y + 0.16) ** 2 < 30:
            continue
        if not _in_poly(BMESH["b"]["outline"], x, y) or \
                _min_edge_dist(BMESH["b"]["outline"], x, y) < 1.6:
            continue
        P.append(box(f"PCB_B_SMT_{i:02d}", (x, y, z + 0.35),
                     (random.uniform(1.0, 1.8), random.uniform(0.6, 1.1),
                      0.7), "ic", "SMT_PASSIVE", "C", board, bevel=0.04))

    # back: one red-top bulk cap + a few passives
    bz = -TOP_Z
    P.append(cyl("PCB_B_B_CAP", (2, -14, bz - 3.2), 4.0, 6.4, "cap_silver",
                 "BULK_CAP", "A", board))
    P.append(cyl("PCB_B_B_CAP_TOP", (2, -14, bz - 6.5), 3.8, 0.4, "cap_red",
                 "BULK_CAP_TOP", "A", board))
    for i in range(6):
        x, y = random.uniform(-22, 22), random.uniform(-20, 20)
        P.append(box(f"PCB_B_B_SMT_{i}", (x, y, bz - 0.3),
                     (1.6, 1.0, 0.6), "ic", "BACK_PASSIVE", "C", board,
                     bevel=0.04))
    return P

# ---------------------------------------------------------------------------
# Scene
# ---------------------------------------------------------------------------


def area_light(name, loc, energy, size, color):
    ld = bpy.data.lights.new(name, "AREA")
    ld.energy, ld.shape, ld.size, ld.color = energy, "DISK", size, color
    o = bpy.data.objects.new(name, ld)
    bpy.context.scene.collection.objects.link(o)
    o.location = loc
    o.rotation_euler = (Vector((0, 0, 0)) - o.location).to_track_quat(
        "-Z", "Y").to_euler()
    return o


def build_scene():
    scn = bpy.context.scene
    scn.render.engine = "BLENDER_EEVEE"
    scn.render.resolution_x, scn.render.resolution_y = 1920, 1080
    scn.render.resolution_percentage = 100
    scn.render.image_settings.file_format = "PNG"
    scn.view_settings.exposure = 3.2
    scn.unit_settings.system = "METRIC"
    scn.unit_settings.scale_length = 0.001

    world = bpy.data.worlds.new("WORLD_V4")
    world.use_nodes = True
    scn.world = world
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Strength"].default_value = 0.7
    bg.inputs["Color"].default_value = (0.09, 0.10, 0.12, 1)

    area_light("V4_KEY", (140, -160, 230), 58000, 180, (1.0, 0.96, 0.90))
    area_light("V4_FILL", (-160, -60, 150), 28000, 160, (0.88, 0.93, 1.0))
    area_light("V4_RIM", (40, 170, 200), 40000, 150, (1.0, 0.92, 0.82))

    bpy.ops.mesh.primitive_plane_add(size=4000, location=(0, 0, -40))
    fl = bpy.context.object
    fl.name = "V4_FLOOR"
    fl.data.materials.append(_mat("MAT_v4_floor", (0.035, 0.038, 0.045), 0.92))

    for name, loc in [("SEM_PCB_A_MAIN_SYSTEM_BOARD", (0, 0, 0)),
                      ("SEM_PCB_B_AUXILIARY_INTERFACE_BOARD", (0, -80, 0)),
                      ("SEM_PCB_RIBBON_CABLE", (60, -13, 4))]:
        e = bpy.data.objects.new(name, None)
        e.empty_display_type = "SPHERE"
        e.empty_display_size = 6
        e.location = loc
        bpy.context.scene.collection.objects.link(e)


def build_cameras():
    specs = [
        ("CAM_V4_OVERVIEW", (150, -235, 235), (5, -40, -4), 58),
        ("CAM_V4_ARCH", (140, -215, 150), (5, -40, 18), 55),
        ("CAM_V4_A_FRONT", (74, -156, 195), (2, 0, 0), 60),
        ("CAM_V4_A_BACK", (74, -156, 195), (2, 0, 0), 60),
        ("CAM_V4_B_FRONT", (49, -114, 138), (0, 0, 0), 60),
        ("CAM_V4_B_BACK", (49, -114, 138), (0, 0, 0), 60),
        ("CAM_V4_A_CLOSE", (52, -52, 105), (2, 12, 3), 68),
        ("CAM_V4_B_CLOSE", (48, -54, 92), (0, -4, 2), 68),
        # photo-matched top-down views for overlay validation
        ("CAM_V4_A_TOP", (0, 0, 320), (0, 0, 0), 52),
        ("CAM_V4_B_TOP", (0, 0, 240), (0, 0, 0), 52),
    ]
    for name, loc, tgt, lens in specs:
        cd = bpy.data.cameras.new(name)
        cd.lens = lens
        cd.sensor_width = 36
        cd.clip_end = 100000
        cd.dof.use_dof = True
        cd.dof.aperture_fstop = 7.1
        o = bpy.data.objects.new(name, cd)
        bpy.context.scene.collection.objects.link(o)
        o.location = loc
        o.rotation_euler = (Vector(tgt) - o.location).to_track_quat(
            "-Z", "Y").to_euler()
        cd.dof.focus_distance = (Vector(tgt) - o.location).length


def organize():
    pres = bpy.data.collections.new("PRESENTATION_PCB_V4")
    rig = bpy.data.collections.new("RIG_V4")
    scn = bpy.context.scene
    scn.collection.children.link(pres)
    scn.collection.children.link(rig)
    for o in list(scn.collection.objects):
        tgt = rig if (o.type in ("LIGHT", "CAMERA")
                      or o.name == "V4_FLOOR") else pres
        scn.collection.objects.unlink(o)
        tgt.objects.link(o)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=ROOT)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:]
                             if "--" in sys.argv else [])

    bpy.ops.wm.read_factory_settings(use_empty=True)
    build_materials()

    tex_a_f = load_texture("TEX4_pcb_a_front")
    tex_a_b = load_texture("TEX4_pcb_a_back")
    tex_b_f = load_texture("TEX4_pcb_b_front")
    tex_b_b = load_texture("TEX4_pcb_b_back")

    mf_a = soldermask_material("MAT4_pcb_a_front", tex_a_f)
    mb_a = soldermask_material("MAT4_pcb_a_back", tex_a_b)
    mf_b = soldermask_material("MAT4_pcb_b_front", tex_b_f)
    mb_b = soldermask_material("MAT4_pcb_b_back", tex_b_b)

    board_a = build_board("PCB_A_MAIN_SYSTEM_BOARD", "a", mf_a, mb_a)
    pa = build_pcb_a(board_a)

    board_b = build_board("PCB_B_AUXILIARY_INTERFACE_BOARD", "b",
                          mf_b, mb_b)
    pb = build_pcb_b(board_b)
    board_b.location = (0, -80, 0)

    build_scene()
    build_cameras()
    organize()
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT_BLEND))
    print(json.dumps({"blend": str(OUT_BLEND),
                      "a_outline_pts": len(A_OUTLINE),
                      "b_outline_pts": len(B_OUTLINE),
                      "a_components": len(pa), "b_components": len(pb)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
