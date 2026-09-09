"""Pure validation and report helpers for the static R1 exploded layout."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
import math
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.task08_data import load_json
from stage_09A_R1_exploded_rework.scripts.apply_explosion_layout import validate_r1_scene_facts
from stage_09A_R1_exploded_rework.scripts.build_explosion_groups import (
    EXPECTED_PART_IDS,
    IMPORTANT_PART_IDS,
    validate_explosion_layout,
)

try:  # pragma: no cover - exercised by Blender integration.
    import bpy  # type: ignore
    from bpy_extras.object_utils import world_to_camera_view  # type: ignore
    from mathutils import Vector  # type: ignore
except ImportError:  # pragma: no cover
    bpy = None  # type: ignore
    world_to_camera_view = None  # type: ignore
    Vector = None  # type: ignore


CAMERA_NAMES = (
    "CAM_EXPLODED_HERO",
    "CAM_EXPLODED_ENGINEERING",
    "CAM_EXPLODED_TOP",
    "CAM_EXPLODED_REAR",
)


def build_explosion_validation(
    layout: Mapping[str, Any],
    *,
    camera_config: Mapping[str, Any] | None = None,
    render_paths: Sequence[Path] = (),
    scene_validation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build final validation from layout, files, and actual Blender facts."""
    validated = validate_explosion_layout(layout)
    parts = validated["parts"]
    visible = [record for record in parts.values() if record["presentation_visibility"] == "VISIBLE"]
    bounds = _bounds(visible)
    group_counts = {
        group_id: len(group["part_ids"])
        for group_id, group in validated["groups"].items()
    }
    unassigned = [
        part_id
        for part_id in IMPORTANT_PART_IDS
        if not parts[part_id].get("group")
    ]
    actual = dict(scene_validation or {})
    actual_available = bool(actual.get("actual_scene_validation"))
    camera_names = list(
        actual.get("camera_names")
        if actual_available
        else (camera_config or {}).get("camera_names") or []
    )
    output_status = {
        str(path): bool(Path(path).is_file() and Path(path).stat().st_size > 0)
        for path in render_paths
    }
    camera_warnings = list(actual.get("camera_clipping_warnings") or []) if actual_available else []
    if camera_config is not None and camera_names != [
        "CAM_EXPLODED_HERO",
        "CAM_EXPLODED_ENGINEERING",
        "CAM_EXPLODED_TOP",
        "CAM_EXPLODED_REAR",
    ]:
        camera_warnings.append("CAMERA_CONFIG_WARNING")
    warnings: list[dict[str, Any]] = []
    if unassigned:
        warnings.append({"code": "UNASSIGNED_MAJOR_COMPONENT", "parts": unassigned})
    if any(value <= 0.0 for value in bounds["dimensions"]):
        warnings.append({"code": "INVALID_EXPLODED_BOUNDS"})
    warnings.extend(
        item if isinstance(item, Mapping) else {"code": str(item)}
        for item in (actual.get("warnings") or [])
    )
    warnings.extend({"code": code} for code in camera_warnings if isinstance(code, str))
    if not actual_available:
        warnings.append({"code": "BLENDER_SCENE_VALIDATION_NOT_RUN"})
    occupancy = actual.get("hero_frame_occupancy") if actual_available else None
    occupancy_status = (occupancy or {}).get("status") if isinstance(occupancy, Mapping) else "NOT_MEASURED"
    scene_status = actual.get("status") if actual_available else "NOT_RUN"
    major_overlaps = list(actual.get("major_overlaps_detected") or []) if actual_available else []
    floating_warnings = list(actual.get("floating_component_warnings") or []) if actual_available else []
    edge_warnings = list(actual.get("edge_on_visibility_warnings") or []) if actual_available else []
    status = (
        "PASS"
        if (
            actual_available
            and scene_status == "PASS"
            and not unassigned
            and all(output_status.values())
            and occupancy_status == "PASS"
            and not major_overlaps
            and not camera_warnings
        )
        else "REVIEW"
    )
    actual_source = actual if actual_available else {}
    return {
        "source_part_count": actual_source.get("source_part_count"),
        "source_faces": actual_source.get("polygons"),
        "source_indexed_vertices": actual_source.get("vertices"),
        "expected_source_baseline": validated["source_baseline"],
        "visible_part_count": actual_source.get("visible_part_count", len(visible)),
        "hidden_part_count": actual_source.get("hidden_part_count", len(parts) - len(visible)),
        "group_counts": group_counts,
        "unassigned_objects": unassigned,
        "primary_axis_objects": [
            part_id for part_id in ("PART_001", "PART_002", "PART_004", "PART_005")
        ],
        "exploded_bounds": bounds,
        "minimum_object_to_object_projected_spacing": actual.get("minimum_object_to_object_projected_spacing"),
        "major_overlaps_detected": major_overlaps,
        "floating_component_warnings": floating_warnings,
        "edge_on_visibility_warnings": edge_warnings,
        "camera_clipping_warnings": camera_warnings,
        "hero_frame_occupancy": occupancy or {
            "target_min": 0.60,
            "target_max": 0.75,
            "measured": None,
            "status": "NOT_MEASURED",
        },
        "render_outputs": output_status,
        "animation_data_count": actual_source.get("animation_data_count"),
        "animation_created": actual_source.get("animation_created", False),
        "actual_scene_validation": actual_available,
        "scene_validation": actual,
        "warnings": warnings,
        "status": status,
    }


def validate_blender_scene(project_root: Path) -> dict[str, Any]:
    """Re-open the generated blend and measure the actual static scene."""
    if bpy is None or Vector is None or world_to_camera_view is None:
        raise RuntimeError("Blender bpy is required for actual R1 scene validation")
    root = Path(project_root).expanduser().resolve()
    blend_path = root / "stage_09A_R1_exploded_rework/scene/exploded_layout_v2.blend"
    bpy.ops.wm.open_mainfile(filepath=str(blend_path))
    source_objects = sorted(
        [
            obj
            for obj in bpy.data.objects
            if obj.type == "MESH" and obj.get("source") == "original_stl"
        ],
        key=lambda obj: _part_number(obj.get("part_id")),
    )
    facts = [_object_fact(obj) for obj in source_objects]
    scene_facts = validate_r1_scene_facts(
        facts,
        vertices=sum(len(obj.data.vertices) for obj in source_objects),
        polygons=sum(len(obj.data.polygons) for obj in source_objects),
    )
    visible = [obj for obj in source_objects if not obj.hide_viewport and not obj.hide_render]
    cameras = {name: bpy.data.objects.get(name) for name in CAMERA_NAMES}
    camera_names = [name for name, obj in cameras.items() if obj is not None and obj.type == "CAMERA"]
    warnings: list[dict[str, Any]] = []
    if camera_names != list(CAMERA_NAMES):
        warnings.append({"code": "CAMERA_SET_MISMATCH", "actual": camera_names})
    if len(visible) != 22:
        warnings.append({"code": "VISIBLE_PART_POLICY_MISMATCH", "count": len(visible)})
    if bpy.context.scene.animation_data is not None:
        warnings.append({"code": "SCENE_ANIMATION_DATA_PRESENT"})

    layout = load_json(root / "stage_09A_R1_exploded_rework/config/explosion_layout_config.json")
    hero = cameras.get("CAM_EXPLODED_HERO")
    occupancy = _camera_occupancy(bpy.context.scene, hero, visible) if hero is not None else _unmeasured_occupancy()
    clipping = _camera_clipping_warnings(cameras, visible)
    overlaps, minimum_spacing = _projected_overlap_warnings(bpy.context.scene, hero, visible)
    floating = _floating_warnings(layout, visible)
    edge_on = _edge_on_warnings(bpy.context.scene, hero, visible)
    warnings.extend(clipping)
    warnings.extend(overlaps)
    warnings.extend(floating)
    warnings.extend(edge_on)
    if occupancy.get("status") != "PASS":
        warnings.append({"code": "HERO_FRAME_OCCUPANCY_WARNING", "occupancy": occupancy})
    status = "PASS" if not warnings else "REVIEW"
    return {
        "actual_scene_validation": True,
        "status": status,
        **scene_facts,
        "polygons": scene_facts["polygons"],
        "vertices": scene_facts["vertices"],
        "camera_names": camera_names,
        "visible_part_ids": [str(obj.get("part_id")) for obj in visible],
        "hero_frame_occupancy": occupancy,
        "minimum_object_to_object_projected_spacing": minimum_spacing,
        "major_overlaps_detected": overlaps,
        "floating_component_warnings": floating,
        "edge_on_visibility_warnings": edge_on,
        "camera_clipping_warnings": clipping,
        "warnings": warnings,
        "animation_created": False,
    }


def build_layout_report(
    layout: Mapping[str, Any],
    validation: Mapping[str, Any],
    *,
    scene_output: str | None = None,
) -> str:
    """Write the human-readable R1 layout explanation."""
    lines = [
        "# Task 9A-R1 Exploded Layout Report",
        "",
        "## 1. Assembly hierarchy",
        "",
        "- Main stack: `MAIN_STACK` — PART_001, PART_002, PART_004, PART_005.",
        "- Sensor branch: `SENSOR_BRANCH` — PART_003, PART_012–PART_014.",
        "- PCB branch: `PCB_BRANCH` — PART_006, PART_007, PART_019.",
        "- Battery branch: `BATTERY_BRANCH` — PART_008–PART_011, PART_015–PART_016.",
        "- Top interface branch: `TOP_INTERFACE_BRANCH` — PART_017–PART_018.",
        "- Leveling branch: `LEVELING_BRANCH` — PART_020–PART_022.",
        "",
        "## 2. Explosion logic",
        "",
        "- Primary axis: global Z, anchored by `PART_001` (`LOWER_HOUSING`).",
        "- Sensor and PCB use compact lateral branches; Battery is a compact 3×2 array.",
        "- Leveling cones preserve the original three-point XY footprint and move downward.",
        "- Hidden source PARTs are retained but do not enter motion/collision review.",
        "",
        "## 3. Camera strategy",
        "",
        "- Hero: elevated 3/4 perspective with a medium/long lens.",
        "- Engineering: controlled near-isometric view.",
        "- Top and rear: validation views for alignment and occlusion.",
        "",
        "## 4. Changes from previous exploded layout",
        "",
        "- Rebuilt from original assembled transforms instead of v4 presentation offsets.",
        "- Replaced flat scattering with a central vertical skeleton and secondary branches.",
        "- Kept secondary geometry compact and reduced visual competition from small parts.",
        "- Kept leveling cones near their actual mounting relationship.",
        "",
        "## 5. Remaining ambiguities",
        "",
        "- This is a presentation layout, not a confirmed physical disassembly sequence.",
        "- PART_017/PART_018 remain a paired interface group without charge/data assignment.",
        "- Neutral presentation materials are not the final product palette.",
        "",
        "## Validation summary",
        "",
        f"- Source PART meshes: {validation['source_part_count']}",
        f"- Faces: {validation['source_faces']}",
        f"- Indexed vertices: {validation['source_indexed_vertices']}",
        f"- Visible presentation parts: {validation['visible_part_count']}",
        f"- Hidden source parts: {validation['hidden_part_count']}",
        f"- Animation data: {validation['animation_data_count']}",
        f"- Actual `.blend` validation executed: {validation['actual_scene_validation']}",
        f"- Hero occupancy: `{validation['hero_frame_occupancy']['measured']}`",
        f"- Major Hero occlusions: {len(validation['major_overlaps_detected'])}",
        f"- Camera clipping warnings: {len(validation['camera_clipping_warnings'])}",
        f"- Status: `{validation['status']}`",
    ]
    if scene_output:
        lines.append(f"- Derived scene: `{scene_output}`")
    return "\n".join(lines) + "\n"


def build_validation_report(validation: Mapping[str, Any]) -> str:
    """Render the machine validation payload as a concise Markdown report."""
    lines = [
        "# Task 9A-R1 Validation Report",
        "",
        f"- Status: `{validation['status']}`",
        f"- Source PART meshes: {validation['source_part_count']}",
        f"- Faces: {validation['source_faces']}",
        f"- Indexed vertices: {validation['source_indexed_vertices']}",
        f"- Visible parts: {validation['visible_part_count']}",
        f"- Hidden parts: {validation['hidden_part_count']}",
        f"- Animation data count: {validation['animation_data_count']}",
        f"- Actual `.blend` validation executed: {validation['actual_scene_validation']}",
        "",
        "## Bounds",
        "",
        f"- Min: `{validation['exploded_bounds']['min']}`",
        f"- Max: `{validation['exploded_bounds']['max']}`",
        f"- Dimensions: `{validation['exploded_bounds']['dimensions']}`",
        "",
        "## Camera and readability metrics",
        "",
        f"- Hero frame occupancy: `{validation['hero_frame_occupancy']}`",
        f"- Minimum projected spacing: `{validation['minimum_object_to_object_projected_spacing']}`",
        f"- Major Hero occlusions: {len(validation['major_overlaps_detected'])}",
        f"- Floating-component warnings: {len(validation['floating_component_warnings'])}",
        f"- Edge-on warnings: {len(validation['edge_on_visibility_warnings'])}",
        f"- Camera-clipping warnings: {len(validation['camera_clipping_warnings'])}",
        "",
        "## Warnings",
        "",
    ]
    warnings = validation.get("warnings") or []
    lines.extend(f"- `{item.get('code', 'UNKNOWN_WARNING')}`" for item in warnings)
    if not warnings:
        lines.append("- None")
    return "\n".join(lines) + "\n"


def _bounds(records: Sequence[Mapping[str, Any]]) -> dict[str, list[float]]:
    low = [float("inf")] * 3
    high = [float("-inf")] * 3
    for record in records:
        location = record["presentation_location"]
        dimensions = record["bbox_dimensions_mm"]
        for index in range(3):
            half = float(dimensions[index]) / 2.0
            low[index] = min(low[index], float(location[index]) - half)
            high[index] = max(high[index], float(location[index]) + half)
    if any(not math.isfinite(value) for value in low + high):
        raise ValueError("R1 exploded bounds are not finite")
    return {
        "min": low,
        "max": high,
        "dimensions": [high[index] - low[index] for index in range(3)],
    }


def _object_fact(obj: Any) -> dict[str, Any]:
    return {
        "part_id": obj.get("part_id"),
        "source": obj.get("source"),
        "type": obj.type,
        "hidden": bool(obj.hide_viewport or obj.hide_render),
        "animation_data": obj.animation_data,
    }


def _part_number(part_id: Any) -> int:
    try:
        return int(str(part_id).split("_")[-1])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid PART ID: {part_id!r}") from exc


def _world_corners(obj: Any) -> list[Any]:
    return [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]


def _camera_rect(scene: Any, camera: Any, obj: Any) -> dict[str, float]:
    points = [world_to_camera_view(scene, camera, point) for point in _world_corners(obj)]
    xs = [float(point.x) for point in points]
    ys = [float(point.y) for point in points]
    return {
        "min_x": min(xs),
        "max_x": max(xs),
        "min_y": min(ys),
        "max_y": max(ys),
        "width": max(xs) - min(xs),
        "height": max(ys) - min(ys),
    }


def _camera_occupancy(scene: Any, camera: Any, objects: Sequence[Any]) -> dict[str, Any]:
    if camera is None or not objects:
        return _unmeasured_occupancy()
    rects = [_camera_rect(scene, camera, obj) for obj in objects]
    min_x = min(rect["min_x"] for rect in rects)
    max_x = max(rect["max_x"] for rect in rects)
    min_y = min(rect["min_y"] for rect in rects)
    max_y = max(rect["max_y"] for rect in rects)
    width = max_x - min_x
    height = max_y - min_y
    measured = {"width": width, "height": height, "area": width * height}
    # A little tolerance is intentional: the 60-75% target is a composition
    # target, not a hard render crop boundary.
    status = "PASS" if 0.55 <= width <= 0.85 and 0.55 <= height <= 0.85 else "REVIEW"
    return {
        "target_min": 0.60,
        "target_max": 0.75,
        "measured": measured,
        "status": status,
        "projected_bounds": {"min": [min_x, min_y], "max": [max_x, max_y]},
    }


def _unmeasured_occupancy() -> dict[str, Any]:
    return {
        "target_min": 0.60,
        "target_max": 0.75,
        "measured": None,
        "status": "NOT_MEASURED",
    }


def _camera_clipping_warnings(cameras: Mapping[str, Any], objects: Sequence[Any]) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    for name, camera in cameras.items():
        if camera is None or camera.type != "CAMERA":
            continue
        inverse = camera.matrix_world.inverted()
        for obj in objects:
            depths = [float(-(inverse @ point).z) for point in _world_corners(obj)]
            if min(depths) < camera.data.clip_start or max(depths) > camera.data.clip_end:
                warnings.append(
                    {
                        "code": "CAMERA_CLIPPING_WARNING",
                        "camera": name,
                        "part_id": obj.get("part_id"),
                        "depth_min": min(depths),
                        "depth_max": max(depths),
                    }
                )
    return warnings


def _projected_overlap_warnings(
    scene: Any, camera: Any, objects: Sequence[Any]
) -> tuple[list[dict[str, Any]], float | None]:
    if camera is None:
        return [], None
    records = [(obj, _camera_rect(scene, camera, obj)) for obj in objects]
    warnings: list[dict[str, Any]] = []
    positive_gaps: list[float] = []
    for index, (left_obj, left) in enumerate(records):
        for right_obj, right in records[index + 1 :]:
            intersection_width = max(
                0.0,
                min(left["max_x"], right["max_x"]) - max(left["min_x"], right["min_x"]),
            )
            intersection_height = max(
                0.0,
                min(left["max_y"], right["max_y"]) - max(left["min_y"], right["min_y"]),
            )
            intersection = intersection_width * intersection_height
            left_area = left["width"] * left["height"]
            right_area = right["width"] * right["height"]
            minimum_area = min(left_area, right_area)
            if intersection <= 0.0:
                horizontal_gap = max(left["min_x"], right["min_x"]) - min(left["max_x"], right["max_x"])
                vertical_gap = max(left["min_y"], right["min_y"]) - min(left["max_y"], right["max_y"])
                positive_gaps.append(max(0.0, horizontal_gap, vertical_gap))
            elif minimum_area > 0.0 and intersection / minimum_area >= 0.72:
                left_group = left_obj.get("r1_group")
                right_group = right_obj.get("r1_group")
                left_center = (
                    (left["min_x"] + left["max_x"]) / 2.0,
                    (left["min_y"] + left["max_y"]) / 2.0,
                )
                right_center = (
                    (right["min_x"] + right["max_x"]) / 2.0,
                    (right["min_y"] + right["max_y"]) / 2.0,
                )
                center_distance = math.hypot(
                    left_center[0] - right_center[0],
                    left_center[1] - right_center[1],
                )
                # Overlap within the intentionally layered central stack is
                # expected; cross-branch occlusion is what this check targets.
                # Bounding boxes can overlap in projection while the actual
                # meshes are clearly separated (for example a connector near
                # a housing edge).  Require centers to be close before calling
                # that a severe presentation occlusion.
                if left_group != right_group and center_distance <= 0.075:
                    warnings.append(
                        {
                            "code": "HERO_OCCLUSION_WARNING",
                            "part_ids": [left_obj.get("part_id"), right_obj.get("part_id")],
                            "overlap_ratio": intersection / minimum_area,
                            "projected_center_distance": center_distance,
                        }
                    )
    return warnings, (min(positive_gaps) if positive_gaps else 0.0)


def _floating_warnings(layout: Mapping[str, Any], objects: Sequence[Any]) -> list[dict[str, Any]]:
    parts = layout.get("parts") if isinstance(layout, Mapping) else None
    if not isinstance(parts, Mapping):
        return [{"code": "FLOATING_COMPONENT_CHECK_UNAVAILABLE"}]
    anchor = parts.get("PART_001", {})
    anchor_bbox = anchor.get("bbox_dimensions_mm") or [0.0, 0.0, 0.0]
    anchor_diagonal = math.sqrt(sum(float(value) ** 2 for value in anchor_bbox))
    threshold = max(anchor_diagonal * 2.5, 450.0)
    warnings: list[dict[str, Any]] = []
    by_id = {str(obj.get("part_id")): obj for obj in objects}
    for part_id, obj in by_id.items():
        record = parts.get(part_id)
        if not isinstance(record, Mapping) or not record.get("probable_parent_object"):
            continue
        parent_id = str(record["probable_parent_object"])
        parent = by_id.get(parent_id)
        if parent is None:
            continue
        delta = (obj.location - parent.location).length
        if delta > threshold:
            warnings.append(
                {
                    "code": "FLOATING_COMPONENT_WARNING",
                    "part_id": part_id,
                    "parent_part_id": parent_id,
                    "distance_mm": float(delta),
                    "threshold_mm": threshold,
                }
            )
    return warnings


def _edge_on_warnings(scene: Any, camera: Any, objects: Sequence[Any]) -> list[dict[str, Any]]:
    if camera is None:
        return [{"code": "EDGE_ON_CHECK_UNAVAILABLE"}]
    warnings: list[dict[str, Any]] = []
    for obj in objects:
        rect = _camera_rect(scene, camera, obj)
        if rect["width"] < 0.012 or rect["height"] < 0.012 or rect["width"] * rect["height"] < 0.00035:
            warnings.append(
                {
                    "code": "EDGE_ON_VISIBILITY_WARNING",
                    "part_id": obj.get("part_id"),
                    "projected_width": rect["width"],
                    "projected_height": rect["height"],
                }
            )
    return warnings


def _script_arguments() -> list[str]:
    arguments = list(sys.argv[1:])
    return arguments[arguments.index("--") + 1 :] if "--" in arguments else arguments


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args(argv if argv is not None else _script_arguments())
    print(json.dumps(validate_blender_scene(args.project_root), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
