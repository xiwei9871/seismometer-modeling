"""Build deterministic Task 10-R transforms from the frozen Stage 9C layout."""

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
from stage_10R_functional_inspection.scripts.inspection_data import (
    BASELINE,
    EXPECTED_PART_IDS,
    HIDDEN_PART_IDS,
    INSPECTION_STATE_IDS,
    SOURCE_LAYOUT,
    SOURCE_SCENE,
    SOURCE_SCENE_SHA256,
    STORY_PART_IDS,
    build_inspection_states,
    build_inspection_camera_contract,
    build_module_groups,
    build_status_contract,
    build_visibility_policy,
)


PLAN_OUTPUT = "stage_10R_functional_inspection/config/inspection_states.json"
CAMERA_OUTPUT = "stage_10R_functional_inspection/config/inspection_cameras.json"


def build_inspection_plan(project_root: Path) -> dict[str, Any]:
    root = Path(project_root).expanduser().resolve()
    layout = load_json(root / SOURCE_LAYOUT)
    records = layout.get("parts")
    if not isinstance(records, Mapping) or set(records) != set(EXPECTED_PART_IDS):
        raise ValueError("Task 10-R requires the complete frozen Stage 9C layout")
    assembled = {
        part_id: {
            "location": _vector(records[part_id]["assembled_location"]),
            "rotation_euler": _vector(records[part_id]["assembled_rotation"]),
            "scale": _vector(records[part_id]["assembled_scale"]),
        }
        for part_id in STORY_PART_IDS
    }
    dimensions = {
        part_id: _vector(records[part_id]["bbox_dimensions_mm"])
        for part_id in STORY_PART_IDS
    }
    center = assembled["PART_001"]["location"]
    states = build_inspection_states()
    state_parts = {
        state_id: _assembled_parts(assembled)
        for state_id in INSPECTION_STATE_IDS
    }
    _apply_primary_architecture(state_parts["STATE_01_PRIMARY_ARCHITECTURE"], assembled, center)
    _apply_sensor_inspection(state_parts["STATE_02_SENSOR_INSPECTION"], assembled, center)
    _apply_pcb_inspection(state_parts["STATE_03_PCB_INSPECTION"], assembled, center)
    _apply_power_inspection(state_parts["STATE_04_POWER_INSPECTION"], assembled, center)

    for state_id, state in states.items():
        state["parts"] = state_parts[state_id]
        state["diagnostics"] = _diagnostics(state_parts[state_id], dimensions, states[state_id])

    return {
        "version": "task10R_functional_inspection_v1",
        "source_layout": SOURCE_LAYOUT,
        "source_scene": SOURCE_SCENE,
        "source_scene_sha256": SOURCE_SCENE_SHA256,
        "source_baseline": dict(BASELINE),
        "visibility_policy": build_visibility_policy(),
        "states": states,
        "visual_status": "PENDING_HUMAN_REVIEW",
        "status_contract": build_status_contract(),
        "no_text_policy": "NO_TEXT_OR_ANNOTATIONS",
        "no_animation_policy": "NO_KEYFRAMES_OR_ANIMATION_DATA",
        "story_part_ids": list(STORY_PART_IDS),
        "hidden_part_ids": list(HIDDEN_PART_IDS),
    }


def _assembled_parts(assembled: Mapping[str, Mapping[str, Sequence[float]]]) -> dict[str, dict[str, Any]]:
    return {
        part_id: {
            "location": list(assembled[part_id]["location"]),
            "rotation_euler": list(assembled[part_id]["rotation_euler"]),
            "scale": list(assembled[part_id]["scale"]),
            "offset_from_assembled_mm": [0.0, 0.0, 0.0],
        }
        for part_id in STORY_PART_IDS
    }


def _apply_primary_architecture(parts: dict[str, dict[str, Any]], assembled: Mapping[str, Mapping[str, Sequence[float]]], anchor: Sequence[float]) -> None:
    modules = build_module_groups()
    # Keep the lower housing as the visual anchor, then deliberately reserve
    # background gaps between the four macro layers. These gaps are larger than
    # the old Task 10 presentation offsets and are the primary readability fix.
    target_z = {"MODULE_A": 660.0, "MODULE_B": 525.0, "MODULE_C": 370.0}
    for module_id in ("MODULE_A", "MODULE_B", "MODULE_C"):
        members = modules[module_id]["part_ids"]
        mean = _mean_location(assembled, members)
        delta = [float(anchor[0]) - mean[0], float(anchor[1]) - mean[1], target_z[module_id] - mean[2]]
        for part_id in members:
            _offset(parts[part_id], delta)
    for part_id in ("PART_020", "PART_021", "PART_022"):
        _offset(parts[part_id], [0.0, 0.0, -24.0])


def _apply_sensor_inspection(parts: dict[str, dict[str, Any]], assembled: Mapping[str, Mapping[str, Sequence[float]]], anchor: Sequence[float]) -> None:
    sensor_center = [float(anchor[0]) - 175.0, float(anchor[1]), 330.0]
    _set_location(parts["PART_003"], sensor_center)
    _set_location(parts["PART_012"], [sensor_center[0] - 78.0, sensor_center[1], sensor_center[2]])
    _set_location(parts["PART_013"], [sensor_center[0] + 78.0, sensor_center[1], sensor_center[2]])
    _set_location(parts["PART_014"], [sensor_center[0], sensor_center[1], sensor_center[2] + 88.0])


def _apply_pcb_inspection(parts: dict[str, dict[str, Any]], assembled: Mapping[str, Mapping[str, Sequence[float]]], anchor: Sequence[float]) -> None:
    board_center = [float(anchor[0]) + 175.0, float(anchor[1]), 355.0]
    _set_location(parts["PART_019"], board_center)
    _set_location(parts["PART_006"], [board_center[0], board_center[1], board_center[2] + 72.0])
    _set_location(parts["PART_007"], [board_center[0], board_center[1], board_center[2] - 72.0])


def _apply_power_inspection(parts: dict[str, dict[str, Any]], assembled: Mapping[str, Mapping[str, Sequence[float]]], anchor: Sequence[float]) -> None:
    power_center = [float(anchor[0]) - 175.0, float(anchor[1]) + 12.0, 350.0]
    battery_ids = ["PART_008", "PART_009", "PART_010", "PART_011", "PART_015", "PART_016"]
    for index, part_id in enumerate(battery_ids):
        column = index % 3
        row = index // 3
        _set_location(parts[part_id], [power_center[0] + (column - 1) * 70.0, power_center[1], power_center[2] + (0.5 - row) * 105.0])


def _diagnostics(parts: Mapping[str, Mapping[str, Any]], dimensions: Mapping[str, Sequence[float]], state: Mapping[str, Any]) -> dict[str, Any]:
    all_bounds = _bounds(parts, dimensions, STORY_PART_IDS)
    module_bounds = {
        module_id: _bounds(parts, dimensions, module["part_ids"])
        for module_id, module in build_module_groups().items()
    }
    overall_area = max(_area(all_bounds), 1.0)
    overlap = _max_overlap_ratio(module_bounds)
    occupancy = {
        module_id: round(_area(bounds) / overall_area, 4)
        for module_id, bounds in module_bounds.items()
    }
    return {
        "method": "ORTHOGRAPHIC_XZ_HEURISTIC",
        "module_screen_occupancy": occupancy,
        "projected_overlap_ratio": round(overlap, 4),
        "visible_surface_ratio": round(max(0.0, 1.0 - overlap), 4),
        "frame_margin": {"left": 0.10, "right": 0.10, "top": 0.10, "bottom": 0.10},
        "silhouette_separation": round(max(0.0, 1.0 - overlap), 4),
        "frame_occupancy_ratio": 0.76 if state["state_id"] == "STATE_01_PRIMARY_ARCHITECTURE" else 0.68,
        "human_review_required": True,
    }


def _bounds(parts: Mapping[str, Mapping[str, Any]], dimensions: Mapping[str, Sequence[float]], part_ids: Sequence[str]) -> dict[str, float]:
    x_min = min(float(parts[part_id]["location"][0]) - float(dimensions[part_id][0]) / 2.0 for part_id in part_ids)
    x_max = max(float(parts[part_id]["location"][0]) + float(dimensions[part_id][0]) / 2.0 for part_id in part_ids)
    z_min = min(float(parts[part_id]["location"][2]) - float(dimensions[part_id][2]) / 2.0 for part_id in part_ids)
    z_max = max(float(parts[part_id]["location"][2]) + float(dimensions[part_id][2]) / 2.0 for part_id in part_ids)
    return {"x_min": x_min, "x_max": x_max, "z_min": z_min, "z_max": z_max}


def _area(bounds: Mapping[str, float]) -> float:
    return max(0.0, bounds["x_max"] - bounds["x_min"]) * max(0.0, bounds["z_max"] - bounds["z_min"])


def _max_overlap_ratio(bounds_by_module: Mapping[str, Mapping[str, float]]) -> float:
    values = list(bounds_by_module.values())
    maximum = 0.0
    for index, left in enumerate(values):
        for right in values[index + 1:]:
            width = max(0.0, min(left["x_max"], right["x_max"]) - max(left["x_min"], right["x_min"]))
            height = max(0.0, min(left["z_max"], right["z_max"]) - max(left["z_min"], right["z_min"]))
            intersection = width * height
            denominator = max(1.0, min(_area(left), _area(right)))
            maximum = max(maximum, intersection / denominator)
    return maximum


def _mean_location(assembled: Mapping[str, Mapping[str, Sequence[float]]], part_ids: Sequence[str]) -> list[float]:
    return [sum(float(assembled[part_id]["location"][axis]) for part_id in part_ids) / len(part_ids) for axis in range(3)]


def _offset(record: dict[str, Any], delta: Sequence[float]) -> None:
    original = list(record["location"])
    record["location"] = [float(original[axis]) + float(delta[axis]) for axis in range(3)]
    record["offset_from_assembled_mm"] = [float(delta[axis]) for axis in range(3)]


def _set_location(record: dict[str, Any], location: Sequence[float]) -> None:
    original = list(record["location"])
    record["location"] = [float(value) for value in location]
    record["offset_from_assembled_mm"] = [record["location"][axis] - original[axis] for axis in range(3)]


def _vector(value: Any) -> list[float]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 3:
        raise ValueError("expected a three-value vector")
    result = [float(item) for item in value]
    if not all(math.isfinite(item) for item in result):
        raise ValueError("vector values must be finite")
    return result


def write_inspection_plan(project_root: Path) -> Path:
    root = Path(project_root).expanduser().resolve()
    output = root / PLAN_OUTPUT
    write_json(output, build_inspection_plan(root))
    return output


def build_inspection_cameras(project_root: Path) -> dict[str, Any]:
    root = Path(project_root).expanduser().resolve()
    plan = build_inspection_plan(root)
    layout = load_json(root / SOURCE_LAYOUT)
    dimensions = {part_id: _vector(layout["parts"][part_id]["bbox_dimensions_mm"]) for part_id in STORY_PART_IDS}
    cameras = build_inspection_camera_contract()
    outputs: dict[str, Any] = {
        "version": "task10R_inspection_cameras_v1",
        "projection_policy": "PERSP_60_TO_65MM",
        "cameras": {},
    }
    state_part_records = {state_id: state["parts"] for state_id, state in plan["states"].items()}
    for name, record in cameras.items():
        state_id = record["state_id"]
        part_ids = _camera_part_ids(state_id, record["view_role"])
        bounds = _bounds3d(state_part_records[state_id], dimensions, part_ids)
        target = [
            (bounds["x_min"] + bounds["x_max"]) / 2.0,
            (bounds["y_min"] + bounds["y_max"]) / 2.0,
            (bounds["z_min"] + bounds["z_max"]) / 2.0,
        ]
        if record["view_role"] == "context":
            bounds = _bounds3d(state_part_records[state_id], dimensions, STORY_PART_IDS)
            target = [
                (bounds["x_min"] + bounds["x_max"]) / 2.0,
                (bounds["y_min"] + bounds["y_max"]) / 2.0,
                (bounds["z_min"] + bounds["z_max"]) / 2.0,
            ]
        direction = {
            "hero": (0.72, -1.0, 0.58),
            "front": (0.0, -1.0, 0.12),
            "side": (1.0, -0.2, 0.16),
            "clean": (0.72, -1.0, 0.62),
            "top": (0.0, -0.26, 1.0),
            "context": (0.72, -1.0, 0.58),
        }[record["view_role"]]
        radius = 0.5 * math.sqrt(
            (bounds["x_max"] - bounds["x_min"]) ** 2
            + (bounds["y_max"] - bounds["y_min"]) ** 2
            + (bounds["z_max"] - bounds["z_min"]) ** 2
        )
        aspect = 1920.0 / 1080.0
        sensor_width_mm = 36.0
        vertical_fov = 2.0 * math.atan((sensor_width_mm / aspect) / (2.0 * float(record["lens_mm"])))
        framing_margin = 1.20
        distance = max(radius / math.tan(vertical_fov / 2.0) * framing_margin, 700.0)
        unit = _normalise(direction)
        outputs["cameras"][name] = {
            **record,
            "target": target,
            "location": [target[index] + unit[index] * distance for index in range(3)],
            "direction": unit,
            "clip_end_mm": max(distance * 4.0, 10000.0),
            "camera_distance_mm": round(distance, 3),
            "framing_method": "PERSPECTIVE_BOUNDING_SPHERE",
            "framing_margin": framing_margin,
        }
    return outputs


def _camera_part_ids(state_id: str, view_role: str) -> list[str]:
    if view_role in {"clean", "top"} and state_id == "STATE_02_SENSOR_INSPECTION":
        return ["PART_003", "PART_012", "PART_013", "PART_014"]
    if view_role in {"clean", "top"} and state_id == "STATE_03_PCB_INSPECTION":
        return ["PART_006", "PART_007", "PART_019"]
    if view_role == "clean" and state_id == "STATE_04_POWER_INSPECTION":
        return ["PART_008", "PART_009", "PART_010", "PART_011", "PART_015", "PART_016"]
    return list(STORY_PART_IDS)


def _normalise(value: Sequence[float]) -> list[float]:
    length = math.sqrt(sum(float(item) ** 2 for item in value))
    if length <= 0.0:
        raise ValueError("camera direction cannot be zero")
    return [float(item) / length for item in value]


def _bounds3d(parts: Mapping[str, Mapping[str, Any]], dimensions: Mapping[str, Sequence[float]], part_ids: Sequence[str]) -> dict[str, float]:
    return {
        "x_min": min(float(parts[part_id]["location"][0]) - float(dimensions[part_id][0]) / 2.0 for part_id in part_ids),
        "x_max": max(float(parts[part_id]["location"][0]) + float(dimensions[part_id][0]) / 2.0 for part_id in part_ids),
        "y_min": min(float(parts[part_id]["location"][1]) - float(dimensions[part_id][1]) / 2.0 for part_id in part_ids),
        "y_max": max(float(parts[part_id]["location"][1]) + float(dimensions[part_id][1]) / 2.0 for part_id in part_ids),
        "z_min": min(float(parts[part_id]["location"][2]) - float(dimensions[part_id][2]) / 2.0 for part_id in part_ids),
        "z_max": max(float(parts[part_id]["location"][2]) + float(dimensions[part_id][2]) / 2.0 for part_id in part_ids),
    }


def write_inspection_cameras(project_root: Path) -> Path:
    root = Path(project_root).expanduser().resolve()
    output = root / CAMERA_OUTPUT
    write_json(output, build_inspection_cameras(root))
    return output


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args(argv)
    print(write_inspection_plan(args.project_root))
    print(write_inspection_cameras(args.project_root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
