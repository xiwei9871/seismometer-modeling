"""Patch v4: deeper wrap + bare-steel negative pole band at the base. Run:
blender -b web_asset/EXPORT_SOURCE/device_master.blend --python scripts/patch_cells_v4.py
"""
import bpy

wrap = bpy.data.materials['MAT_CELL_WRAP']
wb = next(n for n in wrap.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
wb.inputs['Base Color'].default_value = (0.008, 0.185, 0.025, 1.0)  # deep NCR green
wb.inputs['Roughness'].default_value = 0.34
wb.inputs['Metallic'].default_value = 0.0

can = bpy.data.materials['MAT_CELL_CAN']

for i in range(1, 7):
    cid = f'CELL_18650_{i:02d}'
    body = bpy.data.objects[cid]
    nm = cid + '_NEG'
    if not bpy.data.objects.get(nm):
        # bare steel band where the wrap stops short of the negative pole
        bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=9.05,
                                          depth=2.2)
        neg = bpy.context.active_object
        neg.name = nm
        neg.data.materials.append(can)
        neg.parent = body
        neg.location = (0.0, 0.0, -30.6)

bpy.ops.wm.save_mainfile()
print('DONE cells v4')
