"""Build conservative, evidence-backed Task 8 checkpoint data products."""

from __future__ import annotations

import argparse
import csv
import math
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.generate_part_previews import required_part_ids
from scripts.task08_data import load_json, load_manifest, write_json


REFERENCE_EXT = ["REF_EXT_001", "REF_EXT_002", "REF_EXT_003"]
REFERENCE_PCB = ["REF_PCB_001", "REF_PCB_002", "REF_PCB_003"]
USER_CONFIRMATION_REF = "USER_CONFIRMATION_2026-09-09"
MAJOR_PARTS = [f"PART_{index:03d}" for index in range(1, 19)]


def build_reports(project_root: Path) -> dict[str, Any]:
    """Write all Task 8 checkpoint findings and return the checkpoint summary."""
    root = Path(project_root).expanduser().resolve()
    manifest = load_manifest(root)
    by_part = {record["part_id"]: record for record in manifest}
    duplicate_groups = load_json(root / "data/duplicate_groups.json").get("groups", [])
    duplicate_by_part = {
        part_id: group
        for group in duplicate_groups
        for part_id in group["parts"]
    }
    quality = load_json(root / "data/mesh_quality_report.json")
    fragment_input = load_json(root / "data/suspicious_fragments.json")
    reference_manifest = load_json(root / "data/reference_manifest.json")

    semantic_parts = _semantic_parts(by_part, duplicate_by_part)
    feature_validation = _feature_validation()
    missing_features = _missing_features()
    pcb_validation = _pcb_validation()
    non_watertight = _non_watertight_review(quality, by_part)
    fragment_review = _fragment_review(fragment_input, by_part)
    conflicts = _reference_conflicts()
    assembly = _assembly_semantic(semantic_parts)
    mounting = _mounting_relationships()
    dependencies = _disassembly_dependencies()
    manual_queue = _manual_review_queue(semantic_parts)
    confirmations = _human_review_confirmations()

    write_json(root / "data/semantic_parts.json", semantic_parts)
    write_json(root / "data/feature_validation.json", feature_validation)
    write_json(root / "data/reference_missing_features.json", missing_features)
    write_json(root / "data/pcb_validation.json", pcb_validation)
    write_json(root / "data/non_watertight_semantic_review.json", non_watertight)
    write_json(root / "data/fragment_review.json", fragment_review)
    write_json(root / "data/reference_conflicts.json", conflicts)
    write_json(root / "data/assembly_semantic.json", assembly)
    write_json(root / "data/mounting_relationships.json", mounting)
    write_json(root / "data/disassembly_dependencies.json", dependencies)
    write_json(root / "data/human_review_confirmations.json", confirmations)

    summary = _checkpoint_summary(
        semantic_parts,
        reference_manifest,
        pcb_validation,
        non_watertight,
        fragment_review,
        manual_queue,
    )
    write_json(root / "data/task08_checkpoint.json", summary)
    _write_manual_queue(root / "data/manual_review_queue.csv", manual_queue)
    _write_report(
        root / "output/reports/stage08_semantic_recovery.md",
        summary,
        semantic_parts,
        feature_validation,
        missing_features,
        pcb_validation,
        non_watertight,
        fragment_review,
        assembly,
        mounting,
        dependencies,
        confirmations,
    )
    return summary


def _semantic_parts(
    by_part: Mapping[str, Mapping[str, Any]],
    duplicate_by_part: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Create one record per immutable PART, with only conservative seed mappings."""
    seeds: dict[str, tuple[str, str, str, list[str], str]] = {
        "PART_001": (
            "LOWER_HOUSING",
            "ENCLOSURE",
            "HIGH",
            REFERENCE_EXT[:2] + [USER_CONFIRMATION_REF],
            "user confirms PART_001 is the lower housing; exterior geometry and assembled position agree with the references",
        ),
        "PART_002": (
            "UPPER_HOUSING",
            "ENCLOSURE",
            "HIGH",
            REFERENCE_EXT + [USER_CONFIRMATION_REF],
            "user confirms PART_002 is the upper housing; geometry is positioned at the housing seam",
        ),
        "PART_003": (
            "TRI_AXIS_SENSOR_FIXTURE",
            "SENSOR_ASSEMBLY",
            "HIGH",
            ["REF_EXT_003", USER_CONFIRMATION_REF],
            "user confirms this orthogonal clamp fixture holds the three axis sensor core parts PART_012-PART_014; topology remains unrepaired",
        ),
        "PART_004": (
            "UPPER_HOUSING_TOP_COVER",
            "ENCLOSURE",
            "HIGH",
            REFERENCE_EXT + [USER_CONFIRMATION_REF],
            "user confirms this is the upper housing top cover and that it protects/obscures the PCB-side interior and antenna area",
        ),
        "PART_005": (
            "HANDLE",
            "HANDLE",
            "HIGH",
            REFERENCE_EXT[:2] + [USER_CONFIRMATION_REF],
            "U-shaped geometry and top-of-device position directly match the handle; user additionally confirms it conceals the 4G/Wi-Fi antennas",
        ),
        "PART_006": (
            "PCB_PROTECTIVE_PLATE",
            "ENCLOSURE",
            "HIGH",
            ["REF_EXT_003", USER_CONFIRMATION_REF],
            "user identifies PART_006 as a PCB-protective plate with a role similar to PART_004",
        ),
        "PART_019": (
            "MAIN_PCB",
            "PCB_ASSEMBLY",
            "HIGH",
            REFERENCE_PCB + [USER_CONFIRMATION_REF],
            "thin centered polygonal board candidate shares the PCB layer height and central assembly position; user confirms this is the MAIN_PCB",
        ),
        "PART_007": (
            "PCB_SUPPORT_FRAME",
            "PCB_ASSEMBLY",
            "HIGH",
            REFERENCE_PCB + [USER_CONFIRMATION_REF],
            "large thin perimeter frame is consistent with the PCB references; user confirms it bridges the upper and lower protective parts",
        ),
    }
    for index, part_id in enumerate(("PART_008", "PART_009", "PART_010", "PART_011", "PART_015", "PART_016"), start=1):
        seeds[part_id] = (
            f"BATTERY_COMPARTMENT_{index:02d}",
            "BATTERY_ASSEMBLY",
            "HIGH",
            [USER_CONFIRMATION_REF],
            "user identifies this repeated enclosure component as one of the battery compartments",
        )
    for index, part_id in enumerate(("PART_012", "PART_013", "PART_014"), start=1):
        seeds[part_id] = (
            f"SENSOR_CORE_FIXTURE_{('X', 'Y', 'Z')[index - 1]}",
            "SENSOR_ASSEMBLY",
            "HIGH",
            ["REF_EXT_003", USER_CONFIRMATION_REF],
            "user identifies this orthogonal fixture member as the X/Y/Z-axis element of the three-axis sensor core clamp held by PART_003",
        )
    for index, part_id in enumerate(("PART_017", "PART_018"), start=1):
        seeds[part_id] = (
            f"TOP_INTERFACE_PORT_{index:02d}",
            "CONNECTOR",
            "HIGH",
            REFERENCE_EXT[:2] + [USER_CONFIRMATION_REF],
            "user confirms this is one of the two top interface ports; exact charge-versus-data assignment is intentionally unresolved",
        )
    for index, part_id in enumerate(("PART_020", "PART_021", "PART_022"), start=1):
        confidence = "MEDIUM" if part_id == "PART_022" else "HIGH"
        seeds[part_id] = (
            f"LEVELING_CONE_{index:02d}",
            "LEVELING_ASSEMBLY",
            confidence,
            REFERENCE_EXT[:2] + [USER_CONFIRMATION_REF],
            "user identifies the bottom conical support as a leveling cone; the third matching instance is inferred for PART_022 from geometry and placement",
        )
    records: list[dict[str, Any]] = []
    for part_id in required_part_ids():
        source = by_part[part_id]
        duplicate = duplicate_by_part.get(part_id)
        if part_id in seeds:
            semantic_name, category, confidence, evidence, reason = seeds[part_id]
            manual = confidence != "HIGH"
        else:
            semantic_name = "UNKNOWN"
            category = "UNKNOWN"
            confidence = "UNKNOWN"
            evidence = []
            reason = "no sufficiently specific photographic and geometric evidence at the checkpoint"
            manual = True
        records.append(
            {
                "part_id": part_id,
                "source_component_index": source["source_component_index"],
                "size_class": source.get("size_class"),
                "face_count": source["face_count"],
                "vertex_count": source["vertex_count"],
                "bbox_dimensions_mm": source["bbox_dimensions"],
                "centroid_mm": source["centroid"],
                "watertight": source["watertight"],
                "duplicate_group": duplicate["group_id"] if duplicate else None,
                "semantic_name": semantic_name,
                "semantic_category": category,
                "confidence": confidence,
                "evidence": evidence,
                "reason": reason,
                "requires_manual_confirmation": manual,
                "preview_path": f"output/part_previews/{part_id}.png",
                "assembled_highlight_path": f"output/part_highlights/{part_id}_iso.png",
                "source": "original_stl",
                "functional_notes": "",
            }
        )
        _add_functional_metadata(records[-1])
    return records


def _add_functional_metadata(record: dict[str, Any]) -> None:
    part_id = record["part_id"]
    if part_id == "PART_005":
        record["functional_notes"] = "HANDLE also serves as a 4G/Wi-Fi antenna shroud"
    if part_id in {"PART_017", "PART_018"}:
        record["functional_role"] = "CHARGE_PORT_OR_DATA_PORT"
        record["functional_role_confidence"] = "UNKNOWN"
        record["functional_notes"] = "User confirms one port is charging and one is data; assignment to this PART remains unresolved."
    if part_id in {"PART_004", "PART_006"}:
        record["functional_role"] = "PCB_PROTECTIVE_COVER_OR_PLATE"
        record["functional_role_confidence"] = "HIGH"
    if record["size_class"] in {"SMALL", "TINY"}:
        record["review_priority"] = "LOW"
        if record["semantic_name"] == "UNKNOWN":
            record["semantic_name"] = "SMALL_ACCESSORY"
            record["semantic_category"] = "SMALL_ACCESSORY"
            record["confidence"] = "LOW"
            record["evidence"] = [USER_CONFIRMATION_REF]
            record["reason"] = "user classifies the small/tiny hardware as low-priority accessories such as screws or similar fittings; exact type is intentionally not guessed"


def _human_review_confirmations() -> dict[str, Any]:
    return {
        "reviewer": "user",
        "review_date": "2026-09-09",
        "confirmation_count": 23,
        "source": "user-provided semantic review in conversation",
        "confirmed_mappings": {
            "PART_001": "LOWER_HOUSING",
            "PART_002": "UPPER_HOUSING",
            "PART_003": "TRI_AXIS_SENSOR_FIXTURE",
            "PART_004": "UPPER_HOUSING_TOP_COVER",
            "PART_005": "HANDLE_WITH_4G_WIFI_ANTENNA_SHROUD_FUNCTION",
            "PART_006": "PCB_PROTECTIVE_PLATE",
            "PART_007": "PCB_SUPPORT_FRAME_BRIDGING_PART_004_AND_PART_006",
            "PART_008_PART_011": "BATTERY_COMPARTMENTS",
            "PART_012_PART_014": "SENSOR_CORE_FIXTURE_MEMBERS",
            "PART_015_PART_016": "BATTERY_COMPARTMENTS",
            "PART_017_PART_018": "TOP_INTERFACE_PORTS_CHARGE_OR_DATA",
            "PART_019": "MAIN_PCB",
            "PART_020_PART_022": "LEVELING_CONES",
        },
        "notes": "The user confirms one of PART_017/PART_018 is a charge port and the other a data port, but does not assign those roles to a specific PART. Small parts are intentionally kept at low-priority accessory level.",
    }


def _feature_validation() -> dict[str, Any]:
    def item(
        feature_id: str,
        name: str,
        present: bool | None,
        candidates: list[str],
        confidence: str,
        evidence: list[str],
        notes: str,
    ) -> dict[str, Any]:
        return {
            "feature_id": feature_id,
            "semantic_name": name,
            "present_in_reference": True,
            "present_in_stl": present,
            "candidate_parts": candidates,
            "confidence": confidence,
            "evidence": evidence,
            "notes": notes,
        }

    features = [
        item("F_EXT_001", "UPPER_HOUSING", True, ["PART_002", "PART_004"], "MEDIUM", REFERENCE_EXT, "The upper housing is represented by the shell and its top cover components."),
        item("F_EXT_002", "LOWER_HOUSING", True, ["PART_001", "PART_003"], "MEDIUM", REFERENCE_EXT, "PART_001 is the outer lower shell candidate; PART_003 is the internal ribbed support candidate."),
        item("F_EXT_003", "HANDLE", True, ["PART_005"], "HIGH", REFERENCE_EXT[:2], "Direct shape and location correspondence."),
        item("F_EXT_004", "HANDLE_FASTENERS", None, [], "UNKNOWN", REFERENCE_EXT[:2], "Fastener geometry is visible in the photographs but is not uniquely isolated at this checkpoint."),
        item("F_EXT_005", "CARRYING_ROPE", False, [], "HIGH", REFERENCE_EXT[:2] + [USER_CONFIRMATION_REF], "The carrying rope is a flexible exterior feature and is not represented by PART_017 or PART_018; those are the two top interface ports."),
        item("F_EXT_006", "BUBBLE_LEVEL", None, [], "UNKNOWN", REFERENCE_EXT[:2], "Visible in the references; no isolated STL candidate is sufficiently distinctive yet."),
        item("F_EXT_007", "TOP_CONNECTOR_01", True, ["PART_017"], "HIGH", REFERENCE_EXT[:2] + [USER_CONFIRMATION_REF], "User confirms PART_017 is one of the two top interface ports; charging-versus-data role is intentionally unresolved."),
        item("F_EXT_008", "TOP_CONNECTOR_02", True, ["PART_018"], "HIGH", REFERENCE_EXT[:2] + [USER_CONFIRMATION_REF], "User confirms PART_018 is one of the two top interface ports; charging-versus-data role is intentionally unresolved."),
        item("F_EXT_009", "EXTERNAL_HOUSING_FASTENERS", None, [], "UNKNOWN", REFERENCE_EXT, "Fastener positions are visible, but no reliable one-to-one mapping is established."),
        item("F_EXT_010", "LEVELING_FEET", True, ["PART_020", "PART_021", "PART_022"], "HIGH", REFERENCE_EXT[:2] + [USER_CONFIRMATION_REF], "User confirms PART_020 and PART_021 are leveling cones and the third identical geometry is PART_022."),
        item("F_PCB_001", "MAIN_PCB", True, ["PART_019"], "HIGH", REFERENCE_PCB + [USER_CONFIRMATION_REF], "User identifies PART_019 as the MAIN_PCB; PCB geometry details remain separately reported in pcb_validation.json."),
        item("F_PCB_002", "PCB_SUPPORT_FRAME", True, ["PART_007"], "HIGH", REFERENCE_PCB + [USER_CONFIRMATION_REF], "User identifies PART_007 as the frame bridging the protective plates around the PCB."),
        item("F_EXT_011", "MAIN_LABEL", False, [], "HIGH", REFERENCE_EXT[:2], "The printed label is visual/decal content and is not present as recoverable STL geometry."),
        item("F_EXT_012", "NUMBER_LABEL", False, [], "HIGH", REFERENCE_EXT[:2], "The orange number marking is visual/decal content and is not present as recoverable STL geometry."),
    ]
    return {"feature_count": len(features), "features": features}


def _missing_features() -> dict[str, Any]:
    features = [
        {"feature_id": "MISSING_EXT_001", "feature": "CARRYING_ROPE", "type": "FLEXIBLE_COMPONENT", "references": REFERENCE_EXT[:2], "recommended_action": "rebuild_with_curve", "notes": "Only partial curved candidates are present; do not alter source STL."},
        {"feature_id": "MISSING_EXT_002", "feature": "MAIN_LABEL", "type": "DECAL", "references": REFERENCE_EXT[:2], "recommended_action": "create_decal", "notes": "QR/text label is visible in photos but not represented in source geometry."},
        {"feature_id": "MISSING_EXT_003", "feature": "NUMBER_LABEL", "type": "DECAL", "references": REFERENCE_EXT[:2], "recommended_action": "create_decal", "notes": "Printed number is visible in photos but not represented in source geometry."},
        {"feature_id": "MISSING_EXT_004", "feature": "EXTERIOR_COLOR", "type": "MATERIAL", "references": REFERENCE_EXT, "recommended_action": "rebuild_in_blender", "notes": "STL has no reliable material/color metadata; inspection renders intentionally remain neutral."},
        {"feature_id": "MISSING_PCB_001", "feature": "PCB_SILKSCREEN_AND_TRACE_TEXTURE", "type": "TEXTURE", "references": REFERENCE_PCB, "recommended_action": "create_decal", "notes": "PCB reference detail is not treated as source STL geometry."},
    ]
    return {"feature_count": len(features), "features": features}


def _pcb_validation() -> dict[str, Any]:
    return {
        "candidate_parts": ["PART_019"],
        "confidence": "MEDIUM",
        "evidence": REFERENCE_PCB,
        "present_in_stl": True,
        "precision_dimensions_from_photos": False,
        "board_outline_match": "PARTIAL",
        "mounting_holes_match": "LOW",
        "orientation_confidence": "LOW",
        "major_component_coverage": "PARTIAL",
        "major_component_candidates": [],
        "missing_major_components": ["large rectangular modules", "large connectors", "cylindrical components"],
        "support_frame_candidates": ["PART_007"],
        "spacer_candidates": [],
        "fastener_candidates": [],
        "notes": "PART_019 is the current board candidate and PART_007 the frame candidate. PART_004 is treated as an upper housing cover. The board candidate is not approved as final semantic truth until manual comparison against the PCB contact/reference views.",
    }


def _non_watertight_review(
    quality: Mapping[str, Any], by_part: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    quality_by_part = {item["part_id"]: item for item in quality.get("components", [])}
    components = []
    for part_id in ("PART_003", "PART_005"):
        item = quality_by_part.get(part_id, {})
        components.append(
            {
                "part_id": part_id,
                "semantic_candidate": next(
                    (name for pid, name in (("PART_003", "TRI_AXIS_SENSOR_FIXTURE"), ("PART_005", "HANDLE")) if pid == part_id),
                    "UNKNOWN",
                ),
                "bbox_dimensions_mm": by_part[part_id]["bbox_dimensions"],
                "face_count": by_part[part_id]["face_count"],
                "watertight": by_part[part_id]["watertight"],
                "boundary_edge_count": item.get("boundary_edge_count", 0),
                "non_manifold_edge_count": item.get("non_manifold_edge_count", 0),
                "duplicate_face_count": item.get("duplicate_face_count", 0),
                "repair_performed": False,
                "requires_manual_confirmation": True,
                "confidence": "MEDIUM" if part_id == "PART_003" else "HIGH",
                "evidence": ["REF_EXT_003"] if part_id == "PART_003" else REFERENCE_EXT[:2],
                "notes": "Topology is recorded only; no repair, cleanup, merge, or normal-changing operation was performed.",
            }
        )
    return {"repair_performed": False, "components": components}


def _fragment_review(
    fragment_input: Sequence[Mapping[str, Any]],
    by_part: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    fragment = dict(fragment_input[0]) if fragment_input else {
        "part_id": "PART_082",
        "face_count": by_part["PART_082"]["face_count"],
        "bbox": by_part["PART_082"]["bbox"],
        "centroid": by_part["PART_082"]["centroid"],
    }
    part_id = str(fragment["part_id"])
    centroid = [float(value) for value in fragment["centroid"]]
    distances = []
    for candidate_id, record in by_part.items():
        if candidate_id == part_id:
            continue
        other = record["centroid"]
        distance = math.sqrt(sum((centroid[i] - other[i]) ** 2 for i in range(3)))
        distances.append((distance, candidate_id))
    neighbours = [candidate for _, candidate in sorted(distances)[:5]]
    return {
        "part_id": part_id,
        "classification": "UNKNOWN",
        "confidence": "UNKNOWN",
        "face_count": fragment["face_count"],
        "bbox": fragment["bbox"],
        "centroid": fragment["centroid"],
        "nearest_neighbour_parts": neighbours,
        "isolated_render": f"output/part_previews/{part_id}.png",
        "assembled_highlight_render": f"output/part_highlights/{part_id}_iso.png",
        "requires_manual_confirmation": True,
        "notes": "Marked only; not deleted or merged. Determine real component versus export artifact after neighbour inspection.",
    }


def _reference_conflicts() -> dict[str, Any]:
    return {
        "conflict_count": 0,
        "conflicts": [],
        "notes": "No confirmed geometry conflict is asserted at the checkpoint. Visual omissions and revision differences remain possible and must not be treated as STL errors.",
    }


def _assembly_semantic(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[str]] = {}
    for record in records:
        category = str(record["semantic_category"])
        assembly_id = {
            "ENCLOSURE": "ENCLOSURE",
            "HANDLE": "HANDLE_ASSEMBLY",
            "PCB_ASSEMBLY": "PCB_ASSEMBLY",
            "SENSOR_ASSEMBLY": "SENSOR_ASSEMBLY",
            "BATTERY_ASSEMBLY": "BATTERY_ASSEMBLY",
            "CONNECTOR": "TOP_INTERFACE",
            "LEVELING_ASSEMBLY": "LEVELING_ASSEMBLY",
            "SMALL_ACCESSORY": "FASTENERS_AND_SMALL_ACCESSORIES",
        }.get(category, "UNKNOWN")
        groups.setdefault(assembly_id, []).append(record["part_id"])
    return {
        "root": "DEVICE",
        "assemblies": [
            {
                "assembly_id": assembly_id,
                "members": members,
                "confidence": "MEDIUM" if assembly_id != "UNKNOWN" else "UNKNOWN",
                "requires_manual_confirmation": assembly_id == "UNKNOWN",
            }
            for assembly_id, members in groups.items()
        ],
        "notes": "First-pass grouping is semantic metadata only; it does not move, join, or hide source PART objects.",
    }


def _mounting_relationships() -> dict[str, Any]:
    relationships = [
        {"parent": "LOWER_HOUSING", "child": "UPPER_HOUSING", "relationship": "covers", "confidence": "MEDIUM", "evidence": REFERENCE_EXT, "requires_manual_confirmation": True, "reason": "Exterior seam and exploded reference support a two-shell enclosure relationship."},
        {"parent": "UPPER_HOUSING", "child": "HANDLE", "relationship": "attached_to", "confidence": "HIGH", "evidence": REFERENCE_EXT[:2], "requires_manual_confirmation": False, "reason": "Handle feet visibly attach to the upper housing in both exterior references."},
        {"parent": "PCB_SUPPORT_FRAME", "child": "MAIN_PCB", "relationship": "supports", "confidence": "HIGH", "evidence": REFERENCE_PCB + [USER_CONFIRMATION_REF], "requires_manual_confirmation": False, "reason": "User confirms PART_007 is the support frame and PART_019 is the MAIN_PCB; PCB references show the board seated in the frame."},
        {"parent": "UPPER_HOUSING_TOP_COVER", "child": "PCB_SUPPORT_FRAME", "relationship": "connected_to", "confidence": "HIGH", "evidence": [USER_CONFIRMATION_REF], "requires_manual_confirmation": False, "reason": "User confirms PART_007 bridges the upper protective part PART_004 and the lower PCB-protective part PART_006."},
        {"parent": "PCB_SUPPORT_FRAME", "child": "PCB_PROTECTIVE_PLATE", "relationship": "connected_to", "confidence": "HIGH", "evidence": [USER_CONFIRMATION_REF], "requires_manual_confirmation": False, "reason": "User confirms PART_007 bridges the two protective parts PART_004 and PART_006."},
        {"parent": "PCB_PROTECTIVE_PLATE", "child": "MAIN_PCB", "relationship": "protects", "confidence": "MEDIUM", "evidence": ["REF_EXT_003", USER_CONFIRMATION_REF], "requires_manual_confirmation": True, "reason": "PART_006 is identified as a PCB-protective plate; exact clearance and retention details require manual internal inspection."},
        {"parent": "TRI_AXIS_SENSOR_FIXTURE", "child": "SENSOR_CORE_FIXTURE_X", "relationship": "contains", "confidence": "HIGH", "evidence": ["REF_EXT_003", USER_CONFIRMATION_REF], "requires_manual_confirmation": False, "reason": "User confirms PART_003 is the orthogonal three-axis fixture holding the PART_012-PART_014 sensor-core members."},
        {"parent": "TRI_AXIS_SENSOR_FIXTURE", "child": "SENSOR_CORE_FIXTURE_Y", "relationship": "contains", "confidence": "HIGH", "evidence": ["REF_EXT_003", USER_CONFIRMATION_REF], "requires_manual_confirmation": False, "reason": "User confirms PART_003 is the orthogonal three-axis fixture holding the PART_012-PART_014 sensor-core members."},
        {"parent": "TRI_AXIS_SENSOR_FIXTURE", "child": "SENSOR_CORE_FIXTURE_Z", "relationship": "contains", "confidence": "HIGH", "evidence": ["REF_EXT_003", USER_CONFIRMATION_REF], "requires_manual_confirmation": False, "reason": "User confirms PART_003 is the orthogonal three-axis fixture holding the PART_012-PART_014 sensor-core members."},
        {"parent": "LOWER_HOUSING", "child": "MAIN_PCB", "relationship": "inside", "confidence": "LOW", "evidence": ["REF_EXT_003"], "requires_manual_confirmation": True, "reason": "Exploded reference places the board assembly within the enclosure, but the STL candidate mapping is provisional."},
        {"parent": "LOWER_HOUSING", "child": "LEVELING_ASSEMBLY", "relationship": "supported_by", "confidence": "HIGH", "evidence": REFERENCE_EXT[:2] + [USER_CONFIRMATION_REF], "requires_manual_confirmation": False, "reason": "User confirms PART_020-PART_021 are leveling cones and PART_022 is the third matching instance supporting the lower housing."},
    ]
    return {"relationship_count": len(relationships), "relationships": relationships}


def _disassembly_dependencies() -> dict[str, Any]:
    dependencies = [
        {"remove_first": "EXTERNAL_HOUSING_FASTENERS", "before": "UPPER_HOUSING", "confidence": "LOW", "evidence": REFERENCE_EXT, "requires_manual_confirmation": True, "reason": "Visible fasteners appear to retain the upper shell, but exact PART mapping is unresolved."},
        {"remove_first": "UPPER_HOUSING", "before": "MAIN_PCB", "confidence": "LOW", "evidence": ["REF_EXT_003"], "requires_manual_confirmation": True, "reason": "The exploded reference places the upper enclosure above the board assembly; actual disassembly order needs manual confirmation."},
        {"remove_first": "PCB_FASTENERS", "before": "MAIN_PCB", "confidence": "UNKNOWN", "evidence": REFERENCE_PCB, "requires_manual_confirmation": True, "reason": "Fastener-to-board relations are not uniquely recoverable from the current STL/photos."},
        {"remove_first": "TRI_AXIS_SENSOR_FIXTURE", "before": "SENSOR_CORE_FIXTURE_X", "confidence": "MEDIUM", "evidence": ["REF_EXT_003", USER_CONFIRMATION_REF], "requires_manual_confirmation": True, "reason": "The user confirms the orthogonal fixture holds the sensor-core members; exact release order is not visible in the references."},
        {"remove_first": "TRI_AXIS_SENSOR_FIXTURE", "before": "SENSOR_CORE_FIXTURE_Y", "confidence": "MEDIUM", "evidence": ["REF_EXT_003", USER_CONFIRMATION_REF], "requires_manual_confirmation": True, "reason": "The user confirms the orthogonal fixture holds the sensor-core members; exact release order is not visible in the references."},
        {"remove_first": "TRI_AXIS_SENSOR_FIXTURE", "before": "SENSOR_CORE_FIXTURE_Z", "confidence": "MEDIUM", "evidence": ["REF_EXT_003", USER_CONFIRMATION_REF], "requires_manual_confirmation": True, "reason": "The user confirms the orthogonal fixture holds the sensor-core members; exact release order is not visible in the references."},
    ]
    return {"dependency_count": len(dependencies), "dependencies": dependencies, "animation_created": False}


def _manual_review_queue(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for record in records:
        if record["confidence"] == "HIGH":
            continue
        rows.append(
            {
                "part_id": record["part_id"],
                "semantic_candidate": record["semantic_name"],
                "confidence": record["confidence"],
                "reason": record["reason"],
                "reference": ", ".join(record["evidence"]) or "NONE",
                "preview_path": record["preview_path"],
                "question": f"Confirm semantic candidate for {record['part_id']} from the preview and assembled highlight.",
            }
        )
    return rows


def _checkpoint_summary(
    records: Sequence[Mapping[str, Any]],
    reference_manifest: Mapping[str, Any],
    pcb: Mapping[str, Any],
    non_watertight: Mapping[str, Any],
    fragment: Mapping[str, Any],
    manual_queue: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    confidence_counts = {level: sum(record["confidence"] == level for record in records) for level in ("HIGH", "MEDIUM", "LOW", "UNKNOWN")}
    class_counts = {name: sum(record.get("size_class") == name for record in records) for name in ("MAJOR", "MEDIUM", "SMALL", "TINY", "FRAGMENT")}
    return {
        "status": "CHECKPOINT",
        "task": "Task 8 photographic reference validation and semantic assembly recovery",
        "reference_count": reference_manifest.get("reference_count", 0),
        "reference_categories": {category: sum(item.get("category") == category for item in reference_manifest.get("references", [])) for category in ("EXTERIOR", "PCB", "INTERNAL", "DETAIL", "UNKNOWN")},
        "source_part_count": len(records),
        "major_part_count": sum(record.get("size_class") == "MAJOR" for record in records),
        "size_class_counts": class_counts,
        "semantic_confidence_counts": confidence_counts,
        "non_watertight_parts": [item["part_id"] for item in non_watertight["components"]],
        "fragment_part": fragment["part_id"],
        "pcb_candidate_parts": pcb["candidate_parts"],
        "manual_review_count": len(manual_queue),
        "animation_created": False,
        "source_geometry_modified": False,
        "stage01_geometry_baseline": {"source_parts": 82, "faces": 444296, "indexed_vertices": 221902},
    }


def _write_manual_queue(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["part_id", "semantic_candidate", "confidence", "reason", "reference", "preview_path", "question"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _write_report(
    path: Path,
    summary: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
    features: Mapping[str, Any],
    missing: Mapping[str, Any],
    pcb: Mapping[str, Any],
    non_watertight: Mapping[str, Any],
    fragment: Mapping[str, Any],
    assembly: Mapping[str, Any],
    mounting: Mapping[str, Any],
    dependencies: Mapping[str, Any],
    confirmations: Mapping[str, Any],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    counts = summary["semantic_confidence_counts"]
    major = [record for record in records if record.get("size_class") == "MAJOR"]
    lines = [
        "# Task 8 Semantic Recovery Checkpoint",
        "",
        "> Checkpoint only: no animation, material authoring, geometry repair, merge, or CAD reconstruction was performed.",
        "",
        "## Reference dataset",
        "",
        f"- References: {summary['reference_count']} ({summary['reference_categories'].get('EXTERIOR', 0)} exterior, {summary['reference_categories'].get('PCB', 0)} PCB)",
        f"- Source PARTs: {summary['source_part_count']}; MAJOR: {summary['major_part_count']}",
        "",
        "## Semantic recovery",
        "",
        f"- HIGH: {counts['HIGH']}; MEDIUM: {counts['MEDIUM']}; LOW: {counts['LOW']}; UNKNOWN: {counts['UNKNOWN']}",
        "",
        "### MAJOR PART checkpoint mapping",
        "",
        "| PART | Candidate | Confidence | Evidence |",
        "|---|---|---|---|",
    ]
    for record in major:
        lines.append(f"| {record['part_id']} | {record['semantic_name']} | {record['confidence']} | {', '.join(record['evidence']) or 'NONE'} |")
    lines.extend([
        "",
        "## PCB validation",
        "",
        f"- Candidate: {', '.join(pcb['candidate_parts'])}; confidence: {pcb['confidence']}",
        f"- Board outline: {pcb['board_outline_match']}; mounting holes: {pcb['mounting_holes_match']}; orientation: {pcb['orientation_confidence']}",
        f"- Support frame candidate: {', '.join(pcb['support_frame_candidates']) or 'NONE'}",
        f"- Missing/uncertain major coverage: {', '.join(pcb['missing_major_components'])}",
        "",
        "## Non-watertight review",
        "",
        f"- Components: {', '.join(item['part_id'] for item in non_watertight['components'])}; repair performed: {non_watertight['repair_performed']}",
        "",
        "## Missing reference features",
        "",
    ])
    for item in missing["features"]:
        lines.append(f"- {item['feature']} ({item['type']}): {item['recommended_action']}")
    lines.extend([
        "",
        "## Assembly hierarchy",
        "",
        "```text",
        "DEVICE",
    ])
    for group in assembly["assemblies"]:
        lines.append(f"├── {group['assembly_id']} ({len(group['members'])} PARTs)")
    lines.extend([
        "```",
        "",
        f"Mounting relationships: {mounting['relationship_count']} ({sum(item['confidence'] == 'HIGH' for item in mounting['relationships'])} HIGH, {sum(item['confidence'] == 'MEDIUM' for item in mounting['relationships'])} MEDIUM, {sum(item['confidence'] == 'LOW' for item in mounting['relationships'])} LOW).",
        f"Disassembly dependencies: {dependencies['dependency_count']}; animation created: {dependencies['animation_created']}.",
        f"Human confirmations: {confirmations['confirmation_count']} mappings recorded from {confirmations['reviewer']} review on {confirmations['review_date']}.",
        "",
        "## Fragment review",
        "",
        f"- {fragment['part_id']}: {fragment['classification']}; nearest neighbours: {', '.join(fragment['nearest_neighbour_parts'])}",
        "",
        "## Source safety",
        "",
        "- Source geometry modified: false",
        "- All uncertainty is retained in JSON/CSV with evidence and manual-review flags.",
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    result = build_reports(args.project_root)
    print(f"Built Task 8 checkpoint reports: {result['source_part_count']} PARTs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
