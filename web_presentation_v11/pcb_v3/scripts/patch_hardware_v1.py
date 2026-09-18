"""Import the 60 missing small parts (PART_023..082, excl. 019) from
stage01_split.blend into device_master.blend and parent each to its host
part so they ride along in explode/inspect but stay non-interactive.

Also adds: bubble level vial in the top-cover recess (34.2, 85.2) and
tethered rubber caps over the two interface ports.

Run: blender -b device_master.blend --python scripts/patch_hardware_v1.py
"""
import bpy

SPLIT = "/Users/xiwei/modeling/output/stage01_split.blend"

# --- 1. append missing parts -------------------------------------------------
present = {o.name.split("__")[0] for o in bpy.data.objects if o.name.startswith("PART_")}
want = [f"PART_{i:03d}" for i in range(23, 83) if f"PART_{i:03d}" not in present]

with bpy.data.libraries.load(SPLIT) as (src, dst):
    dst.objects = [n for n in src.objects if n in want]
linked = [o for o in dst.objects if o]
print("appended:", len(linked))

# --- 2. parent to host parts (world transform preserved) ---------------------
def host_of(name):
    n = int(name[5:])
    if n in (24, 25):
        return "PART_005"                       # inside the handle legs
    if n in (36, 37, 38, 39):
        return "PART_003"                       # inside the sensor fixture
    if n in (26, 27, 28, 29, 42, 43):
        return "PART_001"                       # bay plates / side strips
    if n in (52, 53, 55, 59, 60, 64):
        return "PART_006"                       # deep internal screws (z~262)
    if 44 <= n <= 72:
        return "PART_002"                       # top-cover screws (z~286)
    return "PART_002"                           # 023,030-035,040,041,073-082

hosts = {}
for o in linked:
    hn = host_of(o.name)
    h = hosts.get(hn) or next(
        (x for x in bpy.data.objects if x.name.startswith(hn)), None)
    hosts[hn] = h
    mw = o.matrix_world.copy()
    o.parent = h
    o.matrix_world = mw
    # plain hardware: rendered + picks with its host, never a semantic entity
    o["source_type"] = "hardware"
    o["selectable"] = False

# --- 3. steel look for the fasteners -----------------------------------------
def pmat(name, rgb, metal, rough):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1.0)
    b.inputs["Metallic"].default_value = metal
    b.inputs["Roughness"].default_value = rough
    return m

steel = pmat("MAT_HW_STEEL", (0.42, 0.44, 0.48), 0.9, 0.38)
for o in linked:
    n = int(o.name[5:])
    if n in range(30, 36) or 44 <= n <= 81:     # bolts, screws, pins
        o.data.materials.clear()
        o.data.materials.append(steel)

# --- 4. bubble level vial — surface-mounted on open deck ---------------------
# Photo: metal-bezel green vial on the deck just in front of the handle bar's
# left end, near the PWR/RUN/ERR LEDs.  The STL's deck has no exposed pocket
# (the (34,85) cavity is internal, hidden under the handle leg), so the vial
# sits proud on the deck at (30, 64), deck z=300.1.
m_liq = pmat("MAT_LEVEL_LIQ", (0.42, 0.68, 0.05), 0.0, 0.12)
m_mark = pmat("MAT_LEVEL_MARK", (0.08, 0.12, 0.02), 0.0, 0.5)
m_bub = pmat("MAT_LEVEL_BUB", (0.75, 0.92, 0.35), 0.0, 0.1)
m_bezel = pmat("MAT_LEVEL_BEZEL", (0.55, 0.57, 0.60), 0.85, 0.30)

host2 = bpy.data.objects["PART_002__UPPER_HOUSING"]

def place(obj, world=None):
    mw = obj.matrix_world.copy()
    obj.parent = host2
    obj.matrix_world = mw

def cyl(r, d, loc, mat, name, verts=48):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=d,
                                        location=loc)
    o = bpy.context.active_object
    o.name = name
    o.data.materials.append(mat)
    for f in o.data.polygons:
        f.use_smooth = True
    place(o)
    return o

def ring(R, r, loc, mat, name):
    bpy.ops.mesh.primitive_torus_add(major_radius=R, minor_radius=r,
                                     major_segments=48, minor_segments=10,
                                     location=loc)
    o = bpy.context.active_object
    o.name = name
    o.data.materials.append(mat)
    place(o)
    return o

# bubble-level vial seated INSIDE the real circular recess at (148,116):
# pocket ~26mm dia in PART_002, floor z=290.1, deck z=300.1.  Metal body
# fills the pocket wall-to-wall; green face covers it with only a ~1mm
# metal edge + hairline rim on the seam, per the reference photo.
LX, LY = 148.0, 116.0
cyl(12.5, 9.45, (LX, LY, 294.83), m_bezel, "LEVEL_BODY")   # top 299.55
cyl(11.7, 0.55, (LX, LY, 299.83), m_liq, "LEVEL_LIQUID")   # top 300.10
ring(12.35, 0.85, (LX, LY, 300.35), m_bezel, "LEVEL_BEZEL")
ring(6.5, 0.5, (LX, LY, 300.15), m_mark, "LEVEL_RING_OUT")
ring(3.2, 0.45, (LX, LY, 300.22), m_mark, "LEVEL_RING_IN")
cyl(1.2, 0.45, (LX, LY, 300.25), m_mark, "LEVEL_DOT")
cyl(2.0, 0.45, (LX + 2.4, LY + 1.2, 300.2), m_bub, "LEVEL_BUBBLE")

# --- 4b. PWR/RUN/ERR indicator lenses on the front deck ----------------------
# three lens bumps exist in the source STL at y~52.7; these domes sit on them
# and carry the emission-capable material the web app blinks.
m_led = pmat("MAT_LED", (0.05, 0.05, 0.05), 0.0, 0.25)
_b = m_led.node_tree.nodes["Principled BSDF"]
if "Emission Color" in _b.inputs:
    _b.inputs["Emission Color"].default_value = (0.0, 0.0, 0.0, 1.0)
    _b.inputs["Emission Strength"].default_value = 0.0
for _i, _x in enumerate([37.7, 42.8, 48.0], 1):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16,
                                         radius=1.55, location=(_x, 52.7, 300.0))
    _o = bpy.context.active_object
    _o.name = f"LED_{_i:02d}"
    _o.scale.z = 0.42
    bpy.ops.object.transform_apply(scale=True)   # dome top ~300.65
    _o.data.materials.append(m_led)
    for _f in _o.data.polygons:
        _f.use_smooth = True
    place(_o)

# --- 5. tethered dust caps over the two interface ports ----------------------
# connector cap centres measured from source geometry, top z=311.6;
# tether = continuous curved strap from the cap rim down to an anchor lug on
# the port's surround flange (top ~307.6)
m_cap = pmat("MAT_CAP_RUBBER", (0.035, 0.035, 0.04), 0.0, 0.75)
m_cap_edge = pmat("MAT_CAP_RUBBER_E", (0.10, 0.10, 0.11), 0.0, 0.6)


def strap_curve(name, pts, bevel=1.25):
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions = '3D'
    cu.bevel_depth = bevel
    cu.bevel_resolution = 3
    cu.resolution_u = 12
    sp = cu.splines.new('BEZIER')
    sp.bezier_points.add(len(pts) - 1)
    for bp, co in zip(sp.bezier_points, pts):
        bp.co = co
        bp.handle_left_type = 'AUTO'
        bp.handle_right_type = 'AUTO'
    o = bpy.data.objects.new(name, cu)
    bpy.context.collection.objects.link(o)
    cu.materials.append(m_cap)
    place(o)


for i, (cx, cy, s) in enumerate(((144.7, 52.6, +1), (46.8, 116.5, -1)), 1):
    cyl(10.2, 3.4, (cx, cy, 313.3), m_cap, f"PORT_CAP_{i:02d}")
    ring(10.0, 0.9, (cx, cy, 314.6), m_cap_edge, f"PORT_CAP_{i:02d}_LIP")
    # short fat link — both ends embedded (inside cap rim / inside the post)
    ax, ay = cx + s * 14.6, cy + 0.8
    strap_curve(f"PORT_CAP_{i:02d}_STRAP", [
        (cx + s * 9.4, cy, 313.1),
        (cx + s * 12.4, cy + 0.3, 311.8),
        (ax, ay, 310.2),
        (ax, ay, 308.6),
    ])
    # anchor post planted on the top cover (deck z=300.1 -> top 309.2)
    cyl(2.5, 9.3, (ax, ay, 304.6), m_cap, f"PORT_CAP_{i:02d}_LUG")

bpy.context.view_layer.update()
bpy.ops.wm.save_mainfile()
print("saved — objects:", len(bpy.data.objects))
