"""Plan the focused, static v4 presentation layout for important parts only."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import csv
import math
from pathlib import Path
from typing import Any

from scripts.task08_data import load_json, load_manifest, write_json
from scripts.task09_data import TASK09_BASELINE, validate_task09_baseline


V4_VIEW_NAMES = (
    "exploded_iso_front_v4",
    "exploded_iso_rear_v4",
    "exploded_front_v4",
    "exploded_top_v4",
)
ALLOWED_ZONES = (
    "top",
    "bottom",
    "left",
    "right",
    "front-left",
    "front-right",
)
EXPECTED_PART_IDS = tuple(f"PART_{index:03d}" for index in range(1, 83))
IMPORTANT_PART_IDS = tuple(f"PART_{index:03d}" for index in range(1, 23))
REVIEW_SCOPE = "IMPORTANT_COMPONENT_LAYOUT_ONLY"
REVIEW_QUESTION = "Is the important component visible, unobstructed, and clearly laid out?"
REVIEW_FIELDS = (
    "part_id",
    "semantic_name",
    "semantic_category",
    "size_class",
    "assembly_id",
    "zone",
    "review_scope",
    "review_question",
)


_ASSEMBLY_SPECS: tuple[dict[str, Any], ...] = (
    {
        "assembly_id": "ENCLOSURE_ASSEMBLY",
        "zone": "bottom",
        "zone_anchor_mm": [0.0, 0.0, 0.0],
        "part_ids": ["PART_001", "PART_002", "PART_004"],
        "description": "lower housing anchor, upper housing, and top cover",
        "expansion_policy": "anchor_then_vertical_components",
    },
    {
        "assembly_id": "HANDLE_ASSEMBLY",
        "zone": "top",
        "zone_anchor_mm": [0.0, 0.0, 440.0],
        "part_ids": ["PART_005"],
        "description": "handle and antenna shroud",
        "expansion_policy": "single_component",
    },
    {
        "assembly_id": "TOP_INTERFACE_ASSEMBLY",
        "zone": "right",
        "zone_anchor_mm": [300.0, 40.0, 220.0],
        "part_ids": ["PART_017", "PART_018"],
        "description": "top charging/data interface pair",
        "expansion_policy": "paired_components",
    },
    {
        "assembly_id": "PCB_ASSEMBLY",
        "zone": "front-right",
        "zone_anchor_mm": [270.0, -210.0, 80.0],
        "part_ids": ["PART_006", "PART_007", "PART_019"],
        "description": "PCB protective plate, main PCB, and support frame",
        "expansion_policy": "group_then_three_layer_components",
    },
    {
        "assembly_id": "SENSOR_ASSEMBLY",
        "zone": "front-left",
        "zone_anchor_mm": [-270.0, -210.0, 80.0],
        "part_ids": ["PART_003", "PART_012", "PART_013", "PART_014"],
        "description": "tri-axis fixture and three orthogonal sensor fixtures",
        "expansion_policy": "group_then_xyz_components",
    },
    {
        "assembly_id": "BATTERY_ASSEMBLY",
        "zone": "left",
        "zone_anchor_mm": [-300.0, 40.0, 40.0],
        "part_ids": [
            "PART_008",
            "PART_009",
            "PART_010",
            "PART_011",
            "PART_015",
            "PART_016",
        ],
        "description": "six battery compartments in a 3-by-2 array",
        "expansion_policy": "group_then_3x2_array",
    },
    {
        "assembly_id": "LEVELING_ASSEMBLY",
        "zone": "bottom",
        "zone_anchor_mm": [0.0, -300.0, -210.0],
        "part_ids": ["PART_020", "PART_021", "PART_022"],
        "description": "three leveling cones in a clear triangle",
        "expansion_policy": "triangular_components",
    },
)


def validate_v4_layout(layout: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the static v4 identity and policy markers."""
    if layout.get("layout_version") != "v4":
        raise ValueError("presentation layout must be v4")
    if layout.get("mode") != "STATIC_FOCUSED_HIERARCHICAL_PRESENTATION":
        raise ValueError("v4 presentation mode is invalid")
    if layout.get("animation_created") is not False:
        raise ValueError("v4 presentation must not create animation")
    parts = layout.get("parts")
    if not isinstance(parts, Mapping) or list(parts) != list(EXPECTED_PART_IDS):
        raise ValueError("v4 layout must contain ordered PART_001..PART_082")
    visible = [
        record for record in parts.values()
        if record.get("presentation_visibility") == "VISIBLE"
    ]
    if len(visible) != len(IMPORTANT_PART_IDS):
        raise ValueError("v4 visible important-part count is invalid")
    if any(record.get("part_id") not in IMPORTANT_PART_IDS for record in visible):
        raise ValueError("v4 visible set contains a non-important PART")
    queue = layout.get("review_queue")
    if not isinstance(queue, list) or len(queue) != len(IMPORTANT_PART_IDS):
        raise ValueError("v4 review queue must contain only the important PARTs")
    if any(item.get("part_id") not in IMPORTANT_PART_IDS for item in queue):
        raise ValueError("v4 review queue contains a non-important PART")
    return dict(layout)


def build_presentation_layout_v4(project_root: Path) -> dict[str, Any]:
    """Build the focused static v4 layout from immutable Stage 02 data."""
    root = Path(project_root).expanduser().resolve()
    baseline = validate_task09_baseline(root)
    manifest = _index_records(load_manifest(root), "parts_manifest.json")
    semantic = _index_records(
        _load_records(root / "data/semantic_parts.json", "semantic_parts.json"),
        "semantic_parts.json",
    )
    initial_payload = _load_mapping(
        root / "data/assembly_initial.json", "assembly_initial.json"
    )
    initial = initial_payload.get("objects")
    if not isinstance(initial, Mapping):
        raise ValueError("assembly_initial.json must contain objects")
    _validate_coverage(manifest, semantic, initial)
    assemblies = _build_assemblies(manifest)
    part_to_assembly = {
        part_id: assembly_id
        for assembly_id, assembly in assemblies.items()
        for part_id in assembly["part_ids"]
    }
    if set(part_to_assembly) != set(IMPORTANT_PART_IDS):
        raise ValueError("v4 assemblies must cover exactly PART_001..PART_022")

    parts: dict[str, dict[str, Any]] = {}
    review_queue: list[dict[str, Any]] = []
    for part_id in EXPECTED_PART_IDS:
        manifest_record = manifest[part_id]
        semantic_record = semantic[part_id]
        assembled = _vector(initial[part_id].get("location"), f"{part_id} location")
        if part_id in part_to_assembly:
            assembly_id = part_to_assembly[part_id]
            assembly = assemblies[assembly_id]
            local = _local_offset(assembly_id, part_id, assembly["part_ids"])
            zone_offset = list(assembly["zone_anchor_mm"])
            presentation = _add(assembled, zone_offset, local)
            mode = "ANCHOR" if part_id == "PART_001" else "VISIBLE_IMPORTANT_COMPONENT"
            visibility = "VISIBLE"
            parent = assembly_id
            zone = assembly["zone"]
            review = {
                "part_id": part_id,
                "semantic_name": str(semantic_record.get("semantic_name") or "UNKNOWN"),
                "semantic_category": str(semantic_record.get("semantic_category") or "UNKNOWN"),
                "size_class": str(manifest_record["size_class"]),
                "assembly_id": assembly_id,
                "zone": zone,
                "review_scope": REVIEW_SCOPE,
                "review_question": REVIEW_QUESTION,
            }
            review_queue.append(review)
        else:
            is_unresolved_medium = str(manifest_record["size_class"]) == "MEDIUM"
            mode = "HIDDEN_UNRESOLVED_MEDIUM" if is_unresolved_medium else "HIDDEN_NO_PARENT"
            visibility = "HIDDEN"
            parent = None
            zone = None
            zone_offset = [0.0, 0.0, 0.0]
            local = [0.0, 0.0, 0.0]
            presentation = list(assembled)
        parts[part_id] = {
            "part_id": part_id,
            "source_component_index": int(manifest_record["source_component_index"]),
            "semantic_name": str(semantic_record.get("semantic_name") or "UNKNOWN"),
            "semantic_category": str(semantic_record.get("semantic_category") or "UNKNOWN"),
            "semantic_confidence": str(semantic_record.get("confidence") or "UNKNOWN"),
            "semantic_evidence": list(semantic_record.get("evidence") or []),
            "semantic_reason": str(semantic_record.get("reason") or ""),
            "size_class": str(manifest_record["size_class"]),
            "bbox_dimensions_mm": [float(value) for value in manifest_record["bbox_dimensions"]],
            "face_count": int(manifest_record["face_count"]),
            "vertex_count": int(manifest_record["vertex_count"]),
            "assembled_location": assembled,
            "presentation_location": presentation,
            "assembly_zone_offset_mm": zone_offset,
            "local_offset_mm": local,
            "presentation_zone": zone,
            "presentation_assembly": parent,
            "presentation_parent": parent,
            "hierarchy_level": 2 if parent is not None else None,
            "presentation_mode": mode,
            "presentation_visibility": visibility,
            "follow_parent_assembly": False,
            "review_scope": REVIEW_SCOPE if visibility == "VISIBLE" else None,
            "review_question": REVIEW_QUESTION if visibility == "VISIBLE" else None,
        }

    layout = {
        "layout_version": "v4",
        "mode": "STATIC_FOCUSED_HIERARCHICAL_PRESENTATION",
        "unit_assumption": "mm",
        "unit_confidence": "assumed",
        "animation_created": False,
        "animation_anchor": "PART_001",
        "source_sha256": baseline["source_sha256"],
        "source_baseline": {
            "source_parts": baseline["source_parts"],
            "faces": baseline["faces"],
            "indexed_vertices": baseline["indexed_vertices"],
        },
        "selection_policy": {
            "visible_part_ids": list(IMPORTANT_PART_IDS),
            "visible_rule": "confirmed important semantic parts PART_001..PART_022",
            "hidden_unresolved_medium": sorted(
                [part_id for part_id in EXPECTED_PART_IDS if part_id not in IMPORTANT_PART_IDS and manifest[part_id]["size_class"] == "MEDIUM"],
                key=_part_number,
            ),
            "hidden_small_fragment": sorted(
                [part_id for part_id in EXPECTED_PART_IDS if part_id not in IMPORTANT_PART_IDS and manifest[part_id]["size_class"] != "MEDIUM"],
                key=_part_number,
            ),
        },
        "policy": {
            "small_fragment_in_collision_queue": False,
            "small_fragment_in_animation_queue": False,
            "small_fragment_in_manual_motion_review": False,
            "unresolved_medium_in_review_queue": False,
            "flat_per_part_explosion": False,
            "realistic_disassembly_order": False,
            "keyframes_created": False,
        },
        "zones": _zone_document(assemblies),
        "assemblies": assemblies,
        "parts": parts,
        "review_queue": review_queue,
        "review_focus": REVIEW_QUESTION,
    }
    return validate_v4_layout(layout)


def write_presentation_outputs_v4(
    project_root: Path, layout: Mapping[str, Any]
) -> dict[str, Path]:
    """Write deterministic v4 layout and important-only review CSV."""
    validated = validate_v4_layout(layout)
    root = Path(project_root).expanduser().resolve()
    layout_path = root / "data/presentation_explosion_v4.json"
    review_path = root / "data/presentation_review_queue_v4.csv"
    write_json(layout_path, validated)
    with review_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for item in validated["review_queue"]:
            writer.writerow({field: item.get(field, "") for field in REVIEW_FIELDS})
    return {"layout": layout_path, "review_queue": review_path}


def _build_assemblies(manifest: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    assemblies: dict[str, dict[str, Any]] = {}
    assigned: list[str] = []
    for raw in _ASSEMBLY_SPECS:
        assembly_id = str(raw["assembly_id"])
        zone = str(raw["zone"])
        if zone not in ALLOWED_ZONES:
            raise ValueError(f"invalid v4 zone: {zone}")
        part_ids = [str(value) for value in raw["part_ids"]]
        for part_id in part_ids:
            if part_id not in manifest:
                raise ValueError(f"unknown v4 PART: {part_id}")
            if part_id not in IMPORTANT_PART_IDS:
                raise ValueError(f"non-important PART assigned to v4 assembly: {part_id}")
        assemblies[assembly_id] = {
            "assembly_id": assembly_id,
            "hierarchy_level": 1,
            "zone": zone,
            "zone_anchor_mm": _vector(raw["zone_anchor_mm"], f"{assembly_id} zone anchor"),
            "part_ids": part_ids,
            "visible_part_ids": part_ids,
            "hidden_followers": [],
            "description": str(raw["description"]),
            "expansion_policy": str(raw["expansion_policy"]),
            "presentation_only": True,
        }
        assigned.extend(part_ids)
    if sorted(assigned, key=_part_number) != list(IMPORTANT_PART_IDS):
        raise ValueError("v4 important assembly coverage mismatch")
    return assemblies


def _local_offset(assembly_id: str, part_id: str, part_ids: Sequence[str]) -> list[float]:
    explicit = {
        "ENCLOSURE_ASSEMBLY": {
            "PART_001": [0.0, 0.0, 0.0],
            "PART_002": [0.0, 0.0, 175.0],
            "PART_004": [0.0, 0.0, 310.0],
        },
        "HANDLE_ASSEMBLY": {"PART_005": [0.0, 0.0, 0.0]},
        "TOP_INTERFACE_ASSEMBLY": {
            "PART_017": [-70.0, 0.0, 0.0],
            "PART_018": [70.0, 0.0, 0.0],
        },
        "PCB_ASSEMBLY": {
            "PART_006": [0.0, 0.0, 100.0],
            "PART_007": [-145.0, 0.0, -55.0],
            "PART_019": [145.0, 0.0, 0.0],
        },
        "SENSOR_ASSEMBLY": {
            "PART_003": [0.0, 0.0, 0.0],
            "PART_012": [-105.0, 0.0, 0.0],
            "PART_013": [0.0, 105.0, 0.0],
            "PART_014": [0.0, 0.0, 105.0],
        },
        "BATTERY_ASSEMBLY": {
            "PART_008": [-95.0, -65.0, 0.0],
            "PART_009": [0.0, -65.0, 0.0],
            "PART_010": [95.0, -65.0, 0.0],
            "PART_011": [-95.0, 65.0, 0.0],
            "PART_015": [0.0, 65.0, 0.0],
            "PART_016": [95.0, 65.0, 0.0],
        },
        "LEVELING_ASSEMBLY": {
            "PART_020": [-180.0, -130.0, 0.0],
            "PART_021": [0.0, 130.0, 0.0],
            "PART_022": [180.0, -130.0, 0.0],
        },
    }
    try:
        return list(explicit[assembly_id][part_id])
    except KeyError as exc:
        raise ValueError(f"missing v4 local offset for {assembly_id}/{part_id}") from exc


def _zone_document(assemblies: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    zones = {
        zone: {"zone": zone, "assembly_ids": []}
        for zone in ALLOWED_ZONES
    }
    for assembly_id, assembly in assemblies.items():
        zones[assembly["zone"]]["assembly_ids"].append(assembly_id)
    return zones


def _validate_coverage(
    manifest: Mapping[str, Mapping[str, Any]],
    semantic: Mapping[str, Mapping[str, Any]],
    initial: Mapping[str, Any],
) -> None:
    for label, mapping in (("manifest", manifest), ("semantic", semantic), ("initial", initial)):
        if list(sorted(mapping, key=_part_number)) != list(EXPECTED_PART_IDS):
            raise ValueError(f"{label} PART coverage is not PART_001..PART_082")


def _load_records(path: Path, label: str) -> list[dict[str, Any]]:
    payload = load_json(path)
    if not isinstance(payload, list) or not all(isinstance(item, Mapping) for item in payload):
        raise ValueError(f"{label} must contain a list of objects")
    return [dict(item) for item in payload]


def _load_mapping(path: Path, label: str) -> dict[str, Any]:
    payload = load_json(path)
    if not isinstance(payload, Mapping):
        raise ValueError(f"{label} must contain an object")
    return dict(payload)


def _index_records(records: Sequence[Mapping[str, Any]], label: str) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for record in records:
        part_id = str(record.get("part_id") or "")
        if not part_id.startswith("PART_") or part_id in indexed:
            raise ValueError(f"invalid or duplicate PART in {label}: {part_id!r}")
        indexed[part_id] = dict(record)
    return indexed


def _part_number(part_id: str) -> int:
    try:
        return int(str(part_id).split("_")[-1])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid PART ID: {part_id!r}") from exc


def _vector(value: Any, label: str) -> list[float]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 3:
        raise ValueError(f"{label} must be a 3-value vector")
    result = [float(item) for item in value]
    if not all(math.isfinite(item) for item in result):
        raise ValueError(f"{label} must contain finite values")
    return result


def _add(*vectors: Sequence[float]) -> list[float]:
    result = [0.0, 0.0, 0.0]
    for vector in vectors:
        values = _vector(vector, "vector")
        result = [left + right for left, right in zip(result, values)]
    return result
