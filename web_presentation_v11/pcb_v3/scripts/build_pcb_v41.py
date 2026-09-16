"""Phase A3 STEP 1 — semantic/package upgrade pass on pcb_presentation_v4.blend.

Scope (per A3 spec execution order):
  * PCB-B white JST connectors -> real packages (housing + top cavity +
    pin strip + locking ramp; LONG / SMALL / RIGHT_ANGLE variants)
  * PCB-B power zone -> real molded power-inductor packages (body +
    metal terminals + label plate)
  * unified A3 material set (warm off-white plastic, cavity, inductor
    grey, terminal metal)
  * assembly hierarchy empties: PCB_ASSEMBLY > PCB_x > TOP/BOTTOM/...
  * pcb_semantic_components.json registry with confidence levels
  * closeup cameras for connector + power zones

Saves pcb_v41_semantic.blend. V4 remains the frozen geometric baseline.

Run: blender -b pcb_presentation_v4.blend --python build_pcb_v41.py
"""
from __future__ import annotations

import json
import math
import random
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
OUT_BLEND = ROOT / "pcb_v41_semantic.blend"
SEM_JSON = ROOT / "pcb_semantic_components.json"

TOP_Z = 0.8  # board face

# ---------------------------------------------------------------------------
# A3 material library (§36-39)
# ---------------------------------------------------------------------------


def _mat(name, base, rough, metal=0.0):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*base, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    return m


def build_a3_materials():
    _mat("MAT_CONNECTOR_WHITE", (0.68, 0.66, 0.60), 0.58)      # warm eng. plastic
    _mat("MAT_CONJ_CAVITY", (0.020, 0.019, 0.018), 0.70)       # deeper cavity
    _mat("MAT_INDUCTOR_GREY", (0.15, 0.15, 0.17), 0.42, 0.15)  # molded ferrite
    _mat("MAT_TERMINAL_METAL", (0.55, 0.56, 0.60), 0.30, 0.95)
    _mat("MAT_IC_BLACK_MATTE", (0.016, 0.017, 0.020), 0.55, 0.10)
    _mat("MAT_PRINT_DARK", (0.09, 0.09, 0.10), 0.60)           # ink on label
    # STEP 2 module set — black PCB / die / hardware kept distinguishable
    _mat("MAT_MODULE_PCB_BLACK", (0.018, 0.024, 0.021), 0.46)  # charcoal-green
    _mat("MAT_IC_BLACK_02", (0.010, 0.011, 0.013), 0.50)       # deeper matte
    _mat("MAT_METAL_SCREW", (0.20, 0.22, 0.26), 0.26, 0.95)
    _mat("MAT_CABLE_WHITE", (0.76, 0.72, 0.66), 0.55)          # soft warm polymer
    _mat("MAT_ADHESIVE_WHITE", (0.70, 0.69, 0.65), 0.48)       # matte-ish glue
    _mat("MAT_LABEL_WHITE", (0.86, 0.85, 0.82), 0.65)          # flat print
    _mat("MAT_EDGE_GOLD", (0.45, 0.38, 0.22), 0.42, 0.85)      # exposed edge
    # STEP 3 — ceramic patch antenna + coil subboard
    _mat("MAT_CERAMIC_WHITE", (0.82, 0.80, 0.74), 0.50)
    _mat("MAT_COPPER_PATCH", (0.50, 0.27, 0.09), 0.35, 0.82)
    _mat("MAT_SUBBOARD_GREEN", (0.030, 0.26, 0.095), 0.44)
    _mat("MAT_SUBBOARD_DARK", (0.022, 0.19, 0.070), 0.50)      # coil pad
    _mat("MAT_COIL_METAL", (0.60, 0.58, 0.53), 0.32, 0.92)     # tinned spiral
    _mat("MAT_LOGO_DARK", (0.016, 0.15, 0.055), 0.50)          # etched logo


# ---------------------------------------------------------------------------
# helpers — children live in BOARD-LOCAL space (parent = board object)
# ---------------------------------------------------------------------------


def _assign(obj, mat_name, sem, parent, props=None):
    if obj.data and hasattr(obj.data, "materials"):
        obj.data.materials.append(bpy.data.materials[mat_name])
    obj["semantic"] = sem
    obj["presentation"] = "PCB_V41"
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
    o.location = loc          # local coords under board parent
    return o


def _kill(names):
    for n in names:
        o = bpy.data.objects.get(n)
        if o:
            bpy.data.objects.remove(o)


# ---------------------------------------------------------------------------
# connector packages (§13-14)
# ---------------------------------------------------------------------------


def _boolean_cut(target, board, local_xyz, size, rot=0.0):
    """recess a real cavity into `target`; local_xyz is board-local."""
    world = board.matrix_world @ Vector(local_xyz)
    bpy.ops.mesh.primitive_cube_add(location=world)
    c = bpy.context.object
    c.scale = (size[0] / 2, size[1] / 2, size[2] / 2)
    bpy.ops.object.transform_apply(scale=True)
    c.rotation_euler.z = rot
    mod = target.modifiers.new("cavity", "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.object = c
    bpy.context.view_layer.objects.active = target
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.data.objects.remove(c)


def _solder_tails(name, x, y, w, d, board, rot, axis="x"):
    """tiny metal stubs poking out of the housing ends at board level."""
    parts = []
    for s in (-1, 1):
        if axis == "x":
            dx, dy = math.cos(rot) * s * (w / 2 + 0.35), \
                math.sin(rot) * s * (w / 2 + 0.35)
            size = (0.9, d * 0.55, 0.5)
        else:
            dx, dy = -math.sin(rot) * s * (d / 2 + 0.35), \
                math.cos(rot) * s * (d / 2 + 0.35)
            size = (w * 0.55, 0.9, 0.5)
        parts.append(box(f"{name}_TAIL_{s:+d}",
                         (x + dx, y + dy, TOP_Z + 0.35), size,
                         "MAT_TERMINAL_METAL", "CONNECTOR_PINS", board,
                         bevel=0.08, rot_z=rot))
    return parts


def jst_vertical(name, x, y, w, d, h, board, rot=0.0):
    """top-entry JST: thin-wall look — base skirt + housing with a real
    recessed cavity + pin strip on the floor + locking ramp + solder
    tails at the ends."""
    parts = []
    # base skirt: 0.9mm proud, 0.7 tall — the solder/base interface
    parts.append(box(f"{name}_BASE", (x, y, TOP_Z + 0.35),
                     (w + 0.9, d + 0.9, 0.7), "MAT_CONNECTOR_WHITE",
                     "CONNECTOR", board, bevel=0.15, rot_z=rot))
    hb = h - 0.5                        # housing sits on the skirt
    housing = box(f"{name}_HOUSING", (x, y, TOP_Z + 0.5 + hb / 2),
                  (w, d, hb), "MAT_CONNECTOR_WHITE", "CONNECTOR", board,
                  bevel=0.15, rot_z=rot, props={"pkg": "VERTICAL"})
    parts.append(housing)
    # real cavity cut into the housing top — wide/deep so walls read thin
    cw, cd = w * 0.78, d * 0.62
    _boolean_cut(housing, board, (x, y, TOP_Z + 0.5 + hb - 0.95),
                 (cw, cd, 1.9), rot)
    # pins on the cavity floor: a real pin row for long connectors,
    # a short strip for small ones — metal must be readable up close
    if w >= 12:
        npins = max(4, int(cw / 1.9))
        for i in range(npins):
            t = (i + 0.5) / npins - 0.5
            px, py = x + math.cos(rot) * t * cw * 0.9, \
                y + math.sin(rot) * t * cw * 0.9
            parts.append(box(f"{name}_PIN_{i}", (px, py,
                             TOP_Z + 0.5 + hb - 1.55),
                             (0.7, cd * 0.5, 0.9), "MAT_TERMINAL_METAL",
                             "CONNECTOR_PINS", board, bevel=0.05,
                             rot_z=rot))
    else:
        parts.append(box(f"{name}_PINS", (x, y, TOP_Z + 0.5 + hb - 1.5),
                         (cw * 0.75, 0.45, 0.9), "MAT_TERMINAL_METAL",
                         "CONNECTOR_PINS", board, bevel=0.08, rot_z=rot))
    parts.append(box(f"{name}_CAVFLOOR", (x, y, TOP_Z + 0.5 + hb - 1.62),
                     (cw, cd, 0.15), "MAT_CONJ_CAVITY",
                     "CONNECTOR_CAVITY", board, bevel=0.05, rot_z=rot))
    # locking ramp on the -d side
    ramp = box(f"{name}_RAMP",
               (x - math.sin(rot) * -(d / 2 - 0.3),
                y - math.cos(rot) * -(d / 2 - 0.3), TOP_Z + h - 0.8),
               (w * 0.45, 0.7, 1.1), "MAT_CONNECTOR_WHITE",
               "CONNECTOR_LOCK", board, bevel=0.1, rot_z=rot)
    ramp.rotation_euler.x = math.radians(-18)
    parts.append(ramp)
    parts += _solder_tails(name, x, y, w, d, board, rot,
                           "x" if w >= d else "y")
    return parts


def jst_right_angle(name, x, y, w, d, h, board, rot=0.0):
    """side-entry JST: base skirt + housing + real side cavity +
    horizontal pins + rear tab + solder tails on the flanks."""
    parts = []
    parts.append(box(f"{name}_BASE", (x, y, TOP_Z + 0.35),
                     (w + 0.9, d + 0.9, 0.7), "MAT_CONNECTOR_WHITE",
                     "CONNECTOR", board, bevel=0.08, rot_z=rot))
    hb = h - 0.5
    housing = box(f"{name}_HOUSING", (x, y, TOP_Z + 0.5 + hb / 2),
                  (w, d, hb), "MAT_CONNECTOR_WHITE", "CONNECTOR", board,
                  bevel=0.15, rot_z=rot, props={"pkg": "RIGHT_ANGLE"})
    parts.append(housing)
    # cavity opening on the outward (+x local) face — cut deep for
    # thin-wall look
    fx = w / 2 - 0.9
    cx, cy = x + math.cos(rot) * fx, y + math.sin(rot) * fx
    _boolean_cut(housing, board, (cx, cy, TOP_Z + 0.5 + hb * 0.5),
                 (2.2, d * 0.66, hb * 0.5), rot)
    # horizontal pins inside the side cavity
    px = w / 2 - 1.1
    px_, py_ = x + math.cos(rot) * px, y + math.sin(rot) * px
    parts.append(box(f"{name}_PINS", (px_, py_, TOP_Z + 0.5 + hb * 0.5),
                     (0.7, d * 0.45, 0.5), "MAT_TERMINAL_METAL",
                     "CONNECTOR_PINS", board, bevel=0.05, rot_z=rot))
    # rear locking tab
    bx = -w / 2 + 0.5
    bx_, by_ = x + math.cos(rot) * bx, y + math.sin(rot) * bx
    parts.append(box(f"{name}_TAB", (bx_, by_, TOP_Z + h - 0.6),
                     (1.4, d * 0.4, 1.0), "MAT_CONNECTOR_WHITE",
                     "CONNECTOR_LOCK", board, bevel=0.1, rot_z=rot))
    parts += _solder_tails(name, x, y, w, d, board, rot, "y")
    return parts


def power_inductor(name, x, y, w, d, h, board, rot=0.0, label=True):
    """molded power inductor: chamfered body + metal terminals wrapping
    the two ends + top label plate."""
    parts = []
    body = box(f"{name}_BODY", (x, y, TOP_Z + h / 2), (w, d, h),
               "MAT_INDUCTOR_GREY", "INDUCTOR", board, bevel=0.45, rot_z=rot,
               props={"pkg": "MOLDED_POWER"})
    parts.append(body)
    # terminals: metal pads wrapping up the short ends, proud of the body
    tw = min(1.1, w * 0.18)
    for s in (-1, 1):
        dx, dy = math.cos(rot) * s * (w / 2 + tw * 0.15), \
            math.sin(rot) * s * (w / 2 + tw * 0.15)
        parts.append(box(f"{name}_TERM_{s:+d}",
                         (x + dx, y + dy, TOP_Z + h * 0.32),
                         (tw, d * 0.94, h * 0.62), "MAT_TERMINAL_METAL",
                         "INDUCTOR_TERMINAL", board, bevel=0.1, rot_z=rot))
    if label:
        parts.append(box(f"{name}_LABEL", (x, y, TOP_Z + h + 0.12),
                         (w * 0.55, d * 0.45, 0.15), "MAT_IC_BLACK_MATTE",
                         "INDUCTOR_MARK", board, bevel=0.05, rot_z=rot))
    return parts


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


def blob(name, loc, rx, ry, rz, mk, sem, parent, seed=0):
    """irregular adhesive mound: squashed ico + offset satellite blob."""
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3, radius=1.0,
                                        location=(0, 0, 0))
    o = bpy.context.object
    o.name = name
    o.scale = (rx, ry, rz)
    bpy.ops.object.transform_apply(scale=True)
    for p in o.data.polygons:
        p.use_smooth = True
    _assign(o, mk, sem, parent)
    o.location = loc
    parts = [o]
    # satellite blob breaks the perfect-dome read
    parts.append(blob_small(name + "_sat",
                            (loc[0] + rx * 0.5, loc[1] + ry * 0.3,
                             loc[2] - rz * 0.15), rx * 0.35, mk, sem, parent))
    return parts


def blob_small(name, loc, r, mk, sem, parent):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=r,
                                        location=(0, 0, 0))
    o = bpy.context.object
    o.name = name
    o.scale.z = 0.6
    bpy.ops.object.transform_apply(scale=True)
    _assign(o, mk, sem, parent)
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


def ic_leaded(name, x, y, w, d, h, z_base, board, rot=0.0,
              pin_sides="lr", mat="MAT_IC_BLACK_MATTE"):
    """leaded package: body + fine pin strips on chosen side pairs."""
    parts = [box(name, (x, y, z_base + h / 2), (w, d, h), mat,
                 "IC", board, bevel=min(0.25, h * 0.2), rot_z=rot)]
    # individual fine-pitch leads along the chosen side pairs — a solid
    # strip reads as a silver frame; real packages show separate pins
    pin_h, pin_w, pitch = 0.5, 0.22, 0.65
    sides = {"lr": [(-1, 0), (1, 0)], "tb": [(0, -1), (0, 1)]}[pin_sides]
    for i, (sx, sy) in enumerate(sides):
        span = d * 0.86 if sx else w * 0.86
        off = (w / 2 + 0.18) if sx else (d / 2 + 0.18)
        npin = max(4, int(span / pitch))
        for k in range(npin):
            t = (k + 0.5) / npin - 0.5
            dx = sx * off if sx else t * span
            dy = sy * off if sy else t * span
            dims = (0.5, pin_w, pin_h) if sx else (pin_w, 0.5, pin_h)
            parts.append(box(f"{name}_p{i}_{k}",
                             (x + dx, y + dy, z_base + pin_h / 2),
                             dims, "MAT_TERMINAL_METAL", "IC_PINS", board,
                             bevel=0.04, rot_z=rot))
    return parts


def spiral_curve(name, cx, cy, z, r0, r1, turns, radius, mk, sem, parent):
    """flat archimedean spiral — the wound metallic coil."""
    cu = bpy.data.curves.new(name + "_c", "CURVE")
    cu.dimensions = "3D"
    cu.resolution_u = 2
    cu.bevel_depth = radius
    cu.bevel_resolution = 3
    n = int(turns * 24)
    spl = cu.splines.new("POLY")
    spl.points.add(n - 1)
    for i in range(n):
        t = i / (n - 1)
        a = 2 * math.pi * turns * t
        r = r0 + (r1 - r0) * t
        spl.points[i].co = (cx + r * math.cos(a), cy + r * math.sin(a),
                            z, 1)
    o = bpy.data.objects.new(name, cu)
    bpy.context.scene.collection.objects.link(o)
    _assign(o, mk, sem, parent)
    return o


def top_marking(name, text, x, y, z, size, board, rot=0.0):
    """flat printed marking (e.g. '3R3') straight on the package top."""
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
    bpy.ops.object.convert(target="MESH")     # freeze text -> mesh
    o.select_set(False)
    _assign(o, "MAT_PRINT_DARK", "INDUCTOR_MARK", board)
    o.location = (x, y, z)
    return o


# ---------------------------------------------------------------------------
# hierarchy + semantic registry (§10, §34-35)
# ---------------------------------------------------------------------------


def make_empty(name, parent=None):
    o = bpy.data.objects.get(name) or bpy.data.objects.new(name, None)
    if o.name not in bpy.context.scene.collection.objects:
        bpy.context.scene.collection.objects.link(o)
    if parent:
        o.parent = parent
    return o


def build_hierarchy(board_a, board_b):
    asm = make_empty("PCB_ASSEMBLY")
    groups = {}
    for tag, board in (("PCB_A_MAIN_BOARD", board_a),
                       ("PCB_B_AUXILIARY_BOARD", board_b)):
        root = make_empty(tag)
        for sub in ("BOARD", "TOP", "BOTTOM", "MODULES", "CONNECTORS",
                    "CABLES"):
            e = make_empty(f"{tag}_{sub}", root)
            groups[(tag, sub)] = e
        # board mesh under its BOARD node; assembly node parents the root
        mw = board.matrix_world.copy()
        board.parent = groups[(tag, "BOARD")]
        board.matrix_world = mw
        mw2 = root.matrix_world.copy()
        root.parent = asm
        root.matrix_world = mw2
    return asm, groups


def reparent_existing(board, groups, tag):
    """sort existing V4 children under TOP/BOTTOM/MODULES/CONNECTORS/CABLES."""
    moved = 0
    for o in bpy.data.objects:
        if o.parent is not board:
            continue
        sem = str(o.get("semantic", ""))
        wz = o.matrix_world.translation.z
        bz = board.matrix_world.translation.z
        if wz < bz:
            grp = "BOTTOM"
        elif "CONNECTOR" in sem or "JST" in o.name or "PLUG" in sem:
            grp = "CONNECTORS"
        elif "CABLE" in sem or "RIBBON" in sem or "COAX" in sem:
            grp = "CABLES"
        elif "MODULE" in sem or "ANTENNA" in sem or "SHIELDED" in sem \
                or "COIL" in sem:
            grp = "MODULES"
        else:
            grp = "TOP"
        mw = o.matrix_world.copy()
        o.parent = groups[(tag, grp)]
        o.matrix_world = mw
        moved += 1
    return moved


CATEGORY_MAP = {
    "MAIN_COMPUTE_MODULE": "MODULE", "MODULE_DIE": "LARGE_IC",
    "MODULE_LABEL": "LABEL", "COAX_ANTENNA_LEAD": "COAX_CABLE",
    "CERAMIC_PATCH_ANTENNA": "ANTENNA", "ANTENNA_PATCH": "ANTENNA",
    "ANTENNA_FEED": "ANTENNA", "SHIELDED_ZONE": "MODULE",
    "SHIELD_COMPONENT": "SMALL_IC", "POWER_COIL": "COIL",
    "EDGE_CONNECTOR": "CONNECTOR", "JST_CONNECTOR": "CONNECTOR",
    "JST_SLOT": "CONNECTOR", "RIBBON_CABLE": "CABLE",
    "RIBBON_PLUG": "CONNECTOR", "POWER_INDUCTOR": "INDUCTOR",
    "POWER_INDUCTOR_2R2": "INDUCTOR", "POWER_INDUCTOR_3R3": "INDUCTOR",
    "POWER_INDUCTOR_6R8": "INDUCTOR", "INDUCTOR_MARK": "LABEL",
    "IC": "SMALL_IC", "IC_PINS": "SMALL_IC", "TANT_CAP": "CAPACITOR_LARGE",
    "TANT_CAP_ROW": "CAPACITOR_LARGE", "CRYSTAL": "SMALL_IC",
    "SMT_PASSIVE": "RESISTOR_CAPACITOR_CLUSTER",
    "BACK_GROUND_TAB": "METAL_SHIELD", "GROUND_WIRE_LOOP": "CABLE",
    "BACK_EDGE_CONN": "CONNECTOR", "SN_LABEL": "LABEL",
    "SILKSCREEN_TEXT": "LABEL", "BULK_CAP": "CAPACITOR_LARGE",
    "BULK_CAP_TOP": "CAPACITOR_LARGE", "BACK_PASSIVE":
    "RESISTOR_CAPACITOR_CLUSTER",
    "CONNECTOR_CAVITY": "CONNECTOR", "CONNECTOR_PINS": "CONNECTOR",
    "CONNECTOR_LOCK": "CONNECTOR", "INDUCTOR": "INDUCTOR",
    "INDUCTOR_TERMINAL": "INDUCTOR",
    "MODULE_PCB": "MODULE", "MODULE_EDGE": "MODULE",
    "STANDOFF": "MOUNTING_HARDWARE", "FASTENER": "FASTENER",
    "ADHESIVE": "MOUNTING_HARDWARE", "LABEL": "LABEL",
    "IC": "SMALL_IC", "TEST_PAD": "TEST_PAD",
}
CONF = {"CONNECTOR": "HIGH", "MODULE": "HIGH", "ANTENNA": "HIGH",
        "COIL": "HIGH", "INDUCTOR": "MEDIUM", "LARGE_IC": "MEDIUM",
        "COAX_CABLE": "HIGH", "CABLE": "HIGH", "CAPACITOR_LARGE": "MEDIUM",
        "METAL_SHIELD": "MEDIUM", "LABEL": "HIGH", "SMALL_IC": "LOW",
        "RESISTOR_CAPACITOR_CLUSTER": "LOW", "FASTENER": "HIGH",
        "MOUNTING_HARDWARE": "HIGH"}


def write_registry(board_a, board_b):
    counters, entries = {}, []
    for o in bpy.data.objects:
        if o.get("presentation") not in ("PCB_V4", "PCB_V41"):
            continue
        if o.type not in ("MESH", "CURVE"):
            continue
        sem = str(o.get("semantic", ""))
        if not sem or o.name.startswith(("PCB_A_MAIN_SYSTEM_BOARD",
                                         "PCB_B_AUXILIARY")):
            continue
        cat = CATEGORY_MAP.get(sem, "UNKNOWN_COMPONENT")
        board = "PCB_A" if "PCB_A" in o.name else "PCB_B"
        side = "BACK" if (o.matrix_world.translation.z
                          < (board_a if board == "PCB_A" else board_b)
                          .matrix_world.translation.z) else "FRONT"
        counters[cat] = counters.get(cat, 0) + 1
        entries.append({
            "id": f"{cat}_{counters[cat]:02d}",
            "object": o.name, "board": board, "side": side,
            "category": cat,
            "confidence": CONF.get(cat, "UNKNOWN"),
            "source": "PHOTO" if CONF.get(cat) == "HIGH" else
                      ("OVERLAY" if CONF.get(cat) == "MEDIUM" else
                       "PROCEDURAL"),
            "presentation_priority": "PRIMARY" if o.get("level") == "A"
                                     else "SECONDARY",
            "geometry_mode": "FULL_3D" if o.get("level") in ("A", "B")
                            else "INSTANCED",
        })
    SEM_JSON.write_text(json.dumps({"components": entries}, indent=2))
    return len(entries)


# ---------------------------------------------------------------------------
# cameras for STEP 1 review shots (§42: long-ish lenses)
# ---------------------------------------------------------------------------


def add_cam(name, target, direction, dist, lens=75,
            ref="PCB_B_AUXILIARY_INTERFACE_BOARD"):
    cd = bpy.data.cameras.get(name) or bpy.data.cameras.new(name)
    cd.lens, cd.sensor_width = lens, 36
    cd.dof.use_dof = True
    cd.dof.aperture_fstop = 8.0
    o = bpy.data.objects.get(name) or bpy.data.objects.new(name, cd)
    if o.name not in bpy.context.scene.collection.objects:
        bpy.context.scene.collection.objects.link(o)
    b = bpy.data.objects[ref]
    t = Vector(target) + b.matrix_world.translation
    o.location = t + Vector(direction).normalized() * dist
    o.rotation_euler = (t - o.location).to_track_quat("-Z", "Y").to_euler()
    cd.dof.focus_distance = dist
    return o


# ---------------------------------------------------------------------------
# main pass
# ---------------------------------------------------------------------------


def main():
    build_a3_materials()
    board_a = bpy.data.objects["PCB_A_MAIN_SYSTEM_BOARD"]
    board_b = bpy.data.objects["PCB_B_AUXILIARY_INTERFACE_BOARD"]

    # --- replace B connectors -------------------------------------------
    # Step 1.1: per-connector verification against registered-photo crops —
    # heights cut again (~2.4-2.9), opening direction per part:
    #   B_01/B_02/B_06 top-entry (pin row visible on top in photo)
    #   B_03 side-entry facing -x (out the left edge)
    #   B_04 side-entry facing +x (cavity on the right face in photo)
    #   B_05 side-entry facing -x (toward board centre)
    #   B_07 side-entry facing -y (out the bottom edge)
    jsts = [("CONN_B_01", (-11, 14), (15, 7, 2.8), 0.0, "V"),
            ("CONN_B_02", (5.5, 16), (5, 6, 2.4), 0.0, "V"),
            ("CONN_B_03", (-26.5, -8), (7.5, 9.5, 2.6), math.pi, "RA"),
            ("CONN_B_04", (-11.5, -12), (16, 10, 2.9), -0.4, "RA"),
            ("CONN_B_05", (20.5, 8.75), (9, 7, 2.4), 2.64, "RA"),
            ("CONN_B_06", (18, -11.5), (9, 5.5, 2.5), 0.0, "V"),
            ("CONN_B_07", (3.5, -23.5), (9, 8, 2.6), -math.pi / 2, "RA")]
    _kill([f"PCB_B_JST_{i}" for i in range(7)] +
          [f"PCB_B_JST_{i}_SLOT" for i in range(7)])
    made = []
    for name, (x, y), (w, d, h), rot, kind in jsts:
        if kind == "RA":
            made += jst_right_angle(name, x, y, w, d, h, board_b, rot)
        else:
            made += jst_vertical(name, x, y, w, d, h, board_b, rot)

    # --- replace B power inductors --------------------------------------
    _kill(["PCB_B_INDUCTOR_3R3", "PCB_B_3R3_MARK", "PCB_B_INDUCTOR_6R8",
           "PCB_B_INDUCTOR_3"])
    made += power_inductor("INDUCTOR_B_3R3", 9.9, -4.75, 10, 7.5, 4.2,
                           board_b, rot=-0.15, label=False)
    # photo shows "3R3" + a smaller second line "2443"
    made += [top_marking("INDUCTOR_B_3R3_PRINT", "3R3", 9.9, -3.6,
                         TOP_Z + 4.2 + 0.06, 2.6, board_b, rot=-0.15)]
    made += [top_marking("INDUCTOR_B_3R3_PRINT2", "2443", 9.9, -6.3,
                         TOP_Z + 4.2 + 0.06, 1.6, board_b, rot=-0.15)]
    # photo clearly prints "2R2" here, not 6R8 — corrected
    made += power_inductor("INDUCTOR_B_2R2", -2.2, -9.6, 6.5, 4, 3.4,
                           board_b, label=False)
    made += [top_marking("INDUCTOR_B_2R2_PRINT", "2R2", -2.2, -9.6,
                         TOP_Z + 3.4 + 0.06, 1.9, board_b)]
    made += power_inductor("INDUCTOR_B_03", -3.2, -23, 5.5, 3.5, 3.2,
                           board_b, label=False)

    # --- STEP 2: A_MAIN_BLACK_MODULE -------------------------------------
    # Layout CV-measured on registered_a_front (20 px/mm, board-local mm):
    #   module PCB 41x28.9 @ (-1.5,30.1), raised ~2.0 on standoffs —
    #   reads as a thin daughterboard, not a black enclosure
    #   screws TL(-21.6,43) TR(16.5,43) BL(-21.75,17) BR(16,17.25)
    #   majors: two equal tall leaded ICs top-left (6.3x14.3 each),
    #   wide IC bottom-left, dominant 17x19 central package, right column
    #   CLMP157BI sticker (1.6,18.6) + printed repeat (1.75,25.7)
    #   white coax drops over the top edge from the main board, arcs
    #   right, ends in the adhesive blob (8.5,31.6)
    _kill(["PCB_A_MAIN_MODULE", "PCB_A_MODULE_DIE_1", "PCB_A_MODULE_DIE_2",
           "PCB_A_MODULE_LABEL", "PCB_A_COAX", "PCB_A_TOP_CONN"])
    MOD_X, MOD_Y, MOD_W, MOD_D = -2.1, 29.8, 42.6, 30.1
    MOD_BOT, MOD_TOP = TOP_Z + 2.0, TOP_Z + 3.4   # 2mm standoff + 1.4 PCB
    MZ = MOD_TOP
    mp = []
    mp.append(box("A_MOD_PCB", (MOD_X, MOD_Y, (MOD_BOT + MOD_TOP) / 2),
                  (MOD_W, MOD_D, 1.4), "MAT_MODULE_PCB_BLACK",
                  "MODULE_PCB", board_a, bevel=0.3,
                  props={"thickness_estimated": True}))
    # subtle exposed brass-toned perimeter edge (visible in photo)
    ew = 0.35
    for i, (ex, ey, dx, dy) in enumerate((
            (MOD_X, MOD_Y + MOD_D / 2, MOD_W, ew),
            (MOD_X, MOD_Y - MOD_D / 2, MOD_W, ew),
            (MOD_X - MOD_W / 2, MOD_Y, ew, MOD_D),
            (MOD_X + MOD_W / 2, MOD_Y, ew, MOD_D))):
        mp.append(box(f"A_MOD_EDGE_{i}", (ex, ey, MOD_BOT + 0.7),
                      (dx + ew, dy + ew, 0.9), "MAT_EDGE_GOLD",
                      "MODULE_EDGE", board_a, bevel=0.05))
    # 4 corner mounts: standoff under + washer + hex-head screw above
    for i, (sx, sy) in enumerate(((-21.75, 44.2), (18.7, 44.2),
                                  (-21.9, 15.5), (18.3, 15.6))):
        mp.append(cyl_at(f"A_MOD_STAND_{i}", (sx, sy, TOP_Z + 1.0), 1.5,
                         2.0, "MAT_METAL_SCREW", "STANDOFF", board_a))
        mp.append(cyl_at(f"A_MOD_WASHER_{i}", (sx, sy, MOD_TOP + 0.18),
                         1.7, 0.35, "MAT_METAL_SCREW", "FASTENER", board_a))
        mp.append(cyl_at(f"A_MOD_SCREW_{i}", (sx, sy, MOD_TOP + 0.8), 1.15,
                         0.9, "MAT_METAL_SCREW", "FASTENER", board_a,
                         verts=6))
    # major ICs — CV-measured on the photo crop; leaded where pins show
    mp += ic_leaded("A_MOD_IC01", -17.4, 31.75, 6.75, 9.5, 1.2, MZ,
                    board_a, pin_sides="lr")
    mp += ic_leaded("A_MOD_IC02", -10.25, 31.75, 6.75, 9.5, 1.2, MZ,
                    board_a, pin_sides="lr")
    mp += ic_leaded("A_MOD_IC03", -13.5, 20.75, 13.0, 10.5, 1.1, MZ,
                    board_a, pin_sides="tb", mat="MAT_IC_BLACK_02")
    mp.append(box("A_MOD_IC04", (1.25, 29.0, MZ + 0.7), (15.0, 19.0, 1.4),
                  "MAT_IC_BLACK_02", "IC", board_a, bevel=0.4,
                  props={"pkg": "LARGE_PACKAGE"}))
    for j, yy in enumerate((33.0, 30.5, 28.0)):   # faint printed marks
        mp.append(box(f"A_MOD_IC04_MARK{j}", (1.25, yy, MZ + 1.405),
                      (9.0, 0.7, 0.03), "MAT_MODULE_PCB_BLACK",
                      "SILKSCREEN_TEXT", board_a, bevel=0.02))
    # right-column ICs — QFN with visible die + smaller packages
    mp.append(box("A_MOD_IC05", (13.5, 36.75, MZ + 0.5), (3.0, 3.5, 1.0),
                  "MAT_IC_BLACK_MATTE", "IC", board_a, bevel=0.15))
    mp.append(box("A_MOD_IC05_DIE", (13.5, 36.75, MZ + 1.02),
                  (1.4, 1.6, 0.1), "MAT_TERMINAL_METAL", "IC", board_a,
                  bevel=0.03))
    mp.append(box("A_MOD_IC06", (13.25, 32.0, MZ + 0.5), (4.5, 3.0, 1.0),
                  "MAT_IC_BLACK_MATTE", "IC", board_a, bevel=0.2))
    mp += ic_leaded("A_MOD_IC07", 12.75, 25.7, 3.0, 3.0, 0.9, MZ,
                    board_a, pin_sides="tb")
    mp += ic_leaded("A_MOD_IC08", 17.9, 22.5, 2.75, 4.0, 0.9, MZ,
                    board_a, pin_sides="lr")
    mp.append(box("A_MOD_IC09", (14.0, 19.5, MZ + 0.45), (4.0, 5.0, 0.9),
                  "MAT_IC_BLACK_MATTE", "IC", board_a, bevel=0.2))
    # castellated pad strip along the module's left edge
    mp.append(box("A_MOD_EDGEPADS", (MOD_X - MOD_W / 2 + 0.5, 21.75,
                  MZ + 0.08), (1.2, 9.0, 0.35), "MAT_TERMINAL_METAL",
                  "CONNECTOR_PINS", board_a, bevel=0.08))
    # labels: CLMP157BI sticker + printed repeat + QR + ESD tri + bin icon
    mp.append(box("A_MOD_LABEL", (1.6, 18.0, MZ + 0.11), (12.25, 3.0, 0.22),
                  "MAT_LABEL_WHITE", "LABEL", board_a, bevel=0.1))
    mp.append(top_marking("A_MOD_LABEL_TXT", "CLMP157BI", 1.6, 18.0,
                          MZ + 0.24, 2.0, board_a))
    mp.append(top_marking("A_MOD_LABEL_TXT2", "CLMP157BI", 1.75, 21.4,
                          MZ + 0.05, 2.3, board_a))
    mp.append(box("A_MOD_QR", (-13.5, 41.5, MZ + 0.09), (4.0, 4.0, 0.18),
                  "MAT_LABEL_WHITE", "LABEL", board_a, bevel=0.05))
    for j, (qx, qy, s) in enumerate(((-14.4, 42.3, 1.1), (-12.6, 41.3, 1.3),
                                     (-13.8, 40.3, 0.8))):
        mp.append(box(f"A_MOD_QR_P{j}", (qx, qy, MZ + 0.21), (s, s, 0.06),
                      "MAT_PRINT_DARK", "LABEL", board_a, bevel=0.02))
    # ESD warning triangle — white outline, large (~6mm in photo)
    mp.append(cyl_at("A_MOD_ESD", (-7.9, 39.7, MZ + 0.1), 3.1, 0.16,
                     "MAT_LABEL_WHITE", "LABEL", board_a, verts=3))
    mp.append(cyl_at("A_MOD_ESD_IN", (-7.9, 39.55, MZ + 0.19), 2.35, 0.06,
                     "MAT_MODULE_PCB_BLACK", "LABEL", board_a, verts=3))
    mp.append(box("A_MOD_ICON", (-1.9, 39.4, MZ + 0.09), (3.0, 3.5, 0.16),
                  "MAT_LABEL_WHITE", "LABEL", board_a, bevel=0.05))
    mp.append(box("A_MOD_ICON_IN", (-1.9, 39.4, MZ + 0.19), (1.9, 2.5, 0.08),
                  "MAT_MODULE_PCB_BLACK", "LABEL", board_a, bevel=0.04))
    # module silkscreen designators — tiny white rects at photo density
    for i, (tx, ty, tw) in enumerate(((-20.0, 16.4, 2.5), (8.0, 18.2, 3.0),
                                      (16.5, 40.0, 2.5), (-16.0, 15.9, 2.0),
                                      (4.5, 43.8, 3.0), (12.5, 18.7, 2.0),
                                      (-20.5, 43.8, 2.5))):
        mp.append(box(f"A_MOD_SS_{i}", (tx, ty, MZ + 0.05),
                      (tw, 0.7, 0.08), "MAT_LABEL_WHITE",
                      "SILKSCREEN_TEXT", board_a, bevel=0.02))
    # SMT field on the module — photo-guided clusters, seeded, secondary
    rng = random.Random(417)
    free = [(-20.0, 43.0, 3.0, 2.0), (-5.5, 42.0, 4.0, 2.0),
            (6.0, 42.0, 5.0, 2.0), (17.5, 30.0, 2.0, 5.0),
            (11.0, 20.5, 4.0, 3.0), (-6.0, 17.0, 4.0, 2.0),
            (-21.0, 26.5, 1.5, 3.0), (-18.0, 24.0, 4.0, 3.0)]
    for i in range(26):
        fx, fy, fw, fd = rng.choice(free)
        px_, py_ = fx + rng.uniform(-fw / 2, fw / 2), \
            fy + rng.uniform(-fd / 2, fd / 2)
        s = rng.uniform(0.5, 1.1)
        mp.append(box(f"A_MOD_SMT_{i}", (px_, py_, MZ + 0.15),
                      (s, s * 0.6, 0.3), "MAT_IC_BLACK_MATTE",
                      "SMT_PASSIVE", board_a, bevel=0.05))
    # white coax — drops over the top edge from the main board at x~7.5,
    # arcs right-down and ends in the adhesive blob (8.9,27.5)
    mp.append(cable_curve("A_MOD_CABLE",
                          [(7.5, 49.5, TOP_Z + 1.3),
                           (7.6, 45.5, MOD_TOP + 0.9),
                           (10.5, 42.0, MOD_TOP + 0.8),
                           (11.0, 37.5, MOD_TOP + 0.65),
                           (10.2, 32.5, MOD_TOP + 0.5),
                           (8.9, 28.0, MOD_TOP + 0.35)],
                          0.6, "MAT_CABLE_WHITE", "COAX_CABLE", board_a))
    mp += blob("A_MOD_GLUE_END", (8.9, 27.5, MOD_TOP + 0.3),
               1.5, 1.4, 0.65, "MAT_ADHESIVE_WHITE", "ADHESIVE", board_a)

    # --- STEP 3: ceramic patch antenna + coil subboard --------------------
    # CV-measured on registered_a_front crops:
    #   antenna frame 22x22 @ (-22,-29.9), 4 corner screws, left-edge slot,
    #   copper ring + white ceramic centre + feed dot
    #   daughterboard 27x41 @ (3,-29) raised ~1.0, etched maze logo top,
    #   6 silver pads, flat wound spiral Ø14.5 @ (0.25,-37.5) on darker
    #   pad, pin row under coil, vertical SN label at left edge
    _kill(["PCB_A_CERAMIC_ANT", "PCB_A_ANT_PATCH", "PCB_A_ANT_DOT",
           "PCB_A_SHIELD_ZONE", "PCB_A_SHIELD_IC", "PCB_A_ZONE_SN",
           "PCB_A_ZONE_TEXT", "PCB_A_COIL_BASE"] +
          [f"PCB_A_COIL_{i}" for i in range(4)])
    sp = []
    AX, AY = -21.5, -31.6                       # antenna centre (photo)
    # white ceramic carrier frame — box with a real window through it
    frame = box("A_ANT_FRAME", (AX, AY, TOP_Z + 1.5), (22.0, 22.0, 3.0),
                "MAT_CERAMIC_WHITE", "ANTENNA", board_a, bevel=0.3)
    _boolean_cut(frame, board_a, (AX, AY, TOP_Z + 1.5), (13.6, 13.6, 3.4))
    # left-edge feed slot + smaller bottom-edge notch (both in photo)
    _boolean_cut(frame, board_a, (AX - 11.0, AY + 0.5, TOP_Z + 1.6),
                 (2.2, 3.6, 1.6))
    _boolean_cut(frame, board_a, (AX - 0.5, AY - 11.0, TOP_Z + 1.7),
                 (3.0, 2.0, 1.4))
    sp.append(frame)
    # copper patch ring + white ceramic centre + feed dot
    sp.append(box("A_ANT_PATCH", (AX, AY, TOP_Z + 1.15), (13.2, 13.2, 0.5),
                  "MAT_COPPER_PATCH", "ANTENNA_PATCH", board_a, bevel=0.3))
    sp.append(box("A_ANT_CERAMIC", (AX, AY, TOP_Z + 1.65), (8.6, 8.6, 0.6),
                  "MAT_CERAMIC_WHITE", "ANTENNA_PATCH", board_a, bevel=0.2))
    sp.append(cyl_at("A_ANT_FEED", (AX, AY, TOP_Z + 2.1), 0.85, 0.35,
                     "MAT_TERMINAL_METAL", "ANTENNA_FEED", board_a))
    # small dark patch inside the window at bottom-right (photo feature)
    sp.append(box("A_ANT_DARKPATCH", (AX + 6.2, AY - 6.8, TOP_Z + 1.45),
                  (2.2, 3.2, 0.25), "MAT_IC_BLACK_MATTE", "ANTENNA_PATCH",
                  board_a, bevel=0.05))
    # 4 corner mounts: square boss ear on the frame corner + metal washer
    # ring at frame top + small screw head — reads as screwed hardware,
    # not a ceramic dome
    for i, (sx, sy) in enumerate(((-31.5, -20.5), (-13.0, -20.5),
                                  (-31.5, -40.25), (-12.75, -40.25))):
        sp.append(box(f"A_ANT_BOSS_{i}", (sx, sy, TOP_Z + 1.5),
                      (4.0, 4.0, 3.0), "MAT_CERAMIC_WHITE", "ANTENNA",
                      board_a, bevel=0.3))
        sp.append(cyl_at(f"A_ANT_WASHER_{i}", (sx, sy, TOP_Z + 3.05), 1.55,
                         0.3, "MAT_METAL_SCREW", "MOUNTING_HARDWARE",
                         board_a))
        sp.append(cyl_at(f"A_ANT_SCREW_{i}", (sx, sy, TOP_Z + 3.5), 1.0,
                         0.8, "MAT_METAL_SCREW", "FASTENER", board_a,
                         verts=12))

    # daughterboard — thin green PCB raised ~1.0 over the main board
    DB_X, DB_Y, DB_W, DB_D = 3.0, -29.0, 27.0, 41.0
    DB_TOP = TOP_Z + 1.9
    sp.append(box("A_DB_PCB", (DB_X, DB_Y, TOP_Z + 1.4), (DB_W, DB_D, 1.0),
                  "MAT_SUBBOARD_GREEN", "MODULE_PCB", board_a, bevel=0.4,
                  props={"thickness_estimated": True}))
    for i, (fx, fy) in enumerate(((DB_X - DB_W / 2 + 2, DB_Y - DB_D / 2 + 2),
                                  (DB_X + DB_W / 2 - 2, DB_Y - DB_D / 2 + 2),
                                  (DB_X - DB_W / 2 + 2, DB_Y + DB_D / 2 - 2),
                                  (DB_X + DB_W / 2 - 2, DB_Y + DB_D / 2 - 2))):
        sp.append(box(f"A_DB_FOOT_{i}", (fx, fy, TOP_Z + 0.5),
                      (2.5, 2.5, 1.0), "MAT_SUBBOARD_DARK",
                      "MOUNTING_HARDWARE", board_a, bevel=0.2))
    # etched maze-like logo centred ~(-0.4,-19.6), spans y -14..-26 —
    # a few nested dark-green bars approximating the monogram
    for j, (lx, ly, lw, lh) in enumerate(((-4.6, -15.0, 7.5, 0.5),
                                         (-4.6, -19.5, 0.5, 9.0),
                                         (0.2, -24.0, 7.5, 0.5),
                                         (3.5, -19.5, 0.5, 9.0),
                                         (-0.5, -17.5, 4.5, 0.5),
                                         (-2.2, -21.8, 0.5, 4.5),
                                         (-0.8, -20.5, 3.0, 0.5),
                                         (1.4, -22.5, 0.5, 3.0))):
        sp.append(box(f"A_DB_LOGO_{j}", (lx, ly, DB_TOP + 0.05),
                      (lw, lh, 0.08), "MAT_LOGO_DARK", "SILKSCREEN_TEXT",
                      board_a, bevel=0.02))
    # 6 silver pads in a row above the logo (photo row y≈-11.6)
    for k in range(6):
        sp.append(box(f"A_DB_PAD_{k}", (-0.75 + k * 1.7, -11.6,
                      DB_TOP + 0.1), (0.9, 1.4, 0.2), "MAT_TERMINAL_METAL",
                      "TEST_PAD", board_a, bevel=0.05))
    # coil pad — darker rounded mount area under the spiral
    sp.append(box("A_DB_COILPAD", (-0.25, -38.0, DB_TOP + 0.12),
                  (16.0, 17.0, 0.22), "MAT_SUBBOARD_DARK", "COIL",
                  board_a, bevel=0.9))
    # flat wound metallic spiral Ø~13 @ (0.1,-36.4) — photo shows ~14
    # tight turns of fine wire; keep pitch slightly wider than the wire
    sp.append(spiral_curve("A_DB_COIL", 0.1, -36.4, DB_TOP + 0.5,
                           0.55, 6.4, 14.0, 0.17, "MAT_COIL_METAL",
                           "COIL", board_a))
    # centre terminal hook — tiny wire end poking into the spiral centre
    sp.append(cable_curve("A_DB_COIL_TAIL",
                          [(0.1, -36.4, DB_TOP + 0.5),
                           (0.8, -37.1, DB_TOP + 0.5),
                           (1.7, -37.7, DB_TOP + 0.3)],
                          0.20, "MAT_COIL_METAL", "COIL", board_a))
    # white pin/marker row under the coil (photo: 8 marks at y≈-45.6)
    for k in range(8):
        sp.append(box(f"A_DB_PIN_{k}", (-2.0 + k * 1.4, -45.6,
                      DB_TOP + 0.1), (0.7, 1.2, 0.18), "MAT_LABEL_WHITE",
                      "SILKSCREEN_TEXT", board_a, bevel=0.03))
    # vertical SN label on the daughterboard's left edge
    sp.append(box("A_DB_SN", (-9.3, -36.5, DB_TOP + 0.1), (2.8, 10.5, 0.18),
                  "MAT_LABEL_WHITE", "LABEL", board_a, bevel=0.05))
    sp.append(box("A_DB_SN_TXT", (-9.3, -36.5, DB_TOP + 0.22),
                  (1.2, 9.0, 0.06), "MAT_PRINT_DARK", "LABEL", board_a,
                  bevel=0.02))
    # two small white triangles at the right edge (photo markers)
    for i, (tx, ty) in enumerate(((10.7, -46.0), (17.6, -47.6))):
        sp.append(cyl_at(f"A_DB_TRI_{i}", (tx, ty, DB_TOP + 0.08), 1.1,
                         0.14, "MAT_LABEL_WHITE", "SILKSCREEN_TEXT",
                         board_a, verts=3))
    # sparse SMT on the daughterboard — near top pads and right edge
    rng2 = random.Random(733)
    dfree = [(-8.0, -11.0, 4.0, 2.0), (8.0, -12.0, 5.0, 2.5),
             (12.0, -20.0, 3.0, 6.0), (-8.5, -20.0, 3.0, 4.0),
             (12.0, -44.0, 3.0, 3.0), (-7.0, -45.0, 4.0, 2.0)]
    for i in range(16):
        fx, fy, fw, fd = rng2.choice(dfree)
        px_, py_ = fx + rng2.uniform(-fw / 2, fw / 2), \
            fy + rng2.uniform(-fd / 2, fd / 2)
        s = rng2.uniform(0.5, 1.0)
        sp.append(box(f"A_DB_SMT_{i}", (px_, py_, DB_TOP + 0.15),
                      (s, s * 0.6, 0.3), "MAT_IC_BLACK_MATTE",
                      "SMT_PASSIVE", board_a, bevel=0.05))

    # --- hierarchy -------------------------------------------------------
    asm, groups = build_hierarchy(board_a, board_b)
    moved_a = reparent_existing(board_a, groups, "PCB_A_MAIN_BOARD")
    moved_b = reparent_existing(board_b, groups, "PCB_B_AUXILIARY_BOARD")
    for o in made:  # new parts -> TOP/CONNECTORS of B
        grp = "CONNECTORS" if "CONN_" in o.name else "TOP"
        o.parent = groups[("PCB_B_AUXILIARY_BOARD", grp)]
    # STEP 2 module parts under their own assembly node
    mod_root = make_empty("A_MAIN_BLACK_MODULE",
                          groups[("PCB_A_MAIN_BOARD", "MODULES")])
    for o in mp:
        o.parent = mod_root
    # STEP 3 assemblies under MODULES too
    ant_root = make_empty("A_CERAMIC_PATCH_ANT", mod_root.parent)
    db_root = make_empty("A_COIL_SUBBOARD", mod_root.parent)
    for o in sp:
        o.parent = ant_root if o.name.startswith("A_ANT_") else db_root

    # --- review cameras ---------------------------------------------------
    add_cam("CAM_V41_B_CONN", (-16, -6, 4), (0.75, -0.85, 0.75), 95, 78)
    add_cam("CAM_V41_B_POWER", (7, -7, 4), (0.65, -0.8, 0.8), 88, 80)
    add_cam("CAM_V41_B_HERO", (0, 0, 3), (0.55, -0.75, 0.65), 105, 62)
    # STEP 2 module review cams (A-board ref frame)
    add_cam("CAM_V41_A_MOD_TOP", (-2.1, 29.8, 4), (0.12, -0.06, 1), 115,
            80, ref="PCB_A_MAIN_SYSTEM_BOARD")
    add_cam("CAM_V41_A_MOD_34", (-2.1, 29.8, 4), (0.55, -0.72, 0.62),
            115, 70, ref="PCB_A_MAIN_SYSTEM_BOARD")
    add_cam("CAM_V41_A_MOD_CLOSE", (-4, 30, 4), (0.5, -0.72, 0.55),
            68, 88, ref="PCB_A_MAIN_SYSTEM_BOARD")
    # STEP 3 review cams — antenna + coil subboard closeups
    add_cam("CAM_V41_A_ANT", (-22, -31, 3), (0.45, -0.7, 0.7), 80, 85,
            ref="PCB_A_MAIN_SYSTEM_BOARD")
    add_cam("CAM_V41_A_COIL", (2, -30, 3), (0.35, -0.72, 0.72), 100, 68,
            ref="PCB_A_MAIN_SYSTEM_BOARD")

    n = write_registry(board_a, board_b)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT_BLEND))
    print(json.dumps({"blend": str(OUT_BLEND), "new_parts": len(made),
                      "reparented_a": moved_a, "reparented_b": moved_b,
                      "registry_entries": n}))


if __name__ == "__main__":
    main()
