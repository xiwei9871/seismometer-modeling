"""Build the deterministic hierarchical static R1 exploded layout."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
from pathlib import Path
from typing import Any

from scripts.task08_data import write_json

from .analyze_assembly import EXPECTED_PART_IDS, analyze_assembled_state


IMPORTANT_PART_IDS = tuple(f"PART_{index:03d}" for index in range(1, 23))
R1_MODE = "STATIC_HIERARCHICAL_PRESENTATION_R1"
ALLOWED_ZONES = ("top", "bottom", "left", "right", "front-left", "front-right")
R1_GROUPS: dict[str, tuple[str, ...]] = {
    "MAIN_STACK": ("PART_001", "PART_002", "PART_004", "PART_005"),
    "SENSOR_BRANCH": ("PART_003", "PART_012", "PART_013", "PART_014"),
    "PCB_BRANCH": ("PART_006", "PART_007", "PART_019"),
    "BATTERY_BRANCH": (
        "PART_008", "PART_009", "PART_010", "PART_011", "PART_015", "PART_016"
    ),
    "TOP_INTERFACE_BRANCH": ("PART_017", "PART_018"),
    "LEVELING_BRANCH": ("PART_020", "PART_021", "PART_022"),
}

_GROUP_SPECS: dict[str, dict[str, Any]] = {
    "MAIN_STACK": {
        "zone": "top",
        "parent_group": "DEVICE",
        "primary_axis": "Z",
        "branch_offset_mm": [0.0, 0.0, 0.0],
        "spacing_level": 1,
        "description": "central housing, cover, and handle vertical stack",
    },
    "SENSOR_BRANCH": {
        "zone": "front-left",
        "parent_group": "DEVICE",
        "primary_axis": "X",
        "branch_offset_mm": [-245.0, -70.0, 35.0],
        "spacing_level": 2,
        "description": "coherent tri-axis fixture and sensor-core branch",
    },
    "PCB_BRANCH": {
        "zone": "front-right",
        "parent_group": "DEVICE",
        "primary_axis": "X",
        "branch_offset_mm": [245.0, -70.0, 35.0],
        "spacing_level": 2,
        "description": "coherent protective plate, PCB, and support-frame branch",
    },
    "BATTERY_BRANCH": {
        "zone": "right",
        "parent_group": "DEVICE",
        "primary_axis": "Y",
        "branch_offset_mm": [255.0, 100.0, 25.0],
        "spacing_level": 2,
        "description": "six battery compartments in a compact 3-by-2 array",
    },
    "TOP_INTERFACE_BRANCH": {
        "zone": "top",
        "parent_group": "MAIN_STACK",
        "primary_axis": "X",
        "branch_offset_mm": [145.0, 10.0, 90.0],
        "spacing_level": 3,
        "description": "paired charging/data top interface parts",
    },
    "LEVELING_BRANCH": {
        "zone": "bottom",
        "parent_group": "MAIN_STACK",
        "primary_axis": "Z",
        "branch_offset_mm": [0.0, 0.0, -95.0],
        "spacing_level": 3,
        "description": "three leveling cones retained near their mounting footprint",
    },
}


def build_explosion_layout(project_root: Path) -> dict[str, Any]:
    """Build the R1 layout from immutable assembled-state facts."""
    analysis = analyze_assembled_state(project_root)
    source_parts = analysis["parts"]
    anchor = source_parts["PART_001"]["assembled_location"]
    groups = _build_groups()
    group_for_part = {
        part_id: group_id
        for group_id, part_ids in R1_GROUPS.items()
        for part_id in part_ids
    }
    if tuple(sorted(group_for_part)) != IMPORTANT_PART_IDS:
        raise ValueError("R1 groups must cover exactly PART_001..PART_022")

    parts: dict[str, dict[str, Any]] = {}
    review_queue: list[dict[str, Any]] = []
    for part_id in EXPECTED_PART_IDS:
        source = source_parts[part_id]
        visible = part_id in IMPORTANT_PART_IDS
        if visible:
            group_id = group_for_part[part_id]
            presentation, local_offset, axis, sign, distance, notes = _presentation_transform(
                part_id, group_id, source, anchor
            )
            group = groups[group_id]
            record = {
                **source,
                "assembled_location": list(source["assembled_location"]),
                "assembled_rotation": list(source["assembled_rotation"]),
                "assembled_scale": list(source["assembled_scale"]),
                "presentation_location": presentation,
                "presentation_rotation": list(source["assembled_rotation"]),
                "group": group_id,
                "parent_group": group["parent_group"],
                "probable_parent_object": _probable_parent(part_id, group_id),
                "explosion_axis": axis,
                "explosion_sign": sign,
                "explosion_distance": distance,
                "assembly_zone": group["zone"],
                "assembly_zone_offset_mm": list(group["branch_offset_mm"]),
                "component_offset_mm": local_offset,
                "presentation_visibility": "VISIBLE",
                "follow_parent_assembly": True,
                "review_scope": "R1_PRESENTATION_LAYOUT",
                "collision_scope": True,
                "confidence": "HIGH",
                "notes": notes,
            }
            review_queue.append(
                {
                    "part_id": part_id,
                    "group": group_id,
                    "semantic_name": source["semantic_name"],
                    "review_question": "Is the important component visible, unobstructed, and clearly laid out?",
                }
            )
        else:
            record = {
                **source,
                "assembled_location": list(source["assembled_location"]),
                "assembled_rotation": list(source["assembled_rotation"]),
                "assembled_scale": list(source["assembled_scale"]),
                "presentation_location": list(source["assembled_location"]),
                "presentation_rotation": list(source["assembled_rotation"]),
                "group": None,
                "parent_group": None,
                "probable_parent_object": None,
                "explosion_axis": None,
                "explosion_sign": 0,
                "explosion_distance": 0.0,
                "assembly_zone": None,
                "assembly_zone_offset_mm": [0.0, 0.0, 0.0],
                "component_offset_mm": [0.0, 0.0, 0.0],
                "presentation_visibility": "HIDDEN",
                "follow_parent_assembly": False,
                "review_scope": None,
                "collision_scope": False,
                "confidence": "NOT_IN_PRESENTATION_SCOPE",
                "notes": "Retained source PART; hidden from R1 presentation and motion review.",
            }
        parts[part_id] = record

    layout = {
        "layout_version": "r1",
        "mode": R1_MODE,
        "unit_assumption": "mm",
        "unit_confidence": "assumed",
        "animation_created": False,
        "animation_anchor": "PART_001",
        "primary_axis": "GLOBAL_Z",
        "source_sha256": analysis["source_sha256"],
        "source_baseline": dict(analysis["source_baseline"]),
        "selection_policy": {
            "visible_part_ids": list(IMPORTANT_PART_IDS),
            "hidden_part_ids": [part_id for part_id in EXPECTED_PART_IDS if part_id not in IMPORTANT_PART_IDS],
            "visible_rule": "confirmed important semantic parts PART_001..PART_022",
        },
        "policy": {
            "flat_per_part_explosion": False,
            "small_fragment_in_collision_queue": False,
            "small_fragment_in_animation_queue": False,
            "small_fragment_in_manual_motion_review": False,
            "hidden_part_presentation": "FOLLOW_PARENT_OR_HIDDEN_WITHOUT_PARENT",
            "realistic_disassembly_order": False,
            "keyframes_created": False,
        },
        "zones": {
            zone: {"zone": zone, "group_ids": [group_id for group_id in R1_GROUPS if groups[group_id]["zone"] == zone]}
            for zone in ALLOWED_ZONES
        },
        "groups": groups,
        "parts": parts,
        "review_queue": review_queue,
        "motion_review_queue": [],
        "animation_queue": [],
        "collision_queue": [],
    }
    return validate_explosion_layout(layout)


def validate_explosion_layout(layout: Mapping[str, Any]) -> dict[str, Any]:
    """Fail closed on R1 identity, coverage, transform, and static policies."""
    if layout.get("layout_version") != "r1":
        raise ValueError("R1 layout_version must be r1")
    if layout.get("mode") != R1_MODE:
        raise ValueError("R1 mode is invalid")
    if layout.get("animation_created") is not False:
        raise ValueError("R1 layout must be static")
    if layout.get("source_sha256") != "fd2a7b78540245fd098724206d5ddf169fd2f44c07638e9a6459cd92fea717d1":
        raise ValueError("R1 source SHA256 does not match frozen baseline")
    if layout.get("source_baseline") != {"source_parts": 82, "faces": 444296, "indexed_vertices": 221902}:
        raise ValueError("R1 source baseline does not match frozen totals")
    parts = layout.get("parts")
    if not isinstance(parts, Mapping) or list(parts) != list(EXPECTED_PART_IDS):
        raise ValueError("R1 parts must be ordered PART_001..PART_082")
    visible = [part_id for part_id, record in parts.items() if record.get("presentation_visibility") == "VISIBLE"]
    if visible != list(IMPORTANT_PART_IDS):
        raise ValueError("R1 visible parts must be exactly PART_001..PART_022")
    groups = layout.get("groups")
    if not isinstance(groups, Mapping) or set(groups) != set(R1_GROUPS):
        raise ValueError("R1 groups are incomplete")
    assigned: list[str] = []
    for group_id, expected_ids in R1_GROUPS.items():
        record = groups[group_id]
        if tuple(record.get("part_ids") or ()) != expected_ids:
            raise ValueError(f"R1 group membership mismatch for {group_id}")
        assigned.extend(expected_ids)
    if sorted(assigned) != list(IMPORTANT_PART_IDS):
        raise ValueError("R1 visible group coverage mismatch")
    hidden_ids = set(EXPECTED_PART_IDS) - set(IMPORTANT_PART_IDS)
    for part_id, record in parts.items():
        location = _vector(record.get("presentation_location"), f"{part_id} presentation_location")
        _vector(record.get("assembled_location"), f"{part_id} assembled_location")
        if part_id in hidden_ids and (
            record.get("review_scope") is not None
            or record.get("collision_scope") is not False
        ):
            raise ValueError(f"hidden R1 PART has review/collision scope: {part_id}")
        if not all(math.isfinite(value) for value in location):
            raise ValueError(f"non-finite R1 location for {part_id}")
    for key in ("motion_review_queue", "animation_queue", "collision_queue"):
        queue = layout.get(key)
        if not isinstance(queue, list):
            raise ValueError(f"R1 {key} must be a list")
        for index, item in enumerate(queue):
            if isinstance(item, str):
                part_id = item
            elif isinstance(item, Mapping) and isinstance(item.get("part_id"), str):
                part_id = item["part_id"]
            else:
                raise ValueError(f"R1 {key} contains an invalid item at index {index}")
            if part_id not in EXPECTED_PART_IDS:
                raise ValueError(f"R1 {key} contains an unknown PART: {part_id}")
            if part_id in hidden_ids:
                raise ValueError(f"hidden PART appears in R1 {key}: {part_id}")
    return dict(layout)


def write_explosion_configs(project_root: Path, layout: Mapping[str, Any]) -> dict[str, Path]:
    """Write deterministic R1 group/layout/camera configuration files."""
    validated = validate_explosion_layout(layout)
    root = Path(project_root).expanduser().resolve()
    config_dir = root / "stage_09A_R1_exploded_rework/config"
    group_payload = {
        "layout_version": "r1",
        "primary_axis": "GLOBAL_Z",
        "groups": validated["groups"],
        "parts": {
            part_id: {
                key: record[key]
                for key in (
                    "part_id", "assembled_location", "assembled_rotation", "bbox_dimensions_mm",
                    "group", "parent_group", "probable_parent_object", "explosion_axis",
                    "explosion_sign", "explosion_distance", "confidence", "notes",
                )
            }
            for part_id, record in validated["parts"].items()
        },
    }
    layout_path = config_dir / "explosion_layout_config.json"
    groups_path = config_dir / "explosion_groups.json"
    camera_path = config_dir / "camera_config.json"
    write_json(groups_path, group_payload)
    write_json(layout_path, validated)
    write_json(
        camera_path,
        {
            "layout_version": "r1",
            "camera_names": [
                "CAM_EXPLODED_HERO",
                "CAM_EXPLODED_ENGINEERING",
                "CAM_EXPLODED_TOP",
                "CAM_EXPLODED_REAR",
            ],
            "render_resolution": [1200, 900],
        },
    )
    return {"groups": groups_path, "layout": layout_path, "camera": camera_path}


def _build_groups() -> dict[str, dict[str, Any]]:
    return {
        group_id: {
            "group_id": group_id,
            "part_ids": list(R1_GROUPS[group_id]),
            "visible_part_ids": list(R1_GROUPS[group_id]),
            "hidden_followers": [],
            "presentation_only": True,
            **{key: value for key, value in _GROUP_SPECS[group_id].items()},
            "component_offsets_mm": {},
        }
        for group_id in R1_GROUPS
    }


def _presentation_transform(
    part_id: str,
    group_id: str,
    source: Mapping[str, Any],
    anchor: Sequence[float],
) -> tuple[list[float], list[float], str, int, float, str]:
    anchor_values = [float(value) for value in anchor]
    source_location = [float(value) for value in source["assembled_location"]]
    group = _GROUP_SPECS[group_id]
    branch = [float(value) for value in group["branch_offset_mm"]]
    if group_id == "MAIN_STACK":
        z_offsets = {
            "PART_001": 0.0,
            "PART_002": 92.0,
            "PART_004": 160.0,
            "PART_005": 235.0,
        }
        location = [anchor_values[0], anchor_values[1], anchor_values[2] + z_offsets[part_id]]
        local = [0.0, 0.0, z_offsets[part_id]]
        return location, local, "Z", 1, z_offsets[part_id], "Central primary-axis stack rebuilt from assembled anchor."
    if group_id == "SENSOR_BRANCH":
        local_map = {
            "PART_003": [0.0, 0.0, 0.0],
            "PART_012": [-68.0, 0.0, 12.0],
            "PART_013": [0.0, 42.0, 12.0],
            "PART_014": [0.0, 0.0, 58.0],
        }
        local = local_map[part_id]
        location = [anchor_values[index] + branch[index] + local[index] for index in range(3)]
        return location, local, "X", -1, abs(branch[0]), "Sensor fixture travels as one left/front branch before local XYZ expansion."
    if group_id == "PCB_BRANCH":
        local_map = {
            "PART_007": [0.0, 0.0, -45.0],
            "PART_019": [0.0, 0.0, 20.0],
            "PART_006": [0.0, 0.0, 82.0],
        }
        local = local_map[part_id]
        location = [anchor_values[index] + branch[index] + local[index] for index in range(3)]
        return location, local, "X", 1, abs(branch[0]), "PCB parts travel as one right/front branch before local layer separation."
    if group_id == "BATTERY_BRANCH":
        local_map = {
            "PART_008": [-54.0, -42.0, 0.0],
            "PART_009": [0.0, -42.0, 0.0],
            "PART_010": [54.0, -42.0, 0.0],
            "PART_011": [-54.0, 42.0, 0.0],
            "PART_015": [0.0, 42.0, 0.0],
            "PART_016": [54.0, 42.0, 0.0],
        }
        local = local_map[part_id]
        location = [anchor_values[index] + branch[index] + local[index] for index in range(3)]
        return location, local, "Y", 1, abs(branch[1]), "Battery compartments form a compact deterministic 3-by-2 array."
    if group_id == "TOP_INTERFACE_BRANCH":
        local_map = {"PART_017": [-28.0, 0.0, 0.0], "PART_018": [28.0, 0.0, 0.0]}
        local = local_map[part_id]
        location = [anchor_values[index] + branch[index] + local[index] for index in range(3)]
        return location, local, "X", 1, abs(branch[0]), "Paired top interface parts remain a secondary branch."
    if group_id == "LEVELING_BRANCH":
        local = [source_location[0] - anchor_values[0], source_location[1] - anchor_values[1], branch[2]]
        location = [source_location[0], source_location[1], source_location[2] + branch[2]]
        return location, local, "Z", -1, abs(branch[2]), "Original leveling footprint retained; only bounded downward separation is applied."
    raise ValueError(f"unknown R1 group: {group_id}")


def _probable_parent(part_id: str, group_id: str) -> str:
    parents = {
        "MAIN_STACK": "PART_001",
        "SENSOR_BRANCH": "PART_003",
        "PCB_BRANCH": "PART_019",
        "BATTERY_BRANCH": "PART_001",
        "TOP_INTERFACE_BRANCH": "PART_004",
        "LEVELING_BRANCH": "PART_001",
    }
    if part_id == parents[group_id]:
        return "PART_001"
    return parents[group_id]


def _vector(value: Any, label: str) -> list[float]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 3:
        raise ValueError(f"{label} must be a 3-value vector")
    result = [float(item) for item in value]
    if not all(math.isfinite(item) for item in result):
        raise ValueError(f"{label} must contain finite values")
    return result


def main() -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    layout = build_explosion_layout(args.project_root)
    paths = write_explosion_configs(args.project_root, layout)
    print(json.dumps({key: str(path) for key, path in paths.items()}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
