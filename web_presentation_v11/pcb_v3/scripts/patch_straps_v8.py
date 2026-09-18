"""Tether v4 — the anchor is a small post PLANTED on the top cover (deck z=300.1),
strap tip embedded in the post top.  Earlier lugs floated ~7mm above the deck."""
import bpy

host2 = bpy.data.objects["PART_002__UPPER_HOUSING"]
m_cap = bpy.data.materials["MAT_CAP_RUBBER"]

for o in [o for o in bpy.data.objects
          if o.name.startswith("PORT_CAP_") and o.name.endswith(("_STRAP","_LUG"))]:
    bpy.data.objects.remove(o, do_unlink=True)

def place(o):
    mw=o.matrix_world.copy(); o.parent=host2; o.matrix_world=mw; return o

def strap_curve(name, pts, bevel=1.25):
    cu=bpy.data.curves.new(name,'CURVE'); cu.dimensions='3D'
    cu.bevel_depth=bevel; cu.bevel_resolution=3; cu.resolution_u=12
    sp=cu.splines.new('BEZIER'); sp.bezier_points.add(len(pts)-1)
    for bp,co in zip(sp.bezier_points,pts):
        bp.co=co; bp.handle_left_type='AUTO'; bp.handle_right_type='AUTO'
    o=bpy.data.objects.new(name,cu); bpy.context.collection.objects.link(o)
    cu.materials.append(m_cap); return place(o)

def cyl(r,d,loc,name):
    bpy.ops.mesh.primitive_cylinder_add(vertices=32,radius=r,depth=d,location=loc)
    o=bpy.context.active_object; o.name=name; o.data.materials.append(m_cap)
    for f in o.data.polygons: f.use_smooth=True
    return place(o)

for i,(cx,cy,s) in enumerate(((144.7,52.6,+1),(46.8,116.5,-1)),1):
    ax, ay = cx + s*14.6, cy + 0.8
    # post: deck 300.1 -> top 309.2  (r=2.5 rubber boss)
    cyl(2.5, 9.3, (ax, ay, 304.6), f"PORT_CAP_{i:02d}_LUG")
    # strap: cap rim -> over edge -> down into the post top
    strap_curve(f"PORT_CAP_{i:02d}_STRAP", [
        (cx + s*9.4,  cy,        313.1),
        (cx + s*12.4, cy + 0.3,  311.8),
        (ax,           ay,        310.2),
        (ax,           ay,        308.6),   # inside the post top
    ])

bpy.context.view_layer.update()
bpy.ops.wm.save_mainfile()
print("saved")
