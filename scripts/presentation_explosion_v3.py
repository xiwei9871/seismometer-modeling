"""Plan a static, hierarchical presentation explosion for the recovered STL."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import csv
import math
from pathlib import Path
from typing import Any

from scripts.task08_data import load_json, load_manifest, write_json
from scripts.task09_data import TASK09_BASELINE, validate_task09_baseline


ALLOWED_ZONES = (
    "top",
    "bottom",
    "left",
    "right",
    "front-left",
    "front-right",
)
VISIBLE_SIZE_CLASSES = frozenset({"MAJOR", "MEDIUM"})
HIDDEN_SIZE_CLASSES = frozenset({"SMALL", "TINY", "FRAGMENT"})
EXPECTED_PART_IDS = tuple(f"PART_{index:03d}" for index in range(1, 83))
REVIEW_QUESTION = (
    "Is the important component visible, unobstructed, and clearly laid out?"
)
REVIEW_QUEUE_FIELDS = (
    "part_id",
    "item_type",
    "semantic_name",
    "size_class",
    "assembly_id",
    "zone",
    "presentation_mode",
    "review_question",
)


_ASSEMBLY_SPECS: tuple[dict[str, Any], ...] = (
    {
        "assembly_id": "ENCLOSURE_ASSEMBLY",
        "zone": "bottom",
        "zone_anchor_mm": [0.0, 0.0, 0.0],
        "part_ids": ["PART_001", "PART_002", "PART_004"],
        "description": "lower anchor plus separated upper housing and top cover",
        "expansion_policy": "anchor_then_vertical_components",
    },
    {
        "assembly_id": "HANDLE_ASSEMBLY",
        "zone": "top",
        "zone_anchor_mm": [0.0, 0.0, 420.0],
        "part_ids": ["PART_005"],
        "description": "handle and antenna shroud shown in its own top zone",
        "expansion_policy": "single_component",
    },
    {
        "assembly_id": "TOP_INTERFACE_ASSEMBLY",
        "zone": "right",
        "zone_anchor_mm": [340.0, 20.0, 250.0],
        "part_ids": ["PART_017", "PART_018"],
        "description": "two top interface ports shown as a separated pair",
        "expansion_policy": "paired_components",
    },
    {
        "assembly_id": "PCB_ASSEMBLY",
        "zone": "front-right",
        "zone_anchor_mm": [330.0, -260.0, 90.0],
        "part_ids": ["PART_006", "PART_007", "PART_019"],
        "description": "PCB protection, board, and support frame separated after group move",
        "expansion_policy": "group_then_three_layer_components",
    },
    {
        "assembly_id": "SENSOR_ASSEMBLY",
        "zone": "front-left",
        "zone_anchor_mm": [-330.0, -260.0, 90.0],
        "part_ids": ["PART_003", "PART_012", "PART_013", "PART_014"],
        "description": "tri-axis fixture moved first, then X/Y/Z fixtures expanded",
        "expansion_policy": "group_then_xyz_components",
    },
    {
        "assembly_id": "BATTERY_ASSEMBLY",
        "zone": "left",
        "zone_anchor_mm": [-350.0, 80.0, 80.0],
        "part_ids": [
            "PART_008",
            "PART_009",
            "PART_010",
            "PART_011",
            "PART_015",
            "PART_016",
        ],
        "description": "six battery compartments shown in a 3-by-2 array",
        "expansion_policy": "group_then_3x2_array",
    },
    {
        "assembly_id": "LEVELING_ASSEMBLY",
        "zone": "bottom",
        "zone_anchor_mm": [0.0, 0.0, -240.0],
        "part_ids": ["PART_020", "PART_021", "PART_022"],
        "description": "three leveling cones shown as a separated triangle",
        "expansion_policy": "triangular_components",
    },
    {
        "assembly_id": "UNRESOLVED_MEDIUM_ASSEMBLY",
        "zone": "right",
        "zone_anchor_mm": [560.0, 100.0, 80.0],
        "part_ids": [
            *(f"PART_{index:03d}" for index in range(23, 39)),
            *(f"PART_{index:03d}" for index in range(40, 46)),
        ],
        "description": "medium geometry kept visible without semantic guessing",
        "expansion_policy": "review_grid",
    },
)


def validate_zone_name(zone: str) -> str:
    """Validate one of the six fixed presentation zones."""
    if zone not in ALLOWED_ZONES:
        raise ValueError(f"invalid presentation zone: {zone!r}")
    return zone


def build_presentation_layout(project_root: Path) -> dict[str, Any]:
    """Return the complete deterministic v3 layout without importing Blender."""
    root = Path(project_root).expanduser().resolve()
    baseline = validate_task09_baseline(root)
    manifest = load_manifest(root)
    semantic = _load_records(root / "data/semantic_parts.json", "semantic_parts.json")
    initial_payload = _load_mapping(
        root / "data/assembly_initial.json", "assembly_initial.json"
    )
    initial = initial_payload.get("objects")
    if not isinstance(initial, Mapping):
        raise ValueError("assembly_initial.json must contain an objects mapping")

    manifest_by_part = _index_records(manifest, "parts_manifest.json")
    semantic_by_part = _index_records(semantic, "semantic_parts.json")
    _validate_part_coverage(manifest_by_part, semantic_by_part, initial)
    assemblies = _build_assemblies(manifest_by_part)
    part_to_assembly = {
        part_id: assembly_id
        for assembly_id, assembly in assemblies.items()
        for part_id in assembly["part_ids"]
    }
    if len(part_to_assembly) != 44:
        raise ValueError("v3 visible assembly map must cover exactly 44 parts")

    parts: dict[str, dict[str, Any]] = {}
    review_queue: list[dict[str, Any]] = []
    for part_id in EXPECTED_PART_IDS:
        manifest_record = manifest_by_part[part_id]
        semantic_record = semantic_by_part[part_id]
        assembled = _vector(initial[part_id].get("location"), f"{part_id} location")
        size_class = str(manifest_record.get("size_class", ""))
        if part_id in part_to_assembly:
            assembly_id = part_to_assembly[part_id]
            assembly = assemblies[assembly_id]
            local_offset = _local_offset_for_part(
                assembly_id,
                part_id,
                assembly["part_ids"],
            )
            zone_offset = list(assembly["zone_anchor_mm"])
            presentation_location = _add_vectors(
                assembled,
                zone_offset,
                local_offset,
            )
            semantic_name = str(semantic_record.get("semantic_name") or "UNKNOWN")
            semantic_category = str(
                semantic_record.get("semantic_category") or "UNKNOWN"
            )
            confidence = str(semantic_record.get("confidence") or "UNKNOWN")
            mode = "ANCHOR" if part_id == "PART_001" else "VISIBLE_COMPONENT"
            parent = assembly_id
            record = _part_record(
                part_id=part_id,
                manifest_record=manifest_record,
                semantic_record=semantic_record,
                assembled=assembled,
                zone=assembly["zone"],
                assembly_id=assembly_id,
                parent=parent,
                mode=mode,
                visibility="VISIBLE",
                zone_offset=zone_offset,
                local_offset=local_offset,
                presentation_location=presentation_location,
                semantic_name=semantic_name,
                semantic_category=semantic_category,
                confidence=confidence,
            )
            parts[part_id] = record
            review_queue.append(_review_record(record))
            continue

        if size_class not in HIDDEN_SIZE_CLASSES:
            raise ValueError(
                f"unassigned v3 part {part_id} has unsupported size class {size_class!r}"
            )
        record = _part_record(
            part_id=part_id,
            manifest_record=manifest_record,
            semantic_record=semantic_record,
            assembled=assembled,
            zone=None,
            assembly_id=None,
            parent=None,
            mode="HIDDEN_NO_PARENT",
            visibility="HIDDEN",
            zone_offset=[0.0, 0.0, 0.0],
            local_offset=[0.0, 0.0, 0.0],
            presentation_location=list(assembled),
            semantic_name=str(semantic_record.get("semantic_name") or "UNKNOWN"),
            semantic_category=str(
                semantic_record.get("semantic_category") or "UNKNOWN"
            ),
            confidence=str(semantic_record.get("confidence") or "UNKNOWN"),
        )
        parts[part_id] = record

    return {
        "layout_version": "v3",
        "mode": "STATIC_HIERARCHICAL_PRESENTATION",
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
        "policy": {
            "visible_size_classes": ["MAJOR", "MEDIUM"],
            "hidden_size_classes": ["SMALL", "TINY", "FRAGMENT"],
            "small_fragment_motion_policy": "HIDDEN_OR_FOLLOW_EXPLICIT_PARENT",
            "small_fragment_in_collision_queue": False,
            "small_fragment_in_animation_queue": False,
            "small_fragment_in_manual_motion_review": False,
            "flat_per_part_explosion": False,
            "keyframes_created": False,
        },
        "zones": _build_zone_document(assemblies),
        "assemblies": assemblies,
        "parts": parts,
        "review_queue": review_queue,
        "review_focus": REVIEW_QUESTION,
    }


def write_presentation_outputs(
    project_root: Path, layout: Mapping[str, Any]
) -> dict[str, Path]:
    """Write deterministic v3 JSON and visible-only CSV outputs."""
    root = Path(project_root).expanduser().resolve()
    layout_path = root / "data/presentation_explosion_v3.json"
    review_path = root / "data/presentation_review_queue_v3.csv"
    write_json(layout_path, layout)
    queue = layout.get("review_queue")
    if not isinstance(queue, Sequence) or isinstance(queue, (str, bytes)):
        raise ValueError("presentation layout review_queue must be a list")
    review_path.parent.mkdir(parents=True, exist_ok=True)
    with review_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_QUEUE_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for item in sorted(queue, key=lambda value: _part_number(str(value["part_id"]))):
            writer.writerow({field: item.get(field, "") for field in REVIEW_QUEUE_FIELDS})
    return {"layout": layout_path, "review_queue": review_path}


def _build_assemblies(manifest_by_part: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Build assembly records and verify every visible part is assigned once."""
    assemblies: dict[str, dict[str, Any]] = {}
    assigned: list[str] = []
    for raw in _ASSEMBLY_SPECS:
        assembly_id = str(raw["assembly_id"])
        zone = validate_zone_name(str(raw["zone"]))
        part_ids = [str(part_id) for part_id in raw["part_ids"]]
        if assembly_id in assemblies:
            raise ValueError(f"duplicate v3 assembly ID: {assembly_id}")
        if len(part_ids) != len(set(part_ids)):
            raise ValueError(f"duplicate PART in {assembly_id}")
        for part_id in part_ids:
            if part_id not in manifest_by_part:
                raise ValueError(f"{assembly_id} references unknown PART {part_id}")
            if str(manifest_by_part[part_id].get("size_class")) not in VISIBLE_SIZE_CLASSES:
                raise ValueError(
                    f"{assembly_id} assigns non-visible size class to {part_id}"
                )
        zone_anchor = _vector(raw["zone_anchor_mm"], f"{assembly_id} zone anchor")
        assemblies[assembly_id] = {
            "assembly_id": assembly_id,
            "hierarchy_level": 1,
            "zone": zone,
            "zone_anchor_mm": zone_anchor,
            "part_ids": part_ids,
            "visible_part_ids": part_ids,
            "hidden_followers": [],
            "description": str(raw["description"]),
            "expansion_policy": str(raw["expansion_policy"]),
            "presentation_only": True,
        }
        assigned.extend(part_ids)
    if len(assigned) != len(set(assigned)):
        raise ValueError("a visible PART is assigned to more than one v3 assembly")
    expected_visible = {
        part_id
        for part_id, record in manifest_by_part.items()
        if str(record.get("size_class")) in VISIBLE_SIZE_CLASSES
    }
    if set(assigned) != expected_visible:
        missing = sorted(expected_visible - set(assigned), key=_part_number)
        extra = sorted(set(assigned) - expected_visible, key=_part_number)
        raise ValueError(f"v3 visible assembly coverage mismatch: missing={missing}, extra={extra}")
    return assemblies


def _build_zone_document(assemblies: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Return all six zone names even when more than one assembly shares a zone."""
    document = {
        zone: {
            "zone": zone,
            "assembly_ids": [],
            "description": f"fixed presentation zone: {zone}",
        }
        for zone in ALLOWED_ZONES
    }
    for assembly_id, assembly in assemblies.items():
        document[assembly["zone"]]["assembly_ids"].append(assembly_id)
    return document


def _local_offset_for_part(
    assembly_id: str,
    part_id: str,
    assembly_part_ids: Sequence[str],
) -> list[float]:
    explicit: dict[str, dict[str, list[float]]] = {
        "ENCLOSURE_ASSEMBLY": {
            "PART_001": [0.0, 0.0, 0.0],
            "PART_002": [0.0, 0.0, 180.0],
            "PART_004": [0.0, 0.0, 305.0],
        },
        "HANDLE_ASSEMBLY": {"PART_005": [0.0, 0.0, 0.0]},
        "TOP_INTERFACE_ASSEMBLY": {
            "PART_017": [-80.0, 0.0, 0.0],
            "PART_018": [80.0, 0.0, 0.0],
        },
        "PCB_ASSEMBLY": {
            "PART_006": [0.0, 0.0, 125.0],
            "PART_007": [-180.0, 0.0, -70.0],
            "PART_019": [180.0, 0.0, 0.0],
        },
        "SENSOR_ASSEMBLY": {
            "PART_003": [0.0, 0.0, 0.0],
            "PART_012": [-115.0, 0.0, 0.0],
            "PART_013": [0.0, 115.0, 0.0],
            "PART_014": [0.0, 0.0, 115.0],
        },
        "BATTERY_ASSEMBLY": {
            "PART_008": [-130.0, -80.0, 0.0],
            "PART_009": [0.0, -80.0, 0.0],
            "PART_010": [130.0, -80.0, 0.0],
            "PART_011": [-130.0, 80.0, 0.0],
            "PART_015": [0.0, 80.0, 0.0],
            "PART_016": [130.0, 80.0, 0.0],
        },
        "LEVELING_ASSEMBLY": {
            "PART_020": [-110.0, -70.0, 0.0],
            "PART_021": [0.0, 70.0, 0.0],
            "PART_022": [110.0, -70.0, 0.0],
        },
    }
    if assembly_id in explicit and part_id in explicit[assembly_id]:
        return list(explicit[assembly_id][part_id])
    if assembly_id == "UNRESOLVED_MEDIUM_ASSEMBLY":
        index = list(assembly_part_ids).index(part_id)
        columns = 5
        column = index % columns
        row = index // columns
        return [
            float((column - 2) * 155.0),
            float((row - 2) * 135.0),
            0.0,
        ]
    raise ValueError(f"no v3 local offset defined for {assembly_id}/{part_id}")


def _part_record(
    *,
    part_id: str,
    manifest_record: Mapping[str, Any],
    semantic_record: Mapping[str, Any],
    assembled: list[float],
    zone: str | None,
    assembly_id: str | None,
    parent: str | None,
    mode: str,
    visibility: str,
    zone_offset: list[float],
    local_offset: list[float],
    presentation_location: list[float],
    semantic_name: str,
    semantic_category: str,
    confidence: str,
) -> dict[str, Any]:
    if visibility == "VISIBLE" and str(manifest_record.get("size_class")) not in VISIBLE_SIZE_CLASSES:
        raise ValueError(f"visible v3 record has invalid size class: {part_id}")
    if visibility == "HIDDEN" and str(manifest_record.get("size_class")) not in HIDDEN_SIZE_CLASSES:
        raise ValueError(f"hidden v3 record has invalid size class: {part_id}")
    return {
        "part_id": part_id,
        "source_component_index": int(manifest_record["source_component_index"]),
        "semantic_name": semantic_name,
        "semantic_category": semantic_category,
        "semantic_confidence": confidence,
        "semantic_evidence": list(semantic_record.get("evidence") or []),
        "semantic_reason": str(semantic_record.get("reason") or ""),
        "size_class": str(manifest_record["size_class"]),
        "bbox_dimensions_mm": [
            float(value) for value in manifest_record["bbox_dimensions"]
        ],
        "face_count": int(manifest_record["face_count"]),
        "vertex_count": int(manifest_record["vertex_count"]),
        "assembled_location": assembled,
        "presentation_location": presentation_location,
        "assembly_zone_offset_mm": zone_offset,
        "local_offset_mm": local_offset,
        "presentation_zone": zone,
        "presentation_assembly": assembly_id,
        "presentation_parent": parent,
        "hierarchy_level": 2 if assembly_id is not None else None,
        "presentation_mode": mode,
        "presentation_visibility": visibility,
        "follow_parent_assembly": False,
        "review_question": REVIEW_QUESTION if visibility == "VISIBLE" else None,
        "requires_manual_confirmation": bool(
            semantic_record.get("requires_manual_confirmation", False)
        ),
    }


def _review_record(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "part_id": record["part_id"],
        "item_type": "PART",
        "semantic_name": record["semantic_name"],
        "size_class": record["size_class"],
        "assembly_id": record["presentation_assembly"],
        "zone": record["presentation_zone"],
        "presentation_mode": record["presentation_mode"],
        "review_question": REVIEW_QUESTION,
    }


def _validate_part_coverage(
    manifest_by_part: Mapping[str, Mapping[str, Any]],
    semantic_by_part: Mapping[str, Mapping[str, Any]],
    initial: Mapping[str, Any],
) -> None:
    for label, mapping in (
        ("manifest", manifest_by_part),
        ("semantic", semantic_by_part),
        ("assembly_initial", initial),
    ):
        actual = sorted(mapping, key=_part_number)
        if actual != list(EXPECTED_PART_IDS):
            raise ValueError(f"{label} PART coverage does not match PART_001..PART_082")


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


def _index_records(
    records: Sequence[Mapping[str, Any]], label: str
) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for record in records:
        part_id = str(record.get("part_id") or "")
        if not part_id.startswith("PART_"):
            raise ValueError(f"{label} contains invalid part_id: {part_id!r}")
        if part_id in indexed:
            raise ValueError(f"{label} contains duplicate part_id: {part_id}")
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
    result: list[float] = []
    for item in value:
        if isinstance(item, bool):
            raise ValueError(f"{label} must contain numeric values")
        try:
            number = float(item)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{label} must contain numeric values") from exc
        if not math.isfinite(number):
            raise ValueError(f"{label} must contain finite values")
        result.append(number)
    return result


def _add_vectors(*vectors: Sequence[float]) -> list[float]:
    result = [0.0, 0.0, 0.0]
    for vector in vectors:
        values = _vector(vector, "vector")
        result = [left + right for left, right in zip(result, values)]
    return result
