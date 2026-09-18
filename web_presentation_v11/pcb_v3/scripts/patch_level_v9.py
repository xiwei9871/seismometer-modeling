"""Bubble level v3 — seated INSIDE the real circular recess at (148,116):
pocket ~23mm dia, floor z=290.1, deck z=300.1.  Vial = metal body in the
pocket, bezel ring flush at deck level, glossy green domed face ~1mm below
the rim with target rings + off-centre bubble (per reference photo)."""
import bpy

def pmat(name, rgb, metal, rough):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb,1.0)
    b.inputs["Metallic"].default_value = metal
    b.inputs["Roughness"].default_value = rough
    return m

for o in [o for o in bpy.data.objects if o.name.startswith("LEVEL_")]:
    bpy.data.objects.remove(o, do_unlink=True)

host2 = bpy.data.objects["PART_002__UPPER_HOUSING"]
def place(o):
    mw=o.matrix_world.copy(); o.parent=host2; o.matrix_world=mw; return o
def cyl(r,d,loc,mat,name,verts=48):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts,radius=r,depth=d,location=loc)
    o=bpy.context.active_object; o.name=name; o.data.materials.append(mat)
    for f in o.data.polygons: f.use_smooth=True
    return place(o)
def ring(R,r,loc,mat,name):
    bpy.ops.mesh.primitive_torus_add(major_radius=R,minor_radius=r,
        major_segments=48,minor_segments=10,location=loc)
    o=bpy.context.active_object; o.name=name; o.data.materials.append(mat)
    return place(o)

LX,LY = 148.0,116.0
m_bezel = pmat("MAT_LEVEL_BEZEL",(0.55,0.57,0.60),0.85,0.30)
m_liq   = pmat("MAT_LEVEL_LIQ",(0.42,0.68,0.05),0.0,0.12)
m_mark  = pmat("MAT_LEVEL_MARK",(0.08,0.12,0.02),0.0,0.5)
m_bub   = pmat("MAT_LEVEL_BUB",(0.75,0.92,0.35),0.0,0.1)

# vial body in the pocket: r=10.6, floor 290.1 -> top 300.6 (0.5 proud)
cyl(10.6, 10.5, (LX,LY,295.35), m_bezel, "LEVEL_BODY")
# domed green face: flattened sphere, top ~299.4 (0.7 below deck)
bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=9.4,
                                     location=(LX,LY,294.0))
liq=bpy.context.active_object; liq.name="LEVEL_LIQUID"
liq.scale.z=0.58; bpy.ops.object.transform_apply(scale=True)
liq.data.materials.append(m_liq)
for f in liq.data.polygons: f.use_smooth=True
place(liq)
# bezel rim ring at deck level around the pocket mouth
ring(10.3, 1.0, (LX,LY,300.3), m_bezel, "LEVEL_BEZEL")
# target rings + centre dot on the green face (top ~299.45)
ring(5.2, 0.45, (LX,LY,299.45), m_mark, "LEVEL_RING_OUT")
ring(2.5, 0.42, (LX,LY,299.60), m_mark, "LEVEL_RING_IN")
cyl(1.0, 0.5, (LX,LY,299.7), m_mark, "LEVEL_DOT")
# trapped bubble off-centre
cyl(1.5, 0.5, (LX+1.7,LY+0.9,299.6), m_bub, "LEVEL_BUBBLE")

bpy.context.view_layer.update()
bpy.ops.wm.save_mainfile()
print("saved")
