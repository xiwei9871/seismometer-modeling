"""Re-append PART_023..082 into device_master.blend — this time LINKING each
object into its host's collection before parenting (orphans die on save).
"""
import bpy

SPLIT = "/Users/xiwei/modeling/output/stage01_split.blend"

present = {o.name.split("__")[0] for o in bpy.data.objects if o.name.startswith("PART_")}
want = [f"PART_{i:03d}" for i in range(23, 83) if f"PART_{i:03d}" not in present]

with bpy.data.libraries.load(SPLIT) as (src, dst):
    dst.objects = [n for n in src.objects if n in want]
linked = [o for o in dst.objects if o]
print("appended:", len(linked), "of", len(want))

def host_of(name):
    n = int(name[5:])
    if n in (24, 25):
        return "PART_005"
    if n in (36, 37, 38, 39):
        return "PART_003"
    if n in (26, 27, 28, 29, 42, 43):
        return "PART_001"
    if n in (52, 53, 55, 59, 60, 64):
        return "PART_006"
    if 44 <= n <= 72:
        return "PART_002"
    return "PART_002"

hosts = {}
for o in linked:
    hn = host_of(o.name)
    h = hosts.get(hn)
    if not h:
        h = next((x for x in bpy.data.objects if x.name.startswith(hn)), None)
        hosts[hn] = h
    # LINK FIRST — into the host's own collection — then parent
    col = h.users_collection[0] if (h and h.users_collection) else bpy.context.scene.collection
    if not o.users_collection:
        col.objects.link(o)
    if h:
        mw = o.matrix_world.copy()
        o.parent = h
        o.matrix_world = mw
    o["source_type"] = "hardware"
    o["selectable"] = False

# steel look for fasteners
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
    if n in range(30, 36) or 44 <= n <= 81:
        o.data.materials.clear()
        o.data.materials.append(steel)

bpy.context.view_layer.update()
bpy.ops.wm.save_mainfile()
# verify persistence in THIS session
print("PART_023 in file:", bool(bpy.data.objects.get("PART_023")),
      "| collections:", [c.name for c in bpy.data.objects["PART_023"].users_collection])
print("saved — objects:", len(bpy.data.objects))
