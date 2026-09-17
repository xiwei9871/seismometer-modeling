"""v44 surgical update: rebuild PCB_A mesh from corrected board_mesh.json
inside the frozen v43 lookdev file, refresh packed TEX42 images, and remove
scatter passives that now land inside the corrected holes.

Run: blender -b --python scripts/build_v44.py
"""
import json
import math
import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "pcb_v43_lookdev.blend"
DST = ROOT / "pcb_v44_lookdev.blend"
BMESH = json.loads((ROOT / "registration" / "board_mesh.json").read_text())
BOARD_T = 1.6

A_HOLES = [(-45.6, 2.6, 3.0), (47.8, -12.8, 3.1), (46.0, 3.2, 2.9),
           (32.9, -24.4, 5.0),
           (-39.0, 38.0, 2.0), (-26.7, 42.7, 2.2), (23.0, 44.0, 2.2),
           (43.0, 29.0, 2.0),
           (-46.0, -22.0, 2.0), (-24.0, -42.0, 2.2), (28.1, -43.7, 2.2),
           (-29.3, -48.2, 2.2)]


def rebuild_board(obj, geom_key):
    g = BMESH[geom_key]
    v2, ends, tris = g["verts"], g["ring_ends"], g["tris"]
    n = len(v2)
    zt, zb = BOARD_T / 2, -BOARD_T / 2
    verts = [(x, y, zt) for x, y in v2] + [(x, y, zb) for x, y in v2]
    faces = []
    for i in range(0, len(tris), 3):
        a, b, c = tris[i], tris[i + 1], tris[i + 2]
        faces.append((a, b, c))
        faces.append((a + n, c + n, b + n))
    starts = [0] + ends[:-1]
    for s0, e0 in zip(starts, ends):
        for i in range(s0, e0):
            j = s0 + (i + 1 - s0) % (e0 - s0)
            faces.append((i, j, j + n, i + n))

    me = bpy.data.meshes.new(obj.data.name + "_v44")
    me.from_pydata(verts, [], faces)
    me.update()
    for m in obj.data.materials:
        me.materials.append(m)
    for poly in me.polygons:
        is_cap = all(abs(me.vertices[me.loops[li].vertex_index].co.z)
                     == zt for li in poly.loop_indices)
        if is_cap and (poly.normal.z > 0) != (poly.center.z > 0):
            poly.flip()
    xs = [p[0] for p in g["outline"]]
    ys = [p[1] for p in g["outline"]]
    bw, bh = max(xs) - min(xs), max(ys) - min(ys)
    cx0, cy0 = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    uv = me.uv_layers.new(name="UVMap")
    for poly in me.polygons:
        if poly.normal.z > 0.5:
            poly.material_index = 0
        elif poly.normal.z < -0.5:
            poly.material_index = 1
        else:
            poly.material_index = 2
            continue
        for li in poly.loop_indices:
            co = me.vertices[me.loops[li].vertex_index].co
            uv.data[li].uv = ((co.x - cx0) / bw + 0.5,
                              (co.y - cy0) / bh + 0.5)
    old = obj.data
    obj.data = me
    bpy.data.meshes.remove(old)
    return me


def refresh_textures():
    swapped = []
    for img in list(bpy.data.images):
        fp = img.filepath
        if "TEX42_" not in fp:
            continue
        path = Path(bpy.path.abspath(fp))
        if not path.exists():
            continue
        new = bpy.data.images.load(str(path), check_existing=False)
        new.name = img.name + "_v44"
        for mat in bpy.data.materials:
            if not mat.use_nodes:
                continue
            for node in mat.node_tree.nodes:
                if node.type == 'TEX_IMAGE' and node.image == img:
                    node.image = new
        bpy.data.images.remove(img)
        new.name = Path(fp).stem
        swapped.append(new.name)
    return swapped


def collision_scan(board):
    inv = board.matrix_world.inverted()
    hits = []
    for o in bpy.data.objects:
        if o.type != 'MESH' or o is board:
            continue
        lp = inv @ o.matrix_world.translation
        if not (-5 < lp.z < 10):
            continue
        for hx, hy, hr in A_HOLES:
            d = math.hypot(lp.x - hx, lp.y - hy)
            if d < hr + 0.5:
                hits.append((o.name, round(lp.x, 1), round(lp.y, 1),
                             round(lp.z, 1), (hx, hy, hr), round(d, 1)))
                break
    return hits


def main():
    bpy.ops.wm.open_mainfile(filepath=str(SRC))
    board = bpy.data.objects["PCB_A_MAIN_SYSTEM_BOARD"]
    me = rebuild_board(board, "a")
    print(f"[v44] board mesh rebuilt: {len(me.vertices)} verts "
          f"{len(me.polygons)} faces")
    swapped = refresh_textures()
    print(f"[v44] textures refreshed: {len(swapped)} -> {swapped}")
    hits = collision_scan(board)
    removed = []
    flagged = []
    for name, x, y, z, hole, d in hits:
        # v42-era scatter passives / small pads sitting inside a corrected
        # through-hole have nothing to solder to — remove them
        if name.startswith(("SMT42_", "PCB_A_SMT_")) or \
                (name.startswith("A_EM_PAD") and d < hole[2]):
            obj = bpy.data.objects.get(name)
            if obj:
                bpy.data.objects.remove(obj)
                removed.append(name)
        else:
            flagged.append((name, x, y, z, hole, d))
    print(f"[v44] collisions: removed {len(removed)} scatter passives, "
          f"flagged {len(flagged)}")
    for f in flagged:
        print("   FLAG", f)
    bpy.ops.wm.save_as_mainfile(filepath=str(DST))
    print(f"[v44] saved {DST}")


if __name__ == "__main__":
    main()
