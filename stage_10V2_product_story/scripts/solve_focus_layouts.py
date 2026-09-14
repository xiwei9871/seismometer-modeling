"""Task 10-V3: solve focus-shot layouts against the real camera frustum.

Runs inside Blender after ``build_story_scene_v2`` (real meshes available) and
before ``apply_story_animation_v2`` (which consumes the JSON it rewrites).

For every isolate-mode focus shot the solver evaluates the actual projected
silhouettes — vertex-projection convex hulls in NDC space — of the focus
subject vs every context part. When a context hull violates the required
screen gap, the focus module receives a shared extra translation ``t·d`` (or a
per-part continuation of its existing explode direction) until the silhouette
is clean. Solved offsets are written back into ``state_transforms.json`` so
the artifact stays the frozen source of truth.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.task08_data import load_json, write_json
from stage_10_product_story.scripts.build_story_scene import VISIBLE_PART_IDS
from stage_10V2_product_story.scripts import frustum_math as fm
from stage_10V2_product_story.scripts.camera_plan import build_camera_records
from stage_10V2_product_story.scripts.story_v2_data import (
    FOCUS_SHOT_POLICY,
    SCENE_OUTPUT,
    STATE_OUTPUT,
    build_story_v2_state_transforms,
)

try:  # pragma: no cover - Blender-only stage.
    import bpy  # type: ignore
    from mathutils import Euler, Matrix, Vector  # type: ignore
except ImportError:  # pragma: no cover
    bpy = None  # type: ignore
    Euler = Matrix = Vector = None  # type: ignore

LAYOUT_PATH = "stage_09C_refined_explosion/config/refined_layout.json"
MAX_VERT_SAMPLES = 1600
FRAME_HULL = ((-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0))

T_MAX_MM = 700.0
GRID_STEPS = 64
BISECT_STEPS = 40


def solve_focus_layouts(project_root: Path) -> dict[str, Any]:
    if bpy is None or Matrix is None:
        raise RuntimeError("Blender bpy is required for Task 10-V3 layout solving")
    root = Path(project_root).expanduser().resolve()
    state_path = root / STATE_OUTPUT
    state_data = load_json(state_path)
    layout = load_json(root / LAYOUT_PATH)

    bpy.ops.wm.open_mainfile(filepath=str(root / SCENE_OUTPUT))
    part_objects = {
        str(obj.get("part_id")): obj
        for obj in bpy.data.objects
        if obj.type == "MESH" and obj.get("source") == "original_stl"
    }
    component_objects = {
        obj.name: obj
        for obj in bpy.data.objects
        if obj.type == "MESH" and obj.get("task10v2_presentation_component") is True
    }

    # Freeze cameras on the deterministic builder output. The hero camera is
    # derived from bounds over all states, so a camera that re-follows solved
    # positions would retroactively invalidate earlier solves. Rendering must
    # use the same frozen cameras (setup_story_presentation_v2 does).
    baseline_data = build_story_v2_state_transforms(root)
    cameras = build_camera_records(baseline_data, layout)["cameras"]

    report: dict[str, Any] = {"shots": {}, "changed": False}
    for shot_id, spec in FOCUS_SHOT_POLICY.items():
        if spec.get("mode") == "layer":
            # Layer-mode subjects (the housing itself) legitimately contain
            # context; nothing to solve, framing is gate-checked later.
            report["shots"][shot_id] = {
                "travel_mm": 0.0, "direction": [], "mode": "layer",
                "violations_before": [], "violations_after": [],
            }
            continue
        state = state_data["states"][shot_id]
        result = _solve_shot(
            spec, state, state_data, part_objects, component_objects, cameras
        )
        report["shots"][shot_id] = result
        if result["travel_mm"] > 0.0:
            report["changed"] = True
            _apply_travel(state, spec, result["travel_mm"], state_data)

    if report["changed"]:
        state_data["version"] = "task10V2_story_states_v3_solved"
        state_data["v3_layout"] = {
            "solver": "frustum_hull_v1",
            "shots": {
                sid: {
                    "travel_mm": report["shots"][sid]["travel_mm"],
                    "direction": report["shots"][sid]["direction"],
                    "margin_ndc": FOCUS_SHOT_POLICY[sid]["margin_ndc"],
                    "violations_before": report["shots"][sid]["violations_before"],
                }
                for sid in FOCUS_SHOT_POLICY
            },
        }
        write_json(state_path, state_data)
    report["state_transforms"] = str(state_path)
    return report


# ---------------------------------------------------------------------------
# solving
# ---------------------------------------------------------------------------

def _solve_shot(
    spec: Mapping[str, Any],
    state: Mapping[str, Any],
    state_data: Mapping[str, Any],
    part_objects: Mapping[str, Any],
    component_objects: Mapping[str, Any],
    cameras: Mapping[str, Any],
) -> dict[str, Any]:
    focus_ids = list(spec["parts"])
    direction = fm.v_norm(spec["direction"])
    margin = float(spec["margin_ndc"])
    state_id = state["state_id"]
    cam = cameras[spec["camera"]]
    basis = fm.camera_frame(cam["location"], cam["target"])
    fovs = fm.fov_xy(cam["lens_mm"])

    def candidate_state(travel: float) -> dict[str, Any]:
        moved = copy.deepcopy(state_data["states"])
        parts = moved[state_id]["parts"]
        for part_id in focus_ids:
            base = state["parts"][part_id]
            delta = _part_direction(spec, part_id, base, direction)
            moved_loc = fm.v_add(base["location"], fm.v_scale(delta, travel))
            parts[part_id]["location"] = list(moved_loc)
        if spec.get("focus_components"):
            # Components ride with the board: recompute their entries.
            board = state_data["presentation"]["components"]
            comps = moved[state_id]["components"]
            new_board = parts["PART_019"]["location"]
            for component in board:
                local = component["board_local_location"]
                comps[component["component_id"]]["location"] = [
                    new_board[i] + float(local[i]) for i in range(3)
                ]
        return {"states": moved, "presentation": state_data.get("presentation", {})}

    def violations(travel: float) -> list[str]:
        candidate = candidate_state(travel)
        hulls = _shot_hulls(
            candidate["states"][state_id], spec, part_objects,
            component_objects, cam, basis, fovs,
        )
        bad = []
        focus = hulls["focus"]
        focus_hull = focus["hull"] if focus else None
        if focus_hull is None or not fm.hull_inside_frame(focus_hull, margin * 0.5):
            bad.append("FOCUS_SUBJECT_OFFFRAME")
        for name, entry in hulls["context"].items():
            if entry is None or focus is None:
                continue
            # Occlusion = context closer to the camera than the subject's
            # nearest surface AND too close on screen. Context hulls behind
            # the subject are layering, which is the intended look.
            if entry["front_depth"] >= focus["front_depth"]:
                continue
            if not fm.hulls_separated(focus_hull, entry["hull"], margin):
                bad.append(name)
        return bad

    before = violations(0.0)
    if not before:
        return {"travel_mm": 0.0, "direction": list(direction), "violations_before": [], "violations_after": []}

    t = _search(violations)
    after = violations(t) if t is not None else before
    if t is None or after:
        raise ValueError(
            f"focus layout unsolvable for {state['state_id']}: residual violations {after}"
        )
    return {
        "travel_mm": t,
        "direction": list(direction),
        "violations_before": before,
        "violations_after": [],
    }


def _part_direction(
    spec: Mapping[str, Any], part_id: str, record: Mapping[str, Any], default: Sequence[float]
) -> Any:
    if not spec.get("per_part"):
        return fm.v_norm(default)
    offset = record.get("offset_from_assembled_mm") or [0.0, 0.0, 0.0]
    if fm.v_len(offset) <= fm.EPSILON:
        return fm.v_norm(default)
    return fm.v_norm(offset)


def _search(violations) -> float | None:
    bracket = None
    for step in range(1, GRID_STEPS + 1):
        t = T_MAX_MM * step / GRID_STEPS
        if not violations(t):
            bracket = (T_MAX_MM * (step - 1) / GRID_STEPS, t)
            break
    if bracket is None:
        return None
    low, high = bracket
    for _ in range(BISECT_STEPS):
        mid = (low + high) * 0.5
        if violations(mid):
            low = mid
        else:
            high = mid
    return high


def _apply_travel(
    state: Mapping[str, Any],
    spec: Mapping[str, Any],
    travel: float,
    state_data: Mapping[str, Any],
) -> None:
    direction = fm.v_norm(spec["direction"])
    for part_id in spec["parts"]:
        record = state["parts"][part_id]
        delta = _part_direction(spec, part_id, record, direction)
        record["location"] = list(fm.v_add(record["location"], fm.v_scale(delta, travel)))
        record["offset_from_assembled_mm"] = list(
            fm.v_add(record.get("offset_from_assembled_mm") or (0.0, 0.0, 0.0), fm.v_scale(delta, travel))
        )
    if spec.get("focus_components"):
        board = state["parts"]["PART_019"]["location"]
        for component in state_data["presentation"]["components"]:
            local = component["board_local_location"]
            state["components"][component["component_id"]]["location"] = [
                board[i] + float(local[i]) for i in range(3)
            ]


# ---------------------------------------------------------------------------
# hull projection
# ---------------------------------------------------------------------------

def _state_matrix(record: Mapping[str, Any]) -> Any:
    loc = record["location"]
    rot = record.get("rotation_euler") or (0.0, 0.0, 0.0)
    scale = record.get("scale") or (1.0, 1.0, 1.0)
    sx, sy, sz = (float(v) for v in scale)
    scale_matrix = Matrix(
        ((sx, 0.0, 0.0, 0.0), (0.0, sy, 0.0, 0.0), (0.0, 0.0, sz, 0.0), (0.0, 0.0, 0.0, 1.0))
    )
    return (
        Matrix.Translation(tuple(float(v) for v in loc))
        @ Euler(tuple(float(v) for v in rot)).to_matrix().to_4x4()
        @ scale_matrix
    )


def _object_hull(
    obj: Any,
    matrix: Any,
    cam: Mapping[str, Any],
    basis: tuple,
    fovs: tuple[float, float],
) -> dict[str, Any] | None:
    """Projected silhouette hull plus the object's nearest depth to camera.

    ``front_depth`` is the minimum camera-space distance of the sampled
    geometry — used to tell occlusion (context closer than the subject)
    from layering (context behind).
    """
    verts = obj.data.vertices
    stride = max(1, len(verts) // MAX_VERT_SAMPLES)
    points = [tuple(matrix @ verts[i].co) for i in range(0, len(verts), stride)]
    for corner in obj.bound_box:
        points.append(tuple(matrix @ Vector(tuple(corner))))
    ndc = []
    front_depth = float("inf")
    for point in points:
        local = fm.world_to_camera(point, cam["location"], basis)
        if local[2] < -fm.EPSILON:
            front_depth = min(front_depth, -local[2])
        projected = fm.project_ndc(point, cam["location"], basis, fovs)
        if projected is not None:
            ndc.append(projected)
    if not ndc:
        return None
    hull = fm.convex_hull_2d(ndc)
    if len(hull) >= 3 and not fm.hulls_overlap(hull, FRAME_HULL):
        return None  # entirely offscreen — cannot occlude anything
    return {"hull": hull, "front_depth": front_depth}


def _shot_hulls(
    state: Mapping[str, Any],
    spec: Mapping[str, Any],
    part_objects: Mapping[str, Any],
    component_objects: Mapping[str, Any],
    cam: Mapping[str, Any],
    basis: tuple,
    fovs: tuple[float, float],
) -> dict[str, Any]:
    focus_ids = set(spec["parts"])
    focus_points: list[tuple[float, float]] = []
    focus_front = float("inf")
    context: dict[str, Any] = {}

    def focus_point(world):
        nonlocal focus_front
        local = fm.world_to_camera(world, cam["location"], basis)
        if local[2] < -fm.EPSILON:
            focus_front = min(focus_front, -local[2])
        ndc = fm.project_ndc(world, cam["location"], basis, fovs)
        if ndc is not None:
            focus_points.append(ndc)

    for part_id in VISIBLE_PART_IDS:
        obj = part_objects.get(part_id)
        record = state["parts"].get(part_id)
        if obj is None or record is None:
            continue
        matrix = _state_matrix(record)
        if part_id in focus_ids:
            verts = obj.data.vertices
            stride = max(1, len(verts) // MAX_VERT_SAMPLES)
            for i in range(0, len(verts), stride):
                focus_point(tuple(matrix @ verts[i].co))
            for corner in obj.bound_box:
                focus_point(tuple(matrix @ Vector(tuple(corner))))
        else:
            entry = _object_hull(obj, matrix, cam, basis, fovs)
            if entry is not None:
                context[part_id] = entry

    for component_id, obj in component_objects.items():
        record = state.get("components", {}).get(component_id)
        if record is None:
            continue
        matrix = _state_matrix(record)
        if spec.get("focus_components"):
            for corner in obj.bound_box:
                focus_point(tuple(matrix @ Vector(tuple(corner))))
        else:
            entry = _object_hull(obj, matrix, cam, basis, fovs)
            if entry is not None:
                context[component_id] = entry

    focus = None
    if len(focus_points) >= 3:
        focus = {"hull": fm.convex_hull_2d(focus_points), "front_depth": focus_front}
    return {"focus": focus, "context": context}


def _script_arguments() -> list[str]:
    arguments = list(sys.argv[1:])
    return arguments[arguments.index("--") + 1 :] if "--" in arguments else arguments


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args(argv if argv is not None else _script_arguments())
    print(json.dumps(solve_focus_layouts(args.project_root), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
