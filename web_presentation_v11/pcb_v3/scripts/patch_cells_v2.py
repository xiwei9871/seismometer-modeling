"""Patch: realistic 18650 cell look — deep-green PVC wrap, steel crimp
shoulder, proud insulator ring + button, dark ink print. Run:
blender -b web_asset/EXPORT_SOURCE/device_master.blend --python scripts/patch_cells_v2.py
"""
import bpy
from mathutils import Vector

SRC = "/Users/xiwei/modeling/web_presentation_v11/pcb_v3/web_asset/EXPORT_SOURCE/device_master.blend"

def mat(name):
    m = bpy.data.materials.get(name)
    return m

# 1. wrap -> deep green PVC (Panasonic NCR18650B style)
wrap = mat('MAT_CELL_WRAP')
bsdf = wrap.node_tree.nodes.get('Principled BSDF') or next(
    n for n in wrap.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
bsdf.inputs['Base Color'].default_value = (0.045, 0.26, 0.05, 1.0)
bsdf.inputs['Roughness'].default_value = 0.55
bsdf.inputs['Metallic'].default_value = 0.0

can = mat('MAT_CELL_CAN')
hold = mat('MAT_CELL_HOLDER')

# dark ink for the print fonts
ink = bpy.data.materials.get('MAT_CELL_INK') or bpy.data.materials.new('MAT_CELL_INK')
ink.use_nodes = True
ib = ink.node_tree.nodes.get('Principled BSDF')
ib.inputs['Base Color'].default_value = (0.06, 0.07, 0.06, 1.0)
ib.inputs['Roughness'].default_value = 0.6
ib.inputs['Metallic'].default_value = 0.0

made = 0
for i in range(1, 7):
    body = bpy.data.objects.get(f'CELL_18650_{i:02d}')
    if not body:
        continue
    btn = bpy.data.objects.get(f'CELL_18650_{i:02d}_BTN')
    ins = bpy.data.objects.get(f'CELL_18650_{i:02d}_INSUL')

    # steel crimp shoulder over the wrap top edge
    nm = f'CELL_18650_{i:02d}_CRIMP'
    if not bpy.data.objects.get(nm):
        bpy.ops.mesh.primitive_cylinder_add(radius=9.2, depth=1.7, location=(0, 0, 0))
        cr = bpy.context.object
        cr.name = nm
        cr.parent = body
        cr.location = (0, 0, 31.4)
        cr.data.materials.append(can)
        made += 1

    # insulator sits ON the shoulder; button clearly proud of it
    if ins:
        ins.location = (0, 0, 32.6)
    if btn:
        btn.location = (0, 0, 33.8)
        btn.scale.z = 1.2

    # dark ink on every print font
    for o in bpy.data.objects:
        if o.name.startswith(f'CELL_18650_{i:02d}_PRINT') and o.type == 'FONT':
            o.data.materials.clear()
            o.data.materials.append(ink)

bpy.ops.wm.save_mainfile()
print(f'DONE crimp rings added: {made}')
