"""Build the deterministic Task 10-R-PCB-V1 presentation plan JSON."""

from __future__ import annotations

import argparse
import math
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.task08_data import load_json, write_json
from stage_10R_pcb_presentation.scripts.pcb_presentation_data import (
    BASELINE,
    BOARD_THICKNESS_MM,
    CAMERAS_PATH,
    EXPECTED_PART_IDS,
    HIDDEN_PART_IDS,
    MANIFEST_PATH,
    MATERIALS_PATH,
    SOURCE_LAYOUT,
    SOURCE_SCENE,
    SOURCE_SCENE_SHA256,
    STORY_PART_IDS,
    ZONE_OFFSET_X_MM,
    build_camera_contract,
    build_component_plan,
    build_material_contract,
    build_part_reclassification,
    build_presentation_hierarchy,
    build_reference_manifest,
    build_status_contract,
    build_view_visibility_policy,
    component_footprint_rect,
)

# Story parts that keep their assembled transforms as device context.
CONTEXT_PART_IDS = tuple(
    part_id for part_id in STORY_PART_IDS if part_id not in {"PART_006", "PART_007", "PART_019"}
)


def build_presentation_manifest(project_root: Path) -> dict[str, Any]:
    root = Path(project_root).expanduser().resolve()
    layout = load_json(root / SOURCE_LAYOUT)
    records = layout.get("parts")
    if not isinstance(records, Mapping) or set(records) != set(EXPECTED_PART_IDS):
        raise ValueError("Task 10-R-PCB-V1 requires the complete frozen Stage 9C layout")
    assembled = {
        part_id: {
            "location": _vector(records[part_id]["assembled_location"]),
            "rotation_euler": _vector(records[part_id]["assembled_rotation"]),
            "scale": _vector(records[part_id]["assembled_scale"]),
        }
        for part_id in STORY_PART_IDS
    }
    board_center = [
        assembled["PART_019"]["location"][0] + ZONE_OFFSET_X_MM,
        assembled["PART_019"]["location"][1],
        assembled["PART_019"]["location"][2],
    ]
    board_top_z = board_center[2] + BOARD_THICKNESS_MM / 2.0

    components = []
    for component in build_component_plan():
        cx, cy = (float(v) for v in component["center_xy_mm"])
        height = float(component["height_mm"])
        footprint = component_footprint_rect(component)
        components.append(
            {
                **component,
                "world_location": [
                    board_center[0] + cx,
                    board_center[1] + cy,
                    board_top_z + height / 2.0,
                ],
                "footprint_board_local": footprint,
                "mounted_on": "PART_019",
            }
        )

    part_transforms: dict[str, Any] = {}
    for part_id in STORY_PART_IDS:
        record = {
            "location": list(assembled[part_id]["location"]),
            "rotation_euler": list(assembled[part_id]["rotation_euler"]),
            "scale": list(assembled[part_id]["scale"]),
            "presentation_tier": "CONTEXT",
        }
        if part_id == "PART_019":
            record["location"] = list(board_center)
            record["presentation_tier"] = "HERO"
        elif part_id == "PART_006":
            record["location"] = [
                assembled["PART_006"]["location"][0] + ZONE_OFFSET_X_MM,
                assembled["PART_006"]["location"][1],
                assembled["PART_006"]["location"][2],
            ]
            record["presentation_tier"] = "SECONDARY"
        elif part_id == "PART_007":
            record["presentation_tier"] = "SUPPORT"
        part_transforms[part_id] = record

    return {
        "version": "task10R_pcb_presentation_v1",
        "source_scene": SOURCE_SCENE,
        "source_scene_sha256": SOURCE_SCENE_SHA256,
        "source_layout": SOURCE_LAYOUT,
        "source_baseline": dict(BASELINE),
        "board_zone_center_mm": board_center,
        "board_top_z_mm": board_top_z,
        "zone_offset_x_mm": ZONE_OFFSET_X_MM,
        "part_transforms": part_transforms,
        "components": components,
        "component_count": len(components),
        "presentation_hierarchy": build_presentation_hierarchy(),
        "part_reclassification": build_part_reclassification(),
        "view_visibility": build_view_visibility_policy(),
        "reference_images": build_reference_manifest(root),
        "context_part_ids": list(CONTEXT_PART_IDS),
        "story_part_ids": list(STORY_PART_IDS),
        "hidden_part_ids": list(HIDDEN_PART_IDS),
        "status_contract": build_status_contract(),
        "no_animation_policy": "NO_KEYFRAMES_OR_ANIMATION_DATA",
        "surface_texture": "stage_10R_pcb_presentation/assets/pcb_surface_detail.png",
    }


def build_presentation_cameras(project_root: Path) -> dict[str, Any]:
    root = Path(project_root).expanduser().resolve()
    manifest = build_presentation_manifest(root)
    layout = load_json(root / SOURCE_LAYOUT)
    dimensions = {
        part_id: _vector(layout["parts"][part_id]["bbox_dimensions_mm"])
        for part_id in STORY_PART_IDS
    }
    transforms = manifest["part_transforms"]
    cameras = build_camera_contract()
    component_bounds = _component_bounds(manifest["components"])
    outputs: dict[str, Any] = {"version": "task10R_pcb_presentation_cameras_v1", "cameras": {}}
    for name, record in cameras.items():
        if record["view_role"] == "context":
            part_ids = list(STORY_PART_IDS)
        else:
            part_ids = ["PART_019"]
        bounds = _bounds3d(transforms, dimensions, part_ids)
        if record["view_role"] != "context":
            bounds = _union_bounds(bounds, component_bounds)
        target = [
            (bounds["x_min"] + bounds["x_max"]) / 2.0,
            (bounds["y_min"] + bounds["y_max"]) / 2.0,
            (bounds["z_min"] + bounds["z_max"]) / 2.0,
        ]
        direction = _normalise(record["direction"])
        radius = 0.5 * math.sqrt(
            (bounds["x_max"] - bounds["x_min"]) ** 2
            + (bounds["y_max"] - bounds["y_min"]) ** 2
            + (bounds["z_max"] - bounds["z_min"]) ** 2
        )
        aspect = 1920.0 / 1080.0
        sensor_width_mm = 36.0
        vertical_fov = 2.0 * math.atan((sensor_width_mm / aspect) / (2.0 * float(record["lens_mm"])))
        framing_margin = 1.02 if record["view_role"] != "context" else 1.06
        distance = max(radius / math.tan(vertical_fov / 2.0) * framing_margin, 300.0)
        outputs["cameras"][name] = {
            **record,
            "target": target,
            "location": [target[i] + direction[i] * distance for i in range(3)],
            "camera_distance_mm": round(distance, 3),
            "framing_method": "PERSPECTIVE_BOUNDING_SPHERE",
            "framing_margin": framing_margin,
            "clip_end_mm": max(distance * 4.0, 10000.0),
        }
    return outputs


def _component_bounds(components: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    x_min = min(float(c["footprint_board_local"]["x_min"]) + float(c["world_location"][0]) - float(c["center_xy_mm"][0]) for c in components)
    x_max = max(float(c["footprint_board_local"]["x_max"]) + float(c["world_location"][0]) - float(c["center_xy_mm"][0]) for c in components)
    y_min = min(float(c["footprint_board_local"]["y_min"]) + float(c["world_location"][1]) - float(c["center_xy_mm"][1]) for c in components)
    y_max = max(float(c["footprint_board_local"]["y_max"]) + float(c["world_location"][1]) - float(c["center_xy_mm"][1]) for c in components)
    z_min = min(float(c["world_location"][2]) - float(c["height_mm"]) / 2.0 for c in components)
    z_max = max(float(c["world_location"][2]) + float(c["height_mm"]) / 2.0 for c in components)
    return {"x_min": x_min, "x_max": x_max, "y_min": y_min, "y_max": y_max, "z_min": z_min, "z_max": z_max}


def _union_bounds(a: Mapping[str, float], b: Mapping[str, float]) -> dict[str, float]:
    return {
        key: (min if key.endswith("min") else max)(a[key], b[key])
        for key in a
    }


def _bounds3d(parts: Mapping[str, Mapping[str, Any]], dimensions: Mapping[str, Sequence[float]], part_ids: Sequence[str]) -> dict[str, float]:
    return {
        "x_min": min(float(parts[p]["location"][0]) - float(dimensions[p][0]) / 2.0 for p in part_ids),
        "x_max": max(float(parts[p]["location"][0]) + float(dimensions[p][0]) / 2.0 for p in part_ids),
        "y_min": min(float(parts[p]["location"][1]) - float(dimensions[p][1]) / 2.0 for p in part_ids),
        "y_max": max(float(parts[p]["location"][1]) + float(dimensions[p][1]) / 2.0 for p in part_ids),
        "z_min": min(float(parts[p]["location"][2]) - float(dimensions[p][2]) / 2.0 for p in part_ids),
        "z_max": max(float(parts[p]["location"][2]) + float(dimensions[p][2]) / 2.0 for p in part_ids),
    }


def _normalise(value: Sequence[float]) -> list[float]:
    length = math.sqrt(sum(float(item) ** 2 for item in value))
    if length <= 0.0:
        raise ValueError("camera direction cannot be zero")
    return [float(item) / length for item in value]


def _vector(value: Any) -> list[float]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 3:
        raise ValueError("expected a three-value vector")
    result = [float(item) for item in value]
    if not all(math.isfinite(item) for item in result):
        raise ValueError("vector values must be finite")
    return result


def write_presentation_configs(project_root: Path) -> dict[str, Path]:
    root = Path(project_root).expanduser().resolve()
    manifest = build_presentation_manifest(root)
    cameras = build_presentation_cameras(root)
    write_json(root / MANIFEST_PATH, manifest)
    write_json(root / MATERIALS_PATH, {"version": "task10R_pcb_presentation_materials_v1", "materials": build_material_contract()})
    write_json(root / CAMERAS_PATH, cameras)
    return {
        "manifest": root / MANIFEST_PATH,
        "materials": root / MATERIALS_PATH,
        "cameras": root / CAMERAS_PATH,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args(argv)
    for path in write_presentation_configs(args.project_root).values():
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
