"""Deterministic, Blender-independent Task 10 story configuration."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from scripts.task08_data import write_json


FUNCTIONAL_MODULES: dict[str, list[str]] = {
    "SMART_3_AXIS_SENSING_SYSTEM": [
        "PART_003", "PART_012", "PART_013", "PART_014"
    ],
    "HIGH_PRECISION_ACQUISITION_CORE": [
        "PART_006", "PART_007", "PART_019"
    ],
    "REAL_TIME_COMMUNICATION_SYSTEM": [
        "PART_005", "PART_017", "PART_018"
    ],
    "LONG_ENDURANCE_POWER_SYSTEM": [
        "PART_008", "PART_009", "PART_010", "PART_011", "PART_015", "PART_016"
    ],
    "RUGGED_FIELD_PLATFORM": [
        "PART_001", "PART_002", "PART_004", "PART_020", "PART_021", "PART_022"
    ],
}


SHOT_RANGES: list[tuple[str, int, int]] = [
    ("ASSEMBLED", 1, 75),
    ("PRIMARY_ARCHITECTURE", 75, 165),
    ("SENSOR_FOCUS", 165, 300),
    ("PCB_FOCUS", 300, 420),
    ("COMMUNICATION_FOCUS", 420, 510),
    ("POWER_FOCUS", 510, 615),
    ("RUGGED_FOCUS", 615, 705),
    ("REASSEMBLED", 705, 810),
    ("FINAL_HERO", 810, 900),
]


_MODULE_METADATA: dict[str, dict[str, Any]] = {
    "SMART_3_AXIS_SENSING_SYSTEM": {
        "title": "SMART 3-AXIS SENSING",
        "customer_takeaway": "Three-axis sensing helps capture accurate field data.",
        "metrics": ["3 Channels", "99% Data Consistency"],
        "material_role": "SENSOR",
        "focus_weight": 1.0,
        "claim_refs": ["PRODUCT_PDF_001:p1", "PRODUCT_PDF_001:p2"],
    },
    "HIGH_PRECISION_ACQUISITION_CORE": {
        "title": "HIGH-PRECISION ACQUISITION",
        "customer_takeaway": "A 32-bit, three-channel core digitizes measurements with high precision.",
        "metrics": ["32-bit ADC", "3 Channels"],
        "material_role": "PCB",
        "focus_weight": 1.0,
        "claim_refs": ["PRODUCT_PDF_001:p2"],
    },
    "REAL_TIME_COMMUNICATION_SYSTEM": {
        "title": "REAL-TIME WIRELESS TRANSMISSION",
        "customer_takeaway": "Field data can be transmitted wirelessly in real time.",
        "metrics": ["Multi-network communication"],
        "material_role": "COMMUNICATION",
        "focus_weight": 0.9,
        "claim_refs": ["PRODUCT_PDF_001:p1", "PRODUCT_PDF_001:p2"],
    },
    "LONG_ENDURANCE_POWER_SYSTEM": {
        "title": "LONG-ENDURANCE POWER",
        "customer_takeaway": "A six-unit power system supports long field deployments.",
        "metrics": ["10-day standby", "3-hour charging"],
        "material_role": "BATTERY",
        "focus_weight": 0.85,
        "claim_refs": ["PRODUCT_PDF_001:p2"],
    },
    "RUGGED_FIELD_PLATFORM": {
        "title": "BUILT FOR FIELD WORK",
        "customer_takeaway": "A lightweight, temperature-tolerant platform supports demanding field work.",
        "metrics": ["-40°C ~ +80°C", "2.5 kg"],
        "material_role": "EXTERIOR",
        "focus_weight": 0.85,
        "claim_refs": ["PRODUCT_PDF_001:p2"],
    },
}


def build_functional_modules() -> dict[str, dict[str, Any]]:
    """Return a fresh, disjoint mapping of story modules to source PART IDs."""
    return {
        module_id: {
            "module_id": module_id,
            "part_ids": list(part_ids),
            **_MODULE_METADATA[module_id],
        }
        for module_id, part_ids in FUNCTIONAL_MODULES.items()
    }


def build_story_config() -> dict[str, Any]:
    """Return the complete 30-second story contract."""
    focus_by_shot = {
        "ASSEMBLED": None,
        "PRIMARY_ARCHITECTURE": None,
        "SENSOR_FOCUS": "SMART_3_AXIS_SENSING_SYSTEM",
        "PCB_FOCUS": "HIGH_PRECISION_ACQUISITION_CORE",
        "COMMUNICATION_FOCUS": "REAL_TIME_COMMUNICATION_SYSTEM",
        "POWER_FOCUS": "LONG_ENDURANCE_POWER_SYSTEM",
        "RUGGED_FOCUS": "RUGGED_FIELD_PLATFORM",
        "REASSEMBLED": None,
        "FINAL_HERO": None,
    }
    title_by_shot = {
        "ASSEMBLED": "SMART FIELD SURVEY DEVICE",
        "PRIMARY_ARCHITECTURE": "PRODUCT FUNCTIONAL ARCHITECTURE",
        "SENSOR_FOCUS": _MODULE_METADATA["SMART_3_AXIS_SENSING_SYSTEM"]["title"],
        "PCB_FOCUS": _MODULE_METADATA["HIGH_PRECISION_ACQUISITION_CORE"]["title"],
        "COMMUNICATION_FOCUS": _MODULE_METADATA["REAL_TIME_COMMUNICATION_SYSTEM"]["title"],
        "POWER_FOCUS": _MODULE_METADATA["LONG_ENDURANCE_POWER_SYSTEM"]["title"],
        "RUGGED_FOCUS": _MODULE_METADATA["RUGGED_FIELD_PLATFORM"]["title"],
        "REASSEMBLED": "FROM SENSING TO FIELD RESULTS",
        "FINAL_HERO": "SMART SURVEY. READY FOR THE FIELD.",
    }
    metrics_by_shot = {
        "ASSEMBLED": [],
        "PRIMARY_ARCHITECTURE": [],
        "SENSOR_FOCUS": ["3 Channels", "99% Data Consistency"],
        "PCB_FOCUS": ["32-bit ADC", "3 Channels"],
        "COMMUNICATION_FOCUS": ["Multi-network communication"],
        "POWER_FOCUS": ["10-day standby", "3-hour charging"],
        "RUGGED_FOCUS": ["-40°C ~ +80°C", "2.5 kg"],
        "REASSEMBLED": [],
        "FINAL_HERO": ["Accurate acquisition", "Wireless transmission"],
    }
    emphasis_by_shot = {
        "ASSEMBLED": "all",
        "PRIMARY_ARCHITECTURE": "architecture",
        "SENSOR_FOCUS": "focus_sensor",
        "PCB_FOCUS": "focus_pcb",
        "COMMUNICATION_FOCUS": "focus_communication",
        "POWER_FOCUS": "focus_power",
        "RUGGED_FOCUS": "focus_rugged",
        "REASSEMBLED": "reassembly",
        "FINAL_HERO": "all",
    }
    shots: list[dict[str, Any]] = []
    for shot_id, frame_start, frame_end in SHOT_RANGES:
        shots.append(
            {
                "shot_id": shot_id,
                "frame_start": frame_start,
                "frame_end": frame_end,
                "state_id": shot_id,
                "focus_module": focus_by_shot[shot_id],
                "title": title_by_shot[shot_id],
                "metrics": list(metrics_by_shot[shot_id]),
                "camera_id": (
                    "CAM_STORY_SENSOR" if shot_id == "SENSOR_FOCUS"
                    else "CAM_STORY_PCB" if shot_id == "PCB_FOCUS"
                    else "CAM_STORY_HERO"
                ),
                "emphasis": emphasis_by_shot[shot_id],
                "validation_target": (
                    "focus_module_clear" if focus_by_shot[shot_id] else "assembly_context_clear"
                ),
            }
        )
    return {
        "story_id": "TASK10_PRODUCT_FUNCTIONAL_STORY",
        "fps": 30,
        "frame_range": [1, 900],
        "duration_seconds": 30.0,
        "communication_protocol_text": "PENDING_PRODUCT_CONFIRMATION",
        "functional_module_order": [
            "SMART_3_AXIS_SENSING_SYSTEM",
            "HIGH_PRECISION_ACQUISITION_CORE",
            "REAL_TIME_COMMUNICATION_SYSTEM",
            "LONG_ENDURANCE_POWER_SYSTEM",
            "RUGGED_FIELD_PLATFORM",
        ],
        "shots": shots,
    }


def build_material_roles() -> dict[str, dict[str, Any]]:
    """Return presentation-only material roles; source meshes stay untouched."""
    return {
        "LOWER_HOUSING": {
            "base_color": [0.95, 0.18, 0.02, 1.0],
            "role": "INDUSTRIAL_ORANGE",
            "roughness": 0.38,
        },
        "UPPER_HOUSING": {
            "base_color": [0.025, 0.03, 0.035, 1.0],
            "role": "MATTE_BLACK",
            "roughness": 0.42,
        },
        "UPPER_HOUSING_TOP_COVER": {
            "base_color": [0.025, 0.03, 0.035, 1.0],
            "role": "MATTE_BLACK",
            "roughness": 0.42,
        },
        "MAIN_PCB": {
            "base_color": [0.02, 0.32, 0.10, 1.0],
            "role": "PCB_GREEN",
            "roughness": 0.5,
        },
        "SENSOR": {
            "base_color": [0.12, 0.14, 0.16, 1.0],
            "role": "DARK_METALLIC",
            "metallic": 0.72,
            "roughness": 0.28,
        },
        "COMMUNICATION": {
            "base_color": [0.06, 0.07, 0.08, 1.0],
            "role": "COMMUNICATION_DARK",
            "roughness": 0.32,
        },
        "BATTERY": {
            "base_color": [0.04, 0.045, 0.05, 1.0],
            "role": "CHARCOAL",
            "roughness": 0.4,
        },
        "SUPPORT": {
            "base_color": [0.36, 0.39, 0.42, 1.0],
            "role": "NEUTRAL_METAL",
            "metallic": 0.5,
            "roughness": 0.34,
        },
    }


def build_camera_sequence() -> dict[str, Any]:
    """Return the restrained camera policy used by the story preview."""
    return {
        "fps": 30,
        "hero_camera": "CAM_STORY_HERO",
        "camera_motion_policy": "SLOW_CONTROLLED",
        "max_orbit_degrees_per_second": 8,
        "camera_segments": [
            {"frame_start": 1, "frame_end": 165, "camera_id": "CAM_STORY_HERO"},
            {"frame_start": 165, "frame_end": 300, "camera_id": "CAM_STORY_SENSOR"},
            {"frame_start": 300, "frame_end": 420, "camera_id": "CAM_STORY_PCB"},
            {"frame_start": 420, "frame_end": 900, "camera_id": "CAM_STORY_HERO"},
        ],
        "cameras": {
            "CAM_STORY_HERO": {"projection": "PERSP", "lens_mm": 78, "elevation_deg": 30},
            "CAM_STORY_SENSOR": {"projection": "PERSP", "lens_mm": 92, "elevation_deg": 28},
            "CAM_STORY_PCB": {"projection": "PERSP", "lens_mm": 92, "elevation_deg": 26},
        },
        "shots": [
            {"shot_id": shot_id, "camera_id": (
                "CAM_STORY_SENSOR" if shot_id == "SENSOR_FOCUS"
                else "CAM_STORY_PCB" if shot_id == "PCB_FOCUS"
                else "CAM_STORY_HERO"
            )}
            for shot_id, _, _ in SHOT_RANGES
        ],
    }


def build_annotation_config() -> dict[str, Any]:
    """Return customer-facing annotations without unresolved protocol names."""
    return {
        "font_style": "PRODUCT_TECHNICAL_SANS",
        "safe_area_percent": 8,
        "items": [
            {"id": "assembled_title", "text": "SMART FIELD SURVEY DEVICE", "shot_id": "ASSEMBLED"},
            {"id": "architecture_title", "text": "PRODUCT FUNCTIONAL ARCHITECTURE", "shot_id": "PRIMARY_ARCHITECTURE"},
            {"id": "sensor_title", "text": "SMART 3-AXIS SENSING", "shot_id": "SENSOR_FOCUS"},
            {"id": "sensor_metric_1", "text": "3 Channels", "shot_id": "SENSOR_FOCUS"},
            {"id": "sensor_metric_2", "text": "99% Data Consistency", "shot_id": "SENSOR_FOCUS"},
            {"id": "pcb_title", "text": "HIGH-PRECISION ACQUISITION", "shot_id": "PCB_FOCUS"},
            {"id": "pcb_metric_1", "text": "32-bit ADC", "shot_id": "PCB_FOCUS"},
            {"id": "pcb_metric_2", "text": "3 Channels", "shot_id": "PCB_FOCUS"},
            {"id": "communication_title", "text": "REAL-TIME WIRELESS TRANSMISSION", "shot_id": "COMMUNICATION_FOCUS"},
            {"id": "communication_metric", "text": "Multi-network communication", "shot_id": "COMMUNICATION_FOCUS"},
            {"id": "power_title", "text": "LONG-ENDURANCE POWER", "shot_id": "POWER_FOCUS"},
            {"id": "power_metric_1", "text": "10-day standby", "shot_id": "POWER_FOCUS"},
            {"id": "power_metric_2", "text": "3-hour charging", "shot_id": "POWER_FOCUS"},
            {"id": "rugged_title", "text": "BUILT FOR FIELD WORK", "shot_id": "RUGGED_FOCUS"},
            {"id": "rugged_metric_1", "text": "-40°C ~ +80°C", "shot_id": "RUGGED_FOCUS"},
            {"id": "rugged_metric_2", "text": "2.5 kg", "shot_id": "RUGGED_FOCUS"},
            {"id": "reassembled_title", "text": "FROM SENSING TO FIELD RESULTS", "shot_id": "REASSEMBLED"},
            {"id": "final_title", "text": "SMART SURVEY. READY FOR THE FIELD.", "shot_id": "FINAL_HERO"},
            {"id": "final_metric_1", "text": "Accurate acquisition", "shot_id": "FINAL_HERO"},
            {"id": "final_metric_2", "text": "Wireless transmission", "shot_id": "FINAL_HERO"},
        ],
    }


def write_story_configs(project_root: Path) -> dict[str, Path]:
    root = Path(project_root).expanduser().resolve()
    config_dir = root / "stage_10_product_story/config"
    payloads = {
        "product_story.json": build_story_config(),
        "functional_modules.json": build_functional_modules(),
        "shot_sequence.json": {"shots": build_story_config()["shots"]},
        "camera_sequence.json": build_camera_sequence(),
        "annotation_config.json": build_annotation_config(),
    }
    outputs: dict[str, Path] = {}
    for name, payload in payloads.items():
        output = config_dir / name
        write_json(output, payload)
        outputs[name] = output
    return outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    for output in write_story_configs(args.project_root).values():
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
