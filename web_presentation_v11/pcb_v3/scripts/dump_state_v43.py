"""STEP 5 regression dump — write object transforms, bboxes, camera params
and UV signatures to JSON for diffing v42 (frozen) vs v43 (lookdev).

Run inside each blend:
  blender -b pcb_v42_surface.blend \
      --python scripts/dump_state_v43.py -- validation_v43/state_v42.json
  blender -b pcb_v43_lookdev.blend \
      --python scripts/dump_state_v43.py -- validation_v43/state_v43.json
"""
import hashlib
import json
import sys
from pathlib import Path

import bpy

out = Path(sys.argv[sys.argv.index("--") + 1])
IGNORE = ("L43_", "CAM_V43_", "SW_", "Ground")

state = {"objects": {}, "cameras": {}}
dg = bpy.context.evaluated_depsgraph_get()

for o in bpy.data.objects:
    if o.name.startswith(IGNORE):
        continue
    loc, rot, sca = o.matrix_world.decompose()
    rec = {
        "loc": [round(v, 4) for v in loc],
        "rot": [round(v, 6) for v in rot.to_euler()],
        "scale": [round(v, 5) for v in sca],
        "parent": o.parent.name if o.parent else None,
        "type": o.type,
    }
    if o.type == "MESH":
        rec["verts"] = len(o.data.vertices)
        rec["uv_layers"] = len(o.data.uv_layers)
        if o.data.uv_layers:
            h = hashlib.md5()
            uv = o.data.uv_layers[0]
            for i in range(0, len(uv.data), max(1, len(uv.data) // 512)):
                h.update(f"{uv.data[i].uv[0]:.5f}{uv.data[i].uv[1]:.5f}"
                         .encode())
            rec["uv_sig"] = h.hexdigest()[:12]
        bb = [o.matrix_world @ __import__("mathutils").Vector(c)
              for c in o.bound_box]
        rec["bbox_min"] = [round(min(v[i] for v in bb), 4) for i in range(3)]
        rec["bbox_max"] = [round(max(v[i] for v in bb), 4) for i in range(3)]
    if o.type == "CAMERA":
        rec["lens"] = o.data.lens
        rec["dof"] = o.data.dof.use_dof
        state["cameras"][o.name] = rec
        continue
    state["objects"][o.name] = rec

out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(state, indent=1, sort_keys=True))
print(f"[dump] {len(state['objects'])} objects, "
      f"{len(state['cameras'])} cameras -> {out.name}")
