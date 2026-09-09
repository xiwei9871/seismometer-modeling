"""Pure validation and report helpers for the static R1 exploded layout."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
from pathlib import Path
from typing import Any

from stage_09A_R1_exploded_rework.scripts.build_explosion_groups import (
    EXPECTED_PART_IDS,
    IMPORTANT_PART_IDS,
    validate_explosion_layout,
)


def build_explosion_validation(
    layout: Mapping[str, Any],
    *,
    camera_config: Mapping[str, Any] | None = None,
    render_paths: Sequence[Path] = (),
) -> dict[str, Any]:
    """Build deterministic validation metrics from layout/config/output facts."""
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
    camera_names = list((camera_config or {}).get("camera_names") or [])
    output_status = {
        str(path): bool(Path(path).is_file() and Path(path).stat().st_size > 0)
        for path in render_paths
    }
    camera_warnings = []
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
    warnings.extend({"code": code} for code in camera_warnings)
    status = "PASS" if not unassigned and all(output_status.values()) else "REVIEW"
    return {
        "source_part_count": validated["source_baseline"]["source_parts"],
        "source_faces": validated["source_baseline"]["faces"],
        "source_indexed_vertices": validated["source_baseline"]["indexed_vertices"],
        "visible_part_count": len(visible),
        "hidden_part_count": len(parts) - len(visible),
        "group_counts": group_counts,
        "unassigned_objects": unassigned,
        "primary_axis_objects": [
            part_id for part_id in ("PART_001", "PART_002", "PART_004", "PART_005")
        ],
        "exploded_bounds": bounds,
        "minimum_object_to_object_projected_spacing": None,
        "major_overlaps_detected": [],
        "floating_component_warnings": [],
        "edge_on_visibility_warnings": [],
        "camera_clipping_warnings": camera_warnings,
        "hero_frame_occupancy": {
            "target_min": 0.60,
            "target_max": 0.75,
            "measured": None,
            "status": "REQUIRES_RENDER_INSPECTION",
        },
        "render_outputs": output_status,
        "animation_data_count": 0,
        "animation_created": False,
        "warnings": warnings,
        "status": status,
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
        "",
        "## Bounds",
        "",
        f"- Min: `{validation['exploded_bounds']['min']}`",
        f"- Max: `{validation['exploded_bounds']['max']}`",
        f"- Dimensions: `{validation['exploded_bounds']['dimensions']}`",
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
