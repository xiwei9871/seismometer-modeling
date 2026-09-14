"""Export the V1 interactive scene to GLB — static geometry + semantic extras.

Unlike export_story_glb.py this intentionally exports NO baked animation:
V1 computes every transform at runtime from baseTransform + state vectors
(spec §6). The GLB carries geometry, materials and per-node semantic extras
(semanticId / systemId / sourcePart / role / flags) from semantic_map.py.

Only the 22 animated source parts and the 15 PCB presentation components are
exported — the 60 permanently hidden source parts never ship to the web.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from stage_10V2_product_story.scripts.semantic_map import (
    COMPONENTS,
    PCB_COMP_PREFIX,
    SYSTEMS,
    component_extras,
    pcb_component_extras,
    validate_semantic_map,
)
from stage_10V2_product_story.scripts.story_v2_data import SCENE_OUTPUT

try:  # pragma: no cover - Blender-only implementation.
    import bpy  # type: ignore
except ImportError:  # pragma: no cover
    bpy = None  # type: ignore

GLB_OUTPUT_V1 = "stage_10V2_product_story/web-v1/product_v1.glb"
DEVICE_ROOT_NAME = "DEVICE_ROOT"


def _system_empties() -> dict[str, object]:
    """Create DEVICE_ROOT + SYS_* empties so the GLB keeps the semantic tree.

    Parts are NOT re-parented — the semantic tree lives in node extras and the
    manifest — but the SYS_ nodes exist as named anchors for tooling/debug.
    """
    root = bpy.data.objects.new(DEVICE_ROOT_NAME, None)
    bpy.context.scene.collection.objects.link(root)
    root["semanticId"] = DEVICE_ROOT_NAME
    root["type"] = "device"
    root["displayName"] = "Smart Field Survey Device"
    empties = {}
    for sys_id, spec in SYSTEMS.items():
        node = bpy.data.objects.new(sys_id, None)
        bpy.context.scene.collection.objects.link(node)
        node.parent = root
        node["semanticId"] = sys_id
        node["type"] = "system"
        node["displayName"] = spec["displayName"]
        node["oneLiner"] = spec["oneLiner"]
        empties[sys_id] = node
    return empties


def export_story_glb_v1(project_root: Path) -> dict[str, object]:
    if bpy is None:
        raise RuntimeError("Blender bpy is required to export the story GLB")
    validate_semantic_map()
    root = Path(project_root).expanduser().resolve()
    bpy.ops.wm.open_mainfile(filepath=str(root / SCENE_OUTPUT))
    scene = bpy.context.scene
    scene.frame_set(1)

    _system_empties()
    exported = 0
    for obj in scene.objects:
        name = obj.name
        part_id = name.split("__")[0] if name.startswith("PART_") else None
        if part_id in COMPONENTS:
            for key, value in component_extras(part_id).items():
                obj[key] = value
            exported += 1
        elif name.startswith(PCB_COMP_PREFIX):
            material_role = str(obj.get("material_role", "component"))
            for key, value in pcb_component_extras(name, material_role).items():
                obj[key] = value
            exported += 1
    if exported != len(COMPONENTS) + 15:
        raise RuntimeError(f"semantic export expected 37 nodes, tagged {exported}")

    output = root / GLB_OUTPUT_V1
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(
        filepath=str(output),
        export_format="GLB",
        export_animations=False,
        export_extras=True,
        export_cameras=False,
        export_apply=False,
        export_yup=True,
        use_visible=True,
    )
    return {
        "output": str(output),
        "size_mb": round(output.stat().st_size / 1e6, 1),
        "tagged_nodes": exported,
    }


def _script_arguments() -> list[str]:
    arguments = list(sys.argv[1:])
    return arguments[arguments.index("--") + 1 :] if "--" in arguments else arguments


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args(argv if argv is not None else _script_arguments())
    print(json.dumps(export_story_glb_v1(args.project_root), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
