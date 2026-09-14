"""Pure data contracts for the Task 10-V2 presentation-grade product story."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
import sys
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.task08_data import load_json
from stage_10_product_story.scripts.build_story_scene import (
    VISIBLE_PART_IDS,
    build_state_transforms,
    validate_state_transforms,
)

ROOT_DIR = "stage_10V2_product_story"
SCENE_OUTPUT = f"{ROOT_DIR}/scene/product_story_v2.blend"
STATE_OUTPUT = f"{ROOT_DIR}/config/state_transforms.json"
LIGHTING_OUTPUT = f"{ROOT_DIR}/config/lighting.json"
RENDER_DIR = f"{ROOT_DIR}/renders"
ASSET_TEXTURE = f"{ROOT_DIR}/assets/pcb_surface_detail.png"
APPROVAL_PATH = f"{ROOT_DIR}/config/human_approval.json"
VALIDATION_PATH = f"{ROOT_DIR}/config/validation.json"
REPORT_PATH = f"{ROOT_DIR}/reports/task10V2_product_story_report.md"
LOG_PATH = f"{ROOT_DIR}/logs/task10V2.log"
RUN_RESULT_PATH = f"{ROOT_DIR}/data_task10V2_run_result.json"

PCB_MANIFEST_PATH = "stage_10R_pcb_presentation/config/pcb_presentation_manifest.json"
PCB_TEXTURE_SOURCE = "stage_10R_pcb_presentation/assets/pcb_surface_detail.png"
PCB_APPROVAL_PATH = "stage_10R_pcb_presentation/config/human_approval.json"

PREVIEW_VIDEO = "product_story_v2_preview.mp4"

# Approved EEVEE presentation values from Task 10-R-PCB-V1 (user-approved
# brightness after the 2026-09-13 review round).
RENDER_ENGINE = "BLENDER_EEVEE"
EXPOSURE = 1.7
WORLD_COLOR = (0.11, 0.125, 0.16, 1.0)
WORLD_STRENGTH = 0.85
# V4 minimalist backdrop: vertical gradient, darker toward the floor.
WORLD_GRADIENT_BOTTOM = (0.063, 0.071, 0.086, 1.0)
WORLD_GRADIENT_TOP = (0.149, 0.169, 0.20, 1.0)
# Annotations shrink to small captions (极简 style) instead of hero titles.
ANNOTATION_SCALE = 0.45
LIGHT_RIG = (
    ("STORY_LIGHT_KEY", (40.0, -160.0, 430.0), 68000.0, 380.0),
    ("STORY_LIGHT_FILL", (-60.0, 200.0, 300.0), 36000.0, 320.0),
    ("STORY_LIGHT_RIM", (60.0, 40.0, 520.0), 46000.0, 260.0),
)
LIGHT_TARGET_OFFSET_Z = -20.0

# PART_007 keeps its exploded position for engineering context but never gets
# full focus emphasis: it is support, not a protagonist.
PART_EMPHASIS_CAP = {"PART_007": 0.55}

# V2-only PCB_FOCUS layout: in v1 the protective plate sat almost directly
# above the board and occluded the populated top surface from the story
# camera. V2 slides the board +x like a pulled-out tray so the
# MAIN_PCB_PRESENTATION surface reads clearly; plate/frame stay as context.
PCB_FOCUS_V2_OFFSETS = {
    "PART_006": [64.0, 2.0, 84.0],
    "PART_019": [135.0, -18.0, 26.0],
    "PART_007": [50.0, 8.0, 14.0],
}

# V2-only SENSOR_FOCUS layout: in v1 the sensor cluster stopped at the
# housing's left silhouette and the body occluded its right half. V2 pulls
# the cluster further left and toward the camera so the focus subject clears
# the housing outline completely. V4 additionally spreads the four parts
# radially from the cluster centroid (~1.8x) so the isolate shot shows the
# sensing cores exploded off the carrier instead of a fused blob.
SENSOR_FOCUS_V2_OFFSETS = {
    "PART_003": [-132.7, -15.8, -0.4],
    "PART_012": [-165.5, -25.8, 25.1],
    "PART_013": [-148.9, -81.2, 22.4],
    "PART_014": [-130.9, 4.9, 72.8],
}

STATE_V2_OFFSETS = {
    "PCB_FOCUS": PCB_FOCUS_V2_OFFSETS,
    "SENSOR_FOCUS": SENSOR_FOCUS_V2_OFFSETS,
}

# Task 10-V3 frustum-aware focus policy. ``isolate`` shots require the focus
# subject's projected silhouette to keep ``margin_ndc`` screen gap from every
# context part; ``layer`` subjects contain context by design and are checked
# for framing only. ``per_part`` continues each part's own explode direction;
# otherwise the module receives one shared rigid translation along
# ``direction``. ``focus_components`` mounts the PCB presentation components
# into the subject.
FOCUS_SHOT_POLICY: dict[str, dict[str, Any]] = {
    "SENSOR_FOCUS": {
        "parts": ("PART_003", "PART_012", "PART_013", "PART_014"),
        "camera": "CAM_STORY_SENSOR",
        "direction": (-0.98077, -0.16518, 0.10324),
        "per_part": False,
        "margin_ndc": 0.04,
        "mode": "isolate",
        "focus_components": False,
    },
    "PCB_FOCUS": {
        "parts": ("PART_019",),
        "camera": "CAM_STORY_PCB",
        "direction": (0.97297, -0.13040, 0.19058),
        "per_part": False,
        "margin_ndc": 0.04,
        "mode": "isolate",
        "focus_components": True,
    },
    "COMMUNICATION_FOCUS": {
        "parts": ("PART_005", "PART_017", "PART_018"),
        "camera": "CAM_STORY_COMM",
        # Toward the dedicated comm camera (its view direction).
        "direction": (0.48, -0.74, 0.44),
        "per_part": False,
        "margin_ndc": 0.03,
        "mode": "isolate",
        "focus_components": False,
    },
    "POWER_FOCUS": {
        "parts": ("PART_008", "PART_009", "PART_010", "PART_011", "PART_015", "PART_016"),
        "camera": "CAM_STORY_POWER",
        "direction": (0.0, -0.34894, 0.93714),
        "per_part": True,
        "margin_ndc": 0.03,
        "mode": "isolate",
        "focus_components": False,
    },
    "RUGGED_FOCUS": {
        "parts": ("PART_001", "PART_002", "PART_004", "PART_020", "PART_021", "PART_022"),
        "camera": "CAM_STORY_HERO",
        "direction": (0.0, 0.0, 1.0),
        "per_part": False,
        "margin_ndc": 0.03,
        "mode": "layer",
        "focus_components": False,
    },
}

FOCUS_FRAME_MARGIN_NDC = 0.03
FOCUS_MIN_HEIGHT_NDC = 0.25
FOCUS_MAX_HEIGHT_NDC = 1.75


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_pcb_manifest(project_root: Path) -> dict[str, Any]:
    root = Path(project_root).expanduser().resolve()
    path = root / PCB_MANIFEST_PATH
    if not path.is_file():
        raise ValueError("Task 10-R-PCB-V1 manifest is required as a frozen input")
    manifest = load_json(path)
    components = manifest.get("components")
    if not isinstance(components, list) or len(components) != int(manifest.get("component_count", 0)):
        raise ValueError("Task 10-R-PCB-V1 manifest component list is inconsistent")
    for component in components:
        if component.get("mounted_on") != "PART_019":
            raise ValueError(f"component is not mounted on PART_019: {component.get('component_id')}")
        if component.get("source") != "photographic_presentation_reconstruction":
            raise ValueError(f"component provenance is invalid: {component.get('component_id')}")
    return dict(manifest)


def component_board_local(component: Mapping[str, Any], manifest: Mapping[str, Any]) -> list[float]:
    """Board-local offset of a component relative to the PART_019 origin."""
    zone = manifest["board_zone_center_mm"]
    return [float(component["world_location"][axis]) - float(zone[axis]) for axis in range(3)]


def build_component_registry(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    registry: list[dict[str, Any]] = []
    for component in manifest["components"]:
        registry.append(
            {
                "component_id": component["component_id"],
                "shape": component["shape"],
                "size_xy_mm": list(component.get("size_xy_mm", [])),
                "radius_mm": component.get("radius_mm"),
                "height_mm": float(component["height_mm"]),
                "bevel_mm": float(component.get("bevel_mm", 0.5)),
                "material_role": component["material_role"],
                "visual_role": component["visual_role"],
                "reference_source": component["reference_source"],
                "mounted_on": "PART_019",
                "board_local_location": component_board_local(component, manifest),
            }
        )
    return registry


def build_story_v2_state_transforms(project_root: Path) -> dict[str, Any]:
    """V1 story transforms plus presentation components riding with PART_019."""
    root = Path(project_root).expanduser().resolve()
    payload = build_state_transforms(root)
    _apply_v2_focus_layouts(payload)
    manifest = load_pcb_manifest(root)
    registry = build_component_registry(manifest)
    for state in payload["states"].values():
        board = state["parts"]["PART_019"]
        state["components"] = {
            component["component_id"]: {
                "location": [
                    float(board["location"][axis]) + component["board_local_location"][axis]
                    for axis in range(3)
                ],
                "rotation_euler": list(board["rotation_euler"]),
                "scale": [1.0, 1.0, 1.0],
            }
            for component in registry
        }
    payload["version"] = "task10V2_story_states_v1"
    payload["presentation"] = {
        "components": registry,
        "component_count": len(registry),
        "part_reclassification": manifest["part_reclassification"],
        "presentation_hierarchy": manifest["presentation_hierarchy"],
        "part_emphasis_cap": dict(PART_EMPHASIS_CAP),
        "source_manifest": PCB_MANIFEST_PATH,
        "source_manifest_sha256": sha256_file(root / PCB_MANIFEST_PATH),
        "surface_texture": ASSET_TEXTURE,
        "surface_texture_source": PCB_TEXTURE_SOURCE,
    }
    return validate_story_v2_state_transforms(payload)


def _apply_v2_focus_layouts(payload: dict[str, Any]) -> None:
    assembled = payload["states"]["ASSEMBLED"]["parts"]
    for state_id, offsets in STATE_V2_OFFSETS.items():
        parts = payload["states"][state_id]["parts"]
        for part_id, delta in offsets.items():
            record = parts[part_id]
            record["location"] = [
                float(assembled[part_id]["location"][axis]) + float(delta[axis])
                for axis in range(3)
            ]
            record["offset_from_assembled_mm"] = [float(value) for value in delta]


def validate_story_v2_state_transforms(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Fail-closed check: v1 part contract plus component-follows-board."""
    validate_state_transforms(payload)
    presentation = payload.get("presentation")
    if not isinstance(presentation, Mapping):
        raise ValueError("Task 10-V2 presentation block is missing")
    registry = presentation.get("components")
    if not isinstance(registry, list) or len(registry) != int(presentation.get("component_count", -1)):
        raise ValueError("Task 10-V2 component registry is incomplete")
    local_by_id = {component["component_id"]: component["board_local_location"] for component in registry}
    if len(local_by_id) != len(registry) or not all(cid.startswith("PCB_COMP_") for cid in local_by_id):
        raise ValueError("Task 10-V2 component ids are invalid")
    for component in registry:
        if len(component["board_local_location"]) != 3:
            raise ValueError(f"component local offset is invalid: {component['component_id']}")
    reclass = presentation.get("part_reclassification", {})
    if reclass.get("PART_007", {}).get("presentation_priority") != "SUPPORT":
        raise ValueError("PART_007 must stay SUPPORT in Task 10-V2")
    if reclass.get("PART_007", {}).get("independent_focus") is not False:
        raise ValueError("PART_007 must not get independent focus in Task 10-V2")
    for state_id, state in payload["states"].items():
        components = state.get("components")
        if not isinstance(components, Mapping) or set(components) != set(local_by_id):
            raise ValueError(f"Task 10-V2 components are missing in state {state_id}")
        board = state["parts"]["PART_019"]
        for component_id, transform in components.items():
            local = local_by_id[component_id]
            for axis in range(3):
                expected = float(board["location"][axis]) + float(local[axis])
                if abs(float(transform["location"][axis]) - expected) > 1e-6:
                    raise ValueError(f"{component_id} does not ride with PART_019 in {state_id}")
    return dict(payload)


def _state_bounds(state_data: Mapping[str, Any], layout: Mapping[str, Any]) -> dict[str, Any]:
    low = [float("inf")] * 3
    high = [float("-inf")] * 3
    for state in state_data["states"].values():
        for part_id, record in state["parts"].items():
            dims = layout["parts"][part_id]["bbox_dimensions_mm"]
            for axis in range(3):
                half = float(dims[axis]) / 2.0
                low[axis] = min(low[axis], float(record["location"][axis]) - half)
                high[axis] = max(high[axis], float(record["location"][axis]) + half)
    return {"min": low, "max": high, "dimensions": [high[i] - low[i] for i in range(3)]}


def build_lighting_config(project_root: Path, state_data: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Deterministic product light rig anchored on the story bounds center."""
    root = Path(project_root).expanduser().resolve()
    if state_data is None:
        state_data = load_json(root / STATE_OUTPUT)
    layout = load_json(root / "stage_09C_refined_explosion/config/refined_layout.json")
    bounds = _state_bounds(state_data, layout)
    center = [
        (float(bounds["min"][axis]) + float(bounds["max"][axis])) / 2.0
        for axis in range(3)
    ]
    lights = []
    for name, offset, energy, size in LIGHT_RIG:
        lights.append(
            {
                "name": name,
                "type": "AREA",
                "shape": "DISK",
                "location": [center[axis] + float(offset[axis]) for axis in range(3)],
                "energy": float(energy),
                "size": float(size),
            }
        )
    return {
        "engine": RENDER_ENGINE,
        "exposure": EXPOSURE,
        "world": {"color": list(WORLD_COLOR), "strength": WORLD_STRENGTH},
        "bounds": bounds,
        "target": [center[0], center[1], center[2] + LIGHT_TARGET_OFFSET_Z],
        "lights": lights,
    }


def build_component_material_roles() -> dict[str, dict[str, Any]]:
    """Approved presentation component colors from Task 10-R-PCB-V1."""
    return {
        "ic": {"base_color": (0.022, 0.026, 0.032, 1.0), "roughness": 0.48, "metallic": 0.05},
        "connector": {"base_color": (0.045, 0.05, 0.058, 1.0), "roughness": 0.42, "metallic": 0.15},
        "shield": {"base_color": (0.10, 0.11, 0.125, 1.0), "roughness": 0.32, "metallic": 0.72},
        "cap": {"base_color": (0.018, 0.02, 0.024, 1.0), "roughness": 0.38, "metallic": 0.35},
    }


def copy_surface_texture(project_root: Path) -> dict[str, Any]:
    """Copy the approved 10R surface texture into the V2 asset dir."""
    root = Path(project_root).expanduser().resolve()
    source = root / PCB_TEXTURE_SOURCE
    if not source.is_file():
        raise ValueError("approved PCB surface texture is required as a frozen input")
    output = root / ASSET_TEXTURE
    output.parent.mkdir(parents=True, exist_ok=True)
    data = source.read_bytes()
    output.write_bytes(data)
    return {
        "path": str(output),
        "sha256": hashlib.sha256(data).hexdigest(),
        "source_sha256": sha256_file(source),
    }


def load_human_approval(project_root: Path) -> dict[str, Any] | None:
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
