"""Patch v3: cells read as real 18650s — saturated wrap, big light-colour
print, +/- polarity marks. Run:
blender -b web_asset/EXPORT_SOURCE/device_master.blend --python scripts/patch_cells_v3.py
"""
import bpy
import math

wrap = bpy.data.materials['MAT_CELL_WRAP']
wb = next(n for n in wrap.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
wb.inputs['Base Color'].default_value = (0.018, 0.30, 0.045, 1.0)  # saturated PVC green
wb.inputs['Roughness'].default_value = 0.38
wb.inputs['Metallic'].default_value = 0.0

ink = bpy.data.materials['MAT_CELL_INK']
ib = next(n for n in ink.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
ib.inputs['Base Color'].default_value = (0.92, 0.93, 0.90, 1.0)   # light print on green
ib.inputs['Roughness'].default_value = 0.5
ib.inputs['Metallic'].default_value = 0.0

for i in range(1, 7):
    cid = f'CELL_18650_{i:02d}'
    body = bpy.data.objects[cid]
    # existing print: enlarge
    for o in bpy.data.objects:
        if o.name.startswith(cid + '_PRINT') and o.type == 'FONT':
            txt = o.data.body
            o.data.size = 6.4 if txt == '18650' else 3.4
            o.data.space_character = 1.15
    # polarity marks on the same face as the print (radial outward dir)
    if not bpy.data.objects.get(cid + '_POLp'):
        # find radial dir from existing print object position
        pr = next(o for o in bpy.data.objects if o.name.startswith(cid + '_PRINT'))
        dx, dy = pr.location.x, pr.location.y
        L = math.hypot(dx, dy) or 1.0
        dx, dy = dx / L, dy / L
        for tag, sym, zoff, sc in (('_POLp', '+', 25.5, 1.0), ('_POLn', '\u2212', -25.0, 1.0)):
            bpy.ops.object.text_add()
            t = bpy.context.active_object
            t.name = cid + tag
            t.data.body = sym
            t.data.size = 7.0 * sc
            t.data.align_x = 'CENTER'
            t.data.align_y = 'CENTER'
            t.data.extrude = 0.02
            t.data.materials.append(ink)
            t.parent = body
            t.location = (dx * 8.9, dy * 8.9, zoff)
            t.rotation_euler = (math.radians(90), 0, math.atan2(dy, dx) + math.radians(90))

bpy.ops.wm.save_mainfile()
print('DONE cells v3')
