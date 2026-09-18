# Embed the wifi antenna INSIDE the left handle leg (IP67-style internal
# antenna). Leg is solid at x 25.7-55 / z 298-350 / y 72-97.
import bpy

SHIFT = (-15.0, 0.0, 14.0)   # x 55->40, whip z 304-330 -> 318-344
for nm in ('WIFI_ANT_WHIP', 'WIFI_ANT_BASE', 'WIFI_ANT_COAX', 'WIFI_ANTENNA'):
    o = bpy.data.objects.get(nm)
    if o:
        o.location.x += SHIFT[0]
        o.location.y += SHIFT[1]
        o.location.z += SHIFT[2]
        print(nm, '->', tuple(round(v, 1) for v in o.matrix_world.translation))

bpy.ops.wm.save_mainfile()
print('saved')
