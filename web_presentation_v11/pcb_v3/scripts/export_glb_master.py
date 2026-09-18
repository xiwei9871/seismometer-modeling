"""STEP 6 — export GLB_RUNTIME + manifests + report.

Run: blender -b --python scripts/export_glb_master.py
"""
import json
import struct
import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "web_asset" / "EXPORT_SOURCE" / "device_master.blend"
OUT = ROOT / "web_asset" / "GLB_RUNTIME"
GLB = OUT / "smart_field_device_master.glb"


def glb_json(path):
    data = path.read_bytes()
    ln = struct.unpack_from("<I", data, 12)[0]
    return json.loads(data[20:20 + ln])


def main():
    bpy.ops.wm.open_mainfile(filepath=str(SRC))
    OUT.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(
        filepath=str(GLB),
        export_format="GLB",
        export_extras=True,          # custom props -> glTF node extras
        export_cameras=False,
        export_lights=False,
        export_animations=False,
        export_apply=False,
        export_yup=True,
        export_image_format='AUTO',
        export_texture_dir="",
    )
    g = glb_json(GLB)
    nodes = g.get("nodes", [])
    meshes = g.get("meshes", [])
    mats = g.get("materials", [])
    imgs = g.get("images", [])
    texs = g.get("textures", [])

    # ---- node manifest -----------------------------------------------------
    children_of = {}
    for i, nd in enumerate(nodes):
        for c in nd.get("children", []):
            children_of[c] = i
    roots_idx = [i for i in range(len(nodes)) if i not in children_of]

    def node_rec(i):
        nd = nodes[i]
        ex = nd.get("extras", {})
        return {
            "name": nd.get("name"),
            "semanticId": ex.get("semanticId"),
            "type": ex.get("type"),
            "systemId": ex.get("systemId"),
            "presentationPriority": ex.get("presentationPriority"),
            "selectable": ex.get("selectable"),
            "hoverable": ex.get("hoverable"),
            "focusable": ex.get("focusable"),
            "explodable": ex.get("explodable"),
            "mesh": nd.get("mesh"),
            "children": [node_rec(c) for c in nd.get("children", [])],
        }

    (OUT / "glb_node_manifest.json").write_text(json.dumps(
        {"file": GLB.name, "nodeCount": len(nodes),
         "roots": [node_rec(i) for i in roots_idx]}, indent=1))

    # ---- material manifest --------------------------------------------------
    mat_rows = []
    for m in mats:
        pbr = m.get("pbrMetallicRoughness", {})
        mat_rows.append({
            "name": m.get("name"),
            "baseColorFactor": pbr.get("baseColorFactor"),
            "hasBaseColorTexture": "baseColorTexture" in pbr,
            "metallicFactor": pbr.get("metallicFactor", 1.0),
            "roughnessFactor": pbr.get("roughnessFactor", 1.0),
            "hasMetallicRoughnessTexture":
                "metallicRoughnessTexture" in pbr,
            "hasNormalTexture": "normalTexture" in m,
            "alphaMode": m.get("alphaMode", "OPAQUE"),
            "doubleSided": m.get("doubleSided", False),
        })
    (OUT / "glb_material_manifest.json").write_text(
        json.dumps(mat_rows, indent=1))

    # ---- texture manifest ---------------------------------------------------
    (OUT / "glb_texture_manifest.json").write_text(json.dumps([
        {"name": t.get("name"), "source": t.get("source"),
         "image": (imgs[t["source"]].get("name")
                   if t.get("source") is not None else None),
         "mime": (imgs[t["source"]].get("mimeType")
                  if t.get("source") is not None else None)}
        for t in texs], indent=1))

    # ---- semantic registry --------------------------------------------------
    reg = {}
    for nd in nodes:
        ex = nd.get("extras", {})
        sid = ex.get("semanticId")
        if sid:
            reg[sid] = {
                "name": nd.get("name"), "type": ex.get("type"),
                "systemId": ex.get("systemId"),
                "presentationPriority": ex.get("presentationPriority"),
                "selectable": ex.get("selectable"),
                "focusable": ex.get("focusable"),
                "explodable": ex.get("explodable"),
            }
    (OUT / "glb_semantic_registry.json").write_text(json.dumps(reg, indent=1))

    # ---- export report ------------------------------------------------------
    tris = verts = 0
    for me in meshes:
        for prim in me.get("primitives", []):
            acc = g["accessors"]
            if "indices" in prim:
                tris += acc[prim["indices"]]["count"] // 3
            if "POSITION" in prim.get("attributes", {}):
                verts += acc[prim["attributes"]["POSITION"]]["count"]
    report = {
        "file": str(GLB),
        "size_mb": round(GLB.stat().st_size / 1e6, 2),
        "nodes": len(nodes),
        "meshes": len(meshes),
        "materials": len(mats),
        "textures": len(texs),
        "images": len(imgs),
        "triangles": tris,
        "vertices": verts,
        "drawCallEstimate": sum(len(m.get("primitives", []))
                                for m in meshes),
        "semanticNodes": len(reg),
    }
    (OUT / "glb_export_report.json").write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
