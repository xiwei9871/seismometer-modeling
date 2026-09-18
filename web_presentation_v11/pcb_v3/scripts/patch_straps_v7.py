"""Tether v3 — short fat link, strap tip embedded INTO the anchor lug so the
cap->tether->anchor reads as one continuous piece from every angle."""
import bpy

host2 = bpy.data.objects["PART_002__UPPER_HOUSING"]
m_cap = bpy.data.materials["MAT_CAP_RUBBER"]

for o in [o for o in bpy.data.objects
          if o.name.startswith("PORT_CAP_") and o.name.endswith(("_STRAP","_LUG"))]:
    bpy.data.objects.remove(o, do_unlink=True)

def place(o):
    mw = o.matrix_world.copy(); o.parent = host2; o.matrix_world = mw
    return o

def strap_curve(name, pts, bevel=1.25):
    cu = bpy.data.curves.new(name, 'CURVE'); cu.dimensions='3D'
    cu.bevel_depth=bevel; cu.bevel_resolution=3; cu.resolution_u=12
    sp = cu.splines.new('BEZIER'); sp.bezier_points.add(len(pts)-1)
    for bp, co in zip(sp.bezier_points, pts):
        bp.co = co; bp.handle_left_type='AUTO'; bp.handle_right_type='AUTO'
    o = bpy.data.objects.new(name, cu); bpy.context.collection.objects.link(o)
    cu.materials.append(m_cap); return place(o)

def cyl(r,d,loc,name):
    bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=r, depth=d, location=loc)
    o=bpy.context.active_object; o.name=name; o.data.materials.append(m_cap)
    for f in o.data.polygons: f.use_smooth=True
    return place(o)

for i,(cx,cy,s) in enumerate(((144.7,52.6,+1),(46.8,116.5,-1)),1):
    ax, ay = cx + s*14.6, cy + 0.8          # anchor lug centre on the flange
    strap_curve(f"PORT_CAP_{i:02d}_STRAP", [
        (cx + s*9.4,  cy,        313.1),  # embedded inside the cap rim
        (cx + s*12.2, cy + 0.3,  312.0),  # over the rim
        (ax,           ay,        310.0), # down to the lug
        (ax,           ay,        308.9), # tip INSIDE the lug
    ])
    # lug: squat rubber boss fused onto the port flange (flange top ~307.6)
    cyl(2.6, 2.6, (ax, ay, 308.6), f"PORT_CAP_{i:02d}_LUG")

bpy.context.view_layer.update()
bpy.ops.wm.save_mainfile()
print("saved")
