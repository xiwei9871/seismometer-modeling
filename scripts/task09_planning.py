"""Deterministic Task 9A disassembly graph and duplicate-group planning."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
import math
from pathlib import Path
from typing import Any

from scripts.task08_data import load_json
from scripts.task09_data import validate_task09_baseline


CONFIDENCE_RANK = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "UNKNOWN": 3}


def kahn_topological_sort(
    node_ids: Sequence[str], edges: Sequence[Mapping[str, Any]]
) -> list[str]:
    """Return a deterministic topological order or reject a directed cycle."""
    nodes = sorted({str(node_id) for node_id in node_ids})
    node_set = set(nodes)
    outgoing: dict[str, set[str]] = {node_id: set() for node_id in nodes}
    indegree: dict[str, int] = {node_id: 0 for node_id in nodes}
    for edge in edges:
        before = str(edge["before"])
        after = str(edge["after"])
        if before not in node_set or after not in node_set:
            raise ValueError(f"edge references unknown DAG node: {before!r} -> {after!r}")
        if after not in outgoing[before]:
            outgoing[before].add(after)
            indegree[after] += 1

    ready = sorted(node_id for node_id, degree in indegree.items() if degree == 0)
    result: list[str] = []
    while ready:
        current = ready.pop(0)
        result.append(current)
        for successor in sorted(outgoing[current]):
            indegree[successor] -= 1
            if indegree[successor] == 0:
                ready.append(successor)
                ready.sort()
    if len(result) != len(nodes):
        raise ValueError("cycle detected in Task 9A disassembly graph")
    return result


def build_disassembly_graph(project_root: Path) -> dict[str, Any]:
    """Expand Task 8 dependencies into a stable DAG with semantic nodes."""
    root = Path(project_root).expanduser().resolve()
    validate_task09_baseline(root)
    semantic_parts = _load_list(root / "data/semantic_parts.json", "semantic_parts.json")
    # Load the complete Task 8 relationship inputs so missing/corrupt files fail
    # before a partial graph can be used as a source of truth.
    assembly = _load_mapping(root / "data/assembly_semantic.json", "assembly_semantic.json")
    mounting = _load_mapping(root / "data/mounting_relationships.json", "mounting_relationships.json")
    dependencies = _load_mapping(root / "data/disassembly_dependencies.json", "disassembly_dependencies.json")
    manifest = _load_list(root / "data/parts_manifest.json", "parts_manifest.json")
    duplicate_groups = _load_mapping(root / "data/duplicate_groups.json", "duplicate_groups.json")
    initial = _load_mapping(root / "data/assembly_initial.json", "assembly_initial.json")
    _validate_input_coverage(semantic_parts, manifest, initial)
    if not isinstance(assembly.get("assemblies"), list):
        raise ValueError("assembly_semantic.json must contain assemblies")
    if not isinstance(mounting.get("relationships"), list):
        raise ValueError("mounting_relationships.json must contain relationships")
    if not isinstance(duplicate_groups.get("groups"), list):
        raise ValueError("duplicate_groups.json must contain groups")

    members_by_semantic: dict[str, list[str]] = defaultdict(list)
    confidence_by_semantic: dict[str, list[str]] = defaultdict(list)
    manual_by_semantic: dict[str, list[bool]] = defaultdict(list)
    for record in sorted(semantic_parts, key=_part_sort_key):
        semantic_name = str(record.get("semantic_name") or "UNKNOWN")
        part_id = str(record["part_id"])
        members_by_semantic[semantic_name].append(part_id)
        confidence_by_semantic[semantic_name].append(
            _valid_confidence(record.get("confidence", "UNKNOWN"))
        )
        manual_by_semantic[semantic_name].append(
            bool(record.get("requires_manual_confirmation", True))
        )

    node_records: dict[str, dict[str, Any]] = {}
    for semantic_name in sorted(members_by_semantic):
        confidences = confidence_by_semantic[semantic_name]
        node_records[semantic_name] = {
            "node_id": semantic_name,
            "kind": "semantic_group",
            "parts": sorted(members_by_semantic[semantic_name], key=_part_number),
            "confidence": _worst_confidence(confidences),
            "requires_manual_confirmation": any(manual_by_semantic[semantic_name])
            or any(confidence != "HIGH" for confidence in confidences),
        }

    edges: list[dict[str, Any]] = []
    for raw_edge in dependencies.get("dependencies", []):
        if not isinstance(raw_edge, Mapping):
            raise ValueError("disassembly dependency must be an object")
        before = str(raw_edge.get("remove_first", ""))
        after = str(raw_edge.get("before", ""))
        if not before or not after:
            raise ValueError("disassembly dependency must contain remove_first and before")
        for node_id in (before, after):
            if node_id not in node_records:
                node_records[node_id] = {
                    "node_id": node_id,
                    "kind": "virtual_group",
                    "parts": [],
                    "confidence": "UNKNOWN",
                    "requires_manual_confirmation": True,
                }
        edges.append(
            {
                "before": before,
                "after": after,
                "confidence": _valid_confidence(raw_edge.get("confidence", "UNKNOWN")),
                "evidence": list(raw_edge.get("evidence", [])),
                "requires_manual_confirmation": bool(
                    raw_edge.get("requires_manual_confirmation", True)
                ),
                "reason": str(raw_edge.get("reason", "")),
            }
        )

    edges = sorted(edges, key=_edge_sort_key)
    node_ids = sorted(node_records)
    topological_order = kahn_topological_sort(node_ids, edges)
    return {
        "directed_acyclic": True,
        "nodes": [node_records[node_id] for node_id in node_ids],
        "edges": edges,
        "topological_order": topological_order,
        "source": "Task 8 disassembly_dependencies.json",
    }


def build_fastener_group_mapping(project_root: Path) -> dict[str, Any]:
    """Describe duplicate groups without merging their physical PART objects."""
    root = Path(project_root).expanduser().resolve()
    validate_task09_baseline(root)
    groups_payload = _load_mapping(root / "data/duplicate_groups.json", "duplicate_groups.json")
    semantic_parts = _load_list(root / "data/semantic_parts.json", "semantic_parts.json")
    manifest = _load_list(root / "data/parts_manifest.json", "parts_manifest.json")
    semantic_by_part = {str(record["part_id"]): record for record in semantic_parts}
    manifest_by_part = {str(record["part_id"]): record for record in manifest}
    results: list[dict[str, Any]] = []
    for raw_group in sorted(groups_payload.get("groups", []), key=lambda item: str(item["group_id"])):
        group_id = str(raw_group["group_id"])
        member_parts = sorted(
            (str(part_id) for part_id in raw_group.get("parts", [])),
            key=_part_number,
        )
        if not member_parts:
            raise ValueError(f"duplicate group {group_id} has no members")
        missing = [part_id for part_id in member_parts if part_id not in semantic_by_part]
        if missing:
            raise ValueError(f"duplicate group {group_id} has unknown PARTs: {missing}")
        anchor = _unambiguous_anchor(member_parts, semantic_by_part, manifest_by_part)
        if anchor is None:
            motion_policy = "UNASSIGNED"
            confidence = "LOW"
            reason = "duplicate geometry is retained as a group, but no unambiguous semantic mounting anchor is available"
            semantic_anchor = "UNASSIGNED"
        else:
            motion_policy = "GROUP_LINEAR"
            confidence = _worst_confidence(
                [_valid_confidence(semantic_by_part[part_id].get("confidence", "UNKNOWN")) for part_id in member_parts]
            )
            semantic_anchor = anchor
            reason = f"all members share the unambiguous semantic assembly anchor {anchor}"
        results.append(
            {
                "group_id": group_id,
                "quantity": len(member_parts),
                "member_parts": member_parts,
                "representative_part": member_parts[0],
                "signature": dict(raw_group.get("signature", {})),
                "source_confidence": _valid_confidence(raw_group.get("confidence", "UNKNOWN")),
                "semantic_anchor": semantic_anchor,
                "motion_policy": motion_policy,
                "confidence": confidence,
                "reason": reason,
            }
        )
    return {
        "group_count": len(results),
        "groups": results,
        "notes": "Duplicate groups describe same-geometry types only; every member remains an independent PART.",
    }


def _load_list(path: Path, label: str) -> list[dict[str, Any]]:
    payload = load_json(path)
    if not isinstance(payload, list) or not all(isinstance(item, Mapping) for item in payload):
        raise ValueError(f"{label} must contain a list of objects")
    return [dict(item) for item in payload]


def _load_mapping(path: Path, label: str) -> dict[str, Any]:
    payload = load_json(path)
    if not isinstance(payload, Mapping):
        raise ValueError(f"{label} must contain an object")
    return dict(payload)


def _validate_input_coverage(
    semantic_parts: Sequence[Mapping[str, Any]],
    manifest: Sequence[Mapping[str, Any]],
    initial: Mapping[str, Any],
) -> None:
    expected = {f"PART_{index:03d}" for index in range(1, 83)}
    semantic_ids = {str(record.get("part_id")) for record in semantic_parts}
    manifest_ids = {str(record.get("part_id")) for record in manifest}
    initial_ids = set((initial.get("objects") or {}).keys())
    if (
        len(semantic_parts) != len(expected)
        or len(manifest) != len(expected)
        or len(semantic_ids) != len(expected)
        or len(manifest_ids) != len(expected)
        or semantic_ids != expected
        or manifest_ids != expected
        or initial_ids != expected
    ):
        raise ValueError("Task 9A input PART coverage does not match PART_001..PART_082")


def _part_number(part_id: str) -> int:
    return int(str(part_id).split("_")[-1])


def _part_sort_key(record: Mapping[str, Any]) -> tuple[int, str]:
    part_id = str(record.get("part_id"))
    return (_part_number(part_id), part_id)


def _edge_sort_key(edge: Mapping[str, Any]) -> tuple[str, str, int, str]:
    confidence = _valid_confidence(edge.get("confidence", "UNKNOWN"))
    return (
        str(edge.get("before", "")),
        str(edge.get("after", "")),
        CONFIDENCE_RANK[confidence],
        str(edge.get("reason", "")),
    )


def _valid_confidence(value: Any) -> str:
    text = str(value)
    if text not in CONFIDENCE_RANK:
        return "UNKNOWN"
    return text


def _worst_confidence(values: Sequence[str]) -> str:
    if not values:
        return "UNKNOWN"
    return max(values, key=lambda value: CONFIDENCE_RANK[_valid_confidence(value)])


def _unambiguous_anchor(
    member_parts: Sequence[str],
    semantic_by_part: Mapping[str, Mapping[str, Any]],
    manifest_by_part: Mapping[str, Mapping[str, Any]],
) -> str | None:
    anchors: list[str] = []
    for part_id in member_parts:
        record = semantic_by_part[part_id]
        category = str(record.get("semantic_category") or "UNKNOWN")
        confidence = _valid_confidence(record.get("confidence", "UNKNOWN"))
        if category == "UNKNOWN" or confidence in {"LOW", "UNKNOWN"}:
            return None
        anchors.append(_category_to_assembly(category))
    if not anchors or len(set(anchors)) != 1:
        return None
    # The manifest lookup is intentional: an anchor is only considered usable
    # when every member still has geometry metadata in the frozen manifest.
    if any(part_id not in manifest_by_part for part_id in member_parts):
        return None
    return anchors[0]


def _category_to_assembly(category: str) -> str:
    return {
        "ENCLOSURE": "ENCLOSURE",
        "HANDLE": "HANDLE_ASSEMBLY",
        "PCB_ASSEMBLY": "PCB_ASSEMBLY",
        "SENSOR_ASSEMBLY": "SENSOR_ASSEMBLY",
        "BATTERY_ASSEMBLY": "BATTERY_ASSEMBLY",
        "CONNECTOR": "TOP_INTERFACE",
        "LEVELING_ASSEMBLY": "LEVELING_ASSEMBLY",
        "SMALL_ACCESSORY": "FASTENERS_AND_SMALL_ACCESSORIES",
    }.get(category, "UNKNOWN")


# ---------------------------------------------------------------------------
# Task 9A exploded-state planning

_EXPLOSION_SAMPLES = [0.0, 0.25, 0.5, 0.75, 1.0]

_EXPLICIT_EXPLODE_VECTORS: dict[str, list[float]] = {
    "HANDLE": [0.0, 0.0, 1.0],
    "UPPER_HOUSING_TOP_COVER": [0.0, 0.0, 1.0],
    "TOP_INTERFACE_PORT_01": [0.0, 0.0, 1.0],
    "TOP_INTERFACE_PORT_02": [0.0, 0.0, 1.0],
    "UPPER_HOUSING": [0.0, 0.0, 1.0],
    "PCB_PROTECTIVE_PLATE": [0.0, 0.0, -1.0],
    "MAIN_PCB": [0.0, 1.0, 0.0],
    "PCB_SUPPORT_FRAME": [0.0, -1.0, 0.0],
    "TRI_AXIS_SENSOR_FIXTURE": [-1.0, 0.0, 0.0],
    "SENSOR_CORE_FIXTURE_X": [-1.0, 0.0, 0.0],
    "SENSOR_CORE_FIXTURE_Y": [-1.0, 0.0, 0.0],
    "SENSOR_CORE_FIXTURE_Z": [-1.0, 0.0, 0.0],
    "LOWER_HOUSING": [0.0, 0.0, -1.0],
}

_EXPLODE_ORDER: dict[str, int] = {
    "HANDLE": 2,
    "UPPER_HOUSING_TOP_COVER": 3,
    "TOP_INTERFACE_PORT_01": 4,
    "TOP_INTERFACE_PORT_02": 4,
    "UPPER_HOUSING": 5,
    "PCB_PROTECTIVE_PLATE": 6,
    "MAIN_PCB": 7,
    "PCB_SUPPORT_FRAME": 8,
    "TRI_AXIS_SENSOR_FIXTURE": 10,
    "SENSOR_CORE_FIXTURE_X": 11,
    "SENSOR_CORE_FIXTURE_Y": 11,
    "SENSOR_CORE_FIXTURE_Z": 11,
    "LOWER_HOUSING": 13,
}


def build_exploded_state(project_root: Path) -> dict[str, Any]:
    """Build a reversible, transform-only exploded state for all source PARTs.

    This function only emits planning data.  It never opens Blender and never
    edits a mesh or an assembled transform in place.
    """
    root = Path(project_root).expanduser().resolve()
    baseline = validate_task09_baseline(root)
    semantic_parts = _load_list(root / "data/semantic_parts.json", "semantic_parts.json")
    manifest = _load_list(root / "data/parts_manifest.json", "parts_manifest.json")
    initial = _load_mapping(root / "data/assembly_initial.json", "assembly_initial.json")
    _validate_input_coverage(semantic_parts, manifest, initial)

    semantic_by_part = {str(item["part_id"]): item for item in semantic_parts}
    manifest_by_part = {str(item["part_id"]): item for item in manifest}
    initial_objects = initial["objects"]
    center = _geometry_center(manifest)

    records: list[dict[str, Any]] = []
    for part_id in sorted(semantic_by_part, key=_part_number):
        semantic = semantic_by_part[part_id]
        geometry = manifest_by_part[part_id]
        transform = initial_objects[part_id]
        assembled_location = _float_vector(transform.get("location"), 3, "location")
        assembled_rotation = _float_vector(
            transform.get("rotation_euler"), 3, "rotation_euler"
        )
        assembled_scale = _float_vector(transform.get("scale"), 3, "scale")
        vector = _planned_explode_vector(semantic, geometry, center)
        distance = _planned_distance(semantic, geometry, vector)
        semantic_name = str(semantic.get("semantic_name") or "UNKNOWN")
        confidence = _valid_confidence(semantic.get("confidence", "UNKNOWN"))
        manual = bool(semantic.get("requires_manual_confirmation", True))
        # Task 8 intentionally left the charge/data role unresolved.
        if part_id in {"PART_017", "PART_018"}:
            manual = True
        if part_id == "PART_022":
            manual = True
        exploded_location = [
            assembled_location[index] + vector[index] * distance for index in range(3)
        ]
        records.append(
            {
                "part_id": part_id,
                "semantic_name": semantic_name,
                "semantic_category": str(semantic.get("semantic_category") or "UNKNOWN"),
                "assembly_group": _category_to_assembly(
                    str(semantic.get("semantic_category") or "UNKNOWN")
                ),
                "assembled_location": assembled_location,
                "assembled_rotation_euler": assembled_rotation,
                "assembled_scale": assembled_scale,
                "exploded_location": exploded_location,
                "assembled_centroid_mm": _float_vector(
                    geometry.get("centroid", [0.0, 0.0, 0.0]), 3, "centroid"
                ),
                "exploded_centroid_mm": [
                    float(geometry.get("centroid", [0.0, 0.0, 0.0])[index])
                    + vector[index] * distance
                    for index in range(3)
                ],
                "explode_vector": vector,
                "explode_distance_mm": distance,
                "motion_type": _planned_motion_type(semantic_name),
                "explode_order": _planned_explode_order(semantic, semantic_name),
                "confidence": confidence,
                "collision_check": "NOT_CHECKED",
                "requires_manual_confirmation": manual,
                "evidence": sorted(str(item) for item in semantic.get("evidence", [])),
                "reason": _planning_reason(semantic, vector, distance),
                "bbox_dimensions_mm": _float_vector(
                    geometry.get("bbox_dimensions", geometry.get("bbox")),
                    3,
                    "bbox_dimensions",
                ),
                "centroid_mm": _float_vector(
                    geometry.get("centroid", [0.0, 0.0, 0.0]), 3, "centroid"
                ),
                "duplicate_group": semantic.get("duplicate_group"),
            }
        )

    motion_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        motion_groups[_motion_group_key(record)].append(record)

    # Keep functional-group members together, then score the preferred axis,
    # its inverse, and the remaining world axes.  Explicit high-confidence
    # major directions stay stable; uncertain groups use the lowest score.
    for group_key in sorted(motion_groups):
        members = motion_groups[group_key]
        preferred = list(members[0]["explode_vector"])
        candidate_scores: list[dict[str, Any]] = []
        for rank, candidate in enumerate(_candidate_vectors(preferred)):
            candidate_distance = max(
                _planned_distance(
                    semantic_by_part[member["part_id"]],
                    manifest_by_part[member["part_id"]],
                    candidate,
                )
                for member in members
            )
            trial_records = [dict(record) for record in records]
            trial_by_id = {record["part_id"]: record for record in trial_records}
            _apply_group_motion(
                [trial_by_id[member["part_id"]] for member in members],
                candidate,
                candidate_distance,
            )
            candidate_scores.append(
                {
                    "vector": list(candidate),
                    "axis": _axis_label(candidate),
                    "distance_mm": candidate_distance,
                    "new_collision_count": check_swept_aabb_collisions(trial_records)[
                        "collision_count"
                    ],
                    "rank": rank,
                }
            )
        selected = _select_candidate(candidate_scores)
        _apply_group_motion(members, selected["vector"], selected["distance_mm"])
        for member in members:
            member["motion_group"] = group_key
            member["candidate_evaluations"] = candidate_scores
            member["selected_candidate_rank"] = selected["rank"]
            member["preferred_candidate"] = selected["rank"] == 0
            if selected["rank"] != 0:
                member["requires_manual_confirmation"] = True
                member["reason"] += (
                    " Alternate axis selected by sampled swept-AABB score; confirm manually."
                )

    collision_summary = check_swept_aabb_collisions(records)
    collision_parts = {
        part_id
        for item in collision_summary["collisions"]
        for part_id in (item["part_a"], item["part_b"])
    }
    for record in records:
        record["collision_check"] = "WARN" if record["part_id"] in collision_parts else "PASS"

    return {
        "state": "EXPLODED",
        "unit_assumption": "mm",
        "source_baseline": {
            "source_parts": baseline["source_parts"],
            "faces": baseline["faces"],
            "indexed_vertices": baseline["indexed_vertices"],
        },
        "parts": {record["part_id"]: record for record in records},
        "collision_summary": collision_summary,
        "source": "Task 9A deterministic transform planning; source STL unchanged",
    }


def check_swept_aabb_collisions(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Flag new positive-volume AABB overlaps at sampled transform positions.

    Contact at the assembled state is not treated as a collision.  This is a
    deliberately conservative screening pass, not a mesh-level path planner.
    """
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)):
        raise ValueError("collision records must be a sequence of objects")
    normalized = [_normalize_collision_record(record) for record in records]
    part_ids = [record["part_id"] for record in normalized]
    if len(part_ids) != len(set(part_ids)):
        raise ValueError("collision records contain duplicate part_id values")
    # The helper is also used by tests and downstream reviewers with virtual
    # identifiers, so collision ordering must not require numeric PART IDs.
    normalized.sort(key=lambda item: item["part_id"])
    initial_pairs: set[tuple[str, str]] = set()
    collisions_by_pair: dict[tuple[str, str], list[float]] = defaultdict(list)
    for index, left in enumerate(normalized):
        for right in normalized[index + 1 :]:
            pair = (left["part_id"], right["part_id"])
            initial_overlap = False
            left_initial_overlap = False
            for sample_t in _EXPLOSION_SAMPLES:
                left_box = _aabb_at(left, sample_t, "assembled_location", "exploded_location")
                right_box = _aabb_at(right, sample_t, "assembled_location", "exploded_location")
                overlap = _aabb_positive_overlap(left_box, right_box)
                if sample_t == 0.0 and overlap:
                    initial_pairs.add(pair)
                    initial_overlap = True
                    continue
                if not overlap:
                    if initial_overlap:
                        left_initial_overlap = True
                    continue
                if not initial_overlap or left_initial_overlap:
                    collisions_by_pair[pair].append(sample_t)
    collisions = []
    for pair in sorted(collisions_by_pair):
        sample_times = collisions_by_pair[pair]
        left = next(item for item in normalized if item["part_id"] == pair[0])
        right = next(item for item in normalized if item["part_id"] == pair[1])
        collisions.append(
            {
                "part_a": pair[0],
                "part_b": pair[1],
                "group_a": left["assembly_group"],
                "group_b": right["assembly_group"],
                "sample_t": sample_times[0],
                "sample_times": sample_times,
                "severity": "WARNING",
                "reason": "sampled swept AABBs overlap after leaving the assembled state",
            }
        )
    return {
        "method": "sampled_swept_aabb",
        "sampling_limitations": "Discrete samples can miss a short collision interval between sample times.",
        "checked_samples": list(_EXPLOSION_SAMPLES),
        "initial_overlap_pair_count": len(initial_pairs),
        "collision_count": len(collisions),
        "collisions": collisions,
    }


def build_explosion_guides(exploded_state: Mapping[str, Any]) -> dict[str, Any]:
    """Emit one reversible source-to-exploded guide record per PART."""
    parts = exploded_state.get("parts")
    if not isinstance(parts, Mapping):
        raise ValueError("exploded state must contain a parts object")
    guides = []
    for part_id in sorted((str(key) for key in parts), key=_part_number):
        record = parts[part_id]
        guides.append(
            {
                "source": part_id,
                "target": str(record.get("assembly_group") or "UNKNOWN"),
                "source_part": part_id,
                "target_group": str(record.get("assembly_group") or "UNKNOWN"),
                "axis": _axis_label(record["explode_vector"]),
                "vector": list(record["explode_vector"]),
                "start": list(record["assembled_location"]),
                "end": list(record["exploded_location"]),
                "confidence": str(record.get("confidence", "UNKNOWN")),
            }
        )
    return {
        "guide_count": len(guides),
        "guides": guides,
        "source": "exploded_state.json",
    }


def build_future_visual_assets(project_root: Path) -> dict[str, Any]:
    """Carry Task 8 missing visual features into a non-destructive future list."""
    root = Path(project_root).expanduser().resolve()
    validate_task09_baseline(root)
    payload = _load_mapping(
        root / "data/reference_missing_features.json", "reference_missing_features.json"
    )
    features = payload.get("features", [])
    if not isinstance(features, list):
        raise ValueError("reference_missing_features.json must contain features")
    if not all(isinstance(feature, Mapping) for feature in features):
        raise ValueError("reference_missing_features.json features must be objects")
    result = [dict(feature) for feature in features]
    result.sort(key=lambda item: (str(item.get("feature_id", "")), str(item.get("feature", ""))))
    return {
        "feature_count": len(result),
        "features": result,
        "source": "Task 8 reference_missing_features.json; no reconstruction performed",
    }


def build_explosion_review_queue(exploded_state: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return only movement decisions that need human review."""
    parts = exploded_state.get("parts")
    if not isinstance(parts, Mapping):
        raise ValueError("exploded state must contain a parts object")
    rows: list[dict[str, Any]] = []
    for part_id in sorted((str(key) for key in parts), key=_part_number):
        record = parts[part_id]
        confidence = _valid_confidence(record.get("confidence", "UNKNOWN"))
        collision = str(record.get("collision_check", "NOT_CHECKED"))
        manual = bool(record.get("requires_manual_confirmation", True))
        if confidence == "HIGH" and not manual and collision not in {"WARN", "NOT_CHECKED"}:
            continue
        semantic_name = str(record.get("semantic_name") or "UNKNOWN")
        if collision == "WARN":
            question = "Does this proposed path avoid neighbouring geometry, or should the axis/distance change?"
        elif semantic_name == "UNKNOWN":
            question = "What physical component or functional group does this PART belong to?"
        elif part_id in {"PART_017", "PART_018"}:
            question = "Which top interface role is this part: charging port or data port?"
        else:
            question = "Is this semantic assignment and proposed disassembly motion supported by the references?"
        rows.append(
            {
                "part": part_id,
                "semantic_name": semantic_name,
                "explode_direction": list(record["explode_vector"]),
                "explode_distance_mm": record["explode_distance_mm"],
                "explode_order": record["explode_order"],
                "motion_type": record["motion_type"],
                "confidence": confidence,
                "collision_check": collision,
                "review_question": question,
            }
        )
    return rows


def _float_vector(value: Any, length: int, label: str) -> list[float]:
    if isinstance(value, Mapping):
        value = [value.get(axis, 0.0) for axis in ("x", "y", "z")]
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != length:
        raise ValueError(f"{label} must be a {length}-element vector")
    numbers: list[float] = []
    for item in value:
        if isinstance(item, bool):
            raise ValueError(f"{label} values must be finite numbers")
        try:
            number = float(item)
        except (TypeError, ValueError) as error:
            raise ValueError(f"{label} values must be finite numbers") from error
        if not math.isfinite(number):
            raise ValueError(f"{label} values must be finite numbers")
        numbers.append(number)
    return numbers


def _geometry_center(manifest: Sequence[Mapping[str, Any]]) -> list[float]:
    centroids = [_float_vector(item.get("centroid"), 3, "centroid") for item in manifest]
    return [sum(values[index] for values in centroids) / len(centroids) for index in range(3)]


def _motion_group_key(record: Mapping[str, Any]) -> str:
    category = str(record.get("semantic_category") or "UNKNOWN")
    semantic_name = str(record.get("semantic_name") or "UNKNOWN")
    if category == "BATTERY_ASSEMBLY":
        return "BATTERY_ASSEMBLY"
    if category == "SENSOR_ASSEMBLY":
        return "SENSOR_ASSEMBLY"
    if category == "LEVELING_ASSEMBLY":
        return "LEVELING_ASSEMBLY"
    if category == "CONNECTOR":
        return "TOP_INTERFACE"
    duplicate_group = record.get("duplicate_group")
    if duplicate_group and category in {"SMALL_ACCESSORY", "UNKNOWN"}:
        return str(duplicate_group)
    return f"PART::{semantic_name}::{record.get('part_id', '')}"


def _candidate_vectors(preferred: Sequence[float]) -> list[list[float]]:
    preferred_vector = _unit_axis(preferred)
    inverse = [-value for value in preferred_vector]
    axes = [[1.0, 0.0, 0.0], [-1.0, 0.0, 0.0], [0.0, 1.0, 0.0],
            [0.0, -1.0, 0.0], [0.0, 0.0, 1.0], [0.0, 0.0, -1.0]]
    ordered = [preferred_vector, inverse] + axes
    result: list[list[float]] = []
    for vector in ordered:
        if vector not in result:
            result.append(vector)
    return result


def _select_candidate(candidate_scores: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    if not candidate_scores:
        raise ValueError("candidate score list cannot be empty")
    clean_candidates = [
        item for item in candidate_scores if int(item.get("new_collision_count", 1)) == 0
    ]
    # Prefer the first clean candidate in deterministic candidate order. If
    # every candidate intersects, retain the preferred rank 0 for review.
    return clean_candidates[0] if clean_candidates else candidate_scores[0]


def _unit_axis(value: Sequence[float]) -> list[float]:
    if len(value) != 3:
        raise ValueError("explode vector must contain three values")
    numbers = _float_vector(value, 3, "explode_vector")
    dominant = max(range(3), key=lambda index: abs(numbers[index]))
    if abs(numbers[dominant]) <= 1e-12:
        raise ValueError("explode vector cannot be zero")
    result = [0.0, 0.0, 0.0]
    result[dominant] = 1.0 if numbers[dominant] > 0.0 else -1.0
    return result


def _apply_group_motion(
    members: Sequence[dict[str, Any]], vector: Sequence[float], distance: float
) -> None:
    normalized = _unit_axis(vector)
    for member in members:
        member["explode_vector"] = list(normalized)
        member["explode_distance_mm"] = round(float(distance), 6)
        member["exploded_location"] = [
            float(member["assembled_location"][index]) + normalized[index] * float(distance)
            for index in range(3)
        ]
        member["exploded_centroid_mm"] = [
            float(member["assembled_centroid_mm"][index]) + normalized[index] * float(distance)
            for index in range(3)
        ]


def _group_has_high_confidence_explicit_direction(
    members: Sequence[Mapping[str, Any]]
) -> bool:
    return all(
        _valid_confidence(member.get("confidence", "UNKNOWN")) == "HIGH"
        and str(member.get("semantic_name") or "UNKNOWN") in _EXPLICIT_EXPLODE_VECTORS
        for member in members
    )


def _planned_explode_vector(
    semantic: Mapping[str, Any], geometry: Mapping[str, Any], center: Sequence[float]
) -> list[float]:
    semantic_name = str(semantic.get("semantic_name") or "UNKNOWN")
    if semantic_name in _EXPLICIT_EXPLODE_VECTORS:
        return list(_EXPLICIT_EXPLODE_VECTORS[semantic_name])
    category = str(semantic.get("semantic_category") or "UNKNOWN")
    if category == "LEVELING_ASSEMBLY":
        return [0.0, 0.0, -1.0]
    if category == "BATTERY_ASSEMBLY":
        return _dominant_signed_axis(geometry.get("centroid"), center, fallback=[1.0, 0.0, 0.0])
    return _dominant_signed_axis(geometry.get("centroid"), center, fallback=[1.0, 0.0, 0.0])


def _dominant_signed_axis(value: Any, center: Sequence[float], fallback: list[float]) -> list[float]:
    point = _float_vector(value, 3, "centroid")
    delta = [point[index] - float(center[index]) for index in range(3)]
    axis = max(range(3), key=lambda index: (abs(delta[index]), -index))
    if abs(delta[axis]) < 1e-6:
        return list(fallback)
    vector = [0.0, 0.0, 0.0]
    vector[axis] = 1.0 if delta[axis] >= 0.0 else -1.0
    return vector


def _planned_distance(
    semantic: Mapping[str, Any], geometry: Mapping[str, Any], vector: Sequence[float]
) -> float:
    dimensions = _float_vector(
        geometry.get("bbox_dimensions", geometry.get("bbox")), 3, "bbox_dimensions"
    )
    extent = sum(abs(float(vector[index])) * dimensions[index] for index in range(3))
    size_class = str(semantic.get("size_class") or "UNKNOWN")
    semantic_name = str(semantic.get("semantic_name") or "UNKNOWN")
    if size_class in {"SMALL", "TINY", "FRAGMENT"}:
        minimum, maximum, clearance = 20.0, 60.0, 15.0
    elif semantic_name in {"UPPER_HOUSING", "LOWER_HOUSING", "HANDLE"}:
        minimum, maximum, clearance = 80.0, 180.0, 40.0
    elif size_class == "MAJOR":
        minimum, maximum, clearance = 50.0, 160.0, 30.0
    else:
        minimum, maximum, clearance = 40.0, 120.0, 25.0
    return round(max(minimum, min(maximum, extent + clearance)), 6)


def _planned_motion_type(semantic_name: str) -> str:
    if semantic_name.startswith("BATTERY_COMPARTMENT_"):
        return "GROUP_LINEAR"
    if semantic_name.startswith("SENSOR_CORE_FIXTURE_"):
        return "GROUP_LINEAR"
    if semantic_name.startswith("LEVELING_CONE_"):
        return "GROUP_LINEAR"
    return "LINEAR"


def _planned_explode_order(semantic: Mapping[str, Any], semantic_name: str) -> int:
    if semantic_name in _EXPLODE_ORDER:
        return _EXPLODE_ORDER[semantic_name]
    category = str(semantic.get("semantic_category") or "UNKNOWN")
    if category in {"SMALL_ACCESSORY", "CONNECTOR"}:
        return 1 if category == "SMALL_ACCESSORY" else 4
    if category == "BATTERY_ASSEMBLY":
        return 9
    if category == "SENSOR_ASSEMBLY":
        return 10
    if category == "LEVELING_ASSEMBLY":
        return 12
    return 14


def _planning_reason(semantic: Mapping[str, Any], vector: Sequence[float], distance: float) -> str:
    original = str(semantic.get("reason") or "No Task 8 semantic reason was recorded.")
    return f"{original}; Task 9A proposes linear motion along {_axis_label(vector)} for {distance:g} mm."


def _axis_label(vector: Sequence[float]) -> str:
    labels = ("X", "Y", "Z")
    dominant = max(range(3), key=lambda index: abs(float(vector[index])))
    sign = "+" if float(vector[dominant]) >= 0.0 else "-"
    return f"{sign}{labels[dominant]}"


def _normalize_collision_record(record: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(record, Mapping):
        raise ValueError("collision records must contain objects")
    part_id = str(record.get("part_id", ""))
    if not part_id:
        raise ValueError("collision record must contain part_id")
    dimensions = _float_vector(record.get("bbox_dimensions_mm"), 3, "bbox_dimensions_mm")
    assembled = _float_vector(
        record.get("assembled_centroid_mm", record.get("assembled_location")),
        3,
        "assembled_centroid_mm",
    )
    exploded = _float_vector(
        record.get("exploded_centroid_mm", record.get("exploded_location")),
        3,
        "exploded_centroid_mm",
    )
    if any(dimension < 0.0 for dimension in dimensions):
        raise ValueError(f"collision record {part_id} has negative bbox dimensions")
    return {
        "part_id": part_id,
        "bbox_dimensions_mm": dimensions,
        "assembled_location": assembled,
        "exploded_location": exploded,
        "assembly_group": str(record.get("assembly_group") or "UNKNOWN"),
    }


def _aabb_at(record: Mapping[str, Any], sample_t: float, start_key: str, end_key: str) -> tuple[list[float], list[float]]:
    start = record[start_key]
    end = record[end_key]
    center = [
        float(start[index]) + (float(end[index]) - float(start[index])) * sample_t
        for index in range(3)
    ]
    half = [float(value) / 2.0 for value in record["bbox_dimensions_mm"]]
    return (
        [center[index] - half[index] for index in range(3)],
        [center[index] + half[index] for index in range(3)],
    )


def _aabb_positive_overlap(
    left: tuple[Sequence[float], Sequence[float]],
    right: tuple[Sequence[float], Sequence[float]],
) -> bool:
    return all(
        left[0][index] < right[1][index] and right[0][index] < left[1][index]
        for index in range(3)
    )
