"""Fix transforms of the appended hardware parts: restore each part's original
world location (from stage01_split.blend), then parent with matrix_parent_inverse
so the world transform is preserved exactly.
"""
import bpy, json

SPLIT = "/Users/xiwei/modeling/output/stage01_split.blend"

# 1. read original world locations from the split file
with bpy.data.libraries.load(SPLIT) as (src, dst):
    dst.objects = [n for n in src.objects if n.startswith("PART_")]
orig = {}
tmp = [o for o in dst.objects if o]
for o in tmp:
    orig[o.name.split(".")[0]] = tuple(o.location)          # unparented in split -> location == world
locs = {k: v for k, v in orig.items() if k >= "PART_023"}
# drop the temp datablocks
for o in tmp:
    bpy.data.objects.remove(o)

def host_of(name):
    n = int(name[5:])
    if n in (24, 25): return "PART_005"
    if n in (36, 37, 38, 39): return "PART_003"
    if n in (26, 27, 28, 29, 42, 43): return "PART_001"
    if n in (52, 53, 55, 59, 60, 64): return "PART_006"
    return "PART_002"

hosts = {}
fixed = 0
for o in bpy.data.objects:
    nm = o.name.split("__")[0]
    if nm not in locs:
        continue
    h = hosts.get(nm and host_of(o.name))
    hn = host_of(o.name)
    h = hosts.get(hn) or next((x for x in bpy.data.objects if x.name.startswith(hn)), None)
    hosts[hn] = h
    o.parent = None
    o.matrix_parent_inverse.identity()
    o.location = locs[nm]
    o.rotation_euler = (0.0, 0.0, 0.0)
    o.scale = (1.0, 1.0, 1.0)
    if h:
        o.parent = h
        o.matrix_parent_inverse = h.matrix_world.inverted()
    fixed += 1

bpy.context.view_layer.update()
print("fixed:", fixed)
for nm in ("PART_073", "PART_044", "PART_030", "PART_023"):
    o = bpy.data.objects.get(nm)
    vs = [o.matrix_world @ v.co for v in o.data.vertices]
    xs=[v.x for v in vs]; ys=[v.y for v in vs]; zs=[v.z for v in vs]
    print(nm, "world x %.1f..%.1f y %.1f..%.1f z %.1f..%.1f" % (min(xs),max(xs),min(ys),max(ys),min(zs),max(zs)))
bpy.ops.wm.save_mainfile()
print("saved")
