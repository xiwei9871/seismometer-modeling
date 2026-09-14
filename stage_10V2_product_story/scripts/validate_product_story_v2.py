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
from stage_10_product_story.scripts.story_data import build_story_config
from stage_10V2_product_story.scripts import frustum_math as fm
from stage_10V2_product_story.scripts.story_v2_data import (
    EXPOSURE,
    FOCUS_FRAME_MARGIN_NDC,
    FOCUS_MAX_HEIGHT_NDC,
    FOCUS_MIN_HEIGHT_NDC,
    FOCUS_SHOT_POLICY,
    LIGHTING_OUTPUT,
    RENDER_ENGINE,
    SCENE_OUTPUT,
    STATE_OUTPUT,
)

try:  # pragma: no cover - Blender-only validation.
    import bpy  # type: ignore
    from mathutils import Vector  # type: ignore
except ImportError:  # pragma: no cover
    bpy = None  # type: ignore
    Vector = None  # type: ignore


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
        bpy.context.view_layer.update()
        board = objects["PART_019"]
        for component_id, local in local_by_id.items():
            obj = components.get(component_id)
            if obj is None:
                continue
            # Check the rendered geometry (matrix_world @ mesh bounds), not just
            # obj.location — a baked-in mesh offset would pass a location check
            # while rendering double-offset.
            bbox_center = sum(
                (Vector(tuple(corner)) for corner in obj.bound_box), Vector()
            ) / 8
            world_center = obj.matrix_world @ bbox_center
            for axis in range(3):
                expected = float(board.location[axis]) + float(local[axis])
                if abs(float(world_center[axis]) - expected) > 1.0:
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

    _occlusion_report(warnings, objects, components, scene)

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


_MAX_VERT_SAMPLES = 1600
_FRAME_HULL = ((-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0))


def _occlusion_report(warnings, part_objects, components, scene):
    """Fail-closed frustum gate (Task 10-V3).

    Evaluates the animated scene at each focus shot's mid-frame through the
    actual camera object and requires the focus subject's projected
    silhouette to stay on-frame, subject-scaled, and — for isolate-mode
    shots — silhouette-clean of every context part.
    """
    frame_for_shot = {
        record["shot_id"]: (record["frame_start"] + record["frame_end"]) // 2
        for record in build_story_config()["shots"]
    }
    aspect = scene.render.resolution_x / scene.render.resolution_y
    for shot_id, spec in FOCUS_SHOT_POLICY.items():
        cam_obj = bpy.data.objects.get(spec["camera"])
        if cam_obj is None:
            warnings.append({"code": "FOCUS_CAMERA_MISSING", "shot_id": shot_id})
            continue
        scene.frame_set(frame_for_shot[shot_id])
        bpy.context.view_layer.update()
        matrix = cam_obj.matrix_world
        cam_loc = tuple(matrix.translation)
        basis = (
            tuple(matrix.col[0].xyz),
            tuple(matrix.col[1].xyz),
            tuple(matrix.col[2].xyz),
        )
        fovs = fm.fov_xy(cam_obj.data.lens, cam_obj.data.sensor_width, aspect)

        focus_ids = set(spec["parts"])
        focus_pts: list[tuple[float, float]] = []
        focus_front = float("inf")
        context_entries: list[dict[str, Any]] = []

        def collect(obj, into):
            """Sampled NDC points plus nearest camera-space depth."""
            obj_matrix = obj.matrix_world
            count = len(obj.data.vertices)
            step = max(1, count // _MAX_VERT_SAMPLES)
            front = float("inf")
            for index in range(0, count, step):
                world = obj_matrix @ obj.data.vertices[index].co
                local = fm.world_to_camera(world, cam_loc, basis)
                if local[2] < -fm.EPSILON:
                    front = min(front, -local[2])
                ndc = fm.project_ndc(world, cam_loc, basis, fovs)
                if ndc is not None:
                    into.append(ndc)
            return front

        visible_context: list[str] = []
        for part_id, obj in part_objects.items():
            if part_id not in VISIBLE_PART_IDS or obj.hide_render:
                continue
            if part_id in focus_ids:
                focus_front = min(focus_front, collect(obj, focus_pts))
            else:
                visible_context.append(part_id)
                pts: list[tuple[float, float]] = []
                front = collect(obj, pts)
                hull = fm.convex_hull_2d(pts)
                if len(hull) >= 3 and fm.hulls_overlap(hull, _FRAME_HULL):
                    context_entries.append(
                        {"name": part_id, "hull": hull, "front_depth": front}
                    )
        if spec.get("focus_components"):
            for obj in components.values():
                if obj.hide_render:
                    continue
                focus_front = min(focus_front, collect(obj, focus_pts))
        else:
            # Mounted components stay with the board elsewhere; when the board
            # is not the subject they are context (and hidden in isolate shots).
            for obj in components.values():
                if obj.hide_render:
                    continue
                visible_context.append(obj.name)
                pts = []
                front = collect(obj, pts)
                hull = fm.convex_hull_2d(pts)
                if len(hull) >= 3 and fm.hulls_overlap(hull, _FRAME_HULL):
                    context_entries.append(
                        {"name": obj.name, "hull": hull, "front_depth": front}
                    )

        focus_hull = fm.convex_hull_2d(focus_pts)
        if len(focus_hull) < 3:
            warnings.append({"code": "FOCUS_SUBJECT_OFFFRAME", "shot_id": shot_id})
            continue
        if spec.get("mode") == "layer":
            # The subject is the housing environment itself; visibility is the
            # only meaningful check — it legitimately fills the frame.
            continue
        if spec.get("mode") == "isolate" and visible_context:
            # V4: isolate shots must render the subject alone — every other
            # part and presentation component is keyed hidden for the range.
            warnings.append({
                "code": "ISOLATE_CONTEXT_VISIBLE",
                "shot_id": shot_id,
                "parts": sorted(visible_context),
            })
        frame_margin = max(FOCUS_FRAME_MARGIN_NDC, spec["margin_ndc"] * 0.5)
        if not fm.hull_inside_frame(focus_hull, frame_margin):
            warnings.append({"code": "FOCUS_SUBJECT_OFFFRAME", "shot_id": shot_id})
        height = fm.hull_extent(focus_hull)[1]
        if not FOCUS_MIN_HEIGHT_NDC <= height <= FOCUS_MAX_HEIGHT_NDC:
            warnings.append({
                "code": "FOCUS_SUBJECT_SCALE",
                "shot_id": shot_id,
                "height_ndc": height,
            })
        offenders = sorted(
            entry["name"]
            for entry in context_entries
            # Occlusion = context closer than the subject's nearest surface.
            # Overlapping context behind the subject is layering by design.
            if entry["front_depth"] < focus_front
            and not fm.hulls_separated(focus_hull, entry["hull"], spec["margin_ndc"])
        )
        if offenders:
            warnings.append({
                "code": "FOCUS_OCCLUSION",
                "shot_id": shot_id,
                "occluders": offenders,
            })


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
