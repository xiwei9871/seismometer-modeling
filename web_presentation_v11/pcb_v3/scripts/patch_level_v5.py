"""Bubble level v2 — photo-faithful: brushed-metal bezel, glossy domed green
face with dark concentric target rings + centre dot, NO glass cover (EEVEE
renders transmission frosted). Surface-mounted at (30,64) on open deck."""
import bpy

def pmat(name, rgb, metal, rough):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1.0)
    b.inputs["Metallic"].default_value = metal
    b.inputs["Roughness"].default_value = rough
    return m

for o in [o for o in bpy.data.objects if o.name.startswith("LEVEL_")]:
    bpy.data.objects.remove(o, do_unlink=True)

host2 = bpy.data.objects["PART_002__UPPER_HOUSING"]
def place(obj):
    mw = obj.matrix_world.copy(); obj.parent = host2; obj.matrix_world = mw
    return obj

def cyl(r, d, loc, mat, name, verts=48):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=d, location=loc)
    o = bpy.context.active_object; o.name = name; o.data.materials.append(mat)
    for f in o.data.polygons: f.use_smooth = True
    return place(o)

def torus(R, r, loc, mat, name):
    bpy.ops.mesh.primitive_torus_add(major_radius=R, minor_radius=r,
        major_segments=48, minor_segments=10, location=loc)
    o = bpy.context.active_object; o.name = name; o.data.materials.append(mat)
    return place(o)

LX, LY = 30.0, 64.0
m_bezel = pmat("MAT_LEVEL_BEZEL", (0.55, 0.57, 0.60), 0.85, 0.30)
m_liq   = pmat("MAT_LEVEL_LIQ",   (0.42, 0.68, 0.05), 0.0, 0.12)   # bright green, glossy
m_mark  = pmat("MAT_LEVEL_MARK",  (0.08, 0.12, 0.02), 0.0, 0.5)
m_bub   = pmat("MAT_LEVEL_BUB",   (0.75, 0.92, 0.35), 0.0, 0.1)

# bezel: stepped cup — outer r9.8 base + r8.4 lip, ~3.2 proud of deck(300.1)
cyl(9.8, 2.2, (LX, LY, 301.2), m_bezel, "LEVEL_BEZEL")
torus(8.7, 1.1, (LX, LY, 302.6), m_bezel, "LEVEL_BEZEL_LIP")

# domed liquid face: flattened UV sphere poking through bezel mouth
bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=7.9,
                                     location=(LX, LY, 298.6))
liq = bpy.context.active_object; liq.name = "LEVEL_LIQUID"
liq.scale.z = 0.55                              # dome top ≈ 298.6+7.9*.55=302.9
bpy.ops.object.transform_apply(scale=True)
liq.data.materials.append(m_liq)
for f in liq.data.polygons: f.use_smooth = True
place(liq)

# target rings + centre dot painted just above the dome
torus(4.9, 0.45, (LX, LY, 302.75), m_mark, "LEVEL_RING_OUT")
torus(2.4, 0.42, (LX, LY, 302.95), m_mark, "LEVEL_RING_IN")
cyl(1.0, 0.5, (LX, LY, 303.05), m_mark, "LEVEL_DOT")
# trapped bubble — small pale disc inside the rings, slightly off-centre
cyl(1.5, 0.5, (LX+1.6, LY+0.9, 302.95), m_bub, "LEVEL_BUBBLE")

bpy.context.view_layer.update()
bpy.ops.wm.save_mainfile()
print("saved")
