# Spec: Task 10-V3 Frustum-Aware Layout & Occlusion Gate

Date: 2026-09-14
Status: proposed — builds on Task 10-V2 (still awaiting human visual review)
Research basis: docs/superpowers/research/2026-09-14-exploded-view-landscape.md
License note: user confirmed the project is internal/non-commercial; clean-room
reimplementation of the EAS algorithm set is authorized. No GPL code is copied.

## Problem

Task 10-V2 focus shots shipped two occlusion defects that technical validation
could not catch and the human reviewer found:

- SENSOR_FOCUS: sensor cluster silhouette merged into the housing outline;
  the housing occluded the cluster's right half.
- PCB_FOCUS: a dark context part overlapped the populated board's edge.

Root cause: part offsets and camera distances are hand-tuned numbers with no
relationship to the camera frustum. Whether a context part covers the focus
subject on screen is decided by the camera's view geometry, not by world-space
offsets — so it must be computed against the camera.

## Goal

Port the exploded-view algorithm suite (see research note §1) into the V2
pipeline as pure-Python math + a deterministic layout solver + a fail-closed
validation gate. Hand-tuned offsets become computed values frozen into
`state_transforms.json`; occlusion becomes a machine-checked contract.

## Non-goals

- No mesh/geometry changes; source baseline stays frozen (82 parts,
  444,296 faces, 221,902 vertices).
- No new story states, shots, annotations, or protocol wording.
- No addon installation at pipeline time — the math lives in our own module.
- Non-focus shots keep v1/V2 transforms unless the gate finds a violation.

## Design

### A. `frustum_math.py` (pure Python, no bpy)

Vector math on 3-tuples. Deterministic, testable under plain pytest.

- `camera_frame(location, target, up=(0,0,1))` → (right, up, back) orthonormal
  basis matching Blender's `-Z` forward / `+Y` up camera convention.
- `world_to_camera(point, frame, location)` → camera-space coords.
- `fov_xy(lens_mm, sensor_width=36, aspect=1920/1080)` → (fov_x, fov_y).
- `frustum_planes(fov_x, fov_y)` → 4 inward-facing plane normals (camera space).
- `offscreen_distance(frame, cam_pos, fovs, point, radius, direction, margin)`
  → minimal travel along `direction` for the sphere to leave the frustum;
  `None` when the direction can never exit (analytic, one linear solve per
  plane — the EAS approach).
- `screen_disc(frame, cam_pos, point, radius)` → (angular center, angular
  radius) of a sphere as seen by the camera.
- `clear_subject_distance(...)` → minimal extra travel along `direction` so
  the context sphere's disc no longer intersects the focus disc (strict disc
  separation; found by fixed-grid scan + bisection — deterministic).
- `framing_distance(radius, fov, screen_fraction)` → camera distance that puts
  the subject's bounding sphere at a chosen fraction of frame height
  (`fraction = subject_diameter / frame_height`).
- `assign_ranks(projections, tolerance)` → cluster parts into explosion layers
  (same-depth parts share a rank and lift as a sheet).
- `staggered_window(index, count, low, high, overlap)` → per-group frame
  window; `segment = span / (count - (count-1)*overlap)`.
- `choose_entry_side(natural, to_camera)` → best side for a context panel that
  does not sweep across the lens.

### B. Focus layout solver (`solve_focus_layouts.py`, Blender stage)

Runs after `build_story_scene_v2` (real meshes available) and before
`apply_story_animation_v2` (which consumes the rewritten JSON). For each
isolate-mode focus shot it evaluates **projected vertex-silhouette convex
hulls** in NDC — subject aggregate vs every context part — and applies the
smallest extra translation `t·d` (shared direction, or per-part continuation
of each part's explode vector) that keeps a configured screen gap.
`RUGGED_FOCUS` is layer-mode: the subject is the housing itself, separation
is not applicable — framing checks only.

Solver contract:
- Cameras are **frozen on the deterministic builder output**
  (`build_story_v2_state_transforms`), not on the mutating JSON — the hero
  camera derives from bounds over all states, so a subject-following camera
  would let later solves retroactively invalidate earlier ones.
- Rendering uses the identical frozen cameras
  (`setup_story_presentation_v2` calls `build_camera_records` on the same
  baseline), so the solver's evaluation IS the rendered frame.
- Deterministic: 64-step grid scan then bisection on `[0, T_MAX_MM=700]`;
  first feasible `t` wins. No feasible `t` → build error (fail-closed).
- Solved offsets are written back into `state_transforms.json`
  (`version: task10V2_story_states_v3_solved` + `v3_layout` metadata).
- PCB-mounted components are remounted to the solved board location.

### C. Camera auto-fit (`camera_plan.py`, shared planner)

`build_camera_records` is the single source of camera truth for solver and
scene build: focus cameras (SENSOR, PCB) auto-fit distance via
`framing_distance(subject_radius, fov_y, SCREEN_FRACTION)`; the hero camera
frames the all-state bounds with `HERO_DISTANCE_FACTOR`.

### D. Occlusion gate (`validate_product_story_v2.py`)

Fail-closed, evaluated on the **animated scene** at each focus shot's
mid-frame through the real camera object (`matrix_world`), not the JSON:

- subject hull inside frame (margin ≥ spec margin/2) → `FOCUS_SUBJECT_OFFFRAME`;
- subject hull height within `[0.25, 1.75]` NDC → `FOCUS_SUBJECT_SCALE`;
- isolate shots: subject hull separated from every context hull by
  `margin_ndc` → `FOCUS_OCCLUSION` listing offenders.

### D2. Bugs found by the gate during implementation

- `transform_apply(scale=True)` in `build_story_scene_v2` silently applied
  location too (Blender defaults all three to True) — 11 of 15 presentation
  components had world-baked verts and rendered double-offset. Fixed with
  `location=False`; validator now checks `matrix_world @ bbox` (rendered
  geometry) instead of `obj.location`.
- Cross-shot camera coupling: solving shot N changed the shared hero camera
  for shots < N. Fixed by freezing cameras on baseline (see §B).

### E. Group-staggered timing + idle float (`apply_story_animation_v2.py`)

- Within the PRIMARY_ARCHITECTURE explode transition, parts land in staggered
  windows grouped by module rank along the move direction (`assign_ranks` +
  `staggered_window`), keeping each group's shared arrival.
- Focus holds add a deterministic idle float: two extra location keyframes at
  ±IDLE_DRIFT_MM inside each focus hold window for the focus module's parts —
  subtle product-video feel, still pure transform keyframes.

## Verification

- `tests/test_v2_frustum_math.py`: pure-python math contracts.
- `tests/test_task10v2_story.py`: updated — offsets are now solver-computed
  (assert gate predicates + determinism, not literal numbers).
- Full pipeline re-run: scene, stills, contact sheet, MP4, validation JSON;
  ocular check of `03_sensor_focus.png` / `04_pcb_focus.png`.

## Acceptance

- Validation reports `occlusion_checks` all green, zero warnings.
- Focus subject disc separated from every context disc (or context behind).
- Focus subject occupies ~FOCUS_SCREEN_FRACTION of frame height.
- 900-frame MP4 re-rendered with computed layouts.
- Human review still required before `human_approval.json`.
