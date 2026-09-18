"""Fix bubble level (surface-mounted on open deck at 30,64 — photo position,
left of the handle bar's left end) and align tethered dust caps to the real
connector caps PART_017 (144.7,52.6) / PART_018 (46.8,116.5), top z=311.6."""
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

# --- drop previous attempts -------------------------------------------------
for o in [o for o in bpy.data.objects if o.name.startswith(("LEVEL_","PORT_CAP_"))]:
    bpy.data.objects.remove(o, do_unlink=True)

host2 = bpy.data.objects["PART_002__UPPER_HOUSING"]

def place(obj):
    mw = obj.matrix_world.copy()
    obj.parent = host2
    obj.matrix_world = mw
    return obj

def cyl(r, d, loc, mat, name, smooth=True, verts=40):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=d, location=loc)
    o = bpy.context.active_object; o.name = name
    o.data.materials.append(mat)
    if smooth:
        for f in o.data.polygons: f.use_smooth = True
    return place(o)

def torus(R, r, loc, mat, name):
    bpy.ops.mesh.primitive_torus_add(major_radius=R, minor_radius=r,
        major_segments=40, minor_segments=10, location=loc)
    o = bpy.context.active_object; o.name = name
    o.data.materials.append(mat)
    return place(o)

# === bubble level — surface-mounted vial at (30, 64), deck z=300.1 ===========
LX, LY = 30.0, 64.0
m_bezel = pmat("MAT_LEVEL_BEZEL", (0.55, 0.57, 0.60), 0.85, 0.30)   # brushed metal
m_liq   = pmat("MAT_LEVEL_LIQ",   (0.35, 0.62, 0.06), 0.0, 0.18)   # yellow-green
m_mark  = pmat("MAT_LEVEL_MARK",  (0.10, 0.14, 0.03), 0.0, 0.55)   # dark rings
m_glass = bpy.data.materials.get("MAT_LEVEL_GLASS") or bpy.data.materials.new("MAT_LEVEL_GLASS")
m_glass.use_nodes = True
gb = m_glass.node_tree.nodes["Principled BSDF"]
gb.inputs["Base Color"].default_value = (0.9, 0.95, 0.95, 1.0)
gb.inputs["Roughness"].default_value = 0.08
gb.inputs["Metallic"].default_value = 0.0
gb.inputs["Transmission Weight"].default_value = 0.92
gb.inputs["IOR"].default_value = 1.46

# bezel cup: r=9.5, sits on deck, 3.0 proud
cyl(9.5, 3.0, (LX, LY, 301.6), m_bezel, "LEVEL_BEZEL")
# green liquid face r=7.6 at z=302.4 (inside bezel lip)
cyl(7.6, 1.6, (LX, LY, 302.2), m_liq, "LEVEL_LIQUID")
# two concentric target rings + centre dot on the face (like the photo)
torus(4.6, 0.42, (LX, LY, 303.0), m_mark, "LEVEL_RING_OUT")
torus(2.2, 0.40, (LX, LY, 303.0), m_mark, "LEVEL_RING_IN")
cyl(1.0, 0.5, (LX, LY, 303.0), m_mark, "LEVEL_DOT")
# tiny trapped bubble, off-centre highlight
cyl(1.3, 0.4, (LX+2.4, LY+1.2, 302.9), m_liq, "LEVEL_BUBBLE")
# glass cover disc, flush with bezel top
cyl(7.9, 0.9, (LX, LY, 303.1), m_glass, "LEVEL_GLASS")

# === tethered dust caps on the two connectors ================================
m_cap = pmat("MAT_CAP_RUBBER", (0.035, 0.035, 0.04), 0.0, 0.75)
m_cap_edge = pmat("MAT_CAP_RUBBER_E", (0.10, 0.10, 0.11), 0.0, 0.6)

# (cx, cy, strap direction sign in x)
for i, (cx, cy, s) in enumerate(((144.7, 52.6, +1), (46.8, 116.5, -1)), 1):
    # cap puck over the connector mouth (top z=311.6), rubber
    cyl(10.2, 3.4, (cx, cy, 313.3), m_cap, f"PORT_CAP_{i:02d}")
    # grip ridge around cap edge
    torus(10.0, 0.9, (cx, cy, 314.6), m_cap_edge, f"PORT_CAP_{i:02d}_LIP")
    # hinge tab + tether strap toward deck edge
    cyl(1.8, 2.2, (cx + s*10.4, cy, 312.4), m_cap, f"PORT_CAP_{i:02d}_HINGE")
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(cx + s*13.5, cy, 306.0))
    st = bpy.context.active_object; st.name = f"PORT_CAP_{i:02d}_STRAP"
    st.scale = (2.6, 1.6, 3.6)
    st.rotation_euler[1] = s * 0.35          # lean outward over the rim
    bpy.ops.object.transform_apply(scale=True, rotation=True)
    st.data.materials.append(m_cap)
    place(st)

bpy.context.view_layer.update()
bpy.ops.wm.save_mainfile()
print("saved — objects:", len(bpy.data.objects))
