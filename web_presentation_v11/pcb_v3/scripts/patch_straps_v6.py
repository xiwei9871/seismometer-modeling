"""Port-cap tethers v2 — continuous curved rubber strap: cap rim -> arc down ->
anchor lug on the deck beside the connector base.  Replaces the detached box
strap/hinge which read as a floating fragment in overview."""
import bpy
from mathutils import Vector

def pmat(name, rgb, metal, rough):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1.0)
    b.inputs["Metallic"].default_value = metal
    b.inputs["Roughness"].default_value = rough
    return m

# drop the old strap + hinge pieces (keep cap puck + grip lip)
for o in [o for o in bpy.data.objects
          if o.name.startswith("PORT_CAP_") and
          (o.name.endswith("_STRAP") or o.name.endswith("_HINGE"))]:
    bpy.data.objects.remove(o, do_unlink=True)

host2 = bpy.data.objects["PART_002__UPPER_HOUSING"]
m_cap = bpy.data.materials.get("MAT_CAP_RUBBER") or pmat(
    "MAT_CAP_RUBBER", (0.035, 0.035, 0.04), 0.0, 0.75)

def place(o):
    mw = o.matrix_world.copy(); o.parent = host2; o.matrix_world = mw
    return o

def strap_curve(name, pts, bevel=1.05):
    cu = bpy.data.curves.new(name, 'CURVE'); cu.dimensions = '3D'
    cu.bevel_depth = bevel; cu.bevel_resolution = 3; cu.resolution_u = 12
    sp = cu.splines.new('BEZIER'); sp.bezier_points.add(len(pts) - 1)
    for bp, co in zip(sp.bezier_points, pts):
        bp.co = co; bp.handle_left_type = 'AUTO'; bp.handle_right_type = 'AUTO'
    o = bpy.data.objects.new(name, cu)
    bpy.context.collection.objects.link(o)
    cu.materials.append(m_cap)
    return place(o)

def cyl(r, d, loc, name):
    bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=r, depth=d, location=loc)
    o = bpy.context.active_object; o.name = name; o.data.materials.append(m_cap)
    for f in o.data.polygons: f.use_smooth = True
    return place(o)

# cap centres / strap side (+x for the right-hand port, -x for the left one)
for i, (cx, cy, s) in enumerate(((144.7, 52.6, +1), (46.8, 116.5, -1)), 1):
    # strap exits the cap rim at mid-height and arcs down to the deck anchor
    strap_curve(f"PORT_CAP_{i:02d}_STRAP", [
        (cx + s*9.6,  cy,       313.2),   # inside the cap rim
        (cx + s*12.8, cy + 0.4, 312.2),   # out over the edge
        (cx + s*15.0, cy + 1.0, 310.0),   # drape down to the port flange
        (cx + s*15.4, cy + 1.3, 308.6),   # onto the anchor lug
    ])
    # anchor lug on the port's surround flange (flange top ~307.6)
    cyl(2.4, 2.4, (cx + s*15.4, cy + 1.3, 308.6), f"PORT_CAP_{i:02d}_LUG")

bpy.context.view_layer.update()
bpy.ops.wm.save_mainfile()
print("saved")
