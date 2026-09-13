"""Pure data contracts for the Task 10-R-PCB-V1 presentation PCB layer."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping, Sequence


BASELINE = {"source_part_count": 82, "faces": 444296, "indexed_vertices": 221902}
SOURCE_LAYOUT = "stage_09C_refined_explosion/config/refined_layout.json"
SOURCE_SCENE = "stage_09C_refined_explosion/scene/exploded_animation_preview.blend"
SOURCE_SCENE_SHA256 = "a3b5359861877e247ad1b035b00cace3e29eea2789ac227e6eeddfaaba1a7766"
EXPECTED_PART_IDS = tuple(f"PART_{index:03d}" for index in range(1, 83))
STORY_PART_IDS = tuple(f"PART_{index:03d}" for index in range(1, 23))
HIDDEN_PART_IDS = tuple(f"PART_{index:03d}" for index in range(23, 83))

ROOT_DIR = "stage_10R_pcb_presentation"
SCENE_OUTPUT = f"{ROOT_DIR}/scene/pcb_presentation_assembly.blend"
RENDER_ROOT = f"{ROOT_DIR}/renders"
ASSET_TEXTURE = f"{ROOT_DIR}/assets/pcb_surface_detail.png"
MANIFEST_PATH = f"{ROOT_DIR}/config/pcb_presentation_manifest.json"
MATERIALS_PATH = f"{ROOT_DIR}/config/pcb_presentation_materials.json"
CAMERAS_PATH = f"{ROOT_DIR}/config/pcb_presentation_cameras.json"
VALIDATION_PATH = f"{ROOT_DIR}/config/pcb_presentation_validation.json"
APPROVAL_PATH = f"{ROOT_DIR}/config/human_approval.json"
REQUIRED_RENDERS = (
    "pcb_presentation_clean.png",
    "pcb_presentation_context.png",
    "pcb_presentation_top.png",
)
COMPARISON_RENDER = "pcb_presentation_reference_comparison.png"
RENDER_CAMERAS = {
    "pcb_presentation_clean.png": "CAM_PCB_CLEAN",
    "pcb_presentation_context.png": "CAM_PCB_CONTEXT",
    "pcb_presentation_top.png": "CAM_PCB_TOP",
}

# Board-local keep-out derived from the real PART_019 outline in the frozen
# Stage 9C scene: an octagon with |x| <= 51, |y| <= 51 and |x|+|y| <= 70.05.
# The chamfered diagonal edges carry a +/-0.5 mm serration, so placements use
# a larger safety margin than the raw polygon.
BOARD_HALF_EXTENT_MM = 51.0
BOARD_DIAGONAL_LIMIT_MM = 70.05
BOARD_EDGE_MARGIN_MM = 8.0
BOARD_THICKNESS_MM = 1.6

ZONE_OFFSET_X_MM = 175.0


def build_component_plan() -> list[dict[str, Any]]:
    """Deterministic presentation components on the PART_019 top surface.

    Positions and sizes are board-local millimetres. Layout follows
    REF_PCB_002 (primary) with height cues from REF_PCB_001/003.
    """

    def box(cid: str, cx: float, cy: float, w: float, d: float, h: float, role: str, refs: str) -> dict[str, Any]:
        return {
            "component_id": f"PCB_COMP_{cid}",
            "shape": "bevel_box",
            "center_xy_mm": [cx, cy],
            "size_xy_mm": [w, d],
            "height_mm": h,
            "bevel_mm": 0.6,
            "material_role": role,
            "visual_role": _role_for_material(role),
            "reference_source": refs,
            "source": "photographic_presentation_reconstruction",
        }

    def cap(cid: str, cx: float, cy: float, radius: float, h: float, refs: str) -> dict[str, Any]:
        return {
            "component_id": f"PCB_COMP_{cid}",
            "shape": "cylinder",
            "center_xy_mm": [cx, cy],
            "radius_mm": radius,
            "height_mm": h,
            "bevel_mm": 0.4,
            "material_role": "cap",
            "visual_role": "capacitor",
            "reference_source": refs,
            "source": "photographic_presentation_reconstruction",
        }

    primary = "REF_PCB_002"
    detail = "REF_PCB_001+REF_PCB_003"
    return [
        box("CONN_MAIN", 0.0, -35.0, 44.0, 8.0, 7.0, "connector", primary),
        box("CONN_TOP", -4.0, 33.0, 30.0, 7.0, 5.0, "connector", primary),
        box("SHIELD_MAIN", 13.0, -3.0, 30.0, 30.0, 9.0, "shield", primary),
        box("SHIELD_LEFT", -25.0, 6.0, 17.0, 14.0, 7.0, "shield", primary),
        box("MODULE_RT", 23.0, 23.0, 18.0, 13.0, 7.0, "ic", primary),
        box("MODULE_LB", -26.0, -22.0, 16.0, 10.0, 6.0, "ic", primary),
        cap("CAP_L1", -39.0, -6.0, 3.8, 11.0, detail),
        cap("CAP_L2", -39.0, 14.0, 3.8, 11.0, detail),
        cap("CAP_R1", 38.0, -8.0, 3.8, 11.0, detail),
        cap("CAP_R2", 38.0, 8.0, 3.8, 11.0, detail),
        box("IC_B1", -12.0, -23.5, 9.0, 6.0, 2.5, "ic", primary),
        box("IC_B2", -1.0, -23.5, 9.0, 6.0, 2.5, "ic", primary),
        box("IC_B3", 10.0, -23.5, 9.0, 6.0, 2.5, "ic", primary),
        box("IC_T1", -8.0, 16.0, 8.0, 6.0, 2.5, "ic", detail),
        box("IC_T2", 2.0, 22.0, 8.0, 6.0, 2.5, "ic", detail),
    ]


def _role_for_material(material_role: str) -> str:
    return {
        "connector": "connector",
        "shield": "shield",
        "ic": "ic",
        "cap": "capacitor",
    }[material_role]


def component_footprint_corners(component: Mapping[str, Any]) -> list[tuple[float, float]]:
    cx, cy = (float(v) for v in component["center_xy_mm"])
    if component["shape"] == "cylinder":
        radius = float(component["radius_mm"])
        half = radius
    else:
        half_w = float(component["size_xy_mm"][0]) / 2.0
        half_d = float(component["size_xy_mm"][1]) / 2.0
        half = (half_w, half_d)
    if isinstance(half, tuple):
        hw, hd = half
    else:
        hw = hd = float(half)
    return [
        (cx - hw, cy - hd),
        (cx + hw, cy - hd),
        (cx + hw, cy + hd),
        (cx - hw, cy + hd),
    ]


def component_footprint_rect(component: Mapping[str, Any]) -> dict[str, float]:
    corners = component_footprint_corners(component)
    return {
        "x_min": min(c[0] for c in corners),
        "x_max": max(c[0] for c in corners),
        "y_min": min(c[1] for c in corners),
        "y_max": max(c[1] for c in corners),
    }


def rects_intersect(a: Mapping[str, float], b: Mapping[str, float], epsilon: float = 1e-6) -> bool:
    return (
        a["x_min"] < b["x_max"] - epsilon
        and a["x_max"] > b["x_min"] + epsilon
        and a["y_min"] < b["y_max"] - epsilon
        and a["y_max"] > b["y_min"] + epsilon
    )


def build_part_reclassification() -> dict[str, Any]:
    return {
        "PART_006": {
            "semantic_name": "PCB_PROTECTIVE_PLATE",
            "functional_importance": "MEDIUM",
            "presentation_priority": "SECONDARY",
            "independent_focus": False,
            "follow_parent": "PCB_ASSEMBLY",
            "presentation_weight": 0.15,
        },
        "PART_007": {
            "semantic_name": "PCB_CONNECTING_FRAME",
            "functional_importance": "LOW",
            "presentation_priority": "SUPPORT",
            "independent_focus": False,
            "follow_parent": "PCB_ASSEMBLY",
            "presentation_weight": 0.10,
        },
        "PART_019": {
            "semantic_name": "MAIN_PCB",
            "functional_importance": "HIGH",
            "presentation_priority": "HERO",
            "independent_focus": True,
            "follow_parent": None,
            "presentation_weight": 0.75,
        },
    }


def build_presentation_hierarchy() -> dict[str, Any]:
    return {
        "MAIN_PCB_PRESENTATION": {
            "tier": "HERO",
            "presentation_weight": 0.75,
            "members": ["PART_019", *[c["component_id"] for c in build_component_plan()]],
        },
        "PART_006": {"tier": "SECONDARY", "presentation_weight": 0.15},
        "PART_007": {"tier": "SUPPORT", "presentation_weight": 0.10},
    }


def build_view_visibility_policy() -> dict[str, Any]:
    return {
        "clean": {
            "visible_focus": ["PART_019", *[c["component_id"] for c in build_component_plan()]],
            "hidden": ["PART_006", "PART_007"],
            "context_visible": False,
        },
        "top": {
            "visible_focus": ["PART_019", *[c["component_id"] for c in build_component_plan()]],
            "hidden": ["PART_006", "PART_007"],
            "context_visible": False,
        },
        "context": {
            "visible_focus": ["PART_019", *[c["component_id"] for c in build_component_plan()]],
            "secondary_visible": True,
            "support_visible": True,
            "context_visible": True,
            "hidden": [],
        },
    }


def build_camera_contract() -> dict[str, dict[str, Any]]:
    records = [
        ("CAM_PCB_CLEAN", 60, "clean", (0.55, -1.0, 0.62)),
        ("CAM_PCB_TOP", 60, "top", (0.0, -0.18, 1.0)),
        ("CAM_PCB_CONTEXT", 55, "context", (0.68, -1.0, 0.55)),
    ]
    return {
        name: {
            "name": name,
            "projection": "PERSP",
            "lens_mm": lens,
            "view_role": role,
            "direction": list(direction),
            "clip_start_mm": 0.1,
            "clip_end_mm": 10000.0,
        }
        for name, lens, role, direction in records
    }


def build_reference_manifest(project_root: Path | None = None) -> dict[str, Any]:
    refs = {
        "REF_PCB_001": {"path": "references/pcb/REF_PCB_001.png", "role": "detail_supplement"},
        "REF_PCB_002": {"path": "references/pcb/REF_PCB_002.png", "role": "primary_layout"},
        "REF_PCB_003": {"path": "references/pcb/REF_PCB_003.png", "role": "detail_supplement"},
    }
    if project_root is not None:
        root = Path(project_root).expanduser().resolve()
        for ref in refs.values():
            ref["sha256"] = hashlib.sha256((root / ref["path"]).read_bytes()).hexdigest()
        return refs
    return {
        key: {**value, "sha256": _REFERENCE_SHA256[key]}
        for key, value in refs.items()
    }


def _sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _reference_sha256() -> dict[str, str]:
    root = Path(__file__).resolve().parents[2]
    return {
        "REF_PCB_001": _sha256_of(root / "references/pcb/REF_PCB_001.png"),
        "REF_PCB_002": _sha256_of(root / "references/pcb/REF_PCB_002.png"),
        "REF_PCB_003": _sha256_of(root / "references/pcb/REF_PCB_003.png"),
    }


try:
    _REFERENCE_SHA256 = _reference_sha256()
except OSError:  # pragma: no cover - reference images are required assets.
    _REFERENCE_SHA256 = {key: "0" * 64 for key in ("REF_PCB_001", "REF_PCB_002", "REF_PCB_003")}


def build_material_contract() -> dict[str, Any]:
    return {
        "pcb_soldermask": {
            "base_color": (0.075, 0.42, 0.09, 1.0),
            "roughness": 0.42,
            "metallic": 0.05,
            "texture": ASSET_TEXTURE,
            "texture_mapping": "GENERATED_XY",
        },
        "ic": {"base_color": (0.022, 0.026, 0.032, 1.0), "roughness": 0.48, "metallic": 0.05},
        "connector": {"base_color": (0.045, 0.05, 0.058, 1.0), "roughness": 0.42, "metallic": 0.15},
        "shield": {"base_color": (0.10, 0.11, 0.125, 1.0), "roughness": 0.32, "metallic": 0.72},
        "cap": {"base_color": (0.018, 0.02, 0.024, 1.0), "roughness": 0.38, "metallic": 0.35},
        "secondary_plate": {"base_color": (0.46, 0.49, 0.52, 1.0), "roughness": 0.45, "metallic": 0.55, "weight": 0.15},
        "support_frame": {"base_color": (0.34, 0.37, 0.40, 1.0), "roughness": 0.5, "metallic": 0.4, "weight": 0.10},
        "context": {"weight": 0.45},
    }


def build_status_contract() -> dict[str, str]:
    return {
        "technical_status": "PASS",
        "visual_status": "PENDING_HUMAN_REVIEW",
        "overall_status": "REVIEW_REQUIRED",
    }


def load_human_approval(project_root: Path) -> dict[str, Any] | None:
    """Return the recorded human visual approval, if the user supplied one."""
    import json

    path = Path(project_root).expanduser().resolve() / APPROVAL_PATH
    if not path.is_file():
        return None
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(record, dict) or record.get("approved") is not True:
        return None
    return record
