"""Pure data contracts for Task 10-R functional inspection states."""

from __future__ import annotations

from typing import Any


BASELINE = {"source_part_count": 82, "faces": 444296, "indexed_vertices": 221902}
SOURCE_LAYOUT = "stage_09C_refined_explosion/config/refined_layout.json"
SOURCE_SCENE = "stage_09C_refined_explosion/scene/exploded_animation_preview.blend"
SOURCE_SCENE_SHA256 = "a3b5359861877e247ad1b035b00cace3e29eea2789ac227e6eeddfaaba1a7766"
EXPECTED_PART_IDS = tuple(f"PART_{index:03d}" for index in range(1, 83))
STORY_PART_IDS = tuple(f"PART_{index:03d}" for index in range(1, 23))
HIDDEN_PART_IDS = tuple(f"PART_{index:03d}" for index in range(23, 83))
INSPECTION_STATE_IDS = (
    "STATE_01_PRIMARY_ARCHITECTURE",
    "STATE_02_SENSOR_INSPECTION",
    "STATE_03_PCB_INSPECTION",
    "STATE_04_POWER_INSPECTION",
)


def build_module_groups() -> dict[str, dict[str, Any]]:
    return {
        "MODULE_A": {
            "name": "TOP_EXTERIOR_MODULE",
            "part_ids": ["PART_002", "PART_004", "PART_005", "PART_017", "PART_018"],
            "focus_role": "TOP_EXTERIOR",
        },
        "MODULE_B": {
            "name": "ELECTRONICS_POWER_MODULE",
            "part_ids": [
                "PART_006", "PART_007", "PART_019", "PART_008", "PART_009",
                "PART_010", "PART_011", "PART_015", "PART_016",
            ],
            "focus_role": "ELECTRONICS_POWER",
        },
        "MODULE_C": {
            "name": "THREE_AXIS_SENSOR_MODULE",
            "part_ids": ["PART_003", "PART_012", "PART_013", "PART_014"],
            "focus_role": "SENSOR",
        },
        "MODULE_D": {
            "name": "LOWER_FIELD_PLATFORM",
            "part_ids": ["PART_001", "PART_020", "PART_021", "PART_022"],
            "focus_role": "LOWER_PLATFORM",
        },
    }


def build_inspection_states() -> dict[str, dict[str, Any]]:
    return {
        "STATE_01_PRIMARY_ARCHITECTURE": {
            "state_id": "STATE_01_PRIMARY_ARCHITECTURE",
            "camera_id": "CAM_INSPECTION_PRIMARY_HERO",
            "module_layout": ["MODULE_A", "MODULE_B", "MODULE_C", "MODULE_D"],
            "hero_output": "01_primary_architecture_hero.png",
            "additional_outputs": ["01_primary_architecture_front.png", "01_primary_architecture_side.png"],
            "text_policy": "NO_TEXT",
            "animation_policy": "NO_KEYFRAMES",
        },
        "STATE_02_SENSOR_INSPECTION": {
            "state_id": "STATE_02_SENSOR_INSPECTION",
            "camera_id": "CAM_INSPECTION_SENSOR_CLEAN",
            "context_camera_id": "CAM_INSPECTION_SENSOR_CONTEXT",
            "local_axes": {"PART_012": "X", "PART_013": "Y", "PART_014": "Z"},
            "hero_output": "02_sensor_inspection_clean.png",
            "additional_outputs": ["02_sensor_inspection_context.png", "02_sensor_inspection_top.png"],
            "text_policy": "NO_TEXT",
            "animation_policy": "NO_KEYFRAMES",
        },
        "STATE_03_PCB_INSPECTION": {
            "state_id": "STATE_03_PCB_INSPECTION",
            "camera_id": "CAM_INSPECTION_PCB_CLEAN",
            "context_camera_id": "CAM_INSPECTION_PCB_CONTEXT",
            "layer_order": ["PART_006", "PART_019", "PART_007"],
            "hero_output": "03_pcb_inspection_clean.png",
            "additional_outputs": ["03_pcb_inspection_context.png", "03_pcb_inspection_top.png"],
            "text_policy": "NO_TEXT",
            "animation_policy": "NO_KEYFRAMES",
        },
        "STATE_04_POWER_INSPECTION": {
            "state_id": "STATE_04_POWER_INSPECTION",
            "camera_id": "CAM_INSPECTION_POWER_CLEAN",
            "context_camera_id": "CAM_INSPECTION_POWER_CONTEXT",
            "array_shape": [3, 2],
            "hero_output": "04_power_inspection_clean.png",
            "additional_outputs": ["04_power_inspection_context.png"],
            "text_policy": "NO_TEXT",
            "animation_policy": "NO_KEYFRAMES",
        },
    }


def build_visibility_policy() -> dict[str, Any]:
    return {
        "visible_part_ids": list(STORY_PART_IDS),
        "hidden_part_ids": list(HIDDEN_PART_IDS),
        "hidden_policy": "PRESENTATION_HIDDEN_NO_ANIMATION",
        "source_parts_preserved": True,
    }


def build_inspection_camera_contract() -> dict[str, dict[str, Any]]:
    """Return the independent camera roles used by the four inspection states."""
    records = [
        ("CAM_INSPECTION_PRIMARY_HERO", 65, "STATE_01_PRIMARY_ARCHITECTURE", "hero"),
        ("CAM_INSPECTION_PRIMARY_FRONT", 65, "STATE_01_PRIMARY_ARCHITECTURE", "front"),
        ("CAM_INSPECTION_PRIMARY_SIDE", 65, "STATE_01_PRIMARY_ARCHITECTURE", "side"),
        ("CAM_INSPECTION_SENSOR_CLEAN", 60, "STATE_02_SENSOR_INSPECTION", "clean"),
        ("CAM_INSPECTION_SENSOR_CONTEXT", 60, "STATE_02_SENSOR_INSPECTION", "context"),
        ("CAM_INSPECTION_SENSOR_TOP", 60, "STATE_02_SENSOR_INSPECTION", "top"),
        ("CAM_INSPECTION_PCB_CLEAN", 60, "STATE_03_PCB_INSPECTION", "clean"),
        ("CAM_INSPECTION_PCB_CONTEXT", 60, "STATE_03_PCB_INSPECTION", "context"),
        ("CAM_INSPECTION_PCB_TOP", 60, "STATE_03_PCB_INSPECTION", "top"),
        ("CAM_INSPECTION_POWER_CLEAN", 60, "STATE_04_POWER_INSPECTION", "clean"),
        ("CAM_INSPECTION_POWER_CONTEXT", 60, "STATE_04_POWER_INSPECTION", "context"),
    ]
    return {
        name: {
            "name": name,
            "projection": "PERSP",
            "lens_mm": lens,
            "state_id": state_id,
            "view_role": view_role,
            "clip_start_mm": 0.1,
            "clip_end_mm": 10000.0,
        }
        for name, lens, state_id, view_role in records
    }


def build_status_contract() -> dict[str, str]:
    return {
        "technical_status": "PASS",
        "visual_status": "PENDING_HUMAN_REVIEW",
        "overall_status": "REVIEW_REQUIRED",
    }
