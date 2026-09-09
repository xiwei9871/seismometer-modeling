"""Build the deterministic Task 9C refined static exploded layout."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
import math
from pathlib import Path
from typing import Any

from scripts.task08_data import load_json, write_json


R1_LAYOUT_PATH = "stage_09A_R1_exploded_rework/config/explosion_layout_config.json"
OUTPUT_PATH = "stage_09C_refined_explosion/config/refined_layout.json"
LAYOUT_VERSION = "9c_refined_v1"
MODE = "STATIC_REFINED_HIERARCHICAL_PRESENTATION"
EXPECTED_PART_IDS = tuple(f"PART_{index:03d}" for index in range(1, 83))
VISIBLE_PART_IDS = tuple(f"PART_{index:03d}" for index in range(1, 23))

GROUPS: dict[str, tuple[str, ...]] = {
    "MAIN_STACK": ("PART_001", "PART_002", "PART_004", "PART_005"),
    "SENSOR_BRANCH": ("PART_003", "PART_012", "PART_013", "PART_014"),
    "PCB_BRANCH": ("PART_006", "PART_007", "PART_019"),
    "BATTERY_BRANCH": ("PART_008", "PART_009", "PART_010", "PART_011", "PART_015", "PART_016"),
    "TOP_INTERFACE_BRANCH": ("PART_017", "PART_018"),
    "LEVELING_BRANCH": ("PART_020", "PART_021", "PART_022"),
}


def build_refined_layout(project_root: Path) -> dict[str, Any]:
    """Derive a more open layout from the frozen R1 presentation state."""
    root = Path(project_root).expanduser().resolve()
    r1 = load_json(root / R1_LAYOUT_PATH)
    _validate_r1_input(r1)
    source_parts = r1["parts"]
    factors = _spacing_factors()
    anchor = source_parts["PART_001"]
    anchor_location = [float(value) for value in anchor["assembled_location"]]
    anchor_bbox = [float(value) for value in anchor["bbox_dimensions_mm"]]
    group_for_part = {
        part_id: group_id
        for group_id, part_ids in GROUPS.items()
        for part_id in part_ids
    }
    primary_gap = anchor_bbox[2] * factors["primary_z_gap_from_anchor"]
    pcb_gap = max(anchor_bbox[2] * factors["pcb_local_z_gap_from_anchor"], factors["minimum_local_gap_mm"])
    sensor_fixture = [float(value) for value in source_parts["PART_003"]["bbox_dimensions_mm"]]
    sensor_shift = [
        sensor_fixture[0] * factors["sensor_xy_shift_from_fixture"],
        sensor_fixture[1] * factors["sensor_xy_shift_from_fixture"],
        sensor_fixture[2] * factors["sensor_z_shift_from_fixture"],
    ]
    pcb_lateral_shift = max(
        float(source_parts["PART_006"]["bbox_dimensions_mm"][0]),
        float(source_parts["PART_007"]["bbox_dimensions_mm"][0]),
    ) * factors["pcb_lateral_shift_from_bbox"]

    parts: dict[str, dict[str, Any]] = {}
    for part_id in EXPECTED_PART_IDS:
        source = deepcopy(source_parts[part_id])
        assembled = [float(value) for value in source["assembled_location"]]
        r1_location = [float(value) for value in source["presentation_location"]]
        refined = list(r1_location)
        group_id = group_for_part.get(part_id)
        local_refinement = [0.0, 0.0, 0.0]
        if group_id == "MAIN_STACK":
            index = ("PART_001", "PART_002", "PART_004", "PART_005").index(part_id)
            local_refinement[2] = primary_gap * index
        elif group_id == "PCB_BRANCH":
            if part_id == "PART_006":
                local_refinement = [pcb_lateral_shift, 0.0, pcb_gap]
            elif part_id == "PART_007":
                local_refinement = [-pcb_lateral_shift, 0.0, -pcb_gap]
        elif group_id == "SENSOR_BRANCH":
            if part_id == "PART_012":
                local_refinement = [-sensor_shift[0], 0.0, sensor_shift[2]]
            elif part_id == "PART_013":
                local_refinement = [0.0, sensor_shift[1], sensor_shift[2]]
            elif part_id == "PART_014":
                local_refinement = [0.0, 0.0, sensor_shift[2]]
        elif group_id == "BATTERY_BRANCH":
            local_refinement[2] = anchor_bbox[2] * factors["battery_z_shift_from_anchor"]
        elif group_id == "LEVELING_BRANCH":
            local_refinement[2] = -anchor_bbox[2] * factors["leveling_extra_drop_from_anchor"]
        refined = [r1_location[index] + local_refinement[index] for index in range(3)]
        visible = part_id in VISIBLE_PART_IDS
        parts[part_id] = {
            **source,
            "assembled_location": assembled,
            "r1_presentation_location": r1_location,
            "refined_presentation_location": refined if visible else assembled,
            "refined_local_offset_mm": local_refinement if visible else [0.0, 0.0, 0.0],
            "presentation_visibility": "VISIBLE" if visible else "HIDDEN",
            "presentation_group": group_id,
            "presentation_parent": _parent_for(group_id) if visible else None,
            "animation_scope": group_id if visible else "NONE",
            "animation_enabled": visible,
            "refined_explosion_distance_mm": _distance(assembled, refined) if visible else 0.0,
            "source_geometry_unchanged": True,
        }

    groups = {
        group_id: {
            "group_id": group_id,
            "part_ids": list(part_ids),
            "anchor_part_id": _parent_for(group_id),
            "primary_axis": "Z" if group_id in {"MAIN_STACK", "LEVELING_BRANCH"} else "LOCAL_MODULE",
            "presentation_policy": "PRIMARY_Z_PLUS_LOCAL_REFINEMENT",
        }
        for group_id, part_ids in GROUPS.items()
    }
    layout = {
        "layout_version": LAYOUT_VERSION,
        "mode": MODE,
        "unit_assumption": "mm",
        "unit_confidence": "assumed",
        "animation_created": False,
        "source_layout": "R1",
        "animation_anchor": "PART_001",
        "primary_axis": "GLOBAL_Z",
        "source_sha256": r1["source_sha256"],
        "source_baseline": dict(r1["source_baseline"]),
        "selection_policy": {
            "visible_part_ids": list(VISIBLE_PART_IDS),
            "hidden_part_ids": [part_id for part_id in EXPECTED_PART_IDS if part_id not in VISIBLE_PART_IDS],
            "small_and_fragment_policy": "FOLLOW_PARENT_IF_EXPLICIT_OTHERWISE_HIDDEN_AND_NO_ANIMATION",
        },
        "policy": {
            "flat_per_part_explosion": False,
            "small_parts_in_animation": False,
            "fragment_in_animation": False,
            "formal_animation": False,
            "commercial_render": False,
            "source_geometry_modified": False,
        },
        "spacing_factors": factors,
        "groups": groups,
        "parts": parts,
    }
    return validate_refined_layout(layout)


def validate_refined_layout(layout: Mapping[str, Any]) -> dict[str, Any]:
    """Validate Task 9C static identity and refinement invariants."""
    if layout.get("layout_version") != LAYOUT_VERSION:
        raise ValueError("Task 9C refined layout version is invalid")
    if layout.get("mode") != MODE:
        raise ValueError("Task 9C refined layout mode is invalid")
    if layout.get("animation_created") is not False:
        raise ValueError("refined layout must be static before animation build")
    if layout.get("source_sha256") != "fd2a7b78540245fd098724206d5ddf169fd2f44c07638e9a6459cd92fea717d1":
        raise ValueError("Task 9C source SHA256 does not match the frozen source")
    if layout.get("source_baseline") != {"source_parts": 82, "faces": 444296, "indexed_vertices": 221902}:
        raise ValueError("Task 9C source baseline does not match frozen totals")
    parts = layout.get("parts")
    if not isinstance(parts, Mapping) or list(parts) != list(EXPECTED_PART_IDS):
        raise ValueError("Task 9C parts must cover PART_001..PART_082 in order")
    visible = [part_id for part_id, record in parts.items() if record.get("presentation_visibility") == "VISIBLE"]
    if visible != list(VISIBLE_PART_IDS):
        raise ValueError("Task 9C visible set must be exactly PART_001..PART_022")
    groups = layout.get("groups")
    if not isinstance(groups, Mapping) or set(groups) != set(GROUPS):
        raise ValueError("Task 9C group set is incomplete")
    for group_id, expected_ids in GROUPS.items():
        if tuple(groups[group_id].get("part_ids") or ()) != expected_ids:
            raise ValueError(f"Task 9C group membership mismatch for {group_id}")
    factors = layout.get("spacing_factors")
    if not isinstance(factors, Mapping) or set(factors) != set(_spacing_factors()):
        raise ValueError("Task 9C spacing factors are incomplete")
    for name, value in factors.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) or float(value) <= 0.0:
            raise ValueError(f"Task 9C spacing factor is invalid: {name}")
    for part_id, record in parts.items():
        _vector(record.get("refined_presentation_location"), f"{part_id} refined location")
        if part_id not in VISIBLE_PART_IDS and (
            record.get("animation_enabled") is not False
            or record.get("animation_scope") != "NONE"
        ):
            raise ValueError(f"hidden Task 9C part has animation scope: {part_id}")
        if record.get("source_geometry_unchanged") is not True:
            raise ValueError(f"Task 9C source geometry marker missing: {part_id}")
    _validate_refinement_is_open(layout)
    return dict(layout)


def write_refined_layout(project_root: Path, layout: Mapping[str, Any]) -> Path:
    root = Path(project_root).expanduser().resolve()
    path = root / OUTPUT_PATH
    write_json(path, validate_refined_layout(layout))
    return path


def _validate_r1_input(layout: Mapping[str, Any]) -> None:
    if layout.get("layout_version") != "r1" or layout.get("animation_created") is not False:
        raise ValueError("Task 9C requires the validated static R1 layout")
    if layout.get("source_baseline") != {"source_parts": 82, "faces": 444296, "indexed_vertices": 221902}:
        raise ValueError("Task 9C R1 input baseline is invalid")
    parts = layout.get("parts")
    if not isinstance(parts, Mapping) or list(parts) != list(EXPECTED_PART_IDS):
        raise ValueError("Task 9C R1 input does not cover all source parts")


def _validate_refinement_is_open(layout: Mapping[str, Any]) -> None:
    parts = layout["parts"]
    for left_id, right_id in (("PART_001", "PART_002"), ("PART_002", "PART_004"), ("PART_004", "PART_005")):
        refined_gap = _surface_gap(parts[left_id], parts[right_id], "refined_presentation_location")
        r1_gap = _surface_gap(parts[left_id], parts[right_id], "r1_presentation_location")
        if refined_gap <= r1_gap:
            raise ValueError(f"Task 9C main stack gap did not increase: {left_id}/{right_id}")
    for part_id in ("PART_020", "PART_021", "PART_022"):
        if parts[part_id]["refined_presentation_location"][2] >= parts[part_id]["r1_presentation_location"][2]:
            raise ValueError(f"Task 9C leveling drop did not increase: {part_id}")


def _surface_gap(left: Mapping[str, Any], right: Mapping[str, Any], location_key: str) -> float:
    left_z = float(left[location_key][2])
    right_z = float(right[location_key][2])
    left_h = float(left["bbox_dimensions_mm"][2])
    right_h = float(right["bbox_dimensions_mm"][2])
    return abs(right_z - left_z) - (left_h + right_h) / 2.0


def _spacing_factors() -> dict[str, float]:
    return {
        "primary_z_gap_from_anchor": 0.45,
        "pcb_local_z_gap_from_anchor": 0.30,
        "sensor_xy_shift_from_fixture": 0.15,
        "sensor_z_shift_from_fixture": 0.25,
        "pcb_lateral_shift_from_bbox": 0.12,
        "battery_z_shift_from_anchor": 0.12,
        "leveling_extra_drop_from_anchor": 0.65,
        "minimum_local_gap_mm": 10.0,
    }


def _parent_for(group_id: str | None) -> str | None:
    return {
        "MAIN_STACK": "PART_001",
        "SENSOR_BRANCH": "PART_003",
        "PCB_BRANCH": "PART_019",
        "BATTERY_BRANCH": "PART_001",
        "TOP_INTERFACE_BRANCH": "PART_004",
        "LEVELING_BRANCH": "PART_001",
    }.get(group_id)


def _distance(left: Sequence[float], right: Sequence[float]) -> float:
    return math.sqrt(sum((float(a) - float(b)) ** 2 for a, b in zip(left, right)))


def _vector(value: Any, label: str) -> list[float]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 3:
        raise ValueError(f"{label} must be a three-value vector")
    result = [float(item) for item in value]
    if not all(math.isfinite(item) for item in result):
        raise ValueError(f"{label} must be finite")
    return result


def main() -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    layout = build_refined_layout(args.project_root)
    path = write_refined_layout(args.project_root, layout)
    print(json.dumps({"layout": str(path), "layout_version": LAYOUT_VERSION}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
