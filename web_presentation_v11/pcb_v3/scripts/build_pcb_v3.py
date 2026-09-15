"""Build pcb_presentation_v3.blend — photo-referenced PCB presentation asset.

Reference lock (real photos, not the earlier CAD renders):
  reference/photo_pcb_a_front.jpg  PCB-A front  (CLMP module, ceramic antenna,
                                   shield area + coil, white ribbon right)
  reference/photo_pcb_a_back.jpg   PCB-A back   (bare, 2 BGA via grids, shield
                                   tab + wire loop, white ribbon left)
  reference/photo_pcb_b_front.jpg  PCB-B front  (7 white JST, 3R3 inductor,
                                   dense small ICs, centre hole)
  reference/photo_pcb_b_back.jpg   PCB-B back   (bare, one red-top cap)

Conventions: board lies in XY, +Z = front face, thickness 1.6mm.
Units: mm (consistent with the project pipeline).
"""

from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    import bpy  # type: ignore
    from mathutils import Vector  # type: ignore
except ImportError:  # pragma: no cover
    bpy = None  # type: ignore

OUT_BLEND = "web_presentation_v11/pcb_v3/pcb_presentation_v3.blend"
TEX_DIR = "web_presentation_v11/pcb_v3/textures"

random.seed(20260915)

# --------------------------------------------------------------------------
# Board outlines (mm), traced from the real photos. +x right, +y "top".
# --------------------------------------------------------------------------

# PCB-A: irregular ~104x88, chamfered corners, double notch right edge,
# notch left edge, 6 plated mounting holes, 2 large interior holes.
PCB_A_OUTLINE = [
    (-46, -40), (-34, -44), (34, -44), (46, -38),   # bottom edge + chamfers
    (52, -28), (52, -14),                          # lower right edge
    (44, -6), (52, 2),                             # notch 1 (lower-right)
    (54, 12), (48, 22),                            # notch 2 exit (upper-right)
    (50, 32), (40, 42),                            # right edge upper + chamfer
    (26, 44), (-26, 44), (-40, 38),                # top edge + chamfer
    (-50, 28), (-52, 14), (-46, 4),                # left edge upper + notch
    (-52, -8), (-50, -28),                         # left edge lower
]

PCB_A_HOLES = [
    (-40, 32, 2.3), (40, 33, 2.3),                 # top mounting holes
    (-45, -4, 2.3), (47, 14, 2.3),                 # side mounting holes
    (-38, -33, 2.3), (40, -30, 2.3),               # bottom mounting holes
    (-20, -2, 5.2), (24, -6, 5.2),                 # two large interior holes
    (-6, 37, 1.9),                                 # small hole near top edge
]

# PCB-B: irregular ~62x56, chamfered corners, edge notches, corner holes,
# one centre hole.
PCB_B_OUTLINE = [
    (-24, -26), (-8, -28), (20, -28), (28, -20),   # bottom edge + chamfers
    (30, -8), (28, 4),                             # right edge lower
    (24, 12), (30, 18), (24, 26),                  # right notch + upper right
    (10, 28), (-2, 26), (-16, 28), (-26, 22),      # top edge with small dip
    (-30, 12), (-28, -6), (-26, -18),              # left edge
]

PCB_B_HOLES = [
    (-24, 20, 2.1), (23, 21, 2.1),                 # top corners
    (-24, -20, 2.1), (24, -19, 2.1),               # bottom corners
    (-27, 0, 2.1),                                 # left edge hole
    (0, -1, 4.2),                                  # centre hole
]

BOARD_THICKNESS = 1.6
TOP_Z = BOARD_THICKNESS / 2.0

# --------------------------------------------------------------------------
# Material library
# --------------------------------------------------------------------------


def _mat(name: str, base, rough: float, metal: float = 0.0,
         coat: float = 0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*base, 1.0)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    if "Coat Weight" in bsdf.inputs:
        bsdf.inputs["Coat Weight"].default_value = coat
    return m


MATS = {}


def build_materials():
    MATS.update({
        "edge":        _mat("MAT_pcb_edge",        (0.30, 0.42, 0.26), 0.55),
        "ic":          _mat("MAT_ic_black",        (0.012, 0.013, 0.016), 0.34, 0.15),
        "module":      _mat("MAT_module_black",    (0.020, 0.021, 0.024), 0.30, 0.10),
        "conn_white":  _mat("MAT_connector_white", (0.72, 0.70, 0.65), 0.55),
        "conn_dark":   _mat("MAT_connector_dark",  (0.028, 0.030, 0.034), 0.40, 0.30),
        "inductor":    _mat("MAT_inductor_gray",   (0.28, 0.28, 0.29), 0.45, 0.10),
        "shield":      _mat("MAT_shield_metal",    (0.48, 0.50, 0.54), 0.32, 0.90),
        "cap_silver":  _mat("MAT_cap_silver",      (0.46, 0.48, 0.52), 0.38, 0.85),
        "cap_red":     _mat("MAT_cap_red",         (0.45, 0.05, 0.04), 0.42),
        "ceramic":     _mat("MAT_ceramic_white",   (0.82, 0.77, 0.66), 0.50),
        "cable":       _mat("MAT_cable_white",     (0.78, 0.77, 0.74), 0.60),
        "gold":        _mat("MAT_gold_pad",        (0.55, 0.38, 0.10), 0.32, 0.90),
        "label":       _mat("MAT_label_white",     (0.80, 0.79, 0.76), 0.65),
        "tantalum":    _mat("MAT_tantalum",        (0.42, 0.22, 0.08), 0.45),
        "coil":        _mat("MAT_coil_silver",     (0.62, 0.63, 0.65), 0.28, 0.92),
        "ferrite":     _mat("MAT_ferrite_dark",    (0.05, 0.05, 0.06), 0.55),
        "daughter":    _mat("MAT_daughter_green",  (0.045, 0.14, 0.06), 0.42, 0.15),
    })


def soldermask_material(name: str, tex_image) -> object:
    """Green soldermask driven by a baked texture (colour + roughness + bump)."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = tex_image
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    # subtle roughness variation from texture luminance
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.55, 0.55, 0.55, 1)
    ramp.color_ramp.elements[1].color = (0.35, 0.35, 0.35, 1)
    nt.links.new(tex.outputs["Color"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Roughness"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.15
    bump.inputs["Distance"].default_value = 0.05
    nt.links.new(tex.outputs["Color"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return m

# --------------------------------------------------------------------------
# Texture baking — draw into a bytearray, then into a bpy image.
# Coordinates: texture space 0..1 == board bbox (x_min..x_max, y_min..y_max).
# --------------------------------------------------------------------------


class TexBuf:
    def __init__(self, w: int, h: int, base=(28, 88, 34)):
        self.w, self.h = w, h
        self.data = bytearray(base * (w * h))

    def px(self, x: int, y: int, c):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            self.data[i:i + 3] = bytes(c)

    def rect(self, x0, y0, x1, y1, c):
        x0, x1 = max(0, int(x0)), min(self.w, int(x1))
        y0, y1 = max(0, int(y0)), min(self.h, int(y1))
        row = bytes(c) * max(0, x1 - x0)
        for y in range(y0, y1):
            i = (y * self.w + x0) * 3
            self.data[i:i + len(row)] = row

    def disc(self, cx, cy, r, c):
        r = int(r)
        for dy in range(-r, r + 1):
            span = int(math.sqrt(max(0, r * r - dy * dy)))
            self.rect(cx - span, cy + dy, cx + span + 1, cy + dy + 1, c)

    def ring(self, cx, cy, r, w_, c):
        for dy in range(-int(r) - 1, int(r) + 2):
            for dx in range(-int(r) - 1, int(r) + 2):
                d = math.sqrt(dx * dx + dy * dy)
                if r - w_ <= d <= r:
                    self.px(cx + dx, cy + dy, c)

    def line(self, x0, y0, x1, y1, c, w_=1):
        dx, dy = x1 - x0, y1 - y0
        n = max(abs(dx), abs(dy), 1)
        for i in range(int(n) + 1):
            x, y = x0 + dx * i / n, y0 + dy * i / n
            self.rect(x - w_ / 2, y - w_ / 2, x + w_ / 2 + 1, y + w_ / 2 + 1, c)

    def to_image(self, name: str, path: Path):
        img = bpy.data.images.new(name, width=self.w, height=self.h, alpha=False)
        flat = []
        ap = flat.append
        d = self.data
        for i in range(0, len(d), 3):
            ap(d[i] / 255.0)
            ap(d[i + 1] / 255.0)
            ap(d[i + 2] / 255.0)
            ap(1.0)
        img.pixels.foreach_set(flat)
        img.filepath_raw = str(path)
        img.file_format = "PNG"
        img.save()
        img.pack()
        return img


def bake_pcb_texture(name: str, board_w: float, board_h: float,
                     holes, side: str, res: int = 2048) -> object:
    """Procedural soldermask texture: green base + noise, traces, vias,
    gold pads, silkscreen marks. `side` selects front/back recipes."""
    w = res
    h = int(res * board_h / board_w)
    tb = TexBuf(w, h)
    px_per_mm = w / board_w

    # soldermask base with subtle tonal noise
    for y in range(0, h, 2):
        for x in range(0, w, 2):
            n = random.random()
            g = 88 + int(n * 26)
            r = 26 + int(n * 10)
            b = 34 + int(n * 8)
            tb.rect(x, y, x + 2, y + 2, (r, g, b))

    def mx(x_mm):
        return int((x_mm + board_w / 2) * px_per_mm)

    def my(y_mm):
        return int((y_mm + board_h / 2) * px_per_mm)

    # traces — mostly Manhattan (0/90 deg) with occasional 45-deg jogs,
    # subtle tonal difference vs. soldermask; organized, not chaotic.
    n_traces = 1500 if side == "front" else 900
    for _ in range(n_traces):
        x, y = random.randint(0, w), random.randint(0, h)
        ang = random.choice([0.0, math.pi / 2, 0.0, math.pi / 2,
                             math.pi / 4, -math.pi / 4])
        seg = random.randint(40, 220)
        c = (23, 80, 29) if side == "front" else (30, 92, 37)
        lw = max(1, int(px_per_mm * 0.10))
        x2 = x + int(seg * math.cos(ang))
        y2 = y + int(seg * math.sin(ang))
        tb.line(x, y, x2, y2, c, lw)
        if ang in (0.0, math.pi / 2) and random.random() < 0.35:
            # short perpendicular continuation — looks like bus routing
            seg2 = random.randint(20, 80)
            ang2 = ang + math.pi / 2
            tb.line(x2, y2, x2 + int(seg2 * math.cos(ang2)),
                    y2 + int(seg2 * math.sin(ang2)), c, lw)

    # via dots — small dark holes with a thin annular ring
    for _ in range(1100):
        x, y = random.randint(0, w), random.randint(0, h)
        r = max(1, int(px_per_mm * 0.16))
        tb.disc(x, y, r + 1, (70, 92, 58))
        tb.disc(x, y, r, (18, 48, 20))

    # gold pads — short neat rows near board edges and connector zones
    n_pad_rows = 26 if side == "front" else 10
    for _ in range(n_pad_rows):
        x = random.randint(0, w - 60)
        y = random.choice([random.randint(0, int(h * 0.15)),
                           random.randint(int(h * 0.85), h)])
        n = random.randint(4, 10)
        for k in range(n):
            tb.rect(x + k * int(px_per_mm * 1.2), y,
                    x + k * int(px_per_mm * 1.2) + int(px_per_mm * 0.8),
                    y + int(px_per_mm * 1.8), (150, 118, 52))

    # silkscreen: white component outlines + refdes-like small bars
    n_silk = 170 if side == "front" else 60
    for _ in range(n_silk):
        x, y = random.randint(0, w - 30), random.randint(0, h - 20)
        ww = random.randint(int(px_per_mm * 1.5), int(px_per_mm * 4))
        hh = random.randint(int(px_per_mm * 1.2), int(px_per_mm * 3))
        if random.random() < 0.6:
            # component outline (open rectangle)
            c = (195, 200, 190)
            lw = max(1, int(px_per_mm * 0.08))
            tb.rect(x, y, x + ww, y + lw, c)
            tb.rect(x, y + hh - lw, x + ww, y + hh, c)
            tb.rect(x, y, x + lw, y + hh, c)
            tb.rect(x + ww - lw, y, x + ww, y + hh, c)
        else:
            tb.rect(x, y, x + ww, y + max(1, int(px_per_mm * 0.28)),
                    (195, 200, 190))

    # passive speckle — dense tiny light dots (0402 pads seen through mask)
    if side == "front":
        for _ in range(2400):
            x, y = random.randint(0, w), random.randint(0, h)
            tb.rect(x, y, x + 2, y + 1, (60, 110, 58))

    # plated mounting-hole rings
    for hx, hy, hr in holes:
        cx, cy = mx(hx), my(hy)
        tb.ring(cx, cy, int(hr * px_per_mm) + int(0.9 * px_per_mm),
                int(0.8 * px_per_mm), (170, 175, 168))

    path = PROJECT_ROOT / TEX_DIR
    path.mkdir(parents=True, exist_ok=True)
    return tb.to_image(name, path / f"{name}.png")

# --------------------------------------------------------------------------
# Board construction: 2D curve outline + hole splines, extruded, to mesh.
# --------------------------------------------------------------------------


def build_board(name: str, outline, holes, mat_front, mat_back) -> object:
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "2D"
    cu.fill_mode = "BOTH"
    cu.resolution_u = 2
    cu.extrude = BOARD_THICKNESS / 2.0

    spl = cu.splines.new("POLY")
    spl.points.add(len(outline) - 1)
    for p, (x, y) in zip(spl.points, outline):
        p.co = (x, y, 0.0, 1.0)
    spl.use_cyclic_u = True

    for hx, hy, hr in holes:
        s = cu.splines.new("POLY")
        n = 14
        s.points.add(n - 1)
        for i, p in enumerate(s.points):
            a = 2 * math.pi * i / n
            p.co = (hx + hr * math.cos(a), hy + hr * math.sin(a), 0.0, 1.0)
        s.use_cyclic_u = True

    obj = bpy.data.objects.new(name, cu)
    bpy.context.scene.collection.objects.link(obj)
    cu.materials.append(mat_front)
    cu.materials.append(mat_back)
    cu.materials.append(MATS["edge"])

    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.convert(target="MESH")
    me = obj.data

    xs = [p[0] for p in outline]
    ys = [p[1] for p in outline]
    bw, bh = max(xs) - min(xs), max(ys) - min(ys)
    cx0, cy0 = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2

    # material index per face by normal; planar UVs on ±Z faces
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
            uv.data[li].uv = ((co.x - cx0) / bw + 0.5, (co.y - cy0) / bh + 0.5)

    obj["presentation"] = "PCB_V3"
    obj["layer"] = "PRESENTATION"
    return obj

# --------------------------------------------------------------------------
# Component helpers
# --------------------------------------------------------------------------


def _assign(obj, mat_key: str, semantic: str, level: str, parent=None):
    if obj.data and hasattr(obj.data, "materials"):
        obj.data.materials.append(MATS[mat_key])
    obj["semantic"] = semantic
    obj["level"] = level
    obj["layer"] = "PRESENTATION"
    obj["presentation"] = "PCB_V3"
    if parent:
        obj.parent = parent
    return obj


def box(name, loc, size, mat_key, semantic, level, parent, bevel=0.25,
        rot_z=0.0):
    bpy.ops.mesh.primitive_cube_add(location=loc)
    o = bpy.context.object
    o.name = name
    o.scale = (size[0] / 2, size[1] / 2, size[2] / 2)
    bpy.ops.object.transform_apply(scale=True)
    if rot_z:
        o.rotation_euler.z = rot_z
    if bevel:
        mod = o.modifiers.new("bev", "BEVEL")
        mod.width = bevel
        mod.segments = 2
        bpy.ops.object.modifier_apply(modifier=mod.name)
    for p in o.data.polygons:
        p.use_smooth = True
    return _assign(o, mat_key, semantic, level, parent)


def cyl(name, loc, radius, depth, mat_key, semantic, level, parent,
        verts=24):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=radius,
                                        depth=depth, location=loc)
    o = bpy.context.object
    o.name = name
    for p in o.data.polygons:
        p.use_smooth = True
    return _assign(o, mat_key, semantic, level, parent)


def torus(name, loc, major, minor, mat_key, semantic, level, parent):
    bpy.ops.mesh.primitive_torus_add(major_radius=major, minor_radius=minor,
                                     major_segments=32, minor_segments=10,
                                     location=loc)
    o = bpy.context.object
    o.name = name
    for p in o.data.polygons:
        p.use_smooth = True
    return _assign(o, mat_key, semantic, level, parent)


def cable_curve(name, pts, radius, mat_key, semantic, parent):
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
    return _assign(obj, mat_key, semantic, "A", parent)

# --------------------------------------------------------------------------
# PCB-A population (positions from photo_pcb_a_front / _back)
# --------------------------------------------------------------------------


def build_pcb_a(board) -> list:
    parts = []
    z = TOP_Z

    # --- Level A: CLMP main compute module (big black rect, top-centre) ---
    mod = box("PCB_A_MAIN_MODULE", (0, 16, z + 2.6), (34, 27, 5.2), "module",
              "MAIN_COMPUTE_MODULE", "A", board, bevel=0.6)
    parts.append(mod)
    # two die areas + label sticker on the module top
    parts.append(box("PCB_A_MODULE_DIE_1", (-7, 15, z + 5.4), (10, 9, 0.8),
                     "ic", "MODULE_DIE", "A", board, bevel=0.1))
    parts.append(box("PCB_A_MODULE_DIE_2", (7, 11, z + 5.4), (9, 7, 0.8),
                     "ic", "MODULE_DIE", "A", board, bevel=0.1))
    parts.append(box("PCB_A_MODULE_LABEL", (4, 22, z + 5.35), (14, 5, 0.3),
                     "label", "MODULE_LABEL", "A", board, bevel=0.05))

    # --- coax antenna wire from module up-right (white coax + plug) ---
    parts.append(cable_curve("PCB_A_COAX_ANTENNA",
                             [(10, 28, z + 4), (16, 34, z + 5),
                              (24, 38, z + 4), (34, 39, z + 2)],
                             0.7, "cable", "COAX_ANTENNA_LEAD", board))
    parts.append(box("PCB_A_COAX_PLUG", (35, 39, z + 1.4), (5, 4, 2.8),
                     "conn_white", "COAX_PLUG", "A", board, bevel=0.4))

    # --- ceramic patch antenna module (white/tan square, lower-left) ---
    ant = box("PCB_A_CERAMIC_ANTENNA", (-33, -18, z + 2.2), (14, 14, 4.4),
              "ceramic", "CERAMIC_PATCH_ANTENNA", "A", board, bevel=0.5)
    parts.append(ant)
    parts.append(cyl("PCB_A_ANT_DOT", (-33, -18, z + 4.45), 1.6, 0.3,
                     "cap_silver", "ANTENNA_FEED", "A", board))

    # --- shielded/daughter area bottom-centre (raised GREEN zone + coil) ---
    # kept clear of the right large hole at (24,-6)
    sh = box("PCB_A_SHIELD_ZONE", (8, -19, z + 1.6), (22, 26, 3.2),
             "daughter", "SHIELDED_ZONE", "A", board, bevel=0.4)
    parts.append(sh)
    parts.append(cyl("PCB_A_COIL_BASE", (8, -20, z + 3.6), 6.0, 1.0,
                     "coil", "POWER_COIL", "A", board))
    for i, r in enumerate((5.2, 3.8, 2.4)):
        parts.append(torus(f"PCB_A_COIL_{i}", (8, -20, z + 4.2 + i * 0.7),
                           r, 0.55, "coil", "POWER_COIL", "A", board))
    parts.append(box("PCB_A_SHIELD_GRAY", (0, -11, z + 3.4), (7, 6, 1.4),
                     "inductor", "SHIELD_COMPONENT", "A", board, bevel=0.15))

    # --- white ribbon cable exiting right edge ---
    parts.append(cable_curve("PCB_A_RIBBON",
                             [(50, 6, z + 1), (56, 7, z + 1.6),
                              (62, 5, z + 1.2)],
                             2.2, "cable", "RIBBON_CABLE", board))
    parts.append(box("PCB_A_RIBBON_PLUG", (65, 4, z + 2.2), (9, 6, 4),
                     "conn_white", "RIBBON_PLUG", "A", board, bevel=0.5,
                     rot_z=-0.25))

    # --- small white module top-left ---
    parts.append(box("PCB_A_RF_MODULE", (-38, 26, z + 1.8), (9, 10, 3.6),
                     "ceramic", "SMALL_RF_MODULE", "A", board, bevel=0.3))
    parts.append(cable_curve("PCB_A_RF_STUB",
                             [(-38, 31, z + 2), (-40, 35, z + 3),
                              (-44, 37, z + 2)], 0.5, "cable",
                             "RF_STUB_LEAD", board))

    # --- Level B: mid ICs, inductors, tantalums, crystal ---
    ic_specs = [
        ((-33, 8, 0), (8, 5, 2.2)), ((-20, 24, 0), (7, 7, 2.4)),
        ((26, 28, 0), (9, 6, 2.2)), ((-36, -6, 0), (7, 5, 2.0)),
        ((30, -20, 0), (8, 6, 2.2)), ((-12, -28, 0), (7, 5, 2.0)),
        ((34, 6, 0), (6, 5, 2.0)), ((-28, 34, 0), (6, 5, 2.0)),
        ((18, 34, 0), (6, 4, 1.8)), ((-8, -36, 0), (7, 4, 1.8)),
    ]
    for i, ((x, y, _), s) in enumerate(ic_specs):
        parts.append(box(f"PCB_A_IC_{i:02d}", (x, y, z + s[2] / 2), s,
                         "ic", "MID_IC", "B", board, bevel=0.15))

    for i, (x, y) in enumerate([(-14, -14), (30, 18), (40, -12)]):
        parts.append(box(f"PCB_A_IND_{i}", (x, y, z + 1.6), (5, 4, 3.2),
                         "inductor", "POWER_INDUCTOR", "B", board, bevel=0.2))

    for i, (x, y) in enumerate([(-16, 30), (16, -32), (42, 22), (-42, -14)]):
        parts.append(box(f"PCB_A_TANT_{i}", (x, y, z + 0.9), (3.2, 1.8, 1.8),
                         "tantalum", "TANT_CAP", "B", board, bevel=0.1))

    parts.append(box("PCB_A_CRYSTAL", (-4, -22, z + 0.9), (5, 3.2, 1.8),
                     "cap_silver", "CRYSTAL", "B", board, bevel=0.15))

    # small dark connectors on board edges
    for i, (x, y, r) in enumerate([(48, -16, 0.3), (-48, 18, 1.2)]):
        parts.append(box(f"PCB_A_DCONN_{i}", (x, y, z + 1.4), (6, 4, 2.8),
                         "conn_dark", "EDGE_CONNECTOR", "B", board,
                         bevel=0.3, rot_z=r))

    # Level C: dense passives — scattered + organized rows near ICs
    def _clear_a(x, y):
        if (x + 20) ** 2 + (y + 2) ** 2 < 90 or (x - 24) ** 2 + (y + 6) ** 2 < 90:
            return False
        if -19 < x < 19 and 1 < y < 31:
            return False
        if -3 < x < 19 and -33 < y < -6:
            return False
        return True

    for i in range(120):
        x = random.uniform(-44, 44)
        y = random.uniform(-40, 40)
        if not _clear_a(x, y):
            continue
        parts.append(box(f"PCB_A_SMT_{i:02d}", (x, y, z + 0.45),
                         (random.uniform(1.2, 2.4), random.uniform(0.8, 1.4),
                          0.9), "ic", "SMT_PASSIVE", "C", board, bevel=0.06))
    # neat rows — the "organized" look of real layouts
    for row_y in (-37, -34.5, 38.5, 41):
        for k in range(10):
            x = -36 + k * 4.0
            if not _clear_a(x, row_y):
                continue
            parts.append(box(f"PCB_A_ROW_{row_y}_{k}", (x, row_y, z + 0.4),
                             (1.6, 1.0, 0.8), "ic", "SMT_PASSIVE_ROW", "C",
                             board, bevel=0.05))

    # --- back side components (photo 2: sparse) ---
    bz = -TOP_Z
    parts.append(box("PCB_A_B_SHIELD_TAB", (30, -22, bz - 0.5), (11, 7, 1.0),
                     "shield", "BACK_GROUND_TAB", "A", board, bevel=0.2))
    parts.append(cable_curve("PCB_A_B_GROUND_LOOP",
                             [(32, -20, bz - 1), (40, -18, bz - 2),
                              (48, -12, bz - 1), (52, -6, bz - 0.5)],
                             0.45, "cap_silver", "GROUND_WIRE_LOOP", board))
    for i, (x, y) in enumerate([(-44, 12), (-44, 6), (-44, 0)]):
        parts.append(box(f"PCB_A_B_WCONN_{i}", (x, y, bz - 1.4), (4, 5, 2.8),
                         "conn_white", "BACK_EDGE_CONN", "A", board,
                         bevel=0.3))
    parts.append(box("PCB_A_B_SN_LABEL", (0, 36, bz - 0.15), (20, 4, 0.3),
                     "label", "SN_LABEL", "B", board, bevel=0.05))
    for i in range(10):
        x = random.uniform(-40, 40)
        y = random.uniform(-36, 36)
        if (x + 20) ** 2 + (y + 2) ** 2 < 70 or (x - 24) ** 2 + (y + 6) ** 2 < 70:
            continue
        parts.append(box(f"PCB_A_B_SMT_{i:02d}", (x, y, bz - 0.4),
                         (random.uniform(1.4, 3.0), random.uniform(1.0, 1.6),
                          0.8), "ic", "BACK_PASSIVE", "C", board, bevel=0.05))

    return parts

# --------------------------------------------------------------------------
# PCB-B population (positions from photo_pcb_b_front / _back)
# --------------------------------------------------------------------------


def build_pcb_b(board) -> list:
    parts = []
    z = TOP_Z

    # Level A: 7 white JST connectors around the perimeter
    jst = [
        ("PCB_B_JST_TOP",   (0, 23, z + 2.6),   (26, 6, 5.2), 0.0),
        ("PCB_B_JST_TR",    (21, 21, z + 2.4),  (8, 6, 4.8), -0.6),
        ("PCB_B_JST_L1",    (-25, 9, z + 2.4),  (9, 6, 4.8), 0.5),
        ("PCB_B_JST_L2",    (-22, -7, z + 2.6), (18, 6, 5.2), -0.5),
        ("PCB_B_JST_R",     (26, -3, z + 2.4),  (8, 6, 4.8), -0.9),
        ("PCB_B_JST_B1",    (-14, -23, z + 2.4), (12, 6, 4.8), 0.4),
        ("PCB_B_JST_B2",    (19, -22, z + 2.4), (8, 6, 4.8), 0.0),
    ]
    for name, loc, size, rz in jst:
        o = box(name, loc, size, "conn_white", "JST_CONNECTOR", "A", board,
                bevel=0.5, rot_z=rz)
        # pin-slot shading: thin dark groove on top
        parts.append(o)
        parts.append(box(name + "_SLOT",
                         (loc[0], loc[1], loc[2] + size[2] / 2),
                         (size[0] * 0.8, 1.6, 0.4), "conn_dark",
                         "JST_SLOT", "A", board, bevel=0.1, rot_z=rz))

    # centre: gray 3R3 power inductor + adjacent blocks
    ind = box("PCB_B_INDUCTOR_3R3", (8, 2, z + 2.2), (8, 8, 4.4),
              "inductor", "POWER_INDUCTOR_3R3", "A", board, bevel=0.3)
    parts.append(ind)
    # printed marking strip on top (the photo shows "3R3" text)
    parts.append(box("PCB_B_INDUCTOR_MARK", (8, 2, z + 4.45), (4.5, 3.0, 0.15),
                     "label", "INDUCTOR_MARKING", "B", board, bevel=0.05))
    parts.append(box("PCB_B_INDUCTOR_2", (-9, -12, z + 1.9), (5, 5, 3.8),
                     "inductor", "POWER_INDUCTOR", "A", board, bevel=0.25))

    # Level B: mid ICs scattered
    ic_specs = [
        ((-14, 12), (7, 7, 2.2)), ((-4, 16), (6, 5, 2.0)),
        ((16, 10), (7, 6, 2.2)), ((-17, -3), (6, 5, 2.0)),
        ((13, -10), (8, 6, 2.2)), ((-6, -18), (6, 5, 2.0)),
        ((2, -12), (5, 5, 2.0)), ((-12, 24), (5, 4, 1.8)),
    ]
    for i, ((x, y), s) in enumerate(ic_specs):
        parts.append(box(f"PCB_B_IC_{i:02d}", (x, y, z + s[2] / 2), s,
                         "ic", "MID_IC", "B", board, bevel=0.12))

    # row of brown tantalum caps bottom-centre (photo shows a row)
    for i in range(5):
        parts.append(box(f"PCB_B_TANT_{i}", (-2 + i * 4.5, -17, z + 0.9),
                         (3.4, 2.0, 1.8), "tantalum", "TANT_CAP_ROW", "B",
                         board, bevel=0.08))

    # Level C: dense tiny passives (photo shows high density)
    for i in range(130):
        x = random.uniform(-26, 26)
        y = random.uniform(-25, 25)
        if x * x + (y + 1) ** 2 < 25:  # centre hole keep-out
            continue
        parts.append(box(f"PCB_B_SMT_{i:02d}", (x, y, z + 0.4),
                         (random.uniform(1.0, 2.0), random.uniform(0.6, 1.2),
                          0.8), "ic", "SMT_PASSIVE", "C", board, bevel=0.05))
    for row_y in (-25.5, 25.5):
        for k in range(12):
            x = -22 + k * 4.0
            if x * x + (row_y + 1) ** 2 < 25:
                continue
            parts.append(box(f"PCB_B_ROW_{row_y}_{k}", (x, row_y, z + 0.35),
                             (1.5, 0.9, 0.7), "ic", "SMT_PASSIVE_ROW", "C",
                             board, bevel=0.04))

    # back: almost bare — one red-top electrolytic cap bottom-centre
    bz = -TOP_Z
    parts.append(cyl("PCB_B_B_CAP", (2, -14, bz - 3.2), 4.0, 6.4,
                     "cap_silver", "BULK_CAP", "A", board))
    parts.append(cyl("PCB_B_B_CAP_TOP", (2, -14, bz - 6.5), 3.8, 0.4,
                     "cap_red", "BULK_CAP_TOP", "A", board))
    for i in range(6):
        x = random.uniform(-22, 22)
        y = random.uniform(-22, 22)
        if x * x + (y + 1) ** 2 < 30:
            continue
        parts.append(box(f"PCB_B_B_SMT_{i:02d}", (x, y, bz - 0.35),
                         (random.uniform(1.2, 2.2), random.uniform(0.8, 1.2),
                          0.7), "ic", "BACK_PASSIVE", "C", board, bevel=0.05))

    return parts

# --------------------------------------------------------------------------
# Scene: lights + floor + empties
# --------------------------------------------------------------------------


def area_light(name, loc, energy, size, color):
    ld = bpy.data.lights.new(name, "AREA")
    ld.energy = energy
    ld.shape = "DISK"
    ld.size = size
    ld.color = color
    o = bpy.data.objects.new(name, ld)
    bpy.context.scene.collection.objects.link(o)
    o.location = loc
    look = Vector((0, 0, 0)) - o.location
    o.rotation_euler = look.to_track_quat("-Z", "Y").to_euler()
    return o


def build_scene():
    scn = bpy.context.scene
    scn.render.engine = "BLENDER_EEVEE"
    scn.render.resolution_x = 1920
    scn.render.resolution_y = 1080
    scn.render.resolution_percentage = 100
    scn.render.image_settings.file_format = "PNG"
    scn.view_settings.exposure = 2.9
    scn.unit_settings.system = "METRIC"
    scn.unit_settings.scale_length = 0.001

    # world: subtle dark gradient like the V1.1 look
    world = bpy.data.worlds.new("WORLD_V3")
    world.use_nodes = True
    scn.world = world
    nt = world.node_tree
    bg = nt.nodes["Background"]
    bg.inputs["Strength"].default_value = 0.6
    tex = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.030, 0.035, 0.045, 1)
    ramp.color_ramp.elements[1].color = (0.10, 0.115, 0.135, 1)
    nt.links.new(tex.outputs["Generated"], sep.inputs[0])
    nt.links.new(sep.outputs["Z"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])

    # studio rig — subject ~100mm, distances ~300-500mm so energies in 10s of kW
    area_light("V3_KEY", (140, -160, 220), 56000, 180, (1.0, 0.96, 0.90))
    area_light("V3_FILL", (-160, -60, 140), 27000, 160, (0.88, 0.93, 1.0))
    area_light("V3_RIM", (40, 170, 190), 38000, 150, (1.0, 0.92, 0.82))

    # dark floor for contact grounding
    bpy.ops.mesh.primitive_plane_add(size=4000, location=(0, 0, -34))
    floor = bpy.context.object
    floor.name = "V3_FLOOR"
    fm = _mat("MAT_v3_floor", (0.035, 0.038, 0.045), 0.92)
    floor.data.materials.append(fm)

    # semantic empties for web mapping later
    for name, loc in [
        ("SEM_PCB_A_MAIN_SYSTEM_BOARD", (0, 0, 0)),
        ("SEM_PCB_B_AUXILIARY_INTERFACE_BOARD", (0, -80, 0)),
        ("SEM_PCB_RIBBON_CABLE", (86, -6, 4)),
        ("SEM_PCB_A_BACK", (0, 0, -8)),
    ]:
        e = bpy.data.objects.new(name, None)
        e.empty_display_type = "SPHERE"
        e.empty_display_size = 6
        e.location = loc
        bpy.context.scene.collection.objects.link(e)


def build_cameras():
    specs = [
        # name, location, target, lens
        ("CAM_V3_OVERVIEW", (155, -240, 240), (5, -40, -4), 58),
        ("CAM_V3_ARCH", (140, -215, 150), (5, -40, 18), 55),
        ("CAM_V3_A_FRONT", (74, -156, 195), (2, 0, 0), 60),
        ("CAM_V3_A_BACK", (74, -156, 195), (2, 0, 0), 60),
        ("CAM_V3_B_FRONT", (49, -114, 138), (0, 0, 0), 60),
        ("CAM_V3_B_BACK", (49, -114, 138), (0, 0, 0), 60),
        ("CAM_V3_A_CLOSE", (52, -52, 105), (2, 12, 3), 68),
        ("CAM_V3_B_CLOSE", (48, -54, 92), (0, -4, 2), 68),
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
        look = Vector(tgt) - o.location
        o.rotation_euler = look.to_track_quat("-Z", "Y").to_euler()
        cd.dof.focus_distance = look.length


def organize_collections():
    """Move PCB objects into PRESENTATION collection; lights/cams into RIG."""
    pres = bpy.data.collections.new("PRESENTATION_PCB_V3")
    rig = bpy.data.collections.new("RIG_V3")
    scn = bpy.context.scene
    scn.collection.children.link(pres)
    scn.collection.children.link(rig)
    for o in list(scn.collection.objects):
        tgt = rig if (o.type in ("LIGHT", "CAMERA")
                      or o.name.startswith("V3_FLOOR")) else pres
        scn.collection.objects.unlink(o)
        tgt.objects.link(o)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:]
                             if "--" in sys.argv else [])

    bpy.ops.wm.read_factory_settings(use_empty=True)
    build_materials()

    bounds_a = ([p[0] for p in PCB_A_OUTLINE], [p[1] for p in PCB_A_OUTLINE])
    bw_a = max(bounds_a[0]) - min(bounds_a[0])
    bh_a = max(bounds_a[1]) - min(bounds_a[1])
    bounds_b = ([p[0] for p in PCB_B_OUTLINE], [p[1] for p in PCB_B_OUTLINE])
    bw_b = max(bounds_b[0]) - min(bounds_b[0])
    bh_b = max(bounds_b[1]) - min(bounds_b[1])

    tex_a_front = bake_pcb_texture("TEX_pcb_a_front", bw_a, bh_a,
                                 PCB_A_HOLES, "front", 2048)
    tex_a_back = bake_pcb_texture("TEX_pcb_a_back", bw_a, bh_a,
                                PCB_A_HOLES, "back", 1024)
    tex_b_front = bake_pcb_texture("TEX_pcb_b_front", bw_b, bh_b,
                                 PCB_B_HOLES, "front", 2048)
    tex_b_back = bake_pcb_texture("TEX_pcb_b_back", bw_b, bh_b,
                                PCB_B_HOLES, "back", 1024)

    mat_a_f = soldermask_material("MAT_pcb_a_front", tex_a_front)
    mat_a_b = soldermask_material("MAT_pcb_a_back", tex_a_back)
    mat_b_f = soldermask_material("MAT_pcb_b_front", tex_b_front)
    mat_b_b = soldermask_material("MAT_pcb_b_back", tex_b_back)

    board_a = build_board("PCB_A_MAIN_SYSTEM_BOARD", PCB_A_OUTLINE,
                          PCB_A_HOLES, mat_a_f, mat_a_b)
    parts_a = build_pcb_a(board_a)

    board_b = build_board("PCB_B_AUXILIARY_INTERFACE_BOARD", PCB_B_OUTLINE,
                          PCB_B_HOLES, mat_b_f, mat_b_b)
    parts_b = build_pcb_b(board_b)
    board_b.location = (0, -80, 0)

    build_scene()
    build_cameras()
    organize_collections()

    out = Path(args.project_root) / OUT_BLEND
    out.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(out))

    print(json.dumps({
        "blend": str(out),
        "board_a_components": len(parts_a),
        "board_b_components": len(parts_b),
        "materials": len(bpy.data.materials),
        "textures": [i.name for i in bpy.data.images],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
