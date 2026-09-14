"""Deterministic camera planning for Task 10-V2/V3 (pure Python, no bpy).

Extracted from ``setup_story_presentation_v2._build_camera_config`` so the
layout solver and the presentation setup derive identical cameras from the
same inputs: camera = f(subject bounds in the shot's state).

Focus cameras auto-fit their distance so the subject fills
``FOCUS_SCREEN_FRACTION`` of the frame height (framing-distance formula), and
aim at the subject's aggregate bounding-sphere centre. Because both the
target and the distance follow the subject, the subject's screen image is
invariant under the solver's rigid translations — only context moves in frame.
"""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

from stage_10V2_product_story.scripts import frustum_math as fm

HERO_DIRECTION = (0.72, -1.0, 0.58)
SENSOR_DIRECTION = (0.68, -1.0, 0.5)
PCB_DIRECTION = (0.6, -1.0, 0.8)
COMM_DIRECTION = (0.55, -0.85, 0.5)
POWER_DIRECTION = (0.5, -0.95, 0.55)

HERO_LENS_MM = 68.0
FOCUS_LENS_MM = 70.0
# Shallow depth of field on the isolate cameras — the subject stays sharp
# while the backdrop falls off, the 极简 product-render signature.
FOCUS_FSTOP = 5.0

SENSOR_PART_IDS = ("PART_003", "PART_012", "PART_013", "PART_014")
PCB_PART_IDS = ("PART_019",)
COMM_PART_IDS = ("PART_005", "PART_017", "PART_018")
POWER_PART_IDS = ("PART_008", "PART_009", "PART_010", "PART_011", "PART_015", "PART_016")

# Subject's angular diameter as a fraction of the vertical FOV.
SENSOR_SCREEN_FRACTION = 0.62
PCB_SCREEN_FRACTION = 0.62
COMM_SCREEN_FRACTION = 0.58
POWER_SCREEN_FRACTION = 0.55
# Hero shot keeps the whole device in frame with context.
HERO_MIN_DISTANCE_MM = 1050.0
HERO_DISTANCE_FACTOR = 2.30


def module_bounds(
    state: Mapping[str, Any],
    part_ids: Sequence[str],
    layout: Mapping[str, Any],
    component_registry: Sequence[Mapping[str, Any]] | None = None,
) -> tuple[tuple[float, float, float], float]:
    """Aggregate bounding sphere of a module's parts (and optionally its
    mounted presentation components) inside one story state."""
    centers: list[tuple[float, float, float]] = []
    radii: list[float] = []
    for part_id in part_ids:
        record = state["parts"][part_id]
        dims = layout["parts"][part_id]["bbox_dimensions_mm"]
        center, radius = fm.bounding_sphere(record["location"], dims)
        centers.append(center)
        radii.append(radius)
    if component_registry:
        components = state.get("components", {})
        for component in component_registry:
            record = components.get(component["component_id"])
            if record is None:
                continue
            size = component.get("size_xy_mm") or [0.0, 0.0]
            dims = [
                float(size[0]),
                float(size[1]),
                float(component.get("height_mm", 0.0)),
            ]
            center, radius = fm.bounding_sphere(record["location"], dims)
            centers.append(center)
            radii.append(radius)
    centroid = (
        sum(c[0] for c in centers) / len(centers),
        sum(c[1] for c in centers) / len(centers),
        sum(c[2] for c in centers) / len(centers),
    )
    radius = max(
        fm.v_len(fm.v_sub(c, centroid)) + r for c, r in zip(centers, radii)
    )
    return centroid, radius


def state_bounds(
    state_data: Mapping[str, Any], layout: Mapping[str, Any]
) -> dict[str, Any]:
    """Bounds over every part position across all states (hero framing)."""
    low = [float("inf")] * 3
    high = [float("-inf")] * 3
    for state in state_data["states"].values():
        for part_id, record in state["parts"].items():
            dims = layout["parts"][part_id]["bbox_dimensions_mm"]
            for axis in range(3):
                half = float(dims[axis]) / 2.0
                low[axis] = min(low[axis], float(record["location"][axis]) - half)
                high[axis] = max(high[axis], float(record["location"][axis]) + half)
    return {
        "min": low,
        "max": high,
        "dimensions": [high[i] - low[i] for i in range(3)],
    }


def _normalise(direction: Sequence[float]) -> list[float]:
    length = math.sqrt(sum(float(v) ** 2 for v in direction))
    if length <= 0.0:
        raise ValueError("camera direction cannot be zero")
    return [float(v) / length for v in direction]


def _camera_record(
    name: str,
    target: Sequence[float],
    direction: Sequence[float],
    distance: float,
    lens: float,
    fstop: float | None = None,
) -> dict[str, Any]:
    unit = _normalise(direction)
    location = [float(target[i]) + unit[i] * distance for i in range(3)]
    record = {
        "name": name,
        "type": "PERSP",
        "target": [float(v) for v in target],
        "location": location,
        "direction": unit,
        "lens_mm": float(lens),
        "clip_start_mm": 0.1,
        "clip_end_mm": max(distance * 4.0, 10000.0),
    }
    if fstop is not None:
        record["fstop"] = float(fstop)
        record["focus_distance_mm"] = float(distance)
    return record


def drifted_pose(
    record: Mapping[str, Any],
    push_fraction: float,
    orbit_deg: float,
) -> list[float]:
    """End-of-shot camera location: push in, then orbit about the target's Z.

    ``target + Rz(orbit) @ ((location - target) * (1 - push))`` — the shot
    slowly dollies toward the subject while swinging around the vertical
    axis, the minimalist "product floats in a studio" drift.
    """
    target = [float(v) for v in record["target"]]
    offset = fm.v_sub(record["location"], target)
    scaled = fm.v_scale(offset, 1.0 - float(push_fraction))
    angle = math.radians(float(orbit_deg))
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    orbited = (
        scaled[0] * cos_a - scaled[1] * sin_a,
        scaled[0] * sin_a + scaled[1] * cos_a,
        scaled[2],
    )
    return [target[i] + orbited[i] for i in range(3)]


def build_camera_records(
    state_data: Mapping[str, Any], layout: Mapping[str, Any]
) -> dict[str, Any]:
    """All three story cameras derived from the (possibly solved) state data.

    Deterministic: identical inputs always produce identical records.
    """
    bounds = state_bounds(state_data, layout)
    low, high = bounds["min"], bounds["max"]
    hero_target = [(low[i] + high[i]) / 2.0 for i in range(3)]
    diagonal = math.sqrt(sum(v * v for v in bounds["dimensions"]))
    hero = _camera_record(
        "CAM_STORY_HERO",
        hero_target,
        HERO_DIRECTION,
        max(diagonal * HERO_DISTANCE_FACTOR, HERO_MIN_DISTANCE_MM),
        HERO_LENS_MM,
    )

    fov_y_70 = fm.fov_xy(FOCUS_LENS_MM)[1]
    sensor_centroid, sensor_radius = module_bounds(
        state_data["states"]["SENSOR_FOCUS"], SENSOR_PART_IDS, layout
    )
    sensor = _camera_record(
        "CAM_STORY_SENSOR",
        sensor_centroid,
        SENSOR_DIRECTION,
        fm.framing_distance(sensor_radius, fov_y_70, SENSOR_SCREEN_FRACTION),
        FOCUS_LENS_MM,
        fstop=FOCUS_FSTOP,
    )

    pcb_centroid, pcb_radius = module_bounds(
        state_data["states"]["PCB_FOCUS"], PCB_PART_IDS, layout,
        component_registry=state_data.get("presentation", {}).get("components"),
    )
    pcb = _camera_record(
        "CAM_STORY_PCB",
        pcb_centroid,
        PCB_DIRECTION,
        fm.framing_distance(pcb_radius, fov_y_70, PCB_SCREEN_FRACTION),
        FOCUS_LENS_MM,
        fstop=FOCUS_FSTOP,
    )

    # V4: every isolate shot gets its own fitted camera — the subject owns
    # the frame instead of floating small inside the whole-device hero view.
    comm_centroid, comm_radius = module_bounds(
        state_data["states"]["COMMUNICATION_FOCUS"], COMM_PART_IDS, layout
    )
    comm = _camera_record(
        "CAM_STORY_COMM",
        comm_centroid,
        COMM_DIRECTION,
        fm.framing_distance(comm_radius, fov_y_70, COMM_SCREEN_FRACTION),
        FOCUS_LENS_MM,
        fstop=FOCUS_FSTOP,
    )
    power_centroid, power_radius = module_bounds(
        state_data["states"]["POWER_FOCUS"], POWER_PART_IDS, layout
    )
    power = _camera_record(
        "CAM_STORY_POWER",
        power_centroid,
        POWER_DIRECTION,
        fm.framing_distance(power_radius, fov_y_70, POWER_SCREEN_FRACTION),
        FOCUS_LENS_MM,
        fstop=FOCUS_FSTOP,
    )

    return {
        "bounds": bounds,
        "camera_names": [
            "CAM_STORY_HERO",
            "CAM_STORY_SENSOR",
            "CAM_STORY_PCB",
            "CAM_STORY_COMM",
            "CAM_STORY_POWER",
        ],
        "cameras": {r["name"]: r for r in (hero, sensor, pcb, comm, power)},
    }
