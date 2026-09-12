"""Validate Task 10-R source integrity and static-scene policies."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any
import math

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.task08_data import load_json
from stage_10R_functional_inspection.scripts.build_inspection_scenes import SCENE_OUTPUTS
from stage_10R_functional_inspection.scripts.inspection_data import (
    BASELINE,
    EXPECTED_PART_IDS,
    HIDDEN_PART_IDS,
    INSPECTION_STATE_IDS,
    STORY_PART_IDS,
    build_module_groups,
)
from stage_10R_functional_inspection.scripts.render_inspection_states import REQUIRED_RENDERS, RENDER_ROOT
from stage_10_product_story.scripts.build_story_scene import mesh_geometry_fingerprint

try:  # pragma: no cover - executed through Blender.
    import bpy  # type: ignore
except ImportError:  # pragma: no cover
    bpy = None  # type: ignore


REQUIRED_SCENE_STATES = tuple(INSPECTION_STATE_IDS)
REQUIRED_COLLECTION_SUFFIXES = ("FOCUS", "CONTEXT", "SOURCE_HIDDEN", "CAMERAS")


def validate_inspection(project_root: Path) -> dict[str, Any]:
    if bpy is None:
        raise RuntimeError("Blender bpy is required to validate Task 10-R scenes")
    root = Path(project_root).expanduser().resolve()
    state_config = load_json(root / "stage_10R_functional_inspection/config/inspection_states.json")
    per_scene: dict[str, Any] = {}
    warnings: list[dict[str, Any]] = []
    for state_id in REQUIRED_SCENE_STATES:
        scene_path = root / SCENE_OUTPUTS[state_id]
        if not scene_path.is_file() or scene_path.stat().st_size <= 0:
            warnings.append({"code": "SCENE_MISSING", "state_id": state_id, "path": str(scene_path)})
            continue
        bpy.ops.wm.open_mainfile(filepath=str(scene_path))
        result = _validate_scene(state_id, scene_path, state_config["states"][state_id], root)
        per_scene[state_id] = result
        warnings.extend(result["warnings"])
    render_checks = {
        name: (root / RENDER_ROOT / name).is_file() and (root / RENDER_ROOT / name).stat().st_size > 0
        for name in REQUIRED_RENDERS
    }
    missing_renders = [name for name, exists in render_checks.items() if not exists]
    if missing_renders:
        warnings.append({"code": "RENDER_MISSING", "renders": missing_renders})
    contact_sheet = root / RENDER_ROOT / "task10R_contact_sheet.png"
    if not contact_sheet.is_file() or contact_sheet.stat().st_size <= 0:
        warnings.append({"code": "CONTACT_SHEET_MISSING", "path": str(contact_sheet)})
    technical_status = "PASS" if not warnings and set(per_scene) == set(REQUIRED_SCENE_STATES) else "FAIL"
    return {
        "technical_status": technical_status,
        "visual_status": "PENDING_HUMAN_REVIEW",
        "overall_status": "REVIEW_REQUIRED",
        "source_baseline": dict(BASELINE),
        "scene_count": len(per_scene),
        "scenes": per_scene,
        "render_checks": render_checks,
        "contact_sheet": str(contact_sheet),
        "warnings": warnings,
        "visual_review_gate": {
            "primary": "PENDING_HUMAN_REVIEW",
            "sensor": "PENDING_HUMAN_REVIEW",
            "pcb": "PENDING_HUMAN_REVIEW",
            "power": "PENDING_HUMAN_REVIEW",
        },
    }


def _validate_scene(state_id: str, scene_path: Path, state: dict[str, Any], root: Path) -> dict[str, Any]:
    objects = {
        str(obj.get("part_id")): obj
        for obj in bpy.data.objects
        if obj.type == "MESH" and obj.get("source") == "original_stl"
    }
    warnings: list[dict[str, Any]] = []
    if set(objects) != set(EXPECTED_PART_IDS):
        warnings.append({"code": "SOURCE_PART_COVERAGE_MISMATCH", "state_id": state_id, "count": len(objects)})
    faces = sum(len(obj.data.polygons) for obj in objects.values())
    vertices = sum(len(obj.data.vertices) for obj in objects.values())
    if faces != BASELINE["faces"] or vertices != BASELINE["indexed_vertices"]:
        warnings.append({"code": "FROZEN_GEOMETRY_TOTAL_MISMATCH", "state_id": state_id, "faces": faces, "vertices": vertices})
    fingerprint_failures = []
    for part_id, obj in objects.items():
        expected = str(obj.get("task10r_source_geometry_fingerprint", ""))
        if not expected or expected != mesh_geometry_fingerprint(obj.data):
            fingerprint_failures.append(part_id)
    if fingerprint_failures:
        warnings.append({"code": "SOURCE_GEOMETRY_FINGERPRINT_MISMATCH", "state_id": state_id, "part_ids": sorted(fingerprint_failures, key=_part_number)})
    visible = sorted([part_id for part_id, obj in objects.items() if not obj.hide_render], key=_part_number)
    hidden = sorted([part_id for part_id, obj in objects.items() if obj.hide_render], key=_part_number)
    if visible != list(STORY_PART_IDS) or hidden != list(HIDDEN_PART_IDS):
        warnings.append({"code": "VISIBILITY_POLICY_MISMATCH", "state_id": state_id, "visible": visible, "hidden": hidden})
    animation_count = sum(obj.animation_data is not None for obj in objects.values())
    if animation_count:
        warnings.append({"code": "ANIMATION_DATA_PRESENT", "state_id": state_id, "count": animation_count})
    fonts = [obj.name for obj in bpy.data.objects if obj.type == "FONT"]
    if fonts:
        warnings.append({"code": "TEXT_OBJECT_PRESENT", "state_id": state_id, "objects": fonts})
    unexpected = [obj.name for obj in bpy.data.objects if obj.type not in {"MESH", "CAMERA"}]
    if unexpected:
        warnings.append({"code": "UNEXPECTED_OBJECT_TYPE", "state_id": state_id, "objects": unexpected})
    scene = bpy.context.scene
    if [scene.frame_start, scene.frame_end] != [1, 1] or int(scene.render.fps) != 30:
        warnings.append({"code": "STATIC_TIMELINE_MISMATCH", "state_id": state_id, "frame_range": [scene.frame_start, scene.frame_end], "fps": scene.render.fps})
    root_name = f"TASK10R_{state_id}"
    required_collections = {root_name, *(f"{root_name}_{suffix}" for suffix in REQUIRED_COLLECTION_SUFFIXES)}
    missing_collections = sorted(name for name in required_collections if bpy.data.collections.get(name) is None)
    if missing_collections:
        warnings.append({"code": "COLLECTIONS_MISSING", "state_id": state_id, "collections": missing_collections})
    if scene.get("task10r_state_id") != state_id:
        warnings.append({"code": "STATE_MARKER_MISMATCH", "state_id": state_id})
    if scene.get("task10r_text_policy") != "NO_TEXT_OR_ANNOTATIONS":
        warnings.append({"code": "TEXT_POLICY_MARKER_MISMATCH", "state_id": state_id})
    return {
        "state_id": state_id,
        "scene_path": str(scene_path),
        "source_part_count": len(objects),
        "source_faces": faces,
        "source_indexed_vertices": vertices,
        "visible_part_count": len(visible),
        "hidden_part_count": len(hidden),
        "animation_data_count": animation_count,
        "font_object_count": len(fonts),
        "camera_count": len([obj for obj in bpy.data.objects if obj.type == "CAMERA"]),
        "warnings": warnings,
        "source_geometry_modified": bool(fingerprint_failures),
        "source_geometry_fingerprint_verified": not fingerprint_failures,
        "screen_space_metrics": _screen_space_metrics(state_id, state, objects),
    }


def _screen_space_metrics(state_id: str, state: dict[str, Any], objects: dict[str, Any]) -> dict[str, Any]:
    """Measure projected object bounds from the active Blender camera.

    These are camera-space bounding-box metrics, not a claim of pixel-perfect
    silhouette visibility. They provide a reproducible warning signal while
    leaving the final visual decision to human review.
    """
    camera_name = str(state.get("camera_id", ""))
    camera = bpy.data.objects.get(camera_name)
    if camera is None or camera.type != "CAMERA":
        return {"method": "BLENDER_CAMERA_PROJECTED_BOUNDS", "error": "camera_missing"}
    modules = build_module_groups()
    allowed = {
        part_id: obj
        for part_id, obj in objects.items()
        if not obj.hide_render and (state_id == "STATE_01_PRIMARY_ARCHITECTURE" or obj.get("task10r_presentation_role") == "FOCUS")
    }
    module_rects: dict[str, dict[str, float]] = {}
    component_rects: dict[str, dict[str, float]] = {}
    for module_id, module in modules.items():
        rects = []
        for part_id in module["part_ids"]:
            if part_id not in allowed:
                continue
            rect = _projected_rect(allowed[part_id], camera)
            if rect is not None:
                component_rects[part_id] = rect
                rects.append(rect)
        if rects:
            module_rects[module_id] = _union_rect(rects)
    union = _union_rect(list(module_rects.values())) if module_rects else None
    occupancy = {
        module_id: round(_rect_area(rect) / max(_rect_area(union), 1e-9), 4)
        for module_id, rect in module_rects.items()
    }
    overlaps = [
        rect_overlap_ratio(left, right)
        for index, left in enumerate(module_rects.values())
        for right in list(module_rects.values())[index + 1:]
    ]
    focus_component_ids = _focus_component_ids(state_id)
    focus_rects = {
        part_id: rect
        for part_id, rect in component_rects.items()
        if part_id in focus_component_ids
    }
    component_overlaps = [
        rect_overlap_ratio(left, right)
        for index, left in enumerate(focus_rects.values())
        for right in list(focus_rects.values())[index + 1:]
    ]
    return {
        "method": "BLENDER_CAMERA_PROJECTED_BOUNDS",
        "camera": camera_name,
        "metric_scope": "FOCUS_OBJECTS_FOR_FOCUS_STATES",
        "module_screen_occupancy": occupancy,
        "projected_overlap_ratio": round(max(overlaps, default=0.0), 4),
        "component_projected_overlap_ratio": round(max(component_overlaps, default=0.0), 4),
        "focus_component_ids": sorted(focus_rects, key=_part_number),
        "visible_surface_ratio_proxy": round(1.0 - max(overlaps, default=0.0), 4),
        "frame_margin": _frame_margin(union),
        "silhouette_separation_proxy": round(1.0 - max(component_overlaps, default=0.0), 4),
        "frame_occupancy_ratio": round(_rect_area(union), 4) if union else 0.0,
        "projected_rects": component_rects,
        "human_review_required": True,
    }


def _projected_rect(obj: Any, camera: Any) -> dict[str, float] | None:
    from bpy_extras.object_utils import world_to_camera_view  # type: ignore

    points = []
    for corner in obj.bound_box:
        world = obj.matrix_world @ __import__("mathutils").Vector(corner)
        ndc = world_to_camera_view(bpy.context.scene, camera, world)
        points.append((float(ndc.x), float(ndc.y)))
    if not points:
        return None
    return {
        "x_min": max(0.0, min(point[0] for point in points)),
        "x_max": min(1.0, max(point[0] for point in points)),
        "y_min": max(0.0, min(point[1] for point in points)),
        "y_max": min(1.0, max(point[1] for point in points)),
    }


def _union_rect(rects: list[dict[str, float]]) -> dict[str, float]:
    return {
        "x_min": min(rect["x_min"] for rect in rects),
        "x_max": max(rect["x_max"] for rect in rects),
        "y_min": min(rect["y_min"] for rect in rects),
        "y_max": max(rect["y_max"] for rect in rects),
    }


def _rect_area(rect: dict[str, float] | None) -> float:
    if rect is None:
        return 0.0
    return max(0.0, rect["x_max"] - rect["x_min"]) * max(0.0, rect["y_max"] - rect["y_min"])


def rect_overlap_ratio(left: dict[str, float], right: dict[str, float]) -> float:
    """Return intersection-over-union for two projected rectangles."""
    width = max(0.0, min(left["x_max"], right["x_max"]) - max(left["x_min"], right["x_min"]))
    height = max(0.0, min(left["y_max"], right["y_max"]) - max(left["y_min"], right["y_min"]))
    intersection = width * height
    denominator = max(_rect_area(left) + _rect_area(right) - intersection, 1e-9)
    return min(1.0, max(0.0, intersection / denominator))


def _focus_component_ids(state_id: str) -> tuple[str, ...]:
    if state_id == "STATE_02_SENSOR_INSPECTION":
        return ("PART_012", "PART_013", "PART_014")
    if state_id == "STATE_03_PCB_INSPECTION":
        return ("PART_006", "PART_019", "PART_007")
    if state_id == "STATE_04_POWER_INSPECTION":
        return ("PART_008", "PART_009", "PART_010", "PART_011", "PART_015", "PART_016")
    return tuple(STORY_PART_IDS)


def _frame_margin(rect: dict[str, float] | None) -> dict[str, float]:
    if rect is None:
        return {"left": 0.0, "right": 0.0, "top": 0.0, "bottom": 0.0}
    return {
        "left": round(rect["x_min"], 4),
        "right": round(1.0 - rect["x_max"], 4),
        "top": round(1.0 - rect["y_max"], 4),
        "bottom": round(rect["y_min"], 4),
    }


def _part_number(part_id: str) -> int:
    return int(str(part_id).split("_")[-1])


def _script_arguments() -> list[str]:
    arguments = list(sys.argv[1:])
    return arguments[arguments.index("--") + 1 :] if "--" in arguments else arguments


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args(argv if argv is not None else _script_arguments())
    result = validate_inspection(args.project_root)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["technical_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
