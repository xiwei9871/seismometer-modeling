"""STEP 6 — build the Web Asset Master (EXPORT_SOURCE).

Assembles the canonical device master:
  story-scene device parts (PART_*) + hero PCB presentation from
  pcb_v44_lookdev.blend, organised under the semantic SYS_* hierarchy with
  per-node extras. Story-only objects (cameras/lights/annotations/animations
  and the PCB_COMP_* placeholders + PART_019 proxy) are removed.

Run: blender -b --python scripts/build_master_asset.py
"""
import json
import math
import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
STORY = ROOT.parents[1] / "stage_10V2_product_story" / "scene" / "product_story_v2.blend"
V44 = ROOT / "pcb_v44_lookdev.blend"
OUT = ROOT / "web_asset" / "EXPORT_SOURCE" / "device_master.blend"
MANIFEST = ROOT.parents[1] / "stage_10V2_product_story" / "web-v1" / "manifest_v1.json"

PART_TO_SYS = {  # semantic_map.SYSTEMS
    "SYS_TOP": ("PART_002", "PART_004", "PART_005", "PART_017", "PART_018"),
    "SYS_ACQUISITION": ("PART_006", "PART_007"),
    "SYS_POWER": ("PART_008", "PART_009", "PART_010", "PART_011",
                  "PART_015", "PART_016"),
    "SYS_SENSOR": ("PART_003", "PART_012", "PART_013", "PART_014"),
    "SYS_FIELD_PLATFORM": ("PART_001", "PART_020", "PART_021", "PART_022"),
}

COMP = {  # semantic_map.COMPONENTS (id, name, role)
    "PART_001": ("CMP_LOWER_HOUSING", "Lower Housing", "SECONDARY"),
    "PART_002": ("CMP_UPPER_HOUSING", "Upper Housing", "SECONDARY"),
    "PART_003": ("CMP_SENSOR_FIXTURE", "Sensor Fixture", "PRIMARY"),
    "PART_004": ("CMP_TOP_COVER", "Top Cover", "SECONDARY"),
    "PART_005": ("CMP_HANDLE", "Carry Handle", "SECONDARY"),
    "PART_006": ("CMP_PCB_PROTECTIVE_PLATE", "PCB Protective Plate", "SUPPORT"),
    "PART_007": ("CMP_PCB_CONNECTING_FRAME", "PCB Connecting Frame", "SUPPORT"),
    "PART_008": ("CMP_CELL_01", "Cell 01", "PRIMARY"),
    "PART_009": ("CMP_CELL_02", "Cell 02", "PRIMARY"),
    "PART_010": ("CMP_CELL_03", "Cell 03", "PRIMARY"),
    "PART_011": ("CMP_CELL_04", "Cell 04", "PRIMARY"),
    "PART_012": ("CMP_SENSOR_X", "Sensing Core X", "HERO"),
    "PART_013": ("CMP_SENSOR_Y", "Sensing Core Y", "HERO"),
    "PART_014": ("CMP_SENSOR_Z", "Sensing Core Z", "HERO"),
    "PART_015": ("CMP_CELL_05", "Cell 05", "PRIMARY"),
    "PART_016": ("CMP_CELL_06", "Cell 06", "PRIMARY"),
    "PART_017": ("CMP_INTERFACE_PORT_01", "Interface Port A", "SUPPORT"),
    "PART_018": ("CMP_INTERFACE_PORT_02", "Interface Port B", "SUPPORT"),
    "PART_020": ("CMP_LEVELING_01", "Leveling Cone 01", "SUPPORT"),
    "PART_021": ("CMP_LEVELING_02", "Leveling Cone 02", "SUPPORT"),
    "PART_022": ("CMP_LEVELING_03", "Leveling Cone 03", "SUPPORT"),
}
PRIORITY = {"HERO": 100, "PRIMARY": 70, "SECONDARY": 40, "SUPPORT": 15,
            "DETAIL": 5, "HIDDEN": 0}

PCB_A_TARGET = (95.7, 84.5, 274.7)      # PART_019 origin = board centre plane
# B board: stacked mezzanine inside the housing — above the protective plate
# (z~264) and below the A board bottom (z~273.9). Hidden in overview, slides
# out to its own inspect spot via the manifest.
# B is a mezzanine board bolted to A's underside, centred on A's bbox
# centre (103,85). Its subtree geometry carries a (0,-80.7,-1.6) offset
# from the root origin, so the origin lands off-board at y=165.7.
# z puts B's slab (264.6-266.2) in the gap between the protective-plate
# top (~264) and A's underside components (269.1); B's bottom caps hang
# below the plate plane through its cutouts.
PCB_B_TARGET = (103.0, 165.7, 265.4)
CELL_PARTS = ("PART_008", "PART_009", "PART_010",
              "PART_011", "PART_015", "PART_016")


def die(msg):
    print("[master] FATAL:", msg)
    sys.exit(1)


def subtree(root):
    out, q = [], [root]
    while q:
        r = q.pop()
        out.append(r)
        q.extend(r.children)
    return out


def mk_empty(name, parent=None):
    e = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(e)
    e.parent = parent
    return e


def main():
    bpy.ops.wm.open_mainfile(filepath=str(STORY))

    # ---- 1. strip story-only objects + animations --------------------------
    kill_prefixes = ("CAM_STORY_", "STORY_LIGHT_", "T10V2_")
    for o in list(bpy.data.objects):
        if o.name.startswith(kill_prefixes) or o.name.startswith("PCB_COMP_"):
            bpy.data.objects.remove(o)
    p19 = bpy.data.objects.get("PART_019__MAIN_PCB")
    if p19:
        bpy.data.objects.remove(p19)
    for o in bpy.data.objects:
        if o.animation_data:
            o.animation_data_clear()
    for act in list(bpy.data.actions):
        bpy.data.actions.remove(act)

    # ---- 2. append ALL v44 objects (most PCB objects live outside the
    # named collection), then drop the non-PCB scene dressing --------------
    with bpy.data.libraries.load(str(V44), link=False) as (src, dst):
        dst.objects = list(src.objects)
    new_objs = [o for o in dst.objects if o is not None]
    for o in new_objs:
        bpy.context.scene.collection.objects.link(o)
    asm = next((o for o in new_objs if o.name == "PCB_ASSEMBLY"), None)
    if asm is None:
        die("PCB_ASSEMBLY not appended")
    for o in new_objs:
        if o.name.startswith(("CAM_", "L43_", "SW_")) or \
                o.name in ("Ground", "V4_FLOOR"):
            bpy.data.objects.remove(o)
    # orphan data purge keeps file lean
    for _ in range(3):
        bpy.ops.outliner.orphans_purge(do_local_ids=True,
                                       do_linked_ids=True, do_recursive=True)

    # ---- 3. drop story leftovers + unmapped accessory strays ----------------
    # SEM_* presentation shells and the stage-01 review fragments (PART_023+,
    # tagged DET_ below) must not reach the runtime asset — they sit at the
    # world origin and read as floating debris.
    for o in list(bpy.data.objects):
        if o.name.startswith("SEM_"):
            bpy.data.objects.remove(o)

    # ---- 4. semantic hierarchy ---------------------------------------------
    man = json.load(open(MANIFEST))
    device = mk_empty("DEVICE_ROOT")
    sys_empties = {}
    for sys_name in PART_TO_SYS:
        sys_empties[sys_name] = mk_empty(sys_name, device)
        e = sys_empties[sys_name]
        e["semanticId"] = sys_name
        e["type"] = "system"
        e["selectable"] = True
        e["hoverable"] = True
        e["focusable"] = True
        e["explodable"] = True
        e["source_type"] = "stl_parts"
        sspec = man["systems"].get(sys_name, {})
        if sspec:
            e["displayName"] = sspec["displayName"]
            e["oneLiner"] = sspec["oneLiner"]

    for sys_name, parts in PART_TO_SYS.items():
        for pid in parts:
            o = next((x for x in bpy.data.objects
                      if x.name.startswith(pid + "__")), None)
            if o is None:
                continue
            o.parent = sys_empties[sys_name]
            sid, disp, role = COMP[pid]
            spec = man["components"].get(pid, {})
            o["semanticId"] = sid
            o["semanticName"] = disp
            o["displayName"] = disp
            o["type"] = "component"
            o["systemId"] = sys_name
            o["sourcePart"] = pid
            o["role"] = role
            o["inspectable"] = bool(spec.get("inspectable", True))
            o["presentationPriority"] = PRIORITY[role]
            o["selectable"] = True
            o["hoverable"] = True
            o["focusable"] = role in ("HERO", "PRIMARY")
            o["explodable"] = True
            o["source_type"] = "stl_part"
            o["confidence"] = "verified"

    # unmapped real parts (PART_023+) are stage-01 review fragments clustered
    # at the world origin — exclude them from the runtime asset entirely
    for o in list(bpy.data.objects):
        if o.name.startswith("PART_") and o.parent not in sys_empties.values():
            bpy.data.objects.remove(o)

    # PCB presentation under SYS_ACQUISITION — the empty itself carries the
    # device-space board offset so board roots stay at their local zeros
    pres = mk_empty("MAIN_PCB_PRESENTATION", sys_empties["SYS_ACQUISITION"])
    pres.location = PCB_A_TARGET                # A lands on PART_019's seat
    pres["semanticId"] = "CMP_MAIN_PCB"
    pres["semanticName"] = "Acquisition Core Board"
    pres["type"] = "component"
    pres["systemId"] = "SYS_ACQUISITION"
    pres["presentationPriority"] = PRIORITY["HERO"]
    pres["selectable"] = True
    pres["hoverable"] = True
    pres["focusable"] = True
    pres["explodable"] = True
    pres["source_type"] = "photographic_presentation_reconstruction"
    pres["sourcePart"] = "PART_019"
    pres["displayName"] = "Acquisition Core Board"
    pres["role"] = "HERO"
    pres["inspectable"] = True

    # A board rides with the presentation node; type=geometry keeps it out of
    # the page's "other components" set while still moving with CMP_MAIN_PCB
    ra = bpy.data.objects.get("PCB_A_MAIN_BOARD")
    if ra is not None:
        ra.location = (0.0, 0.0, 0.0)
        ra.parent = pres
        ra["semanticId"] = "PCB_A"
        ra["semanticName"] = "Main System Board A"
        ra["displayName"] = "Main System Board A"
        ra["type"] = "geometry"
        ra["systemId"] = "SYS_ACQUISITION"
        ra["inspectable"] = True
        ra["presentationPriority"] = PRIORITY["HERO"]
        ra["selectable"] = True
        ra["hoverable"] = True
        ra["focusable"] = True

    # B board is a separate component of SYS_ACQUISITION (own inspect spot)
    rb = bpy.data.objects.get("PCB_B_AUXILIARY_BOARD")
    if rb is not None:
        rb.parent = sys_empties["SYS_ACQUISITION"]
        rb.location = PCB_B_TARGET
        rb["semanticId"] = "PCB_B"
        rb["semanticName"] = "Auxiliary Interface Board B"
        rb["displayName"] = "Auxiliary Interface Board B"
        rb["type"] = "component"
        rb["systemId"] = "SYS_ACQUISITION"
        rb["sourcePart"] = "PCB_B"
        rb["role"] = "PRIMARY"
        rb["inspectable"] = True
        rb["presentationPriority"] = PRIORITY["PRIMARY"]
        rb["selectable"] = True
        rb["hoverable"] = True
        rb["focusable"] = True
        rb["explodable"] = True
        rb["source_type"] = "photographic_presentation_reconstruction"

    # the v44 wrapper empty is now an orphan shell — drop it
    if asm is not None and len(asm.children) == 0:
        bpy.data.objects.remove(asm)

    # tag every remaining PCB-presentation mesh as detail-geometry
    for o in subtree(pres):
        if o.type == 'MESH' and "semanticId" not in o:
            o["semanticId"] = "GEO_" + o.name
            o["type"] = "geometry"
            o["systemId"] = "SYS_ACQUISITION"
            o["presentationPriority"] = 30
            o["selectable"] = True
            o["hoverable"] = True
            o["focusable"] = False
            o["explodable"] = True
            o["source_type"] = "photographic_presentation_reconstruction"
            o["confidence"] = "verified"

    device["semanticId"] = "DEVICE_ROOT"
    device["type"] = "device"
    device["type"] = "device"
    device["displayName"] = "Smart Field Device"

    # ---- 5. 18650 cells inside the battery compartments --------------------
    # Each compartment is a vertical tube; the cell sits at the tube's bbox
    # centre (invisible inside the shell) and slides out on inspection via its
    # own manifest entry (assembled / inspect positions in three.js coords).
    wrap = bpy.data.materials.get("MAT_CELL_WRAP") or bpy.data.materials.new(
        "MAT_CELL_WRAP")
    wrap.use_nodes = True
    wbs = wrap.node_tree.nodes["Principled BSDF"]
    wbs.inputs["Base Color"].default_value = (0.008, 0.185, 0.025, 1.0)
    wbs.inputs["Metallic"].default_value = 0.0
    wbs.inputs["Roughness"].default_value = 0.34
    hold = bpy.data.materials.get("MAT_CELL_HOLDER") or bpy.data.materials.new(
        "MAT_CELL_HOLDER")
    hold.use_nodes = True
    hbs = hold.node_tree.nodes["Principled BSDF"]
    hbs.inputs["Base Color"].default_value = (0.03, 0.03, 0.035, 1.0)
    hbs.inputs["Metallic"].default_value = 0.0
    hbs.inputs["Roughness"].default_value = 0.6
    ink = bpy.data.materials.get("MAT_CELL_INK") or bpy.data.materials.new(
        "MAT_CELL_INK")
    ink.use_nodes = True
    ibs = ink.node_tree.nodes["Principled BSDF"]
    ibs.inputs["Base Color"].default_value = (0.92, 0.93, 0.90, 1.0)
    ibs.inputs["Metallic"].default_value = 0.0
    ibs.inputs["Roughness"].default_value = 0.5
    can = bpy.data.materials.get("MAT_CELL_CAN") or bpy.data.materials.new(
        "MAT_CELL_CAN")
    can.use_nodes = True
    cbs = can.node_tree.nodes["Principled BSDF"]
    cbs.inputs["Base Color"].default_value = (0.62, 0.65, 0.68, 1.0)
    cbs.inputs["Metallic"].default_value = 0.9
    cbs.inputs["Roughness"].default_value = 0.35

    def bbox_centre(obj):
        from mathutils import Vector
        w = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
        return (Vector((min(v[i] for v in w) + max(v[i] for v in w)) / 2
                for i in range(3)))

    cell_manifest = {}
    for idx, pid in enumerate(CELL_PARTS, 1):
        comp = next((x for x in bpy.data.objects
                     if x.name.startswith(pid + "__")), None)
        if comp is None:
            continue
        ctr = bbox_centre(comp)          # tube interior centre (blender)
        cid = f"CELL_18650_{idx:02d}"
        # cell body
        bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=9.0,
                                          depth=64.0,
                                          location=(ctr.x, ctr.y, ctr.z))
        body = bpy.context.active_object
        body.name = cid
        body.data.materials.append(wrap)
        for p in body.data.polygons:
            p.use_smooth = True
        body.parent = sys_empties["SYS_POWER"]
        body["semanticId"] = cid
        body["displayName"] = f"18650 Cell {idx:02d}"
        body["type"] = "geometry"
        body["systemId"] = "SYS_POWER"
        body["sourcePart"] = cid
        body["inspectable"] = True
        body["selectable"] = True
        body["hoverable"] = True
        # positive terminal stack: steel crimp shoulder over the wrap edge,
        # black insulator ring, proud button — the "18650" top signature
        bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=9.2,
                                            depth=1.7)
        cr = bpy.context.active_object
        cr.name = cid + "_CRIMP"
        cr.data.materials.append(can)
        cr.parent = body
        cr.location = (0.0, 0.0, 31.4)
        bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=5.4,
                                            depth=1.2)
        ins = bpy.context.active_object
        ins.name = cid + "_INSUL"
        ins.data.materials.append(hold)
        ins.parent = body
        ins.location = (0.0, 0.0, 32.6)
        bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=2.6,
                                            depth=2.4)
        cap = bpy.context.active_object
        cap.name = cid + "_BTN"
        cap.data.materials.append(can)
        cap.parent = body
        cap.location = (0.0, 0.0, 33.8)   # local offset, not world coords
        # bare steel negative band where the wrap stops short of the base
        bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=9.05,
                                          depth=2.2)
        neg = bpy.context.active_object
        neg.name = cid + "_NEG"
        neg.data.materials.append(can)
        neg.parent = body
        neg.location = (0.0, 0.0, -30.6)
        # holder ring at base
        bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=10.2,
                                          depth=6.0)
        hld = bpy.context.active_object
        hld.name = cid + "_HOLDER"
        hld.data.materials.append(hold)
        hld.parent = body
        hld.location = (0.0, 0.0, -29.0)
        # printed wrap marking, like a real 18650 (big type + polarity marks)
        ang = math.atan2(ctr.y - 84.5, ctr.x - 95.7)
        dx, dy = math.cos(ang), math.sin(ang)
        for txt, zoff, sc in (("18650", 4.0, 1.6), ("Li-ion 3.7V", -3.5, 0.85),
                              ("+", 25.5, 1.75), ("\u2212", -25.0, 1.75)):
            bpy.ops.object.text_add()
            t = bpy.context.active_object
            t.name = cid + "_PRINT"
            t.data.body = txt
            t.data.size = 4.0 * sc
            t.data.align_x = 'CENTER'
            t.data.align_y = 'CENTER'
            t.data.extrude = 0.02
            t.data.materials.append(ink)
            t.parent = body
            t.location = (dx * 8.9, dy * 8.9, zoff)
            t.rotation_euler = (math.radians(90), 0, ang + math.radians(90))
        # three.js-space manifest positions
        cell_manifest[cid] = {
            "assembled": [round(ctr.x, 2), round(ctr.z, 2), round(-ctr.y, 2)],
            "inspect": None,              # filled below from compartment spec
            "displayName": f"18650 Cell {idx:02d}",
            "inspectable": True,
            "role": "PRIMARY",
            "semanticId": cid,
            "systemId": "SYS_POWER",
        }
        cspec = man["components"].get(pid)
        if cspec and cspec.get("inspect"):
            cell_manifest[cid]["inspect"] = [
                cspec["inspect"][0], cspec["inspect"][1] + 30.0,
                cspec["inspect"][2]]

    (ROOT / "web_asset" / "cells_manifest.json").write_text(
        json.dumps(cell_manifest, indent=2))

    # ---- 6. leveling cones are machined brass/copper feet -------------------
    copper = bpy.data.materials.get("MAT_COPPER") or bpy.data.materials.new(
        "MAT_COPPER")
    copper.use_nodes = True
    cbs2 = copper.node_tree.nodes["Principled BSDF"]
    cbs2.inputs["Base Color"].default_value = (0.55, 0.27, 0.12, 1.0)
    cbs2.inputs["Metallic"].default_value = 0.95
    cbs2.inputs["Roughness"].default_value = 0.32
    for o in bpy.data.objects:
        if any(o.name.startswith(p + "__")
               for p in ("PART_020", "PART_021", "PART_022")) \
                and o.type == 'MESH':
            if o.data.materials:
                o.data.materials[0] = copper
            else:
                o.data.materials.append(copper)

    # ---- 6b. tag the edge module as the WiFi/RF front-end (rides the board) -
    mod = bpy.data.objects.get("A_EDGE_MODULE")
    if mod is not None:
        for k, v in {"semanticId": "WIFI_MODULE", "displayName": "WiFi Module",
                     "type": "geometry", "systemId": "SYS_ACQUISITION",
                     "role": "PRIMARY", "hoverable": True,
                     "presentationPriority": 20,
                     "source_type": "presentation_reconstruction",
                     "confidence": 0.9}.items():
            mod[k] = v

    # ---- 7. WiFi antenna: stub whip parked inside the handle arch -----------
    def pmat(name, rgb, metal, rough):
        m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
        m.use_nodes = True
        b = m.node_tree.nodes["Principled BSDF"]
        b.inputs["Base Color"].default_value = (*rgb, 1.0)
        b.inputs["Metallic"].default_value = metal
        b.inputs["Roughness"].default_value = rough
        return m

    m_rad = pmat("MAT_ANT_BLACK", (0.02, 0.02, 0.025), 0.0, 0.55)
    m_cox = pmat("MAT_COAX", (0.35, 0.35, 0.38), 0.4, 0.5)
    m_cua = pmat("MAT_COPPER_ANT", (0.72, 0.45, 0.20), 0.9, 0.35)

    sysT = bpy.data.objects.get("SYS_TRANSMISSION")
    if sysT is None:
        sysT = mk_empty("SYS_TRANSMISSION", device)
        sysT["semanticId"] = "SYS_TRANSMISSION"
        sysT["type"] = "system"
        sysT["displayName"] = "Transmission"
    ant = bpy.data.objects.new("WIFI_ANTENNA", None)
    bpy.context.collection.objects.link(ant)
    ant.parent = sysT
    ant.location = (40.0, 84.5, 331.0)      # whip centre, sealed inside handle leg
    for nm, d, m_, lz in (("WIFI_ANT_WHIP", (24, 3.4, 26.0), m_rad, 0.0),
                          ("WIFI_ANT_BASE", (24, 4.2, 4.0), m_cua, -15.0),
                          ("WIFI_ANT_COAX", (12, 1.0, 14.0), m_cox, -25.0)):
        bpy.ops.mesh.primitive_cylinder_add(vertices=d[0], radius=d[1],
                                            depth=d[2])
        p = bpy.context.active_object
        p.name = nm
        p.data.materials.append(m_)
        for f in p.data.polygons:
            f.use_smooth = True
        p.parent = ant
        p.location = (0.0, 0.0, lz)
    for k, v in {"semanticId": "WIFI_ANTENNA", "semanticName": "WiFi Antenna",
                 "displayName": "WiFi Antenna", "type": "component",
                 "systemId": "SYS_TRANSMISSION", "sourcePart": "WIFI_ANTENNA",
                 "role": "PRIMARY", "inspectable": True, "selectable": True,
                 "hoverable": True, "focusable": True, "explodable": True,
                 "presentationPriority": 30,
                 "source_type": "synthetic_presentation",
                 "confidence": 1.0}.items():
        ant[k] = v

    OUT.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT))
    print(json.dumps({"saved": str(OUT),
                      "objects": len(bpy.data.objects),
                      "meshes": len([o for o in bpy.data.objects
                                     if o.type == 'MESH'])}))


if __name__ == "__main__":
    main()
