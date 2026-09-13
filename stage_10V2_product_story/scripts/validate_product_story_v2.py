"""Validate the generated Task 10-V2 scene and review outputs."""

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
from stage_10_product_story.scripts.build_story_scene import (
    EXPECTED_PART_IDS,
    HIDDEN_PART_IDS,
    VISIBLE_PART_IDS,
    mesh_geometry_fingerprint,
)
from stage_10V2_product_story.scripts.render_product_story_v2 import (
    PREVIEW_VIDEO,
    RENDER_DIR,
    REQUIRED_STILLS,
)
from stage_10V2_product_story.scripts.story_v2_data import (
    EXPOSURE,
    LIGHTING_OUTPUT,
    RENDER_ENGINE,
    SCENE_OUTPUT,
    STATE_OUTPUT,
)

try:  # pragma: no cover - Blender-only validation.
    import bpy  # type: ignore
except ImportError:  # pragma: no cover
    bpy = None  # type: ignore


REQUIRED_COLLECTIONS = {
    "STORY_10V2", "STORY_MODULES", "STORY_SOURCE_HIDDEN", "STORY_PCB_PRESENTATION",
    "STORY_ANNOTATIONS", "STORY_CAMERAS", "STORY_LIGHTS",
}
COMPONENT_FRAME_CHECKS = (1, 365, 900)
COMPONENT_STATE_BY_FRAME = {1: "ASSEMBLED", 365: "PCB_FOCUS", 900: "FINAL_HERO"}


def validate_product_story_v2(project_root: Path) -> dict[str, Any]:
    if bpy is None:
        raise RuntimeError("Blender bpy is required for Task 10-V2 validation")
    root = Path(project_root).expanduser().resolve()
    scene_path = root / SCENE_OUTPUT
    state_data = load_json(root / STATE_OUTPUT)
    bpy.ops.wm.open_mainfile(filepath=str(scene_path))
    objects = {
        str(obj.get("part_id")): obj
        for obj in bpy.data.objects
        if obj.type == "MESH" and obj.get("source") == "original_stl"
    }
    warnings: list[dict[str, Any]] = []
    if set(objects) != set(EXPECTED_PART_IDS):
        warnings.append({"code": "SOURCE_PART_COVERAGE_MISMATCH", "count": len(objects)})
    faces = sum(len(obj.data.polygons) for obj in objects.values())
    vertices = sum(len(obj.data.vertices) for obj in objects.values())
    if faces != 444296 or vertices != 221902:
        warnings.append({"code": "FROZEN_GEOMETRY_TOTAL_MISMATCH", "faces": faces, "vertices": vertices})
    fingerprint_failures = []
    for part_id, obj in objects.items():
        expected_fingerprint = obj.get("task10v2_source_geometry_fingerprint")
        actual_fingerprint = mesh_geometry_fingerprint(obj.data)
        if not expected_fingerprint or str(expected_fingerprint) != actual_fingerprint:
            fingerprint_failures.append(part_id)
    if fingerprint_failures:
        warnings.append({"code": "SOURCE_GEOMETRY_FINGERPRINT_MISMATCH", "part_ids": sorted(fingerprint_failures, key=_part_number)})
    missing_collections = sorted(name for name in REQUIRED_COLLECTIONS if bpy.data.collections.get(name) is None)
    if missing_collections:
        warnings.append({"code": "TASK10V2_COLLECTIONS_MISSING", "collections": missing_collections})
    visible = sorted([part_id for part_id, obj in objects.items() if not obj.hide_render], key=_part_number)
    hidden = sorted([part_id for part_id, obj in objects.items() if obj.hide_render], key=_part_number)
    if visible != list(VISIBLE_PART_IDS) or hidden != list(HIDDEN_PART_IDS):
        warnings.append({"code": "VISIBILITY_POLICY_MISMATCH", "visible": visible, "hidden": hidden})
    animated = sorted([part_id for part_id, obj in objects.items() if obj.animation_data is not None], key=_part_number)
    if animated != list(VISIBLE_PART_IDS):
        warnings.append({"code": "ANIMATION_SCOPE_MISMATCH", "animated": animated})

    components = {
        obj.name: obj
        for obj in bpy.data.objects
        if obj.type == "MESH" and obj.get("task10v2_presentation_component") is True
    }
    expected_components = state_data["presentation"]["components"]
    if set(components) != {c["component_id"] for c in expected_components}:
        warnings.append({"code": "PRESENTATION_COMPONENT_MISMATCH", "count": len(components)})
    unanimated_components = sorted(name for name, obj in components.items() if obj.animation_data is None)
    if unanimated_components:
        warnings.append({"code": "COMPONENT_ANIMATION_MISSING", "components": unanimated_components})
    local_by_id = {c["component_id"]: c["board_local_location"] for c in expected_components}

    scene = bpy.context.scene
    for frame in COMPONENT_FRAME_CHECKS:
        state_id = COMPONENT_STATE_BY_FRAME[frame]
        scene.frame_set(frame)
        board = objects["PART_019"]
        for component_id, local in local_by_id.items():
            obj = components.get(component_id)
            if obj is None:
                continue
            for axis in range(3):
                expected = float(board.location[axis]) + float(local[axis])
                if abs(float(obj.location[axis]) - expected) > 1e-4:
                    warnings.append({
                        "code": "COMPONENT_NOT_ON_BOARD",
                        "frame": frame,
                        "component_id": component_id,
                    })
                    break
    for frame, state_id in ((1, "ASSEMBLED"), (900, "FINAL_HERO")):
        scene.frame_set(frame)
        for part_id in VISIBLE_PART_IDS:
            actual = [float(value) for value in objects[part_id].location]
            expected = [float(value) for value in state_data["states"][state_id]["parts"][part_id]["location"]]
            if any(abs(left - right) > 1e-4 for left, right in zip(actual, expected)):
                warnings.append({"code": "STATE_TRANSFORM_MISMATCH", "frame": frame, "part_id": part_id})
                break

    if [scene.frame_start, scene.frame_end] != [1, 900] or scene.render.fps != 30:
        warnings.append({"code": "TIMELINE_MISMATCH", "frame_range": [scene.frame_start, scene.frame_end], "fps": scene.render.fps})
    if scene.get("task10v2_animation_created") is not True:
        warnings.append({"code": "ANIMATION_MARKER_MISSING"})
    if scene.get("task10v2_story_state_source") != STATE_OUTPUT:
        warnings.append({"code": "STATE_SOURCE_MARKER_MISSING"})
    for part_id, obj in objects.items():
        expected_enabled = part_id in VISIBLE_PART_IDS
        if obj.get("task10v2_story_animation_enabled") is not expected_enabled:
            warnings.append({"code": "STORY_ANIMATION_PROPERTY_MISMATCH", "part_id": part_id})
            break
        if obj.get("task10v2_story_state_source") != STATE_OUTPUT:
            warnings.append({"code": "PART_STATE_SOURCE_MARKER_MISSING", "part_id": part_id})
            break

    board_materials = list(objects["PART_019"].data.materials)
    has_texture = any(
        material is not None and material.use_nodes
        and any(node.type == "TEX_IMAGE" for node in material.node_tree.nodes)
        for material in board_materials
    )
    if not has_texture:
        warnings.append({"code": "PART019_TEXTURE_MATERIAL_MISSING"})
    frame_obj = objects["PART_007"]
    if frame_obj.get("presentation_priority") != "SUPPORT" or frame_obj.get("independent_focus") is not False:
        warnings.append({"code": "PART007_DEMOTION_MISSING"})
    if scene.render.engine != RENDER_ENGINE:
        warnings.append({"code": "RENDER_ENGINE_MISMATCH", "engine": scene.render.engine})
    lights = [obj for obj in bpy.data.objects if obj.type == "LIGHT"]
    if len(lights) != 3:
        warnings.append({"code": "LIGHT_RIG_MISMATCH", "count": len(lights)})
    if abs(float(scene.view_settings.exposure) - EXPOSURE) > 1e-4:
        warnings.append({"code": "EXPOSURE_MISMATCH", "exposure": scene.view_settings.exposure})
    for marker in scene.timeline_markers:
        if marker.name.startswith("T10_CAMERA_") and marker.camera is None:
            warnings.append({"code": "CAMERA_MARKER_UNBOUND", "marker": marker.name})

    forbidden = ("PENDING_PRODUCT_CONFIRMATION", "4G", "Bluetooth")
    annotation_text = [str(obj.data.body) for obj in bpy.data.objects if obj.type == "FONT"]
    for text in annotation_text:
        for word in forbidden:
            if word in text:
                warnings.append({"code": "UNCONFIRMED_PROTOCOL_IN_RENDER_TEXT", "word": word})
    stray_fonts = [
        obj.name for obj in bpy.data.objects
        if obj.type == "FONT" and not obj.name.startswith("T10V2_ANNOTATION_")
    ]
    if stray_fonts:
        warnings.append({"code": "STRAY_TEXT_OBJECTS", "objects": stray_fonts})

    outputs = _output_paths(root)
    missing = [name for name, path in outputs.items() if not path.is_file() or path.stat().st_size <= 0]
    if missing:
        warnings.append({"code": "REQUIRED_OUTPUT_MISSING", "outputs": missing})
    return {
        "technical_status": "PASS" if not warnings else "REVIEW",
        "source_part_count": len(objects),
        "source_faces": faces,
        "source_indexed_vertices": vertices,
        "visible_part_ids": visible,
        "hidden_part_ids": hidden,
        "animated_part_ids": animated,
        "animated_part_count": len(animated),
        "presentation_component_count": len(components),
        "render_engine": scene.render.engine,
        "exposure": float(scene.view_settings.exposure),
        "light_count": len(lights),
        "frame_range": [scene.frame_start, scene.frame_end],
        "fps": scene.render.fps,
        "annotation_text": annotation_text,
        "output_checks": {name: name not in missing for name in outputs},
        "warnings": warnings,
        "source_geometry_modified": bool(fingerprint_failures),
        "source_geometry_fingerprint_verified": not fingerprint_failures,
    }


def _output_paths(root: Path) -> dict[str, Path]:
    renders = root / RENDER_DIR
    return {
        **{name: renders / name for name in REQUIRED_STILLS},
        "storyboard_contact_sheet.png": renders / "storyboard_contact_sheet.png",
        PREVIEW_VIDEO: renders / PREVIEW_VIDEO,
        "product_story_v2.blend": root / SCENE_OUTPUT,
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
    result = validate_product_story_v2(args.project_root)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["technical_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
