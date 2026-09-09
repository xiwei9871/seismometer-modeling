"""Validate actual Task 9C Blender scene facts and review outputs."""

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
from stage_09C_refined_explosion.scripts.build_refined_layout import (
    EXPECTED_PART_IDS,
    VISIBLE_PART_IDS,
    validate_refined_layout,
)

try:  # pragma: no cover - executed by Blender.
    import bpy  # type: ignore
except ImportError:  # pragma: no cover
    bpy = None  # type: ignore


REQUIRED_OUTPUTS = (
    "exploded_hero_refined.png",
    "exploded_engineering_refined.png",
    "pcb_detail_refined.png",
    "sensor_detail_refined.png",
    "exploded_animation_preview.blend",
    "exploded_preview.mp4",
    "exploded_keyframes_contact_sheet.png",
)


def validate_refined_scene(project_root: Path) -> dict[str, Any]:
    if bpy is None:
        raise RuntimeError("Blender bpy is required for Task 9C validation")
    root = Path(project_root).expanduser().resolve()
    layout = validate_refined_layout(load_json(root / "stage_09C_refined_explosion/config/refined_layout.json"))
    blend_path = root / "stage_09C_refined_explosion/scene/exploded_animation_preview.blend"
    bpy.ops.wm.open_mainfile(filepath=str(blend_path))
    objects = {
        str(obj.get("part_id")): obj
        for obj in bpy.data.objects
        if obj.type == "MESH" and obj.get("source") == "original_stl"
    }
    warnings: list[dict[str, Any]] = []
    if set(objects) != set(EXPECTED_PART_IDS):
        warnings.append({"code": "SOURCE_PART_COVERAGE_MISMATCH", "actual_count": len(objects)})
    vertices = sum(len(obj.data.vertices) for obj in objects.values())
    polygons = sum(len(obj.data.polygons) for obj in objects.values())
    visible = sorted(
        [part_id for part_id, obj in objects.items() if not obj.hide_viewport and not obj.hide_render],
        key=_part_number,
    )
    if vertices != 221902 or polygons != 444296:
        warnings.append({"code": "FROZEN_GEOMETRY_TOTAL_MISMATCH", "vertices": vertices, "polygons": polygons})
    if visible != list(VISIBLE_PART_IDS):
        warnings.append({"code": "VISIBLE_PART_POLICY_MISMATCH", "actual": visible})
    animated = sorted(
        [part_id for part_id, obj in objects.items() if obj.animation_data is not None],
        key=_part_number,
    )
    hidden_animated = sorted(set(animated) - set(VISIBLE_PART_IDS), key=_part_number)
    if hidden_animated:
        warnings.append({"code": "HIDDEN_PART_ANIMATION_PRESENT", "parts": hidden_animated})
    if set(animated) != set(VISIBLE_PART_IDS):
        warnings.append({"code": "ANIMATION_SCOPE_MISMATCH", "actual": animated})
    scene = bpy.context.scene
    if scene.render.fps != 30 or scene.frame_start != 1 or scene.frame_end != 540:
        warnings.append({"code": "ANIMATION_TIMELINE_MISMATCH"})
    frame1_mismatches = _transform_mismatches(scene, objects, layout, "assembled_location", 1)
    frame540_mismatches = _transform_mismatches(scene, objects, layout, "refined_presentation_location", 540)
    if frame1_mismatches:
        warnings.append({"code": "ASSEMBLED_FRAME_MISMATCH", "parts": frame1_mismatches})
    if frame540_mismatches:
        warnings.append({"code": "REFINED_FRAME_MISMATCH", "parts": frame540_mismatches})
    # The blend lives in scene/, while renders live in renders/.
    output_checks = {
        name: (blend_path if name.endswith(".blend") else root / "stage_09C_refined_explosion/renders" / name).is_file()
        for name in REQUIRED_OUTPUTS
    }
    for name in REQUIRED_OUTPUTS:
        path = blend_path if name.endswith(".blend") else root / "stage_09C_refined_explosion/renders" / name
        output_checks[name] = path.is_file() and path.stat().st_size > 0
    if not all(output_checks.values()):
        warnings.append({"code": "REQUIRED_OUTPUT_MISSING", "outputs": [name for name, ok in output_checks.items() if not ok]})
    status = "PASS" if not warnings else "REVIEW"
    return {
        "status": status,
        "source_part_count": len(objects),
        "source_faces": polygons,
        "source_indexed_vertices": vertices,
        "visible_part_ids": visible,
        "visible_part_count": len(visible),
        "animated_part_ids": animated,
        "animated_part_count": len(animated),
        "hidden_part_animation_count": len(hidden_animated),
        "frame_range": [scene.frame_start, scene.frame_end],
        "fps": scene.render.fps,
        "frame1_assembled_mismatches": frame1_mismatches,
        "frame540_refined_mismatches": frame540_mismatches,
        "output_checks": output_checks,
        "warnings": warnings,
        "source_geometry_modified": False,
    }


def _transform_mismatches(scene: Any, objects: dict[str, Any], layout: dict[str, Any], key: str, frame: int) -> list[str]:
    scene.frame_set(frame)
    mismatches = []
    for part_id in VISIBLE_PART_IDS:
        actual = [float(value) for value in objects[part_id].location]
        expected = [float(value) for value in layout["parts"][part_id][key]]
        if any(abs(left - right) > 1e-4 for left, right in zip(actual, expected)):
            mismatches.append(part_id)
    return mismatches


def _part_number(part_id: str) -> int:
    return int(str(part_id).split("_")[-1])


def _script_arguments() -> list[str]:
    arguments = list(sys.argv[1:])
    return arguments[arguments.index("--") + 1 :] if "--" in arguments else arguments


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args(argv if argv is not None else _script_arguments())
    result = validate_refined_scene(args.project_root)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
