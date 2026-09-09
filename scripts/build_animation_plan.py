"""Build the Task 9A timing plan without creating Blender animation data."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from scripts.task08_data import load_json
from scripts.task09_data import validate_task09_baseline
from scripts.task09_planning import build_disassembly_graph, build_exploded_state


def build_animation_plan(project_root: Path) -> dict[str, Any]:
    """Create a reviewable schedule; deliberately omit keyframe payloads."""
    root = Path(project_root).expanduser().resolve()
    validate_task09_baseline(root)
    state = build_exploded_state(root)
    graph = build_disassembly_graph(root)
    order = graph["topological_order"]

    stages = [
        _stage("ASSEMBLED_HOLD", 1, 45, [], "complete device remains assembled"),
        _stage("EXTERNAL_FASTENERS", 46, 90, ["EXTERNAL_HOUSING_FASTENERS"], "remove visible external fasteners"),
        _stage("HANDLE", 75, 120, ["HANDLE"], "lift handle from upper housing"),
        _stage("TOP_COVER", 105, 150, ["UPPER_HOUSING_TOP_COVER"], "lift top cover"),
        _stage("TOP_INTERFACE", 120, 165, ["TOP_INTERFACE"], "separate top interface ports"),
        _stage("UPPER_HOUSING", 135, 190, ["UPPER_HOUSING"], "raise upper housing"),
        _stage("PCB_PROTECTIVE_PLATE", 175, 225, ["PCB_PROTECTIVE_PLATE"], "separate board protective plate"),
        _stage("MAIN_PCB", 205, 255, ["MAIN_PCB"], "translate main PCB for inspection"),
        _stage("PCB_SUPPORT_FRAME", 240, 300, ["PCB_SUPPORT_FRAME"], "separate support frame"),
        _stage("BATTERY_ASSEMBLY", 280, 360, ["BATTERY_ASSEMBLY"], "move battery compartments in parallel"),
        _stage("SENSOR_ASSEMBLY", 330, 410, ["SENSOR_ASSEMBLY"], "move sensor fixture and cores together"),
        _stage("LEVELING_ASSEMBLY", 390, 450, ["LEVELING_ASSEMBLY"], "lower three leveling cones together"),
        _stage("LOWER_HOUSING", 420, 480, ["LOWER_HOUSING"], "separate lower housing last"),
        _stage("EXPLODED_HOLD", 481, 540, [], "hold the engineering exploded state"),
        _stage("REVIEW_HOLD", 541, 570, [], "hold for inspection; no animation implementation yet"),
    ]
    part_stage_counts: dict[str, int] = defaultdict(int)
    for record in state["parts"].values():
        part_stage_counts[str(record["assembly_group"])] += 1

    return {
        "fps": 30,
        "frame_range": [1, 570],
        "total_duration_seconds": 570 / 30,
        "animation_created": False,
        "keyframe_policy": "No keyframes are created in Task 9A.",
        "easing": "BEZIER_EASE_IN_OUT",
        "stages": stages,
        "parallel_groups": [
            {"group": group, "part_count": count, "policy": "GROUP_LINEAR"}
            for group, count in sorted(part_stage_counts.items())
            if count > 1
        ],
        "disassembly_order": order,
        "planned_part_count": len(state["parts"]),
        "collision_count": state["collision_summary"]["collision_count"],
        "source": "Task 9A schedule only; generated without Blender keyframes",
    }


def _stage(stage_id: str, start: int, end: int, groups: list[str], rationale: str) -> dict[str, Any]:
    return {
        "stage_id": stage_id,
        "start_frame": start,
        "end_frame": end,
        "duration_frames": end - start + 1,
        "groups": list(groups),
        "rationale": rationale,
        "motion_policy": "LINEAR_PLAN_ONLY",
    }
