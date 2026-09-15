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
    _mat("MAT_CONNECTOR_WHITE", (0.72, 0.70, 0.65), 0.55)      # warm off-white
    _mat("MAT_CONJ_CAVITY", (0.035, 0.033, 0.030), 0.65)       # dark cavity
    _mat("MAT_INDUCTOR_GREY", (0.15, 0.15, 0.17), 0.42, 0.15)  # molded ferrite
    _mat("MAT_TERMINAL_METAL", (0.55, 0.56, 0.60), 0.30, 0.95)
    _mat("MAT_IC_BLACK_MATTE", (0.016, 0.017, 0.020), 0.55, 0.10)


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


def jst_vertical(name, x, y, w, d, h, board, rot=0.0):
    """top-entry JST: housing with a REAL recessed top cavity (boolean),
    pin strip visible at the cavity floor, locking ramp."""
    parts = []
    housing = box(f"{name}_HOUSING", (x, y, TOP_Z + h / 2), (w, d, h),
                  "MAT_CONNECTOR_WHITE", "CONNECTOR", board, bevel=0.4,
                  rot_z=rot, props={"pkg": "VERTICAL"})
    parts.append(housing)
    # real cavity: cut ~1.7mm into the housing top
    cw, cd = w * 0.72, d * 0.55
    _boolean_cut(housing, board, (x, y, TOP_Z + h - 0.85), (cw, cd, 1.7),
                 rot)
    # pin strip at the cavity floor — visible through the opening
    parts.append(box(f"{name}_PINS", (x, y, TOP_Z + h - 1.5),
                     (cw * 0.8, 0.5, 0.9), "MAT_TERMINAL_METAL",
                     "CONNECTOR_PINS", board, bevel=0.08, rot_z=rot))
    # inner cavity floor plate (dark) just under pin level for contrast
    parts.append(box(f"{name}_CAVFLOOR", (x, y, TOP_Z + h - 1.72),
                     (cw, cd, 0.15), "MAT_CONJ_CAVITY",
                     "CONNECTOR_CAVITY", board, bevel=0.05, rot_z=rot))
    # locking ramp: small wedge on the -d side, tilted
    ramp = box(f"{name}_RAMP",
               (x - math.sin(rot) * -(d / 2 - 0.4),
                y - math.cos(rot) * -(d / 2 - 0.4), TOP_Z + h - 0.9),
               (w * 0.45, 0.8, 1.4), "MAT_CONNECTOR_WHITE",
               "CONNECTOR_LOCK", board, bevel=0.12, rot_z=rot)
    ramp.rotation_euler.x = math.radians(-18)
    parts.append(ramp)
    return parts


def jst_right_angle(name, x, y, w, d, h, board, rot=0.0):
    """side-entry JST: real cavity cut into the outward (+x local) face,
    horizontal pin strip visible inside it."""
    parts = []
    housing = box(f"{name}_HOUSING", (x, y, TOP_Z + h / 2), (w, d, h),
                  "MAT_CONNECTOR_WHITE", "CONNECTOR", board, bevel=0.35,
                  rot_z=rot, props={"pkg": "RIGHT_ANGLE"})
    parts.append(housing)
    # cavity opening on the outward face
    fx = w / 2 - 0.7
    cx, cy = x + math.cos(rot) * fx, y + math.sin(rot) * fx
    _boolean_cut(housing, board, (cx, cy, TOP_Z + h * 0.55),
                 (1.8, d * 0.6, h * 0.45), rot)
    # horizontal pins inside the side cavity
    px = w / 2 - 1.1
    px_, py_ = x + math.cos(rot) * px, y + math.sin(rot) * px
    parts.append(box(f"{name}_PINS", (px_, py_, TOP_Z + h * 0.55),
                     (0.7, d * 0.45, 0.5), "MAT_TERMINAL_METAL",
                     "CONNECTOR_PINS", board, bevel=0.05, rot_z=rot))
    # rear locking tab
    bx = -w / 2 + 0.5
    bx_, by_ = x + math.cos(rot) * bx, y + math.sin(rot) * bx
    parts.append(box(f"{name}_TAB", (bx_, by_, TOP_Z + h - 0.6),
                     (1.4, d * 0.4, 1.0), "MAT_CONNECTOR_WHITE",
                     "CONNECTOR_LOCK", board, bevel=0.1, rot_z=rot))
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
}
CONF = {"CONNECTOR": "HIGH", "MODULE": "HIGH", "ANTENNA": "HIGH",
        "COIL": "HIGH", "INDUCTOR": "MEDIUM", "LARGE_IC": "MEDIUM",
        "COAX_CABLE": "HIGH", "CABLE": "HIGH", "CAPACITOR_LARGE": "MEDIUM",
        "METAL_SHIELD": "MEDIUM", "LABEL": "HIGH", "SMALL_IC": "LOW",
        "RESISTOR_CAPACITOR_CLUSTER": "LOW"}


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


def add_cam(name, target, direction, dist, lens=75):
    cd = bpy.data.cameras.get(name) or bpy.data.cameras.new(name)
    cd.lens, cd.sensor_width = lens, 36
    cd.dof.use_dof = True
    cd.dof.aperture_fstop = 8.0
    o = bpy.data.objects.get(name) or bpy.data.objects.new(name, cd)
    if o.name not in bpy.context.scene.collection.objects:
        bpy.context.scene.collection.objects.link(o)
    b = bpy.data.objects["PCB_B_AUXILIARY_INTERFACE_BOARD"]
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
    # measured positions/rotations carried over from V4 (registration)
    jsts = [("CONN_B_01", (-11, 14), (15, 7, 5.2), 0.0, "V"),
            ("CONN_B_02", (5.5, 16), (5, 6, 4.8), 0.0, "V"),
            ("CONN_B_03", (-26, -3.5), (6, 11, 4.8), 0.0, "V"),
            ("CONN_B_04", (-11.5, -12), (16, 7, 5.2), -0.4, "RA"),
            ("CONN_B_05", (20.5, 8.75), (9, 6.5, 4.8), -0.5, "RA"),
            ("CONN_B_06", (15, -10), (8.5, 6, 4.8), 0.0, "V"),
            ("CONN_B_07", (4, -22.7), (10, 6.5, 4.8), 0.0, "V")]
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
                           board_b, rot=-0.15)
    made += power_inductor("INDUCTOR_B_6R8", -2.2, -9.6, 6.5, 4, 3.4,
                           board_b)
    made += power_inductor("INDUCTOR_B_03", -3.2, -23, 5.5, 3.5, 3.2,
                           board_b, label=False)

    # --- hierarchy -------------------------------------------------------
    asm, groups = build_hierarchy(board_a, board_b)
    moved_a = reparent_existing(board_a, groups, "PCB_A_MAIN_BOARD")
    moved_b = reparent_existing(board_b, groups, "PCB_B_AUXILIARY_BOARD")
    for o in made:  # new parts -> TOP/CONNECTORS of B
        grp = "CONNECTORS" if "CONN_" in o.name else "TOP"
        o.parent = groups[("PCB_B_AUXILIARY_BOARD", grp)]

    # --- review cameras ---------------------------------------------------
    add_cam("CAM_V41_B_CONN", (-16, -6, 4), (0.75, -0.85, 0.75), 95, 78)
    add_cam("CAM_V41_B_POWER", (7, -7, 4), (0.65, -0.8, 0.8), 88, 80)
    add_cam("CAM_V41_B_HERO", (0, 0, 3), (0.55, -0.75, 0.65), 105, 62)

    n = write_registry(board_a, board_b)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT_BLEND))
    print(json.dumps({"blend": str(OUT_BLEND), "new_parts": len(made),
                      "reparented_a": moved_a, "reparented_b": moved_b,
                      "registry_entries": n}))


if __name__ == "__main__":
    main()
