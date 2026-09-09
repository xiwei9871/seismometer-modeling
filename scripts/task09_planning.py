"""Deterministic Task 9A disassembly graph and duplicate-group planning."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
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
    if semantic_ids != expected or manifest_ids != expected or initial_ids != expected:
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
