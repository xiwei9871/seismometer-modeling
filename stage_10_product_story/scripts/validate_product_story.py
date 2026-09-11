"""Validate the generated Task 10 scene and review outputs."""

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
    SCENE_OUTPUT,
    VISIBLE_PART_IDS,
    mesh_geometry_fingerprint,
)
from stage_10_product_story.scripts.render_product_story import REQUIRED_OUTPUTS, REQUIRED_STILLS

try:  # pragma: no cover - Blender-only validation.
    import bpy  # type: ignore
except ImportError:  # pragma: no cover
    bpy = None  # type: ignore


STATE_PATH = "stage_10_product_story/config/state_transforms.json"


def validate_product_story(project_root: Path) -> dict[str, Any]:
    if bpy is None:
        raise RuntimeError("Blender bpy is required for Task 10 validation")
    root = Path(project_root).expanduser().resolve()
    scene_path = root / SCENE_OUTPUT
    state_data = load_json(root / STATE_PATH)
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
        expected_fingerprint = obj.get("task10_source_geometry_fingerprint")
        actual_fingerprint = mesh_geometry_fingerprint(obj.data)
        if not expected_fingerprint or str(expected_fingerprint) != actual_fingerprint:
            fingerprint_failures.append(part_id)
    if fingerprint_failures:
        warnings.append({"code": "SOURCE_GEOMETRY_FINGERPRINT_MISMATCH", "part_ids": sorted(fingerprint_failures, key=_part_number)})
    required_collections = {
        "STORY_10", "STORY_MODULES", "STORY_SOURCE_HIDDEN", "STORY_ANNOTATIONS", "STORY_CAMERAS",
    }
    missing_collections = sorted(name for name in required_collections if bpy.data.collections.get(name) is None)
    if missing_collections:
        warnings.append({"code": "TASK10_COLLECTIONS_MISSING", "collections": missing_collections})
    visible = sorted([part_id for part_id, obj in objects.items() if not obj.hide_render], key=_part_number)
    hidden = sorted([part_id for part_id, obj in objects.items() if obj.hide_render], key=_part_number)
    if visible != list(VISIBLE_PART_IDS) or hidden != list(HIDDEN_PART_IDS):
        warnings.append({"code": "VISIBILITY_POLICY_MISMATCH", "visible": visible, "hidden": hidden})
    animated = sorted([part_id for part_id, obj in objects.items() if obj.animation_data is not None], key=_part_number)
    if animated != list(VISIBLE_PART_IDS):
        warnings.append({"code": "ANIMATION_SCOPE_MISMATCH", "animated": animated})

    scene = bpy.context.scene
    if [scene.frame_start, scene.frame_end] != [1, 900] or scene.render.fps != 30:
        warnings.append({"code": "TIMELINE_MISMATCH", "frame_range": [scene.frame_start, scene.frame_end], "fps": scene.render.fps})
    if scene.get("task10_animation_created") is not True:
        warnings.append({"code": "ANIMATION_MARKER_MISSING"})
    if scene.get("task10_story_state_source") != STATE_PATH:
        warnings.append({"code": "STATE_SOURCE_MARKER_MISSING"})
    for part_id, obj in objects.items():
        expected_enabled = part_id in VISIBLE_PART_IDS
        if obj.get("task10_story_animation_enabled") is not expected_enabled:
            warnings.append({"code": "STORY_ANIMATION_PROPERTY_MISMATCH", "part_id": part_id})
            break
        if obj.get("task10_story_state_source") != STATE_PATH:
            warnings.append({"code": "PART_STATE_SOURCE_MARKER_MISSING", "part_id": part_id})
            break
    for frame, state_id in ((1, "ASSEMBLED"), (900, "FINAL_HERO")):
        scene.frame_set(frame)
        for part_id in VISIBLE_PART_IDS:
            actual = [float(value) for value in objects[part_id].location]
            expected = [float(value) for value in state_data["states"][state_id]["parts"][part_id]["location"]]
            if any(abs(left - right) > 1e-4 for left, right in zip(actual, expected)):
                warnings.append({"code": "STATE_TRANSFORM_MISMATCH", "frame": frame, "part_id": part_id})
                break
    forbidden = ("PENDING_PRODUCT_CONFIRMATION", "4G", "Bluetooth")
    annotation_text = [str(obj.data.body) for obj in bpy.data.objects if obj.type == "FONT"]
    for text in annotation_text:
        for word in forbidden:
            if word in text:
                warnings.append({"code": "UNCONFIRMED_PROTOCOL_IN_RENDER_TEXT", "word": word})
    outputs = _output_paths(root)
    missing = [name for name, path in outputs.items() if not path.is_file() or path.stat().st_size <= 0]
    if missing:
        warnings.append({"code": "REQUIRED_OUTPUT_MISSING", "outputs": missing})
    return {
        "status": "PASS" if not warnings else "REVIEW",
        "source_part_count": len(objects),
        "source_faces": faces,
        "source_indexed_vertices": vertices,
        "visible_part_ids": visible,
        "hidden_part_ids": hidden,
        "animated_part_ids": animated,
        "animated_part_count": len(animated),
        "hidden_part_animation_count": len([part_id for part_id in hidden if objects[part_id].animation_data is not None]),
        "frame_range": [scene.frame_start, scene.frame_end],
        "fps": scene.render.fps,
        "annotation_text": annotation_text,
        "output_checks": {name: name not in missing for name in outputs},
        "warnings": warnings,
        "source_geometry_modified": bool(fingerprint_failures),
        "source_geometry_fingerprint_verified": not fingerprint_failures,
    }


def _output_paths(root: Path) -> dict[str, Path]:
    renders = root / "stage_10_product_story/renders"
    return {
        **{name: renders / name for name in REQUIRED_STILLS},
        "storyboard_contact_sheet.png": renders / "storyboard_contact_sheet.png",
        "product_story_preview.mp4": renders / "product_story_preview.mp4",
        "product_story_preview.blend": root / SCENE_OUTPUT,
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
    result = validate_product_story(args.project_root)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
