"""Validate the Task 10-R-PCB-V1 presentation scene and review assets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.task08_data import load_json
from stage_10R_pcb_presentation.scripts.pcb_presentation_data import (
    BASELINE,
    CAMERAS_PATH,
    COMPARISON_RENDER,
    EXPECTED_PART_IDS,
    HIDDEN_PART_IDS,
    MANIFEST_PATH,
    MATERIALS_PATH,
    RENDER_ROOT,
    REQUIRED_RENDERS,
    SCENE_OUTPUT,
    STORY_PART_IDS,
)
from stage_10_product_story.scripts.build_story_scene import mesh_geometry_fingerprint

try:  # pragma: no cover - executed through Blender.
    import bpy  # type: ignore
except ImportError:  # pragma: no cover
    bpy = None  # type: ignore


ALLOWED_OBJECT_TYPES = {"MESH", "CAMERA", "LIGHT"}
REQUIRED_COLLECTIONS = {
    "TASK10R_PCB",
    "TASK10R_PCB_HERO",
    "TASK10R_PCB_SECONDARY",
    "TASK10R_PCB_SUPPORT",
    "TASK10R_PCB_CONTEXT",
    "TASK10R_PCB_SOURCE_HIDDEN",
    "TASK10R_PCB_CAMERAS",
    "TASK10R_PCB_LIGHTS",
}


def validate_presentation(project_root: Path) -> dict[str, Any]:
    if bpy is None:
        raise RuntimeError("Blender bpy is required to validate the PCB presentation scene")
    root = Path(project_root).expanduser().resolve()
    manifest = load_json(root / MANIFEST_PATH)
    warnings: list[dict[str, Any]] = []

    scene_path = root / SCENE_OUTPUT
    scene_report: dict[str, Any] = {}
    if not scene_path.is_file() or scene_path.stat().st_size <= 0:
        warnings.append({"code": "SCENE_MISSING", "path": str(scene_path)})
    else:
        bpy.ops.wm.open_mainfile(filepath=str(scene_path))
        scene_report = _validate_scene(manifest, warnings)

    for path in (root / CAMERAS_PATH, root / MATERIALS_PATH):
        if not path.is_file():
            warnings.append({"code": "CONFIG_MISSING", "path": str(path)})

    render_checks = {}
    for name in (*REQUIRED_RENDERS, COMPARISON_RENDER):
        path = root / RENDER_ROOT / name
        render_checks[name] = path.is_file() and path.stat().st_size > 0
    missing = [name for name, ok in render_checks.items() if not ok]
    if missing:
        warnings.append({"code": "RENDER_MISSING", "renders": missing})

    technical_status = "PASS" if not warnings else "FAIL"
    return {
        "technical_status": technical_status,
        "visual_status": "PENDING_HUMAN_REVIEW",
        "overall_status": "REVIEW_REQUIRED" if technical_status == "PASS" else "FAIL",
        "source_baseline": dict(BASELINE),
        "scene": scene_report,
        "render_checks": render_checks,
        "warnings": warnings,
        "visual_review_gate": {
            "density": "PENDING_HUMAN_REVIEW",
            "hierarchy": "PENDING_HUMAN_REVIEW",
            "part007_demoted": "PENDING_HUMAN_REVIEW",
            "reference_fidelity": "PENDING_HUMAN_REVIEW",
        },
    }


def _validate_scene(manifest: dict[str, Any], warnings: list[dict[str, Any]]) -> dict[str, Any]:
    source_objects = {
        str(obj.get("part_id")): obj
        for obj in bpy.data.objects
        if obj.type == "MESH" and obj.get("source") == "original_stl"
    }
    if set(source_objects) != set(EXPECTED_PART_IDS):
        warnings.append({"code": "SOURCE_PART_COVERAGE_MISMATCH", "count": len(source_objects)})
    faces = sum(len(o.data.polygons) for o in source_objects.values())
    vertices = sum(len(o.data.vertices) for o in source_objects.values())
    if faces != BASELINE["faces"] or vertices != BASELINE["indexed_vertices"]:
        warnings.append({"code": "FROZEN_GEOMETRY_TOTAL_MISMATCH", "faces": faces, "vertices": vertices})
    fingerprint_failures = [
        part_id
        for part_id, obj in source_objects.items()
        if str(obj.get("task10r_pcb_source_geometry_fingerprint")) != mesh_geometry_fingerprint(obj.data)
    ]
    if fingerprint_failures:
        warnings.append({"code": "SOURCE_GEOMETRY_FINGERPRINT_MISMATCH", "part_ids": fingerprint_failures})

    components = {
        obj.name: obj
        for obj in bpy.data.objects
        if obj.type == "MESH" and obj.get("source") == "photographic_presentation_reconstruction"
    }
    expected_components = {c["component_id"] for c in manifest["components"]}
    if set(components) != expected_components:
        warnings.append(
            {
                "code": "COMPONENT_SET_MISMATCH",
                "missing": sorted(expected_components - set(components)),
                "unexpected": sorted(set(components) - expected_components),
            }
        )
    mount_failures = _verify_mounts(manifest, source_objects.get("PART_019"), components)
    if mount_failures:
        warnings.append({"code": "COMPONENT_MOUNT_MISMATCH", "components": mount_failures})

    hidden = sorted(p for p, o in source_objects.items() if o.hide_render)
    if hidden != list(HIDDEN_PART_IDS):
        warnings.append({"code": "HIDDEN_POLICY_MISMATCH", "hidden": hidden})
    part007 = source_objects.get("PART_007")
    if part007 is None or str(part007.get("presentation_priority")) != "SUPPORT" or bool(part007.get("independent_focus")):
        warnings.append({"code": "PART007_DEMOTION_MISSING"})
    board = source_objects.get("PART_019")
    if board is None or not _has_texture(board):
        warnings.append({"code": "SOLDERMASK_TEXTURE_MISSING"})

    animation_count = sum(obj.animation_data is not None for obj in bpy.data.objects)
    if animation_count:
        warnings.append({"code": "ANIMATION_DATA_PRESENT", "count": animation_count})
    fonts = [obj.name for obj in bpy.data.objects if obj.type == "FONT"]
    if fonts:
        warnings.append({"code": "TEXT_OBJECT_PRESENT", "objects": fonts})
    unexpected = sorted({obj.type for obj in bpy.data.objects} - ALLOWED_OBJECT_TYPES)
    if unexpected:
        warnings.append({"code": "UNEXPECTED_OBJECT_TYPE", "types": unexpected})
    scene = bpy.context.scene
    if [scene.frame_start, scene.frame_end] != [1, 1] or int(scene.render.fps) != 30:
        warnings.append({"code": "STATIC_TIMELINE_MISMATCH"})
    missing_collections = sorted(name for name in REQUIRED_COLLECTIONS if bpy.data.collections.get(name) is None)
    if missing_collections:
        warnings.append({"code": "COLLECTIONS_MISSING", "collections": missing_collections})
    cameras = sorted(o.name for o in bpy.data.objects if o.type == "CAMERA" and o.name.startswith("CAM_PCB_"))
    if cameras != ["CAM_PCB_CLEAN", "CAM_PCB_CONTEXT", "CAM_PCB_TOP"]:
        warnings.append({"code": "CAMERA_SET_MISMATCH", "cameras": cameras})
    return {
        "source_part_count": len(source_objects),
        "source_faces": faces,
        "source_indexed_vertices": vertices,
        "component_count": len(components),
        "animation_data_count": animation_count,
        "font_object_count": len(fonts),
        "camera_count": len(cameras),
        "source_geometry_modified": bool(fingerprint_failures),
        "source_geometry_fingerprint_verified": not fingerprint_failures,
        "hidden_part_count": len(hidden),
    }


def _verify_mounts(manifest: dict[str, Any], board_obj: Any, components: dict[str, Any]) -> list[str]:
    if board_obj is None:
        return [c["component_id"] for c in manifest["components"]]
    from mathutils import Vector  # type: ignore

    depsgraph = bpy.context.evaluated_depsgraph_get()
    board_top_z = float(manifest["board_top_z_mm"])
    failures = []
    for component in manifest["components"]:
        component_obj = components.get(component["component_id"])
        rect = component["footprint_board_local"]
        cx, cy = (float(v) for v in component["center_xy_mm"])
        points = [
            (cx, cy),
            (rect["x_min"], rect["y_min"]),
            (rect["x_max"], rect["y_min"]),
            (rect["x_max"], rect["y_max"]),
            (rect["x_min"], rect["y_max"]),
        ]
        for lx, ly in points:
            origin = Vector((board_obj.location.x + lx, board_obj.location.y + ly, board_top_z + 30.0))
            result, _l, _n, _i, hit_obj, _m = bpy.context.scene.ray_cast(
                depsgraph, origin, Vector((0.0, 0.0, -1.0))
            )
            if not result or hit_obj not in {board_obj, component_obj}:
                failures.append(component["component_id"])
                break
    return failures


def _has_texture(obj: Any) -> bool:
    for material in obj.data.materials:
        if material and material.use_nodes and material.node_tree:
            if any(node.type == "TEX_IMAGE" and node.image for node in material.node_tree.nodes):
                return True
    return False


def _script_arguments() -> list[str]:
    arguments = list(sys.argv[1:])
    return arguments[arguments.index("--") + 1 :] if "--" in arguments else arguments


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args(argv if argv is not None else _script_arguments())
    result = validate_presentation(args.project_root)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["technical_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
